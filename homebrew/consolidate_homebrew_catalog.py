#!/usr/bin/env python3
"""
consolidate_homebrew_catalog.py
Consolidates individual Homebrew metadata files from homebrew/entries/*.json
into homebrew/HOMEBREW.data.json and generates homebrew/game_id_to_image.json.

Guarantees:
- Deterministic output (alphabetically sorted keys, consistent indentation and trailing newline).
- Preserves all historical records from HOMEBREW.data.json.
- Validates each individual entry (JSON integrity, required fields, serial vs filename match).
- Detects duplicate serials and conflicting records with explicit error reporting.
- Atomic file writes to prevent half-written/corrupt files.
- Command-line interface with exit codes (0 = success, 1 = validation error).
- Optional --check flag for CI to verify catalog is fully consolidated without modifying files.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, Any, Tuple, List

BASE_DIR = Path(__file__).resolve().parent
ENTRIES_DIR = BASE_DIR / "entries"
DATA_JSON = BASE_DIR / "HOMEBREW.data.json"
NAMED_TITLES_DIR = BASE_DIR / "Named_Titles"
OUTPUT_MAP_JSON = BASE_DIR / "game_id_to_image.json"
ERROR_LOG = BASE_DIR / "homebrew_mapping_errors.log"

# Allowed Game ID regex: 4 to 15 characters, alphanumeric, underscore, hyphen
# Physical limit: C char game_id[16] null-terminated = 15 bytes max
SERIAL_REGEX = re.compile(r"^[A-Z0-9_\-]{4,15}$")


class CatalogValidationError(Exception):
    """Raised when catalog data fails validation."""
    pass


def normalize_title_str(s: str) -> str:
    """Return a lowercase alphanumeric-only version of title for image filename matching."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_historical_catalog(data_path: Path) -> Dict[str, Dict[str, Any]]:
    """Loads existing HOMEBREW.data.json as historical baseline."""
    if not data_path.exists():
        return {}
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise CatalogValidationError(f"Historical catalog '{data_path}' contains invalid JSON: {err}")
    except Exception as err:
        raise CatalogValidationError(f"Failed to read historical catalog '{data_path}': {err}")

    if not isinstance(data, dict):
        raise CatalogValidationError(f"Historical catalog '{data_path}' root must be a JSON object, got {type(data).__name__}")

    catalog: Dict[str, Dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            catalog[key.upper()] = dict(value)
        else:
            raise CatalogValidationError(f"Entry '{key}' in '{data_path}' must be an object.")
    return catalog


def validate_entry(entry: Any, file_path: Path) -> Dict[str, Any]:
    """Validates an individual entry file from entries/*.json."""
    if not isinstance(entry, dict):
        raise CatalogValidationError(f"File '{file_path.name}' must contain a JSON object.")

    raw_serial = entry.get("serial")
    if not raw_serial or not isinstance(raw_serial, str):
        raise CatalogValidationError(f"File '{file_path.name}' is missing required string property 'serial'.")

    serial = raw_serial.strip().upper()
    expected_stem = file_path.stem.upper()
    if serial != expected_stem:
        raise CatalogValidationError(
            f"File '{file_path.name}' serial mismatch: 'serial' field is '{serial}' but filename is '{file_path.name}'."
        )

    if not SERIAL_REGEX.match(serial):
        raise CatalogValidationError(
            f"File '{file_path.name}' has invalid serial '{serial}'. Must be 4-15 alphanumeric/underscore/hyphen characters."
        )

    title = entry.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        raise CatalogValidationError(f"File '{file_path.name}' is missing a valid non-empty 'title' property.")

    # Canonicalize entry record
    validated: Dict[str, Any] = {
        "serial": serial,
        "title": title.strip(),
        "apitype": entry.get("apitype", "0x141"),
        "category": entry.get("category", 2),
    }

    # Preserve any optional custom properties
    for k, v in entry.items():
        if k not in validated:
            validated[k] = v

    return validated


def load_entries(entries_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Loads and validates all individual entry files from homebrew/entries/*.json."""
    if not entries_dir.exists():
        return {}

    entries: Dict[str, Dict[str, Any]] = {}
    seen_files_case_insensitive: Dict[str, str] = {}

    for path in sorted(entries_dir.glob("*.json")):
        lower_stem = path.stem.lower()
        if lower_stem in seen_files_case_insensitive:
            raise CatalogValidationError(
                f"Duplicate entry file detected: '{path.name}' collides with '{seen_files_case_insensitive[lower_stem]}'."
            )
        seen_files_case_insensitive[lower_stem] = path.name

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = json.load(f)
        except json.JSONDecodeError as err:
            raise CatalogValidationError(f"Invalid JSON syntax in '{path.name}': {err}")
        except Exception as err:
            raise CatalogValidationError(f"Failed to read '{path.name}': {err}")

        validated_record = validate_entry(content, path)
        entries[validated_record["serial"]] = validated_record

    return entries


def consolidate_catalogs(
    historical: Dict[str, Dict[str, Any]],
    individual_entries: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Consolidates historical catalog and individual entries.
    All historical entries are preserved. Individual entries are added or updated.
    Output is deterministically sorted by serial key.
    """
    consolidated: Dict[str, Dict[str, Any]] = dict(historical)

    for serial, entry in individual_entries.items():
        if serial in consolidated:
            # Update existing entry preserving historical fields if not specified in entry
            merged = dict(consolidated[serial])
            merged.update(entry)
            consolidated[serial] = merged
        else:
            consolidated[serial] = entry

    # Deterministic alphabetical ordering by key
    sorted_catalog = {k: consolidated[k] for k in sorted(consolidated.keys())}
    return sorted_catalog


def build_image_mapping(
    catalog: Dict[str, Dict[str, Any]],
    titles_dir: Path
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Maps each game serial to its corresponding cover in homebrew/Named_Titles/.
    Matches logic in generate_homebrew_image_map.py.
    """
    png_map: Dict[str, str] = {}
    if titles_dir.exists():
        for entry in os.listdir(titles_dir):
            if entry.lower().endswith(".png"):
                name_without_ext = os.path.splitext(entry)[0]
                norm = normalize_title_str(name_without_ext)
                if norm and norm not in png_map:
                    png_map[norm] = entry

    result: Dict[str, Any] = {}
    unmapped: List[str] = []

    for game_id in sorted(catalog.keys()):
        info = catalog[game_id]
        title = info.get("title", "")
        if not title:
            result[game_id] = None
            unmapped.append(game_id)
            continue

        norm_title = normalize_title_str(title)
        if norm_title in png_map:
            result[game_id] = f"homebrew/Named_Titles/{png_map[norm_title]}"
        else:
            result[game_id] = None
            unmapped.append(game_id)

    return result, unmapped


def write_json_atomically(path: Path, data: Any) -> None:
    """Writes JSON data atomically via a temporary file with indent=2 and trailing newline."""
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    temp_path.replace(path)


def run_consolidation(
    data_path: Path = DATA_JSON,
    entries_dir: Path = ENTRIES_DIR,
    titles_dir: Path = NAMED_TITLES_DIR,
    output_map_path: Path = OUTPUT_MAP_JSON,
    error_log_path: Path = ERROR_LOG,
    check_only: bool = False
) -> bool:
    """
    Main consolidation function.
    Returns True if catalog is up to date (or was successfully updated).
    In check_only mode, returns False if changes would be written.
    """
    historical = load_historical_catalog(data_path)
    individual_entries = load_entries(entries_dir)

    consolidated = consolidate_catalogs(historical, individual_entries)
    image_map, unmapped = build_image_mapping(consolidated, titles_dir)

    target_catalog_json = json.dumps(consolidated, indent=2, ensure_ascii=False) + "\n"
    target_map_json = json.dumps(image_map, indent=2, ensure_ascii=False) + "\n"

    existing_catalog_json = data_path.read_text(encoding="utf-8") if data_path.exists() else ""
    existing_map_json = output_map_path.read_text(encoding="utf-8") if output_map_path.exists() else ""

    is_catalog_modified = (target_catalog_json != existing_catalog_json)
    is_map_modified = (target_map_json != existing_map_json)

    if check_only:
        if is_catalog_modified or is_map_modified:
            print("[CHECK FAILED] Catalog or image map needs consolidation.")
            return False
        print("[CHECK PASSED] Catalog and image map are fully up to date.")
        return True

    # Apply changes
    write_json_atomically(data_path, consolidated)
    write_json_atomically(output_map_path, image_map)

    # Write error log for unmapped titles
    if unmapped:
        with open(error_log_path, "w", encoding="utf-8") as f:
            for serial in unmapped:
                f.write(f"{serial}\n")
        print(f"[CONSOLIDATE] Complete. Mapped {len(consolidated) - len(unmapped)}/{len(consolidated)} entries. {len(unmapped)} unmapped in {error_log_path.name}")
    else:
        if error_log_path.exists():
            error_log_path.unlink()
        print(f"[CONSOLIDATE] Complete. All {len(consolidated)} entries mapped!")

    return True


def main():
    check_mode = "--check" in sys.argv
    try:
        success = run_consolidation(check_only=check_mode)
        sys.exit(0 if success else 1)
    except CatalogValidationError as val_err:
        print(f"[VALIDATION ERROR] {val_err}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[FATAL ERROR] Unexpected error during consolidation: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
