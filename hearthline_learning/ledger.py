"""A deterministic, evidence-bounded learning ledger.

The ledger records supplied observations and resolves requests only from those
observations.  It has no data-loading, network, model, strategy, translation-map,
or code-execution capability.  A ledger is bound to one session/problem scope,
must be closed before it is reset, and clears all learned state on reset.

This module is suitable as a future adapter boundary for task-local Gloss work,
but it is not canonical Bridge Gloss and makes no claim about that subsystem.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

LEDGER_SCHEMA_VERSION = "hearthline-learning-ledger.v1"
RESET_SCHEMA_VERSION = "hearthline-learning-reset.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ResolutionOutcome(StrEnum):
    """Every possible result of a learning-ledger request."""

    SUPPORTED_RENDER = "SUPPORTED_RENDER"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    UNRESOLVED = "UNRESOLVED"
    CONTRACT_ERROR = "CONTRACT_ERROR"


class EvidenceKind(StrEnum):
    """The shape of one supplied observation."""

    SUPPORTED = "SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"


class EvidenceSourceKind(StrEnum):
    """Declared origin class; a label supplied by the caller, not an attestation."""

    SUPPLIED_DEMONSTRATION = "SUPPLIED_DEMONSTRATION"
    ORIGINAL_MICRO_FIXTURE = "ORIGINAL_MICRO_FIXTURE"
    PUBLIC_SOURCE = "PUBLIC_SOURCE"


class ReceiptMode(StrEnum):
    """Whether exported receipts contain forms or only their SHA-256 digests."""

    DIGESTS = "DIGESTS"
    RAW = "RAW"


class LedgerState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class LedgerStateError(RuntimeError):
    """Raised when an operation violates the explicit ledger lifecycle."""


class LedgerClosedError(LedgerStateError):
    """Raised when an active operation is attempted on a closed ledger."""


def _require_opaque_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field} must be 1-64 characters using only letters, numbers, dot, underscore, or hyphen"
        )
    return value


def _require_form(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _with_digest(document: dict[str, Any], field: str) -> dict[str, Any]:
    result = copy.deepcopy(document)
    result[field] = hashlib.sha256(_canonical_json(document).encode("utf-8")).hexdigest()
    return result


@dataclass(frozen=True, slots=True)
class LearningScope:
    """Opaque identifiers binding a ledger to exactly one local context."""

    session_id: str
    problem_id: str

    def __post_init__(self) -> None:
        _require_opaque_id(self.session_id, "session_id")
        _require_opaque_id(self.problem_id, "problem_id")

    def to_dict(self) -> dict[str, str]:
        return {"session_id": self.session_id, "problem_id": self.problem_id}


@dataclass(frozen=True, slots=True)
class Provenance:
    """A caller-declared opaque locator for supplied evidence."""

    source_id: str
    source_kind: EvidenceSourceKind = EvidenceSourceKind.SUPPLIED_DEMONSTRATION
    ordinal: int | None = None
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_opaque_id(self.source_id, "source_id")
        if not isinstance(self.source_kind, EvidenceSourceKind):
            raise TypeError("source_kind must be an EvidenceSourceKind")
        if self.ordinal is not None and (
            isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0
        ):
            raise ValueError("ordinal must be a non-negative integer or None")
        if self.source_sha256 is not None and not _SHA256_RE.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest or None")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "ordinal": self.ordinal,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True, slots=True)
class Resolution:
    """A request result. Only ``SUPPORTED_RENDER`` carries a rendering."""

    request_id: str
    outcome: ResolutionOutcome
    requested_form: str | None
    direction: str | None
    rendering: str | None
    candidates: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    refusal_reason: str | None

    @property
    def accepted(self) -> bool:
        return self.outcome is ResolutionOutcome.SUPPORTED_RENDER

    @property
    def refused(self) -> bool:
        return not self.accepted


@dataclass(frozen=True, slots=True)
class _Observation:
    observation_id: str
    kind: EvidenceKind
    requested_form: str
    direction: str
    candidates: tuple[str, ...]
    provenance: Provenance


class LearningLedger:
    """Problem-local observations with deterministic evidence resolution.

    ``EXACT`` is intentionally the only normalization policy in version 1.
    Forms are compared byte-for-byte after UTF-8 encoding; the ledger performs
    no case folding, token inference, heuristic matching, or vocabulary repair.
    """

    def __init__(
        self,
        scope: LearningScope,
        *,
        receipt_mode: ReceiptMode = ReceiptMode.DIGESTS,
    ) -> None:
        if not isinstance(scope, LearningScope):
            raise TypeError("scope must be a LearningScope")
        if not isinstance(receipt_mode, ReceiptMode):
            raise TypeError("receipt_mode must be a ReceiptMode")
        self._scope = scope
        self._receipt_mode = receipt_mode
        self._state = LedgerState.OPEN
        self._generation = 0
        self._observations: list[_Observation] = []
        self._requests: list[Resolution] = []
        self._closed_receipt: dict[str, Any] | None = None
        self._reset_from_receipt_sha256: str | None = None

    @property
    def scope(self) -> LearningScope:
        return self._scope

    @property
    def state(self) -> LedgerState:
        return self._state

    @property
    def generation(self) -> int:
        return self._generation

    def _require_open(self) -> None:
        if self._state is LedgerState.CLOSED:
            raise LedgerClosedError(
                "ledger is closed; call reset() with a new scope before recording or resolving"
            )

    def observe_supported(
        self,
        requested_form: str,
        rendering: str,
        provenance: Provenance,
        *,
        direction: str = "source_to_render",
    ) -> str:
        """Record one directly supported rendering and return its stable local ID."""

        return self._observe(
            EvidenceKind.SUPPORTED,
            requested_form,
            (rendering,),
            provenance,
            direction,
        )

    def observe_ambiguous(
        self,
        requested_form: str,
        candidates: tuple[str, ...] | list[str],
        provenance: Provenance,
        *,
        direction: str = "source_to_render",
    ) -> str:
        """Record evidence that leaves at least two distinct renderings possible."""

        if not isinstance(candidates, (tuple, list)):
            raise TypeError("candidates must be a tuple or list of strings")
        return self._observe(
            EvidenceKind.AMBIGUOUS,
            requested_form,
            tuple(candidates),
            provenance,
            direction,
        )

    def _observe(
        self,
        kind: EvidenceKind,
        requested_form: object,
        candidates: tuple[object, ...],
        provenance: object,
        direction: object,
    ) -> str:
        self._require_open()
        source = _require_form(requested_form, "requested_form")
        resolved_direction = _require_opaque_id(direction, "direction")
        if not isinstance(provenance, Provenance):
            raise TypeError("provenance must be a Provenance")
        rendered = tuple(sorted({_require_form(value, "candidate") for value in candidates}))
        expected_count = 1 if kind is EvidenceKind.SUPPORTED else 2
        if len(rendered) < expected_count:
            qualifier = "exactly one" if kind is EvidenceKind.SUPPORTED else "at least two distinct"
            raise ValueError(f"{kind.value} evidence requires {qualifier} rendering(s)")
        if kind is EvidenceKind.SUPPORTED and len(rendered) != 1:
            raise ValueError("SUPPORTED evidence requires exactly one rendering")

        observation_id = f"observation-{len(self._observations) + 1:04d}"
        self._observations.append(
            _Observation(
                observation_id=observation_id,
                kind=kind,
                requested_form=source,
                direction=resolved_direction,
                candidates=rendered,
                provenance=provenance,
            )
        )
        return observation_id

    def resolve(
        self,
        requested_form: object,
        *,
        direction: object = "source_to_render",
        scope: object | None = None,
    ) -> Resolution:
        """Resolve one request and append its accepted/refused audit record.

        Invalid request fields and explicit cross-scope attempts return
        ``CONTRACT_ERROR``. A closed ledger instead raises ``LedgerClosedError``
        because a sealed receipt cannot accept another audit mutation.
        """

        self._require_open()
        request_id = f"request-{len(self._requests) + 1:04d}"

        if scope is not None and not isinstance(scope, LearningScope):
            return self._record_contract_error(
                request_id,
                requested_form,
                direction,
                "SCOPE_MUST_BE_LEARNING_SCOPE",
            )
        if isinstance(scope, LearningScope) and scope != self._scope:
            return self._record_contract_error(
                request_id,
                requested_form,
                direction,
                "CROSS_SCOPE_REQUEST_REFUSED",
            )
        if not isinstance(requested_form, str) or not requested_form:
            return self._record_contract_error(
                request_id,
                requested_form,
                direction,
                "REQUESTED_FORM_MUST_BE_NONEMPTY_STRING",
            )
        if not isinstance(direction, str) or _OPAQUE_ID_RE.fullmatch(direction) is None:
            return self._record_contract_error(
                request_id,
                requested_form,
                direction,
                "DIRECTION_MUST_BE_OPAQUE_ID",
            )

        matches = [
            observation
            for observation in self._observations
            if observation.requested_form == requested_form and observation.direction == direction
        ]
        evidence_ids = tuple(observation.observation_id for observation in matches)
        if not matches:
            resolution = Resolution(
                request_id=request_id,
                outcome=ResolutionOutcome.UNRESOLVED,
                requested_form=requested_form,
                direction=direction,
                rendering=None,
                candidates=(),
                evidence_ids=(),
                refusal_reason="NO_SUPPORTING_OBSERVATION",
            )
        else:
            candidate_sets = [set(observation.candidates) for observation in matches]
            common = set.intersection(*candidate_sets)
            candidate_union = set.union(*candidate_sets)
            if not common:
                resolution = Resolution(
                    request_id=request_id,
                    outcome=ResolutionOutcome.CONFLICTING,
                    requested_form=requested_form,
                    direction=direction,
                    rendering=None,
                    candidates=tuple(sorted(candidate_union)),
                    evidence_ids=evidence_ids,
                    refusal_reason="EVIDENCE_INTERSECTION_EMPTY",
                )
            elif len(common) > 1:
                resolution = Resolution(
                    request_id=request_id,
                    outcome=ResolutionOutcome.AMBIGUOUS,
                    requested_form=requested_form,
                    direction=direction,
                    rendering=None,
                    candidates=tuple(sorted(common)),
                    evidence_ids=evidence_ids,
                    refusal_reason="MULTIPLE_EVIDENCE_SUPPORTED_RENDERINGS",
                )
            else:
                rendering = next(iter(common))
                resolution = Resolution(
                    request_id=request_id,
                    outcome=ResolutionOutcome.SUPPORTED_RENDER,
                    requested_form=requested_form,
                    direction=direction,
                    rendering=rendering,
                    candidates=(rendering,),
                    evidence_ids=evidence_ids,
                    refusal_reason=None,
                )
        self._requests.append(resolution)
        return resolution

    def _record_contract_error(
        self,
        request_id: str,
        requested_form: object,
        direction: object,
        reason: str,
    ) -> Resolution:
        resolution = Resolution(
            request_id=request_id,
            outcome=ResolutionOutcome.CONTRACT_ERROR,
            requested_form=requested_form if isinstance(requested_form, str) else None,
            direction=direction if isinstance(direction, str) else None,
            rendering=None,
            candidates=(),
            evidence_ids=(),
            refusal_reason=reason,
        )
        self._requests.append(resolution)
        return resolution

    def close(self) -> dict[str, Any]:
        """Seal the current scope and return an idempotent receipt copy."""

        if self._state is LedgerState.OPEN:
            self._state = LedgerState.CLOSED
            self._closed_receipt = self._build_receipt()
        if self._closed_receipt is None:  # pragma: no cover - defensive invariant
            raise AssertionError("closed ledger is missing its receipt")
        return copy.deepcopy(self._closed_receipt)

    def reset(self, scope: LearningScope) -> dict[str, Any]:
        """Clear a sealed scope and open a different session/problem scope.

        Reset is forbidden while open so observations cannot be silently lost,
        and the new scope must differ so a problem cannot accidentally retain an
        identity while its evidence is replaced.
        """

        if self._state is not LedgerState.CLOSED:
            raise LedgerStateError("close() must seal the current scope before reset()")
        if not isinstance(scope, LearningScope):
            raise TypeError("scope must be a LearningScope")
        if scope == self._scope:
            raise LedgerStateError("reset() requires a different session/problem scope")
        if self._closed_receipt is None:  # pragma: no cover - defensive invariant
            raise AssertionError("closed ledger is missing its receipt")

        previous_scope = self._scope
        previous_digest = self._closed_receipt["receipt_sha256"]
        next_generation = self._generation + 1
        reset_document: dict[str, Any] = {
            "schema_version": RESET_SCHEMA_VERSION,
            "from_scope": self._scope_receipt_dict(previous_scope),
            "to_scope": self._scope_receipt_dict(scope),
            "from_receipt_sha256": previous_digest,
            "generation": next_generation,
            "prior_observations_cleared": True,
            "prior_requests_cleared": True,
        }
        reset_receipt = _with_digest(reset_document, "reset_receipt_sha256")

        self._scope = scope
        self._generation = next_generation
        self._observations.clear()
        self._requests.clear()
        self._state = LedgerState.OPEN
        self._closed_receipt = None
        self._reset_from_receipt_sha256 = previous_digest
        return reset_receipt

    def export_receipt(self) -> dict[str, Any]:
        """Return a detached, deterministic, JSON-safe receipt snapshot."""

        if self._state is LedgerState.CLOSED:
            return self.close()
        return self._build_receipt()

    def canonical_receipt_json(self) -> str:
        """Return the receipt in its unique hashing/transport representation."""

        return _canonical_json(self.export_receipt())

    def _build_receipt(self) -> dict[str, Any]:
        outcome_counts = {outcome.value: 0 for outcome in ResolutionOutcome}
        for request in self._requests:
            outcome_counts[request.outcome.value] += 1

        signatures = Counter(
            (observation.direction, observation.requested_form, observation.candidates)
            for observation in self._observations
        )
        document: dict[str, Any] = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "identity": "experimental_evidence_bounded_learning_ledger_not_canonical_gloss",
            "scope": self._scope_receipt_dict(self._scope),
            "configuration": {
                "normalization": "EXACT",
                "receipt_mode": self._receipt_mode.value,
                "resolution_rule": "candidate_set_intersection_v1",
            },
            "lifecycle": {
                "state": self._state.value,
                "generation": self._generation,
                "reset_from_receipt_sha256": self._reset_from_receipt_sha256,
                "reset_required_before_new_scope": True,
            },
            "observations": [self._observation_dict(value) for value in self._observations],
            "requests": [self._resolution_dict(value) for value in self._requests],
            "counts": {
                "observations": len(self._observations),
                "supported_observations": sum(
                    value.kind is EvidenceKind.SUPPORTED for value in self._observations
                ),
                "ambiguous_observations": sum(
                    value.kind is EvidenceKind.AMBIGUOUS for value in self._observations
                ),
                "observations_with_source_sha256": sum(
                    value.provenance.source_sha256 is not None
                    for value in self._observations
                ),
                "repeated_claim_groups": sum(count > 1 for count in signatures.values()),
                "repeated_claim_observations": sum(
                    count - 1 for count in signatures.values() if count > 1
                ),
                "requests": len(self._requests),
                "accepted": sum(value.accepted for value in self._requests),
                "refused": sum(value.refused for value in self._requests),
                "outcomes": outcome_counts,
            },
            "implementation_boundary": {
                "scope": "LEDGER_MODULE_OPERATIONS_ONLY_NOT_CALLER_ACTIVITY",
                "caller_evidence_origin_verified": False,
                "public_release_review_required": True,
                "raw_content_included": self._receipt_mode is ReceiptMode.RAW,
                "module_performs": {
                    "cross_scope_learning_state": False,
                    "cross_scope_receipt_lineage": True,
                    "external_access": False,
                    "generated_code_execution": False,
                    "mapping_invention": False,
                    "model_calls": False,
                    "strategy_selection": False,
                },
            },
        }
        return _with_digest(document, "receipt_sha256")

    def _observation_dict(self, observation: _Observation) -> dict[str, Any]:
        result: dict[str, Any] = {
            "observation_id": observation.observation_id,
            "kind": observation.kind.value,
            "provenance": self._provenance_receipt_dict(observation.provenance),
        }
        if self._receipt_mode is ReceiptMode.RAW:
            result["direction"] = observation.direction
            result["requested_form"] = observation.requested_form
            result["candidates"] = list(observation.candidates)
        else:
            result["direction_sha256"] = _sha256_text(observation.direction)
            result["requested_form_sha256"] = _sha256_text(observation.requested_form)
            result["candidate_sha256"] = [
                _sha256_text(candidate) for candidate in observation.candidates
            ]
        return result

    def _scope_receipt_dict(self, scope: LearningScope) -> dict[str, str]:
        if self._receipt_mode is ReceiptMode.RAW:
            return scope.to_dict()
        return {
            "session_id_sha256": _sha256_text(scope.session_id),
            "problem_id_sha256": _sha256_text(scope.problem_id),
        }

    def _provenance_receipt_dict(self, provenance: Provenance) -> dict[str, object]:
        result: dict[str, object] = {
            "source_kind": provenance.source_kind.value,
            "ordinal": provenance.ordinal,
            "source_sha256": provenance.source_sha256,
            "caller_declared_not_verified": True,
        }
        if self._receipt_mode is ReceiptMode.RAW:
            result["source_id"] = provenance.source_id
        else:
            result["source_id_sha256"] = _sha256_text(provenance.source_id)
        return result

    def _resolution_dict(self, resolution: Resolution) -> dict[str, Any]:
        result: dict[str, Any] = {
            "request_id": resolution.request_id,
            "outcome": resolution.outcome.value,
            "accepted": resolution.accepted,
            "refused": resolution.refused,
            "evidence_ids": list(resolution.evidence_ids),
            "refusal_reason": resolution.refusal_reason,
        }
        if self._receipt_mode is ReceiptMode.RAW:
            result["direction"] = resolution.direction
            result["requested_form"] = resolution.requested_form
            result["rendering"] = resolution.rendering
            result["candidates"] = list(resolution.candidates)
        else:
            result["direction_sha256"] = (
                _sha256_text(resolution.direction) if resolution.direction is not None else None
            )
            result["requested_form_sha256"] = (
                _sha256_text(resolution.requested_form)
                if resolution.requested_form is not None
                else None
            )
            result["rendering_sha256"] = (
                _sha256_text(resolution.rendering) if resolution.rendering is not None else None
            )
            result["candidate_sha256"] = [
                _sha256_text(candidate) for candidate in resolution.candidates
            ]
        return result
