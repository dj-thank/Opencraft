from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess
import sys

from .mcp import discover_response

ROOT = Path(__file__).resolve().parents[2]


def quality_main() -> int:
    """Run the repository quality gate from an installed editable checkout."""
    gate = ROOT / "scripts" / "run_quality_gate.py"
    if not gate.exists():
        print("OpenCraft quality gate is available only from a source checkout", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, str(gate)], cwd=ROOT)


def mcp_main() -> int:
    """Print the reference MCP discovery document without opening a server."""
    parser = ArgumentParser(description="Inspect the OpenCraft reference MCP contract")
    parser.add_argument("--discover", action="store_true", help="print server/discover result")
    args = parser.parse_args()
    if not args.discover:
        parser.print_help()
        return 0
    print(json.dumps(discover_response(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(mcp_main())
