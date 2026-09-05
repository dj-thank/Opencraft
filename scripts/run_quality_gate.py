from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import compileall
import json
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


@dataclass
class Check:
    name: str
    status: str
    seconds: float
    detail: str
    blocking: bool = True


def run(name: str, command: list[str], *, optional_if_missing: str | None = None) -> Check:
    if optional_if_missing and shutil.which(optional_if_missing) is None:
        return Check(name, "blocked", 0.0, f"{optional_if_missing} is not installed", blocking=False)
    start = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    detail = (result.stdout + result.stderr).strip()[-12000:]
    return Check(name, "passed" if result.returncode == 0 else "failed", round(time.monotonic() - start, 3), detail)


def main() -> int:
    checks: list[Check] = []
    start = time.monotonic()
    ok = compileall.compile_dir(ROOT / "src", quiet=1) and compileall.compile_dir(ROOT / "scripts", quiet=1)
    checks.append(Check("python-compile", "passed" if ok else "failed", round(time.monotonic() - start, 3), "compiled src and scripts"))
    checks.append(run("python-unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]))
    validator = ROOT / "scripts" / "validate_schemas.py"
    if validator.exists():
        checks.append(run("json-schema-examples", [sys.executable, str(validator)]))
    checks.append(run("javascript-syntax", ["npm", "run", "check"], optional_if_missing="npm"))
    checks.append(run("javascript-tests", ["npm", "test"], optional_if_missing="npm"))

    DIST.mkdir(exist_ok=True)
    report = {
        "project": "OpenCraft",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checks": [asdict(check) for check in checks],
    }
    blocking_failures = [check for check in checks if check.blocking and check.status != "passed"]
    report["summary"] = {
        "passed": sum(check.status == "passed" for check in checks),
        "failed": sum(check.status == "failed" for check in checks),
        "blocked": sum(check.status == "blocked" for check in checks),
        "blockingFailures": len(blocking_failures),
        "developerPreviewGatePassed": not blocking_failures,
        "generalReleaseAllowed": False,
    }
    (DIST / "quality-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
