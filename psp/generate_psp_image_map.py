import os
import json
import re
from pathlib import Path

# Paths (adjust if script moved)
BASE_DIR = Path(__file__).resolve().parent
DATA_JSON = BASE_DIR / "PSP.data.json"
NAMED_TITLES_DIR = BASE_DIR / "Named_Titles"
OUTPUT_JSON = BASE_DIR / "game_id_to_image.json"
ERROR_LOG = BASE_DIR / "psp_mapping_errors.log"

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
            norm = normalize_str(name_without_ext)
            stripped = normalize_str(strip_parens(name_without_ext))
            
            # Map exact normalized name
            if norm not in mapping:
                mapping[norm] = entry
            
            # Map stripped name with priority for non-disc versions
            if stripped:
                current_val = mapping.get(stripped)
                is_new_disc = "disc" in entry.lower()
                is_current_disc = current_val and "disc" in current_val.lower()
                
                # Overwrite if:
                # 1. No mapping exists for this stripped name yet
                # 2. The existing mapping is a "Disc" version but the new one is NOT
                if stripped not in mapping or (is_current_disc and not is_new_disc):
                    mapping[stripped] = entry
    return mapping

def main():
    data = load_data()
    png_map = get_png_filenames()
    result = {}
    unmapped = []

    print(f"Processing {len(data)} entries from {DATA_JSON.name}...")

    for key, info in data.items():
        if not isinstance(info, dict) or 'serial' not in info:
            continue
            
        serial = info['serial']
        serial_clean = serial.replace('-', '')
        
        # Priority 1: Direct serial match
        serial_norm = normalize_str(serial_clean)
        
        # Priority 2: Title and Key matches
        title = info.get('title', '')
        if isinstance(title, list):
            title = title[0] if title else ''
            
        release_name = info.get('release_name', '')
        if isinstance(release_name, list):
            release_name = release_name[0] if release_name else ''
        
        # Logic: Try specific match first. If it's too small (< 5KB), fallback to Master match.
        found_filename = None
        
        # 1. Try Specific Match
        specific_candidates = [
            serial_norm,
            normalize_str(title),
            normalize_str(release_name),
            normalize_str(key)
        ]
        
        for c in specific_candidates:
            if c and c in png_map:
                fname = png_map[c]
                fpath = NAMED_TITLES_DIR / fname
                if fpath.exists():
                    # If it's a "Disc" file, check size. If < 5KB, we'll try to find a better one.
                    if "disc" in fname.lower() and fpath.stat().st_size < 5120:
                        continue # Skip this small disc image
                    
                    found_filename = fname
                    break
        
        # 2. Fallback to Master Match (if no specific found or all were small disc images)
        if not found_filename:
            master_candidates = [
                normalize_str(strip_parens(title)),
                normalize_str(strip_parens(release_name)),
                normalize_str(strip_parens(key))
            ]
            for c in master_candidates:
                if c and c in png_map:
                    found_filename = png_map[c]
                    break # Take the best master available

        if found_filename:
            result[serial_clean] = f"psp/Named_Titles/{found_filename}"
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
