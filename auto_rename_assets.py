import os
import json
import re
from pathlib import Path

# Configuration
BASE_DIR = Path(__file__).resolve().parent
PLATFORMS = {
    "psp": {
        "data": BASE_DIR / "psp" / "PSP.data.json",
        "titles": BASE_DIR / "psp" / "Named_Titles"
    },
    "psx": {
        "data": BASE_DIR / "psx" / "PSX.data.json",
        "titles": BASE_DIR / "psx" / "Named_Titles"
    },
    "homebrew": {
        "data": BASE_DIR / "homebrew" / "HOMEBREW.data.json",
        "titles": BASE_DIR / "homebrew" / "Named_Titles"
    }
}


def sanitize_filename(filename: str) -> str:
    """Remove characters that are illegal in Windows filenames."""
    # Replace colons, slashes, etc with a hyphen
    s = re.sub(r'[:\\/*?"<>|]', ' -', filename)
    # Remove double spaces
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def load_db(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def auto_rename():
    for platform, paths in PLATFORMS.items():
        print(f"\n--- Processing {platform.upper()} ---")
        db = load_db(paths["data"])
        titles_dir = paths["titles"]
        
        if not titles_dir.exists():
            print(f"Skipping {platform}: Folder {titles_dir} not found.")
            continue

        # Create a lookup for clean serials -> title
        # Database keys usually have hyphens like ULUS-10190
        serial_to_title = {}
        for key, info in db.items():
            if isinstance(info, dict) and "serial" in info:
                clean_serial = info["serial"].replace("-", "").upper()
                title = info.get("title", "")
                if isinstance(title, list): title = title[0]
                if title:
                    serial_to_title[clean_serial] = title

        count = 0
        for filename in os.listdir(titles_dir):
            if not filename.lower().endswith(".png"):
                continue
            
            name_no_ext = os.path.splitext(filename)[0].upper()
            
            # Check if the filename looks like a serial (e.g. ULUS10190)
            if name_no_ext in serial_to_title:
                new_title = serial_to_title[name_no_ext]
                new_filename = f"{sanitize_filename(new_title)}.png"
                
                old_path = titles_dir / filename
                new_path = titles_dir / new_filename
                
                if old_path == new_path:
                    continue

                # Avoid overwriting existing files
                if new_path.exists():
                    print(f"[!] Cannot rename {filename} to {new_filename}: Destination already exists.")
                    continue
                
                try:
                    os.rename(old_path, new_path)
                    print(f"[OK] Renamed: {filename} -> {new_filename}")
                    count += 1
                except Exception as e:
                    print(f"[ERR] Failed to rename {filename}: {e}")
        
        print(f"Done {platform.upper()}. Renamed {count} files.")

if __name__ == "__main__":
    auto_rename()
