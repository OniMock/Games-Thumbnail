# Games-Thumbnail — Open Game Cover Art & Metadata Catalog

[![Catalog Consolidation](https://github.com/OniMock/Games-Thumbnail/actions/workflows/consolidate-catalog.yml/badge.svg)](https://github.com/OniMock/Games-Thumbnail/actions/workflows/consolidate-catalog.yml)
[![PR Validation](https://github.com/OniMock/Games-Thumbnail/actions/workflows/validate-pr.yml/badge.svg)](https://github.com/OniMock/Games-Thumbnail/actions/workflows/validate-pr.yml)
[![Total Covers](https://img.shields.io/badge/covers-13%2C200%2B-blue.svg)](#catalog-statistics)
[![Platforms](https://img.shields.io/badge/platforms-PSP%20%7C%20PSX%20%7C%20Homebrew-orange.svg)](#catalog-statistics)
[![Powered By GameDiary](https://img.shields.io/badge/powered%20by-GameDiary-emerald.svg)](https://gamediary.onimock.com)

A high-performance, open-source repository organizing and mapping official and community boxart covers for **PlayStation Portable (PSP)**, **PlayStation 1 (PSX)**, and **Homebrew** games.

Covers are mapped to canonical Game IDs / Serials (`ULUS-10041`, `SLUS-00068`, [`HBXA1B9195B`](#homebrew-identifier-game-id-convention)), enabling instant cover resolution in Web Apps, Emulators, Launchers, Frontend Hubs, and Discord Bots via GitHub Raw or jsDelivr CDN with zero backend required.

---

## Catalog Statistics

| Platform | Games with Covers | Directory Path | Metadata Catalog |
| :--- | :---: | :--- | :--- |
| **PlayStation Portable (PSP)** | **2,900+** | `psp/Named_Titles/` | `psp/PSP.data.json` |
| **PlayStation 1 (PSX)** | **10,300+** | `psx/Named_Titles/` | `psx/PSX.data.json` |
| **Homebrew (PSP & Custom)** | **Growing** | `homebrew/Named_Titles/` | `homebrew/HOMEBREW.data.json` |
| **Global Combined Map** | **13,200+** | `full_game_map.json` | All platforms combined |

---

## How to Use in Your Project

You do not need to clone this repository to use the covers. You can fetch mappings and images directly from the CDN.

### 1. Direct CDN Endpoints

#### Global Combined Map (All Platforms)
```text
https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/full_game_map.json
```
*(Also available via jsDelivr CDN for high-performance edge caching):*
```text
https://cdn.jsdelivr.net/gh/OniMock/Games-Thumbnail@main/full_game_map.json
```

#### Platform-Specific Maps
- **PSP:** `https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/psp/game_id_to_image.json`
- **PS1 (PSX):** `https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/psx/game_id_to_image.json`
- **Homebrew:** `https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/homebrew/game_id_to_image.json`

#### Image Base URL
```text
https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/<IMAGE_PATH>
```

---

### 2. Integration Examples

#### JavaScript / TypeScript (Web App, Node.js, Electron)

```typescript
// 1. Fetch the mapping dictionary once (cache in memory or LocalStorage)
const MAP_URL = 'https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/full_game_map.json';
const CDN_BASE = 'https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/';

let coverMap: Record<string, string | null> = {};

async function initCoverMap() {
  const response = await fetch(MAP_URL);
  coverMap = await response.json();
}

// 2. Resolve a cover URL by Game ID / Serial
function getCoverUrl(gameId: string): string | null {
  // Normalize serial: remove hyphens, spaces, and uppercase (e.g., 'ULUS-10041' -> 'ULUS10041')
  const cleanId = gameId.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
  const relativePath = coverMap[cleanId];

  if (!relativePath) {
    return null; // Fallback or placeholder
  }

  // Construct final URL (encode path to handle special title characters safely)
  const encodedPath = relativePath.split('/').map(encodeURIComponent).join('/');
  return `${CDN_BASE}${encodedPath}`;
}

// Example usage:
// getCoverUrl('ULUS-10041') -> 'https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/psp/Named_Titles/Persona%203%20Portable.png'
// getCoverUrl('SLUS-00068') -> 'https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/psx/Named_Titles/Crash%20Bandicoot.png'
```

#### Python (Emulators, Scrapers, CLI Tools)

```python
import requests
import urllib.parse
import re

CDN_BASE = "https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/"
MAP_URL = f"{CDN_BASE}full_game_map.json"

# Load map
catalog = requests.get(MAP_URL).json()

def resolve_cover(game_id: str) -> str | None:
    clean_id = re.sub(r"[^A-Za-z0-9]", "", game_id).upper()
    relative_path = catalog.get(clean_id)
    if not relative_path:
        return None
    return CDN_BASE + urllib.parse.quote(relative_path)

print(resolve_cover("ULUS-10041"))
# https://raw.githubusercontent.com/OniMock/Games-Thumbnail/main/psp/Named_Titles/Persona%203%20Portable.png
```

---

## Cover Image Standards & Specifications

To maintain high visual quality across applications, all submitted covers must follow these guidelines:

1. **File Format:** True **PNG** format strictly (`.png`). Renamed JPEG or WebP files are automatically rejected by validation tests.
2. **Aspect Ratio & Platform Specifications:**
   - **PlayStation 1 (PSX):** Strict **1:1 aspect ratio** (Square jewel case front cover, e.g. `272×272`, `500×500`, `1000×1000`). Minimum size: `80×80`.
   - **PlayStation Portable (PSP):** Approximately **1.8:1 aspect ratio** (Horizontal title banner, e.g. `144×80` or `480×272`). Minimum size: `144×80`.
   - **Homebrew:** Approximately **1.8:1 aspect ratio** (Horizontal banner matching PSP homebrew launchers, e.g. `144×80`), or **1:1** if explicitly targeting PSX homebrew.
3. **Naming Convention:**
   - Must be placed under the respective platform folder: `psp/Named_Titles/`, `psx/Named_Titles/`, or `homebrew/Named_Titles/`.
   - The file name should match the **canonical game title** (e.g. `Grand Theft Auto - Liberty City Stories.png`).
4. **Resolution & Quality:** Clean edges, sharp artwork, no aggressive watermarks, and no corrupt scanlines.

---

## Homebrew Identifier (Game ID) Convention

Unlike commercial PlayStation titles that ship with fixed Sony disc serials (`ULUS-10041`, `SLUS-00068`, `ULES-00123`), homebrew games, source ports, and emulators lack standard serial numbers. Furthermore, custom firmware (CFW) ISO loaders frequently spoof the internal `DISC_ID` to dummy IDs (such as LocoRoco `UCJS10041`), which GameDiary detects and rejects.

To guarantee that homebrew titles receive **deterministic, collision-resistant, and cross-device identifiers**, the **GameDiary PSP Homebrew & Tracker Plugin** uses a canonical hashing specification.

### 1. Identifier Format (`HBX%08X`)
- **Prefix:** `HBX` (HomeBrew eXtension)
- **Hash Digits:** Exactly 8 uppercase hexadecimal characters (`[0-9A-F]{8}`) representing an unsigned 32-bit integer.
- **Total Length:** Exactly 11 ASCII characters (e.g., `HBXA1B9195B`).
- **Validation Regex:** `^HBX[0-9A-F]{8}$`

### 2. How GameDiary PSP Generates Homebrew IDs
The PSP tracker plugin (`src/plugin/metadata_repository.c`) runs the following pipeline at game launch:

1. **Title Extraction:**
   - **Primary:** The **parent folder name** under `ms0:/PSP/GAME/<folder>/` (e.g., `ms0:/PSP/GAME/pspalatro/EBOOT.PBP` &rarr; `"pspalatro"`). On PSP, users and creators maintain clean directory names.
   - **Fallback:** If the folder name is generic (empty, `"GAME"`, or `"Unknown Game"`), the `TITLE` string embedded inside the `PARAM.SFO` of the `EBOOT.PBP` is read instead.
2. **Title Normalization:**
   To ensure that naming variations (e.g., `"GameDiary"`, `"Game Diary"`, and `"gamediary"`) yield identical IDs across different PSP consoles:
   - All ASCII space characters (`0x20` / `' '`) are stripped.
   - All ASCII uppercase characters (`A`-`Z`) are converted to lowercase (`a`-`z`).
   - Digits, symbols, and non-ASCII UTF-8 sequences (> 127) are preserved byte-for-byte.
   - The normalized buffer is clamped to 127 bytes.
3. **DJB2 Hash Computation:**
   The normalized string is hashed using Daniel J. Bernstein's 32-bit **DJB2** hash algorithm (initial hash value `5381`):
   ```text
   hash = 5381
   for each character c in normalized_title:
       hash = ((hash << 5) + hash) + c    /* hash * 33 + c (32-bit unsigned wrapping) */
   ```
4. **Identifier Formatting:**
   The unsigned 32-bit integer is formatted as `HBX%08X`:
   ```c
   snprintf(metadata->game_id, sizeof(metadata->game_id), "HBX%08X", (unsigned int)hash);
   ```

### 3. Reference Implementation

#### Python
```python
def generate_homebrew_id(title: str) -> str:
    """
    Generates a canonical GameDiary HBX identifier for a homebrew title or folder name.
    """
    # 1. Normalize: strip ASCII spaces and lowercase ASCII A-Z
    normalized = "".join(c.lower() for c in title if c != " ")[:127]

    # 2. Compute 32-bit unsigned DJB2 hash
    h = 5381
    for b in normalized.encode("utf-8"):
        h = ((h << 5) + h + b) & 0xFFFFFFFF

    # 3. Format as HBX + 8 uppercase hex digits
    return f"HBX{h:08X}"

# Examples:
# generate_homebrew_id("pspalatro")      -> "HBXA1B9195B"
# generate_homebrew_id("GameDiary")      -> "HBX0E9162F8"
# generate_homebrew_id("Super Mario 64") -> "HBXE9780D96"
```

#### TypeScript / JavaScript
```typescript
export function generateHomebrewId(title: string): string {
  // 1. Normalize: strip ASCII spaces and lowercase ASCII A-Z (max 127 chars)
  const normalized = title.replace(/ /g, '').toLowerCase().slice(0, 127);
  const bytes = new TextEncoder().encode(normalized);

  // 2. Compute 32-bit unsigned DJB2 hash (replicating C signed char arithmetic)
  let hash = 5381 >>> 0;
  for (let i = 0; i < bytes.length; i++) {
    const signedByte = (bytes[i] << 24) >> 24;
    hash = (Math.imul(hash, 33) + signedByte) >>> 0;
  }

  // 3. Format as HBX + 8 uppercase hex digits
  return `HBX${hash.toString(16).toUpperCase().padStart(8, '0')}`;
}
```

### 4. Special Cases & Exceptions
- **Official PSP Apps (`PSP/APP`):** Official Sony utility apps (e.g., *SenseMe™*, *Comic Reader*) installed under `ms0:/PSP/APP/` or folders with authentic Sony Content IDs (4 letters + 5 digits, e.g., `NPIA00013`) retain their authentic Sony serial instead of generating an `HBX` hash.
- **Custom SFO Serials:** If a homebrew author configured an explicit, non-spoofed custom `DISC_ID` in `PARAM.SFO` (e.g., `ARK_01234`), GameDiary preserves it as-is.
- **Legacy IDs:** Historical entries created prior to June 2026 computed the DJB2 hash on unnormalized titles with original spaces and casing (e.g., `"Super Mario 64"` &rarr; `HBX392ABD96`, `"Forms3D"` &rarr; `HBX1B6576C3`). These legacy records are maintained in `HOMEBREW.data.json` for backwards compatibility, while all new community submissions and modern plugin releases use the normalized standard.

---

## How to Contribute

We welcome community contributions! You can submit covers through either of the following methods:

### Option 1: Via GameDiary Web App (Easiest & Automated)
1. Open [GameDiary](https://gamediary.onimock.com).
2. Find or add your game.
3. Open the cover editor, upload your image (PNG, JPG, or WebP), and adjust the frame.
4. Click **"Contribute to Community"**.
5. The application converts the image to a standardized PNG, checks for duplicates, and automatically opens a Pull Request on GitHub for you!

### Option 2: Via Manual GitHub Pull Request

1. **Fork** this repository and clone your fork.
2. Prepare your cover image according to the [Cover Standards](#cover-image-standards--specifications).
3. **For PSP:**
   - Place the image in `psp/Named_Titles/<Canonical Game Title>.png`.
   - The Game ID must exist in `psp/PSP.data.json`.
4. **For PS1 (PSX):**
   - Place the image in `psx/Named_Titles/<Canonical Game Title>.png`.
   - The Game ID must exist in `psx/PSX.data.json`.
5. **For Homebrew:**
   - Follow the [Homebrew Identifier Convention](#homebrew-identifier-game-id-convention) to derive the canonical `HBX` ID for your title.
   - Place the image in `homebrew/Named_Titles/<Game Title>.png`.
   - Create an individual metadata file in `homebrew/entries/<SERIAL>.json`:
     ```json
     {
       "serial": "HBXA1B9195B",
       "title": "pspalatro",
       "author": "Developer or Team",
       "platform": "PSP",
       "version": "1.0.0",
       "category": "Game",
       "description": "Short summary of the homebrew project."
     }
     ```
6. Open a Pull Request targeting the `main` branch.
7. The automated CI workflow ([`validate-pr.yml`](.github/workflows/validate-pr.yml)) will verify your image integrity and catalog entries automatically.
8. Once merged, the consolidation pipeline will automatically update all mapping files.

---

## Repository Automation & Architecture

This repository uses automated GitHub Actions workflows to guarantee zero manual maintenance after merging:

- **`.github/workflows/validate-pr.yml`:**
  - Runs automatically on every Pull Request.
  - Verifies PNG binary signature, chunks, and data integrity.
  - Validates Homebrew JSON entry schema.
  - Checks for duplicates against the existing catalog.
- **`.github/workflows/consolidate-catalog.yml`:**
  - Runs automatically on merge to `main`.
  - Executes Python generators:
    1. `auto_rename_assets.py` (standardizes titles).
    2. `psx/generate_psx_image_map.py` (builds PS1 map).
    3. `psp/generate_psp_image_map.py` (builds PSP map).
    4. `homebrew/consolidate_homebrew_catalog.py` (consolidates modular `entries/*.json` into `HOMEBREW.data.json`).
    5. `homebrew/generate_homebrew_image_map.py` (builds Homebrew map).
    6. `generate_full_map.py` (merges all platform maps into `full_game_map.json`).
  - Automatically commits and pushes the updated maps back to `main`.

---

## Local Development & Maintenance

If you are developing locally or maintaining the repository scripts:

### Requirements
- Python 3.9+
- Pillow (`pip install pillow`)

### Update All Maps Locally
```bash
python update_all.py
```

### Validate PR Rules Locally
```bash
python validate_pr.py
```

---

## Credits & Acknowledgments

This project is a compilation and mapping bridge built upon the hard work of retro gaming preservation communities:

### Cover Art & Thumbnails
- **[Libretro Thumbnails Project](https://github.com/libretro-thumbnails):**
  - **PSX / PS1:** [`libretro-thumbnails/Sony_-_PlayStation`](https://github.com/libretro-thumbnails/Sony_-_PlayStation) (`Named_Titles` / `Named_Boxarts`)
  - **PSP:** [`libretro-thumbnails/Sony_-_PlayStation_Portable`](https://github.com/libretro-thumbnails/Sony_-_PlayStation_Portable) (`Named_Titles` / `Named_Boxarts`)
- Standardized game titles and filenames conform to the naming conventions established by the **[No-Intro](https://www.no-intro.org/)** and **[Redump.org](http://redump.org/)** preservation projects.
- New and updated covers submitted by community members via [GameDiary](https://gamediary.onimock.com).

### Metadata Catalogs & Databases
- **[niemasd/GameDB-PSX](https://github.com/niemasd/GameDB-PSX):** Comprehensive PlayStation 1 metadata index (`PSX.data.json`), compiled from the PSX Data Center.
- **[niemasd/GameDB-PSP](https://github.com/niemasd/GameDB-PSP):** PlayStation Portable metadata index (`PSP.data.json`), compiled from official UMD and digital release records.
- **GameDiary Community:** Curated catalog for PlayStation Portable Homebrew applications and games (`homebrew/entries/`).

### Disclaimer & Copyright
- Compilation, automated mapping scripts, and CI/CD pipelines created and maintained by [OniMock](https://github.com/OniMock) for [GameDiary](https://gamediary.onimock.com).
- All game cover artwork, trademarks, titles, and logos belong to their respective publishers, developers, and copyright holders (Sony Interactive Entertainment, Konami, Capcom, Square Enix, Bandai Namco, Sega, EA, etc.).
- Artwork is mirrored and indexed strictly for personal library organization, cataloging, non-commercial interoperability, and digital preservation.
