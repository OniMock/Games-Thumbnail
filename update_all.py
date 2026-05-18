import subprocess
import sys

scripts = [
    "auto_rename_assets.py",
    "psx/generate_psx_image_map.py",
    "psp/generate_psp_image_map.py",
    "homebrew/generate_homebrew_image_map.py",
    "generate_full_map.py"
]


def run():
    print("=== STARTING FULL UPDATE PROCESS ===\n")
    
    for script in scripts:
        print(f"--- Running {script} ---")
        try:
            # Use sys.executable to ensure we use the same python interpreter
            result = subprocess.run([sys.executable, script], capture_output=False, text=True)
            if result.returncode != 0:
                print(f"[!] Error running {script}. Stopping.")
                return
        except Exception as e:
            print(f"[!] Fatal error: {e}")
            return
            
    print("\n=== SUCCESS: ALL MAPS UPDATED AND ASSETS ORGANIZED ===")

if __name__ == "__main__":
    run()
