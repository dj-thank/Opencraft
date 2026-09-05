from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


@dataclass
class Step:
    name: str
    command: list[str]
    status: str
    returncode: int
    seconds: float
    output: str


def execute(name: str, command: list[str]) -> Step:
    started = time.monotonic()
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = (process.stdout + process.stderr).strip()[-20000:]
    return Step(
        name=name,
        command=command,
        status="passed" if process.returncode == 0 else "failed",
        returncode=process.returncode,
        seconds=round(time.monotonic() - started, 3),
        output=output,
    )


def main() -> int:
    steps = [
        execute("repository-invariants", [sys.executable, "scripts/check_repo.py"]),
        execute("language-and-unit-gate", [sys.executable, "scripts/run_quality_gate.py"]),
    ]
    DIST.mkdir(exist_ok=True)
    passed = all(step.returncode == 0 for step in steps)
    report = {
        "schemaVersion": "1.0",
        "project": "OpenCraft",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "steps": [asdict(step) for step in steps],
        "summary": {
            "developerPreviewGatePassed": passed,
            "closedAlphaAllowed": False,
            "generalReleaseAllowed": False,
        },
    }
    (DIST / "full-quality-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
