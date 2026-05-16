# Games Thumbnail Manager

Repository for organizing and mapping game covers (PSX and PSP) for use in Web Apps.

## 📁 Folder Structure
- `psx/Named_Titles/`: Place PlayStation 1 covers here (.png).
- `psp/Named_Titles/`: Place PSP covers here (.png).

## 🚀 How to Update Everything
Whenever you add new images or want to update the site mapping, open your terminal in the root of this project and run:

```powershell
python update_all.py
```

### What this command does:
1. **Auto-Rename**: Automatically renames files named after IDs (e.g., `ULUS10102.png`) to the actual game title.
2. **Platform Mapping**: Generates individual mapping files for PSX and PSP.
3. **Full Merge**: Generates the final `full_game_map.json` file used by the website.

---
*Tip: Keep the .json files in the root (`PSX.data.json`, etc.) updated to ensure the best possible mapping.*
