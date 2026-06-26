from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "resources" / "conf" / "settings.json"
EXAMPLE_PATH = PROJECT_ROOT / "config" / "settings.example.json"
TARGET_PATH = PROJECT_ROOT / "config" / "settings.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy resources/conf/settings.json to config/settings.json.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite config/settings.json if it already exists.",
    )
    args = parser.parse_args()

    if not SOURCE_PATH.is_file():
        print(f"Legacy settings file not found: {SOURCE_PATH}", file=sys.stderr)
        return 1
    if not EXAMPLE_PATH.is_file():
        print(f"Settings example file not found: {EXAMPLE_PATH}", file=sys.stderr)
        return 1
    if TARGET_PATH.exists() and not args.overwrite:
        print(
            f"Target already exists: {TARGET_PATH}\n"
            "Use --overwrite to replace it.",
            file=sys.stderr,
        )
        return 1

    example_settings = read_json_object(EXAMPLE_PATH)
    legacy_settings = read_json_object(SOURCE_PATH)
    merged = {**example_settings, **legacy_settings}

    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(
        json.dumps(merged, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Migrated settings to {TARGET_PATH}")
    return 0


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {path}")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
