from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".opencraft-data", "venv"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".dmg", ".exe", ".msi", ".app", ".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm"}


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


SOURCE_DIRECTORIES = {".github", "src", "tests", "tests-js", "scripts", "docs", "product",
                      "examples", "protocols", "prototype", "webmcp", "mcp", "blender_extension"}
ROOT_FILES = {"README.md", "ARCHITECTURE.md", "CHANGELOG.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md",
              "DEVELOPMENT.md", "GOVERNANCE.md", "LICENSE", "NOTICE", "ROADMAP.md", "SECURITY.md",
              "SUPPORT.md", "VERSION", "pyproject.toml", "package.json", "package-lock.json",
              ".gitignore", "AGENTS.md", "CLAUDE.md"}
PRIVATE_NAMES = {"token-pepper.bin", "bootstrap-token.txt", "credentials.json", "secrets.json",
                 "id_rsa", "id_ed25519", ".DS_Store", "Thumbs.db"}


def source_files() -> list[Path]:
    """Allowlisted source roots only; never bundle local worlds or authentication.

    Works in both a Git checkout and an extracted source archive. Adding a new
    top-level source directory is an explicit, reviewable packaging decision.
    """
    result: list[Path] = []
    for parent, directories, names in os.walk(ROOT, followlinks=False):
        directory = Path(parent)
        for name in list(directories):
            child = directory / name
            allowed = name not in EXCLUDED_PARTS and not name.endswith(".egg-info")
            if directory == ROOT:
                allowed = allowed and name in SOURCE_DIRECTORIES
            if allowed and child.is_symlink():
                raise RuntimeError("refusing to package a symlinked source directory")
            if not allowed:
                directories.remove(name)
        for name in names:
            path = directory / name
            if directory == ROOT and name not in ROOT_FILES:
                continue
            if name in PRIVATE_NAMES or name.startswith((".env", ".pepper-", "owner-session")):
                continue
            if path.suffix.lower() in EXCLUDED_SUFFIXES or name.endswith(("-wal", "-shm", "-journal")):
                continue
            if path.is_symlink():
                raise RuntimeError("refusing to package a symlinked source file")
            if path.is_file():
                result.append(path)
    return sorted(result, key=lambda item: item.relative_to(ROOT).as_posix())


def write_zip(archive: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"opencraft-{VERSION}/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = path.name.endswith(".sh") or relative.startswith("scripts/") and not path.suffix
            info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
            output.writestr(info, path.read_bytes())


def main() -> int:
    subprocess.run([sys.executable, "scripts/full_quality_gate.py"], cwd=ROOT, check=True)
    DIST.mkdir(exist_ok=True)
    files = source_files()
    if not files:
        raise RuntimeError("refusing to build an empty source archive")

    manifest = {
        "schemaVersion": "1.0",
        "project": "OpenCraft",
        "version": VERSION,
        "kind": "developer-preview-source",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generalReleaseAllowed": False,
        "files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "size": path.stat().st_size,
                "sha256": digest(path),
            }
            for path in files
        ],
    }
    manifest_path = DIST / "artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"OpenCraft-{VERSION}",
        "documentNamespace": f"https://github.com/dj-thank/Opencraft/sbom/{VERSION}",
        "creationInfo": {
            "created": manifest["generatedAt"],
            "creators": ["Tool: OpenCraft deterministic source builder"],
        },
        "packages": [
            {
                "name": "opencraft-foundation",
                "SPDXID": "SPDXRef-Package-OpenCraft",
                "versionInfo": VERSION,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "licenseConcluded": "Apache-2.0 AND GPL-3.0-or-later",
                "licenseDeclared": "Apache-2.0 AND GPL-3.0-or-later",
                "copyrightText": "Copyright 2026 OpenCraft contributors",
            }
        ],
        "files": [
            {
                "fileName": entry["path"],
                "SPDXID": f"SPDXRef-File-{index}",
                "checksums": [{"algorithm": "SHA256", "checksumValue": entry["sha256"]}],
                "licenseConcluded": "GPL-3.0-or-later" if entry["path"].startswith("blender_extension/") else "Apache-2.0",
                "copyrightText": "NOASSERTION",
            }
            for index, entry in enumerate(manifest["files"], start=1)
        ],
    }
    (DIST / "sbom.spdx.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readiness = {
        "schemaVersion": "1.0",
        "version": VERSION,
        "developerPreviewSourceBuilt": True,
        "closedAlphaAllowed": False,
        "generalReleaseAllowed": False,
        "blockingEvidence": [
            "cloudflare-staging-e2e",
            "two-browser-world-e2e",
            "two-blender-instance-e2e",
            "live-webrtc-sfu-turn-e2e",
            "real-llm-adversarial-evaluation",
            "owner-authentication-and-recovery",
            "untrusted-asset-sandbox",
            "signed-windows-installer",
            "notarized-macos-distribution",
            "nontechnical-usability-study",
            "independent-security-and-privacy-review"
        ]
    }
    (DIST / "release-readiness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive = DIST / f"OpenCraft-{VERSION}-source.zip"
    write_zip(archive, files)
    checksum = digest(archive)
    (DIST / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
