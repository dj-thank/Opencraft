"""Configure ONLY the requested native MCP client, without provider API keys.

Run from the selected client's terminal: python scripts/setup_client.py codex
or python scripts/setup_client.py claude. --dry-run changes nothing.
"""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def registration_command(client: str, executable: str, python: Path, data: Path) -> list[str]:
    if client not in {"codex", "claude"}:
        raise ValueError("unsupported client")
    server = [str(python), "-m", "opencraft_server.mcp", "--data-dir", str(data), "--client", client]
    if client == "codex":
        return [executable, "mcp", "add", "opencraft", "--", *server]
    return [executable, "mcp", "add", "--transport", "stdio", "--scope", "local", "opencraft", "--", *server]


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("client", choices=("codex", "claude"))
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".opencraft-data")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required", file=sys.stderr)
        return 2
    executable = shutil.which(args.client)
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    data = args.data_dir.expanduser().absolute()
    command = registration_command(args.client, executable or args.client, python, data)
    if args.dry_run:
        print(subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command))
        return 0
    if executable is None:
        print(f"{args.client} was not found on PATH. Install/login to this client only, or use the manual MCP config in docs/NATIVE_CLIENTS.md.", file=sys.stderr)
        return 2
    try:
        if environment.is_symlink():
            raise ValueError("refusing a symlinked .venv")
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(environment)], cwd=ROOT, check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-e", f"{ROOT}[mcp]"], cwd=ROOT, check=True)
        subprocess.run([str(python), "-m", "opencraft_server.mcp", "--data-dir", str(data), "--init"], cwd=ROOT, check=True)
        # Native CLIs own their own settings. Do not parse, replace or delete them.
        subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Setup did not complete ({type(exc).__name__}). Existing client entries were not removed; inspect the command error above.", file=sys.stderr)
        return 1
    print(f"Configured {args.client} only. Reconnect MCP in that client and ask OpenCraft to read the world. No other client or provider API key is required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
