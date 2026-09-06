from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def quality_main() -> int:
    """Run the repository quality gate from an installed editable checkout."""
    gate = ROOT / "scripts" / "run_quality_gate.py"
    if not gate.exists():
        print("OpenCraft quality gate is available only from a source checkout", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, str(gate)], cwd=ROOT)


def mcp_main() -> int:
    """Launch the native-client MCP server (or its setup/diagnostic commands)."""
    from opencraft_server.mcp import main
    return main()


if __name__ == "__main__":
    raise SystemExit(mcp_main())
