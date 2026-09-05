from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

_ALLOWED_KINDS = {"proxy.upsert", "proxy.delete", "selection.focus", "world.reset"}
_MAX_MESSAGE_BYTES = 1_000_000


class SidecarError(ValueError):
    pass


def validate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise SidecarError("message must be an object")
    if set(document) - {"schemaVersion", "sequence", "kind", "payload"}:
        raise SidecarError("unknown top-level field")
    if document.get("schemaVersion") != "1.0":
        raise SidecarError("unsupported schema version")
    sequence = document.get("sequence")
    if not isinstance(sequence, int) or sequence < 1:
        raise SidecarError("sequence must be a positive integer")
    if document.get("kind") not in _ALLOWED_KINDS:
        raise SidecarError("operation is not allowlisted")
    if not isinstance(document.get("payload"), dict):
        raise SidecarError("payload must be an object")
    serialized = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(serialized) > _MAX_MESSAGE_BYTES:
        raise SidecarError("message exceeds size limit")
    lowered = serialized.lower()
    for forbidden in (b'"python"', b'"script"', b'"command"', b'"shell"', b'"filepath"'):
        if forbidden in lowered:
            raise SidecarError("executable or filesystem field rejected")
    return document


def secure_spool(path: Path) -> Path:
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    (path / "inbox").mkdir(exist_ok=True)
    (path / "outbox").mkdir(exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
        (path / "inbox").chmod(0o700)
        (path / "outbox").chmod(0o700)
    return path


def atomic_enqueue(spool: Path, document: dict[str, Any]) -> Path:
    sequence = int(document["sequence"])
    inbox = spool / "inbox"
    final = inbox / f"{sequence:020d}.json"
    if final.exists():
        existing = json.loads(final.read_text(encoding="utf-8"))
        if existing != document:
            raise SidecarError("sequence collision with different content")
        return final
    data = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    fd, temporary_name = tempfile.mkstemp(prefix=".incoming-", suffix=".tmp", dir=inbox)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    return final


def run(spool: Path) -> int:
    spool = secure_spool(spool)
    for line in sys.stdin:
        try:
            if len(line.encode("utf-8")) > _MAX_MESSAGE_BYTES:
                raise SidecarError("input line exceeds size limit")
            document = validate_document(json.loads(line))
            path = atomic_enqueue(spool, document)
            response = {"ok": True, "sequence": document["sequence"], "queued": path.name}
        except (json.JSONDecodeError, OSError, SidecarError, ValueError) as exc:
            response = {"ok": False, "error": type(exc).__name__}
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenCraft Blender declarative sidecar")
    parser.add_argument("--spool", type=Path, required=True, help="private local spool directory")
    args = parser.parse_args()
    return run(args.spool)


if __name__ == "__main__":
    raise SystemExit(main())
