import os
import json
import re
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_JSON = BASE_DIR / "HOMEBREW.data.json"
NAMED_TITLES_DIR = BASE_DIR / "Named_Titles"
OUTPUT_JSON = BASE_DIR / "game_id_to_image.json"
ERROR_LOG = BASE_DIR / "homebrew_mapping_errors.log"

def normalize_str(s: str) -> str:
    """Return a lowercase alphanumeric‑only version of *s*."""
    if not s: return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())

def load_data() -> dict:
    if not DATA_JSON.exists():
        return {}
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
            norm = normalize_str(name_without_ext)
            if norm not in mapping:
                mapping[norm] = entry
    return mapping

def main():
    data = load_data()
    png_map = get_png_filenames()
    result = {}
    unmapped = []

    print(f"Processing {len(data)} entries from {DATA_JSON.name}...")

    for game_id, info in data.items():
        title = info.get('title', '')
        if not title:
            continue
            
        norm_title = normalize_str(title)
        
        found_filename = None
        if norm_title in png_map:
            found_filename = png_map[norm_title]
            
        if found_filename:
            result[game_id] = f"homebrew/Named_Titles/{found_filename}"
        else:
            result[game_id] = None
            unmapped.append(game_id)

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
