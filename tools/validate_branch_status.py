from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}")
TOP_KEYS = {
    "schema", "snapshot", "authority", "preservation", "branches",
    "relationships", "canonical_arc3_candidate_ci", "astra_embargo",
    "scientific_run_entry",
}
BRANCH_KEYS = {
    "name", "commit", "tree", "parents", "role", "declared_status",
    "index_classification", "activity_class", "status_source_paths",
    "claim_ceiling", "branch_url",
}
ARC3_BRANCH = "arc-agi/titles/arc-agi-3-hearthline-launch-20260903"
ARC3_SHA = "97f580504e22bbd59b425274d6b5e0f9a18fe66e"
ARC3_TREE = "18897b5c31c5dc83385935b56accda3bb4ba58fa"
ARC3_STATUS = "OFFLINE_CANDIDATE_SOURCE_READY_HUMAN_GATES_CLOSED"
ARC3_BLOCKER = "RUNTIME_CLOSURE_UNFROZEN"
CI_IDS = {33917834890, 33917834892, 33917834935}


class ValidationError(ValueError):
    pass


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON number: {value}")


def load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ValidationError("manifest root must be an object")
    return value


def require_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{label} keys differ: {sorted(set(value) ^ expected)}")


def require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValidationError(f"{label} must be a lowercase 40-character SHA")
    return value


def require_safe_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError("status source path must be a nonempty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValidationError(f"unsafe status source path: {value}")
    return value


def require_repo_url(value: object) -> None:
    if not isinstance(value, str):
        raise ValidationError("branch URL must be a string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValidationError(f"unsafe branch URL: {value}")
    if parsed.username or parsed.password:
        raise ValidationError("credential-bearing branch URL")
    if not parsed.path.startswith("/Grativy6/hearthline-plays/"):
        raise ValidationError(f"wrong repository URL: {value}")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT}", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    if result.returncode:
        raise ValidationError(f"git {' '.join(args)} failed")
    return result.stdout.strip()


def validate(data: dict[str, object], check_local_refs: bool = False) -> None:
    require_keys(data, TOP_KEYS, "top-level")
    if data["schema"] != "hearthline-plays.branch-status.v1":
        raise ValidationError("wrong schema")
    if data["scientific_run_entry"] != "docs/SCIENTIFIC_RUN_ENTRY.md":
        raise ValidationError("scientific run entry drift")

    snapshot = data["snapshot"]
    if not isinstance(snapshot, dict):
        raise ValidationError("snapshot must be an object")
    require_sha(snapshot.get("default_branch_commit"), "default branch commit")
    require_sha(snapshot.get("default_branch_tree"), "default branch tree")
    try:
        datetime.fromisoformat(str(snapshot["observed_at_utc"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValidationError("invalid observed_at_utc") from exc

    authority = data["authority"]
    if not isinstance(authority, dict) or any(value is not False for value in authority.values()):
        raise ValidationError("every authority flag must remain false")
    preservation = data["preservation"]
    if not isinstance(preservation, dict):
        raise ValidationError("preservation must be an object")
    if preservation != {
        "title_trees_modified": False,
        "source_locks_modified": False,
        "status_sources_remain_on_owning_branches": True,
    }:
        raise ValidationError("preservation boundary drift")

    branches = data["branches"]
    if not isinstance(branches, list) or len(branches) != 12:
        raise ValidationError("exactly 12 branch entries are required")
    names: list[str] = []
    by_name: dict[str, dict[str, object]] = {}
    for raw in branches:
        if not isinstance(raw, dict):
            raise ValidationError("branch entry must be an object")
        require_keys(raw, BRANCH_KEYS, f"branch {raw.get('name')}")
        name = raw["name"]
        if not isinstance(name, str) or not name:
            raise ValidationError("invalid branch name")
        names.append(name)
        by_name[name] = raw
        require_sha(raw["commit"], f"{name} commit")
        require_sha(raw["tree"], f"{name} tree")
        parents = raw["parents"]
        if not isinstance(parents, list) or not parents:
            raise ValidationError(f"{name} parents must be a nonempty list")
        for parent in parents:
            require_sha(parent, f"{name} parent")
        paths = raw["status_source_paths"]
        if not isinstance(paths, list) or not paths:
            raise ValidationError(f"{name} needs a status source")
        for path in paths:
            require_safe_path(path)
        require_repo_url(raw["branch_url"])
    if names != sorted(names) or len(names) != len(set(names)):
        raise ValidationError("branch names must be sorted and unique")

    arc3 = by_name.get(ARC3_BRANCH)
    if arc3 is None or arc3["commit"] != ARC3_SHA or arc3["tree"] != ARC3_TREE:
        raise ValidationError("canonical ARC-AGI-3 candidate drift")
    if arc3["index_classification"] != "ACTIVE_CANDIDATE":
        raise ValidationError("exactly designated ARC-AGI-3 candidate is required")
    if ARC3_STATUS not in arc3["declared_status"] or ARC3_BLOCKER not in arc3["declared_status"]:
        raise ValidationError("ARC-AGI-3 status or blocker drift")
    if sum(branch["index_classification"] == "ACTIVE_CANDIDATE" for branch in branches) != 1:
        raise ValidationError("exactly one active candidate is required")

    relationships = data["relationships"]
    if not isinstance(relationships, list):
        raise ValidationError("relationships must be a list")
    kinds = {item.get("kind") for item in relationships if isinstance(item, dict)}
    required_kinds = {
        "TREE_EQUAL_TO_MERGED_TITLE",
        "DIVERGENT_SIBLINGS_ONE_UNIQUE_COMMIT_EACH",
        "DIRECT_SUCCESSOR",
    }
    if kinds != required_kinds:
        raise ValidationError("relationship set drift")
    if by_name["arc-agi/main"]["tree"] != by_name["arc-agi/titles/arc-agi-2-readiness-20260904"]["tree"]:
        raise ValidationError("ARC-AGI-2 tree-equality relationship failed")
    inherited = "HISTORICAL_INHERITED_NOT_CURRENT_NOT_EXECUTABLE"
    for name in ("millennium/playground-genesis-20260904", "design/creature-charter-20260905"):
        if inherited not in by_name[name]["claim_ceiling"]:
            raise ValidationError(f"missing inherited-text classification: {name}")

    ci = data["canonical_arc3_candidate_ci"]
    if not isinstance(ci, dict):
        raise ValidationError("ARC-AGI-3 CI record must be an object")
    for key, expected in {
        "branch": ARC3_BRANCH,
        "head_sha": ARC3_SHA,
        "tree": ARC3_TREE,
        "status": ARC3_STATUS,
        "blocker": ARC3_BLOCKER,
        "claim_ceiling": "offline repository verification only",
    }.items():
        if ci.get(key) != expected:
            raise ValidationError(f"ARC-AGI-3 CI {key} drift")
    runs = ci.get("runs")
    if not isinstance(runs, list) or {run.get("id") for run in runs if isinstance(run, dict)} != CI_IDS:
        raise ValidationError("ARC-AGI-3 CI run set drift")
    for run in runs:
        if run.get("head_sha") != ARC3_SHA or run.get("event") != "push" or run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ValidationError("ARC-AGI-3 CI receipt mismatch")
        require_repo_url(run.get("url"))

    embargo = data["astra_embargo"]
    if not isinstance(embargo, dict) or embargo.get("state") != "ACTIVE" or embargo.get("condition_status") != "UNRESOLVED_NOT_RECORDED" or embargo.get("this_index_lifts_embargo") is not False or embargo.get("this_index_admits_astra_contribution") is not False:
        raise ValidationError("Astra embargo boundary drift")

    if check_local_refs:
        for branch in branches:
            commit = str(branch["commit"])
            expected_tree = str(branch["tree"])
            actual_tree = git("show", "-s", "--format=%T", commit)
            if actual_tree != expected_tree:
                raise ValidationError(f"local tree mismatch: {branch['name']}")
            for path in branch["status_source_paths"]:
                git("cat-file", "-e", f"{commit}:{path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-local-refs", action="store_true")
    args = parser.parse_args()
    try:
        validate(load(args.manifest), args.check_local_refs)
    except ValidationError as exc:
        raise SystemExit(f"branch status validation failed: {exc}") from exc
    print("branch status validation: PASS")


if __name__ == "__main__":
    main()
