from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("opencraft_blender_sidecar", ROOT / "blender_extension" / "sidecar.py")
assert SPEC and SPEC.loader
sidecar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sidecar)


class SidecarTests(unittest.TestCase):
    def valid(self):
        return {
            "schemaVersion": "1.0",
            "sequence": 1,
            "kind": "proxy.upsert",
            "payload": {"entityId": "tree-1", "location": [1, 2, 3]},
        }

    def test_allowlisted_message_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = sidecar.secure_spool(Path(directory))
            document = sidecar.validate_document(self.valid())
            path = sidecar.atomic_enqueue(spool, document)
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), document)

    def test_same_sequence_same_content_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = sidecar.secure_spool(Path(directory))
            first = sidecar.atomic_enqueue(spool, self.valid())
            second = sidecar.atomic_enqueue(spool, self.valid())
            self.assertEqual(first, second)

    def test_same_sequence_different_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = sidecar.secure_spool(Path(directory))
            sidecar.atomic_enqueue(spool, self.valid())
            changed = self.valid()
            changed["payload"] = {"entityId": "other"}
            with self.assertRaises(sidecar.SidecarError):
                sidecar.atomic_enqueue(spool, changed)

    def test_executable_fields_are_rejected(self):
        for key in ("python", "script", "command", "shell", "filepath"):
            document = self.valid()
            document["payload"] = {key: "do something"}
            with self.assertRaises(sidecar.SidecarError):
                sidecar.validate_document(document)

    def test_unknown_operation_is_rejected(self):
        document = self.valid()
        document["kind"] = "python.exec"
        with self.assertRaises(sidecar.SidecarError):
            sidecar.validate_document(document)


if __name__ == "__main__":
    unittest.main()
