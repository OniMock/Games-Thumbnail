import os
import json
import re
from pathlib import Path

# Paths (adjust if script moved)
BASE_DIR = Path(__file__).resolve().parent
DATA_JSON = BASE_DIR / "PSX.data.json"
NAMED_TITLES_DIR = BASE_DIR / "Named_Titles"
OUTPUT_JSON = BASE_DIR / "game_id_to_image.json"
ERROR_LOG = BASE_DIR / "psx_mapping_errors.log"

def normalize_str(s: str) -> str:
    """Return a lowercase alphanumeric‑only version of *s*."""
    if not s: return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def strip_parens(s: str) -> str:
    """Remove parenthetical region/disc info from a title string."""
    if not s: return ""
    return re.sub(r"\s*\([^)]*\)", "", s).strip()

def load_data() -> dict:
    with open(DATA_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def get_png_filenames() -> dict:
    """Return a mapping of normalized filename (without extension) → actual filename."""
    mapping = {}
    if not NAMED_TITLES_DIR.exists():
        return {}
    for entry in os.listdir(NAMED_TITLES_DIR):
        if entry.lower().endswith('.png'):
            name_without_ext = os.path.splitext(entry)[0]
            mapping[normalize_str(name_without_ext)] = entry
    return mapping

def main():
    data = load_data()
    png_map = get_png_filenames()
    result = {}
    unmapped = []

    for key, info in data.items():
        # Only process entries with a serial
        if not isinstance(info, dict) or 'serial' not in info:
            continue

        serial = info['serial']
        serial_clean = serial.replace('-', '')

        # Priority 1: Direct serial match
        serial_norm = normalize_str(serial_clean)

        # Priority 2: Title and Key matches
        title = info.get('title', '')
        release_name = info.get('release_name', '')

        candidates = [
            serial_norm,
            normalize_str(title),
            normalize_str(release_name),
            normalize_str(key)
        ]

        found_filename = None
        for c in candidates:
            if c and c in png_map:
                found_filename = png_map[c]
                break

        if not found_filename:
            # Priority 3: Relaxed (no parens) matches
            relaxed = [
                normalize_str(strip_parens(title)),
                normalize_str(strip_parens(release_name)),
                normalize_str(strip_parens(key))
            ]
            for r in relaxed:
                if r and r in png_map:
                    found_filename = png_map[r]
                    break

        if found_filename:
            result[serial_clean] = f"psx/Named_Titles/{found_filename}"
        else:
            result[serial_clean] = None
            unmapped.append(serial_clean)

    # Atomic write
    temp_path = OUTPUT_JSON.with_suffix('.tmp')
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    temp_path.replace(OUTPUT_JSON)

    # Log unmapped
    if unmapped:
        with open(ERROR_LOG, "w", encoding="utf-8") as f:
            for s in unmapped:
                f.write(f"{s}\n")
        print(f"Done. Mapped {len(result) - len(unmapped)} / {len(result)} entries. Errors in {ERROR_LOG.name}")
    else:
        if ERROR_LOG.exists(): ERROR_LOG.unlink()
        print(f"Done. All {len(result)} entries matched!")

if __name__ == "__main__":
    main()
