"""Regression tests for quality-gate command execution."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "run_quality_gate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load_script("run_quality_gate_regression")


class QualityGateTests(unittest.TestCase):
    def test_required_program_is_resolved_with_which(self):
        resolved = str(ROOT / "Program Files" / "nodejs" / "npm.CMD")
        command = ["npm", "run", "check"]
        completed = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(gate.shutil, "which", return_value=resolved) as which, \
             patch.object(gate.subprocess, "run", return_value=completed) as run:
            result = gate.run("js", command, required_program="npm")

        which.assert_called_once_with("npm")
        run.assert_called_once_with(
            [resolved, "run", "check"], cwd=gate.ROOT,
            text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=180,
        )
        self.assertEqual(command, ["npm", "run", "check"])
        self.assertEqual(result.status, "passed")

    def test_missing_required_program_is_blocked(self):
        with patch.object(gate.shutil, "which", return_value=None), \
             patch.object(gate.subprocess, "run") as run:
            result = gate.run("js", ["npm", "test"], required_program="npm")

        self.assertEqual(result.status, "blocked")
        self.assertTrue(result.blocking)
        self.assertEqual(result.detail, "npm is not installed")
        run.assert_not_called()

    def test_nonzero_exit_is_failed_and_retains_output(self):
        completed = MagicMock(returncode=1, stdout="syntax check\n", stderr="invalid JavaScript\n")
        with patch.object(gate.shutil, "which", return_value="/usr/local/bin/npm"), \
             patch.object(gate.subprocess, "run", return_value=completed):
            result = gate.run("js", ["npm", "run", "check"], required_program="npm")

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.blocking)
        self.assertEqual(result.detail, "syntax check\ninvalid JavaScript")

    def test_timeout_remains_a_blocking_failure(self):
        with patch.object(gate.shutil, "which", return_value="/usr/local/bin/npm"), \
             patch.object(gate.subprocess, "run", side_effect=gate.subprocess.TimeoutExpired(["npm", "test"], 180)):
            result = gate.run("js", ["npm", "test"], required_program="npm")

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.blocking)
        self.assertIn("TimeoutExpired", result.detail)

    def test_oserror_detail_includes_exception(self):
        resolved = str(ROOT / "fake" / "npm.CMD")
        with patch.object(gate.shutil, "which", return_value=resolved), \
             patch.object(gate.subprocess, "run", side_effect=FileNotFoundError("boom")):
            result = gate.run("js", ["npm", "test"], required_program="npm")

        self.assertEqual(result.status, "failed")
        self.assertIn("FileNotFoundError", result.detail)
        self.assertIn("boom", result.detail)

    def test_utf8_subprocess_output_is_preserved(self):
        command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes.fromhex('e29c9420706173736564'))"]
        result = gate.run("utf8-output", command)

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.detail, "\u2714 passed")

    def test_invalid_output_bytes_do_not_hide_a_failed_check(self):
        command = [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'failed: \\xff'); sys.exit(1)"]
        result = gate.run("invalid-output", command)

        self.assertEqual(result.status, "failed")
        self.assertTrue(result.blocking)
        self.assertEqual(result.detail, "failed: \ufffd")

    def test_python_commands_are_not_rewritten(self):
        completed = MagicMock(returncode=0, stdout="", stderr="")
        command = ["original-python", "-m", "unittest"]
        with patch.object(gate.shutil, "which") as which, \
             patch.object(gate.subprocess, "run", return_value=completed) as run:
            result = gate.run("python", command)

        which.assert_not_called()
        self.assertEqual(run.call_args.args[0], command)
        self.assertEqual(result.status, "passed")


if __name__ == "__main__":
    unittest.main()
