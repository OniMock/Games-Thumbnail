"""
Validation script for Pull Requests in Games-Thumbnail (Capas).
Ensures all contributed assets and metadata conform to repository standards
across PSP, PS1 (PSX), and Homebrew platforms.

Validates:
1. Valid binary PNG (Magic Bytes: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A).
2. Platform-specific aspect ratio and dimensions:
   - PSX: 1:1 aspect ratio (square jewel case, e.g. 272x272, min 80x80).
   - PSP: ~1.8:1 aspect ratio (horizontal banner, 1.70 - 1.86, e.g. 144x80, 480x272).
   - Homebrew: ~1.8:1 aspect ratio (horizontal banner, 1.70 - 1.86, or 1:1 if targeting PSX).
3. Naming convention and catalog correspondence.
4. Homebrew entry integrity and absence of duplicate IDs.
5. Clean dry-run of map consolidation.

Exit code 0 on success, non-zero on failure.
DOES NOT modify repository state or make commits.
"""

import sys
import os
import json
import re
import struct
import subprocess
import tempfile
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PNG_MAGIC_BYTES = b'\x89PNG\r\n\x1a\n'

def normalize_str(s: str) -> str:
    """Return lowercase alphanumeric only version of string."""
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())

def strip_parens(s: str) -> str:
    """Remove parenthetical region/disc information."""
    if not s:
        return ""
    return re.sub(r'\s*\([^)]*\)', '', s).strip()

def validate_png_magic_bytes(filepath: Path) -> tuple[bool, str]:
    if not filepath.exists():
        return False, f"File does not exist: {filepath}"
    if filepath.stat().st_size == 0:
        return False, f"Image file is empty: {filepath.name}"
    try:
        with open(filepath, 'rb') as f:
            header = f.read(8)
            if header != PNG_MAGIC_BYTES:
                return False, f"File '{filepath.name}' is not a valid binary PNG (invalid magic bytes)."
    except Exception as e:
        return False, f"Error reading {filepath.name}: {e}"
    return True, "Valid PNG"

def get_png_dimensions(filepath: Path) -> tuple[int, int] | None:
    """Reads width and height from PNG IHDR chunk without external image libraries."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(24)
            if len(header) < 24:
                return None
            if header[:8] != PNG_MAGIC_BYTES:
                return None
            if header[12:16] != b'IHDR':
                return None
            width, height = struct.unpack('>II', header[16:24])
            return width, height
    except Exception:
        return None

def validate_png_dimensions_and_ratio(filepath: Path) -> tuple[bool, str]:
    """
    Validates platform-specific aspect ratio and dimension standards:
    - PSX: 1:1 aspect ratio (square, e.g. 272x272, min 80x80).
    - PSP: ~1.8:1 aspect ratio (horizontal banner, 1.70 - 1.86, min 120x60).
    - Homebrew: ~1.8:1 aspect ratio (horizontal banner, 1.70 - 1.86, or 1:1 if targeting PSX).
    """
    dims = get_png_dimensions(filepath)
    if not dims:
        return False, f"File '{filepath.name}' is corrupt or missing standard PNG IHDR header."

    width, height = dims
    if width <= 0 or height <= 0:
        return False, f"File '{filepath.name}' has invalid dimensions ({width}x{height})."

    parts = [p.lower() for p in filepath.parts]
    ratio = width / height

    if 'psx' in parts:
        if not (0.95 <= ratio <= 1.05):
            return False, (
                f"PSX cover '{filepath.name}' must have a 1:1 aspect ratio (square jewel case, e.g. 272x272). "
                f"Detected dimensions: {width}x{height} (aspect ratio {ratio:.2f}:1)."
            )
        if width < 80 or height < 80:
            return False, (
                f"PSX cover '{filepath.name}' is too small ({width}x{height}). "
                f"Minimum resolution is 80x80 (recommended: 272x272)."
            )
        return True, f"Valid PSX dimensions: {width}x{height} (1:1)"

    if 'psp' in parts:
        if not (1.70 <= ratio <= 1.86):
            return False, (
                f"PSP cover '{filepath.name}' must have approximately a 1.8:1 aspect ratio (horizontal banner, e.g. 144x80, 480x272). "
                f"Detected dimensions: {width}x{height} (aspect ratio {ratio:.2f}:1)."
            )
        if width < 120 or height < 60:
            return False, (
                f"PSP cover '{filepath.name}' is too small ({width}x{height}). "
                f"Minimum resolution is 144x80."
            )
        return True, f"Valid PSP dimensions: {width}x{height} (1.8:1)"

    if 'homebrew' in parts:
        # Check if the homebrew entry explicitly targets PSX
        is_psx_homebrew = False
        stem = normalize_str(filepath.stem)
        entries_dir = BASE_DIR / 'homebrew' / 'entries'
        if entries_dir.exists():
            for ent_file in entries_dir.glob('*.json'):
                try:
                    with open(ent_file, 'r', encoding='utf-8') as ef:
                        data = json.load(ef)
                        title_clean = normalize_str(data.get('title', ''))
                        serial_clean = normalize_str(data.get('serial', ''))
                        if stem == title_clean or stem == serial_clean or stem == normalize_str(ent_file.stem):
                            if str(data.get('platform', '')).upper() == 'PSX' or data.get('category') == 1:
                                is_psx_homebrew = True
                                break
                except Exception:
                    pass

        if is_psx_homebrew:
            if not (0.95 <= ratio <= 1.05):
                return False, (
                    f"Homebrew PSX cover '{filepath.name}' must have a 1:1 aspect ratio (square, e.g. 272x272). "
                    f"Detected dimensions: {width}x{height} (aspect ratio {ratio:.2f}:1)."
                )
            if width < 80 or height < 80:
                return False, (
                    f"Homebrew PSX cover '{filepath.name}' is too small ({width}x{height}). Minimum resolution is 80x80."
                )
            return True, f"Valid Homebrew PSX dimensions: {width}x{height} (1:1)"
        else:
            if not (1.70 <= ratio <= 1.86):
                return False, (
                    f"Homebrew cover '{filepath.name}' must have approximately a 1.8:1 aspect ratio (horizontal banner, e.g. 144x80). "
                    f"Detected dimensions: {width}x{height} (aspect ratio {ratio:.2f}:1)."
                )
            if width < 120 or height < 60:
                return False, (
                    f"Homebrew cover '{filepath.name}' is too small ({width}x{height}). Minimum resolution is 144x80."
                )
            return True, f"Valid Homebrew PSP dimensions: {width}x{height} (1.8:1)"

    return True, f"Valid dimensions: {width}x{height}"

def load_catalog(filepath: Path) -> dict:
    if not filepath.exists():
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_pr_changed_files() -> list[str]:
    """
    Detects files added or modified in the current branch compared to main.
    Falls back to sys.argv[1:] if provided.
    """
    if len(sys.argv) > 1:
        return [arg.replace('\\', '/') for arg in sys.argv[1:]]

    try:
        # Check git diff against origin/main or main
        res = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=d', 'origin/main...HEAD'],
            capture_output=True,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            return [line.strip().replace('\\', '/') for line in res.stdout.strip().splitlines() if line.strip()]
        
        # Fallback to local main
        res = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=d', 'main...HEAD'],
            capture_output=True,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            return [line.strip().replace('\\', '/') for line in res.stdout.strip().splitlines() if line.strip()]
    except Exception:
        pass

    return []

def validate_homebrew_entries() -> list[str]:
    """Validate all individual entries in homebrew/entries/."""
    errors = []
    entries_dir = BASE_DIR / 'homebrew' / 'entries'
    if not entries_dir.exists():
        return errors

    seen_serials = set()
    serial_regex = re.compile(r'^[A-Za-z0-9_\-]{4,16}$')

    for filename in sorted(os.listdir(entries_dir)):
        if not filename.endswith('.json'):
            errors.append(f"Unexpected non-JSON file in homebrew/entries: {filename}")
            continue

        entry_path = entries_dir / filename
        try:
            with open(entry_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"Invalid JSON syntax in {filename}: {e}")
            continue

        if not isinstance(data, dict):
            errors.append(f"Entry {filename} root must be a JSON object.")
            continue

        serial = data.get('serial')
        title = data.get('title')

        if not serial or not isinstance(serial, str) or not serial.strip():
            errors.append(f"Entry {filename} is missing required 'serial' string.")
            continue

        if not title or not isinstance(title, str) or not title.strip():
            errors.append(f"Entry {filename} is missing required 'title' string.")
            continue

        clean_serial = serial.strip()
        expected_filename = f"{clean_serial}.json"
        if filename != expected_filename:
            errors.append(f"Filename mismatch: expected '{expected_filename}', got '{filename}'.")

        if not serial_regex.match(clean_serial):
            errors.append(f"Invalid serial format '{clean_serial}' in {filename}.")

        if clean_serial in seen_serials:
            errors.append(f"Duplicate serial '{clean_serial}' found in entries.")
        seen_serials.add(clean_serial)

    return errors

def validate_contributed_images(changed_files: list[str]) -> list[str]:
    """Validate only contributed images (or all if specific targets specified)."""
    errors = []

    # Filter for image files in Named_Titles directories
    image_files = []
    if changed_files:
        for f in changed_files:
            p = Path(f)
            if 'Named_Titles' in p.parts and p.suffix.lower() == '.png':
                image_files.append(BASE_DIR / p)
    else:
        # If no specific diff, check all homebrew Named_Titles (community contributions)
        hb_titles = BASE_DIR / 'homebrew' / 'Named_Titles'
        if hb_titles.exists():
            for fn in os.listdir(hb_titles):
                if fn.endswith('.png'):
                    image_files.append(hb_titles / fn)

    for filepath in image_files:
        if not filepath.exists():
            continue
        is_valid, msg = validate_png_magic_bytes(filepath)
        if not is_valid:
            errors.append(msg)
            continue

        is_valid_dims, dims_msg = validate_png_dimensions_and_ratio(filepath)
        if not is_valid_dims:
            errors.append(dims_msg)

    return errors

def dry_run_catalog_consolidation() -> list[str]:
    """
    Test that consolidate_homebrew_catalog, generate_full_map, and alias validation execute cleanly.
    Runs in an isolated temporary environment to ensure zero side-effects or file modifications
    on the user's checkout.
    """
    errors = []

    with tempfile.TemporaryDirectory(prefix="pr_dry_run_") as tmpdir:
        tmp_path = Path(tmpdir)
        temp_data = tmp_path / "HOMEBREW.data.json"
        temp_map = tmp_path / "game_id_to_image.json"
        temp_log = tmp_path / "homebrew_mapping_errors.log"
        temp_full_map = tmp_path / "full_game_map.json"

        from homebrew.consolidate_homebrew_catalog import (
            DATA_JSON, OUTPUT_MAP_JSON, ENTRIES_DIR, NAMED_TITLES_DIR,
            run_consolidation
        )

        # Seed with current catalog data as baseline
        if DATA_JSON.exists():
            shutil.copyfile(DATA_JSON, temp_data)
        if OUTPUT_MAP_JSON.exists():
            shutil.copyfile(OUTPUT_MAP_JSON, temp_map)

        try:
            success = run_consolidation(
                data_path=temp_data,
                entries_dir=ENTRIES_DIR,
                titles_dir=NAMED_TITLES_DIR,
                output_map_path=temp_map,
                error_log_path=temp_log,
                check_only=False
            )
            if not success:
                errors.append("Homebrew consolidation dry-run failed.")
        except Exception as e:
            errors.append(f"Exception during Homebrew consolidation dry-run: {e}")

        try:
            import generate_full_map
            orig_output = generate_full_map.OUTPUT_FILE
            orig_hb_map = generate_full_map.HOMEBREW_MAP
            generate_full_map.OUTPUT_FILE = temp_full_map
            if temp_map.exists():
                generate_full_map.HOMEBREW_MAP = temp_map
            try:
                generate_full_map.merge_mappings()
            finally:
                generate_full_map.OUTPUT_FILE = orig_output
                generate_full_map.HOMEBREW_MAP = orig_hb_map
        except Exception as e:
            errors.append(f"Exception during full map generation dry-run: {e}")

        try:
            from generate_by_id_aliases import load_and_validate_sources
            load_and_validate_sources()
        except Exception as e:
            errors.append(f"Exception during By-ID alias validation dry-run: {e}")

    return errors

def main():
    print("=== RUNNING PULL REQUEST VALIDATION SUITE ===")
    all_errors = []

    changed = get_pr_changed_files()
    if changed:
        print(f"Detected {len(changed)} changed file(s) for validation.")
    else:
        print("No specific git diff detected; running baseline integrity checks.")

    # 1. Validate Homebrew entries
    print("\n[1/3] Validating Homebrew entries integrity...")
    hb_errors = validate_homebrew_entries()
    if hb_errors:
        all_errors.extend(hb_errors)
        for err in hb_errors:
            print(f"  [ERROR] {err}")
    else:
        print("  [OK] All Homebrew entries are valid and unique.")

    # 2. Validate PNG magic bytes & format
    print("\n[2/3] Validating contributed PNG assets (format, dimensions & aspect ratio)...")
    img_errors = validate_contributed_images(changed)
    if img_errors:
        all_errors.extend(img_errors)
        for err in img_errors:
            print(f"  [ERROR] {err}")
    else:
        print("  [OK] Contributed image assets have valid PNG magic bytes and conform to platform aspect ratio.")

    # 3. Dry-run consolidation and map generation
    print("\n[3/3] Testing catalog consolidation and map build...")
    map_errors = dry_run_catalog_consolidation()
    if map_errors:
        all_errors.extend(map_errors)
        for err in map_errors:
            print(f"  [ERROR] {err}")
    else:
        print("  [OK] Catalog consolidation and mapping dry-run succeeded.")

    if all_errors:
        print(f"\n[FAIL] PR validation failed with {len(all_errors)} errors.")
        sys.exit(1)

    print("\n[SUCCESS] All PR validation checks passed cleanly!")
    sys.exit(0)

if __name__ == '__main__':
    main()
