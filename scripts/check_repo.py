from __future__ import annotations

from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "README.md",
    "ARCHITECTURE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "VERSION",
    "pyproject.toml",
    "package.json",
    "src/opencraft_core/world.py",
    "src/opencraft_server/service.py",
    "src/opencraft_server/mcp.py",
    "src/opencraft_server/workspace.py",
    "tests/test_mcp_native.py",
    "tests/test_server_safety.py",
    "scripts/setup_client.py",
    "docs/NATIVE_CLIENTS.md",
    "AGENTS.md",
    "CLAUDE.md",
    "src/opencraft_core/consent.py",
    "src/opencraft_core/webmcp.py",
    "src/opencraft_social/shell.py",
    "webmcp/adapter.js",
    "blender_extension/blender_manifest.toml",
    "protocols/agent-plan.schema.json",
    "product/RELEASE_GATE_JA.md",
)

SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "OpenAI key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "generic bearer": re.compile(rb"Authorization:\s*Bearer\s+[A-Za-z0-9._~-]{24,}", re.I),
}

IGNORED_PARTS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".opencraft-data", "venv"}


def files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not IGNORED_PARTS.intersection(path.parts):
            yield path


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else ""
    if not re.fullmatch(r"0\.16\.0-dev\.1", version):
        errors.append(f"unexpected VERSION: {version!r}")

    manifest_path = ROOT / "blender_extension" / "blender_manifest.toml"
    if manifest_path.exists():
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "1.0.0":
            errors.append("Blender manifest schema_version must be 1.0.0")
        if manifest.get("blender_version_min") != "4.2.0":
            errors.append("Blender minimum version must be 4.2.0")
        if "SPDX:GPL-3.0-or-later" not in manifest.get("license", []):
            errors.append("Blender extension must declare GPL-3.0-or-later")
        permissions = manifest.get("permissions", {})
        if not permissions.get("network") or not permissions.get("files"):
            errors.append("Blender extension must explain network and files permissions")

    forbidden_names = {".env", "id_rsa", "credentials.json", "secrets.json", "token-pepper.bin", "bootstrap-token.txt"}
    for path in files():
        relative = path.relative_to(ROOT)
        if path.name in forbidden_names:
            errors.append(f"forbidden sensitive file: {relative}")
            continue
        if path.stat().st_size > 10 * 1024 * 1024:
            errors.append(f"unreviewed large file: {relative}")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read {relative}: {exc}")
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                errors.append(f"secret-like material ({label}): {relative}")

    import_workflow = ROOT / ".github" / "workflows" / "import-opencraft-source.yml"
    if import_workflow.exists():
        errors.append("obsolete ephemeral source import workflow is still present")

    readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="replace") if (ROOT / "README.md").exists() else ""
    for required_phrase in ("Developer Preview", "一般配布版ではありません", "Canonical World"):
        if required_phrase not in readme:
            errors.append(f"README must communicate status/invariant: {required_phrase}")

    if errors:
        print("Repository invariant check failed:", file=sys.stderr)
        # Never log values or paths derived from secret-bearing input.
        print(f"{len(errors)} invariant violation(s); inspect required files and local source privately.", file=sys.stderr)
        return 1
    print("Repository invariants: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
