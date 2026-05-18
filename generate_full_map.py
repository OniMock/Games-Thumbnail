import json
from pathlib import Path

# Constants for file paths
BASE_DIR = Path(__file__).resolve().parent
PSX_MAP = BASE_DIR / "psx" / "game_id_to_image.json"
PSP_MAP = BASE_DIR / "psp" / "game_id_to_image.json"
HOMEBREW_MAP = BASE_DIR / "homebrew" / "game_id_to_image.json"
OUTPUT_FILE = BASE_DIR / "full_game_map.json"

def merge_mappings():
    """
    Combines PSX, PSP and Homebrew image mappings into a single JSON file.
    Filters out null values to keep the resulting file clean and small.
    """
    full_map = {}
    
    # Systems to process
    systems = {
        "PSX": PSX_MAP,
        "PSP": PSP_MAP,
        "Homebrew": HOMEBREW_MAP
    }

    
    print("Starting mapping merge process...")
    
    for system_name, map_path in systems.items():
        if map_path.exists():
            try:
                with open(map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                count = 0
                for game_id, image_path in data.items():
                    # Only include valid mappings
                    if image_path:
                        full_map[game_id] = image_path
                        count += 1
                
                print(f"Successfully processed {system_name}: {count} valid entries found.")
            except Exception as e:
                print(f"Error processing {system_name} at {map_path}: {e}")
        else:
            print(f"Warning: {system_name} mapping file not found at {map_path}")

    # Save the consolidated mapping
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(full_map, f, indent=2, ensure_ascii=False)
        print(f"\nSuccess! Generated '{OUTPUT_FILE.name}' with {len(full_map)} total mappings.")
    except Exception as e:
        print(f"Failed to write output file: {e}")

if __name__ == "__main__":
    merge_mappings()
