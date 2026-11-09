import subprocess
import sys

scripts = [
    "auto_rename_assets.py",
    "psx/generate_psx_image_map.py",
    "psp/generate_psp_image_map.py",
    "homebrew/consolidate_homebrew_catalog.py",
    "homebrew/generate_homebrew_image_map.py --no-consolidate",
    "generate_full_map.py",
    "generate_by_id_aliases.py",
    "generate_search_index.py"
]


def run():
    print("=== STARTING FULL UPDATE PROCESS ===\n")
    
    for script in scripts:
        print(f"--- Running {script} ---")
        try:
            # Use sys.executable to ensure we use the same python interpreter
            cmd = [sys.executable] + script.split()
            result = subprocess.run(cmd, capture_output=False, text=True)
            if result.returncode != 0:
                print(f"[!] Error running {script}. Stopping.")
                sys.exit(result.returncode)
        except Exception as e:
            print(f"[!] Fatal error: {e}")
            sys.exit(1)
            
    print("\n=== SUCCESS: ALL MAPS UPDATED AND ASSETS ORGANIZED ===")

if __name__ == "__main__":
    run()
