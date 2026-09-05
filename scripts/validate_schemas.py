from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "protocols"
EXAMPLE_DIR = ROOT / "examples"


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot parse {path.relative_to(ROOT)}: {exc}") from exc


def schema_for(example: Path, document: dict) -> Path:
    explicit = document.get("$schemaFile")
    if explicit:
        candidate = SCHEMA_DIR / explicit
    else:
        stem = example.name.removesuffix(".example.json")
        candidate = SCHEMA_DIR / f"{stem}.schema.json"
    if not candidate.is_file():
        raise RuntimeError(f"no matching schema for {example.relative_to(ROOT)}: {candidate.name}")
    return candidate


def main() -> int:
    schema_files = sorted(SCHEMA_DIR.glob("*.schema.json"))
    example_files = sorted(EXAMPLE_DIR.glob("*.example.json"))
    if not schema_files:
        raise RuntimeError("no protocol schemas found")
    if not example_files:
        raise RuntimeError("no protocol examples found")

    for path in schema_files:
        Draft202012Validator.check_schema(load(path))

    validated = 0
    for example in example_files:
        document = load(example)
        if not isinstance(document, dict):
            raise RuntimeError(f"example must be an object: {example.relative_to(ROOT)}")
        schema_path = schema_for(example, document)
        instance = dict(document)
        instance.pop("$schemaFile", None)
        validator = Draft202012Validator(load(schema_path), format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.absolute_path))
        if errors:
            details = []
            for error in errors[:20]:
                location = "$" + "".join(f"[{part!r}]" for part in error.absolute_path)
                details.append(f"{location}: {error.message}")
            raise RuntimeError(f"{example.relative_to(ROOT)} failed {schema_path.name}:\n" + "\n".join(details))
        validated += 1

    print(f"Validated {len(schema_files)} schemas and {validated} examples")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
