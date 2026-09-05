"""Evidence-bounded, problem-local learning utilities.

This package is a small experimental library for Hearthline playground work.
It is deliberately not an implementation of canonical Bridge Gloss.
"""

from .ledger import (
    EvidenceKind,
    EvidenceSourceKind,
    LearningLedger,
    LearningScope,
    LedgerClosedError,
    LedgerState,
    LedgerStateError,
    Provenance,
    ReceiptMode,
    Resolution,
    ResolutionOutcome,
)

__all__ = [
    "EvidenceKind",
    "EvidenceSourceKind",
    "LearningLedger",
    "LearningScope",
    "LedgerClosedError",
    "LedgerState",
    "LedgerStateError",
    "Provenance",
    "ReceiptMode",
    "Resolution",
    "ResolutionOutcome",
]
