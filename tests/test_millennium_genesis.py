from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "millennium" / "tools" / "verify_genesis.py"
GENESIS = ROOT / "millennium" / "receipts" / "20260904T073424Z-genesis.json"
CIRCUIT_GARDEN = ROOT / "millennium" / "games" / "p-vs-np" / "circuit_garden.py"
CERTIFICATE = ROOT / "millennium" / "games" / "p-vs-np" / "certificate-n2-nand.json"

SPEC = importlib.util.spec_from_file_location("verify_millennium_genesis", VERIFY)
assert SPEC is not None and SPEC.loader is not None
VERIFY_MODULE = importlib.util.module_from_spec(SPEC)
try:
    SPEC.loader.exec_module(VERIFY_MODULE)
except SystemExit as exc:
    raise RuntimeError("verifier exited while the frozen test imported it") from exc


class MillenniumGenesisTests(unittest.TestCase):
    def test_offline_verifier(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-I", str(VERIFY), "--allow-uncommitted"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_circuit_garden_certificate(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-I", str(CIRCUIT_GARDEN), "--verify", str(CERTIFICATE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_genesis_event_id_is_content_addressed(self) -> None:
        receipt = VERIFY_MODULE.load_json(GENESIS)
        self.assertEqual(receipt["event_id"], VERIFY_MODULE.compute_event_id(receipt))

    def test_duplicate_json_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"same": 1, "same": 2}', encoding="utf-8")
            with self.assertRaises(VERIFY_MODULE.VerificationError):
                VERIFY_MODULE.load_json(path)

    def test_private_public_path_is_rejected(self) -> None:
        with self.assertRaises(VERIFY_MODULE.VerificationError):
            VERIFY_MODULE.safe_public_path("millennium/private/example.json")

    def test_private_material_is_not_declared_public(self) -> None:
        receipt = json.loads(GENESIS.read_text(encoding="utf-8"))
        commitment = receipt["private_checkpoint_commitment"]
        self.assertFalse(commitment["nonce_disclosed_in_git"])
        self.assertFalse(commitment["artifact_digest_disclosed_in_git"])
        self.assertFalse(commitment["artifact_bytes_committed_to_git"])
        self.assertEqual(commitment["historical_astra_provenance"], "NOT_ATTESTED")


if __name__ == "__main__":
    unittest.main()
