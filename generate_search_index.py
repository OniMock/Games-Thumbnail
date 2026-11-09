#!/usr/bin/env python3
"""
generate_search_index.py
------------------------
Deterministic, idempotent generator of the compact game search index for GameDiary.
Consolidates PSP, PS1 (PSX), and Homebrew catalogs into 'search-index.json'.

Features:
- Canonical Game ID normalization (hyphens/spaces stripped, uppercase for PSP/PSX, homebrew preserved).
- Deterministic ordering by (platform, canonical_id).
- Main title and deduplicated alternative titles (aliases) resolution.
- Consolidation of multi-release serials (e.g. SLPS00004) into single entries with aliases.
- Safe filtering of entries lacking serials (no synthetic IDs invented).
- Real-time cover availability indicator (`hasCover`) verified against platform image maps.
- Atomic file writes via temporary files.
- Fail-closed collision detection.
- Fast, read-only `--check` verification mode for CI and PR validation.
- Zero mutation of source catalogs or existing image maps.
"""

import sys
import json
import re
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent
SEARCH_INDEX_FILE = BASE_DIR / "search-index.json"

PSP_CATALOG_FILE = BASE_DIR / "psp" / "PSP.data.json"
PSP_MAP_FILE = BASE_DIR / "psp" / "game_id_to_image.json"

PSX_CATALOG_FILE = BASE_DIR / "psx" / "PSX.data.json"
PSX_MAP_FILE = BASE_DIR / "psx" / "game_id_to_image.json"

HOMEBREW_CATALOG_FILE = BASE_DIR / "homebrew" / "HOMEBREW.data.json"
HOMEBREW_MAP_FILE = BASE_DIR / "homebrew" / "game_id_to_image.json"

MANIFEST_FILE = BASE_DIR / "by-id" / ".manifest.json"


def strip_parens(s: str) -> str:
    """Removes parenthetical regions, discs, or tags from a title string."""
    if not s:
        return ""
    return re.sub(r'\s*\([^)]*\)', '', s).strip()


def clean_noise_tokens(s: str) -> str:
    """Removes noisy catalog tags like [E], [J], [U], [En,Ja], HTML remnants (/td>) and trims whitespace."""
    if not s:
        return ""
    # Strip bracketed language/region flags like [E], [J], [En,Ja]
    s = re.sub(r'\[[A-Za-z0-9,\s]+\]', '', s)
    # Strip HTML remnants
    s = s.replace('/td>', '').replace('</td>', '')
    # Normalize multiple whitespace characters
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def normalize_game_id(raw_id: str, platform: str) -> str:
    """
    Normalizes a Game ID according to platform rules:
    - PSP: strip hyphens and spaces, uppercase.
    - PSX: strip hyphens and spaces, uppercase.
    - Homebrew: strip spaces, uppercase, preserve underscores.
    """
    if not raw_id:
        return ""
    cleaned = raw_id.strip()
    plat = platform.lower()
    if plat in ("psp", "psx"):
        cleaned = cleaned.replace("-", "").replace(" ", "").upper()
    else:
        cleaned = cleaned.replace(" ", "").upper()
    return cleaned


def build_search_index_data(base_dir: Path = BASE_DIR) -> Dict[str, Any]:
    """
    Constructs the canonical search index data dictionary from catalog files.
    Fails closed on unresolvable collisions.
    """
    psp_cat_path = base_dir / "psp" / "PSP.data.json"
    psp_map_path = base_dir / "psp" / "game_id_to_image.json"

    psx_cat_path = base_dir / "psx" / "PSX.data.json"
    psx_map_path = base_dir / "psx" / "game_id_to_image.json"

    hb_cat_path = base_dir / "homebrew" / "HOMEBREW.data.json"
    hb_map_path = base_dir / "homebrew" / "game_id_to_image.json"

    # Pre-validation: ensure input files exist
    for p in (psp_cat_path, psp_map_path, psx_cat_path, psx_map_path, hb_cat_path, hb_map_path):
        if not p.exists():
            raise FileNotFoundError(f"Required source catalog/map missing: {p}")

    psp_data: Dict[str, Any] = json.loads(psp_cat_path.read_text(encoding="utf-8"))
    psp_map: Dict[str, Any] = json.loads(psp_map_path.read_text(encoding="utf-8"))

    psx_data: Dict[str, Any] = json.loads(psx_cat_path.read_text(encoding="utf-8"))
    psx_map: Dict[str, Any] = json.loads(psx_map_path.read_text(encoding="utf-8"))

    hb_data: Dict[str, Any] = json.loads(hb_cat_path.read_text(encoding="utf-8"))
    hb_map: Dict[str, Any] = json.loads(hb_map_path.read_text(encoding="utf-8"))

    games: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    # -------------------------------------------------------------
    # 1. PSP Platform (Category: PSP)
    # -------------------------------------------------------------
    psp_by_serial: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for key, item in psp_data.items():
        if not isinstance(item, dict):
            continue
        serial = item.get("serial")
        if not serial:
            # Safely skip entries without serial (no synthetic IDs)
            continue
        canon_id = normalize_game_id(serial, "psp")
        if not canon_id:
            continue
        psp_by_serial[canon_id].append(item)

    for canon_id in sorted(psp_by_serial.keys()):
        if canon_id in seen_ids:
            raise ValueError(f"Cross-platform or unexpected duplicate Game ID: {canon_id}")
        seen_ids.add(canon_id)

        entries = psp_by_serial[canon_id]
        primary_title = ""
        aliases: Set[str] = set()

        for e in entries:
            raw_title = e.get("title")
            if isinstance(raw_title, list):
                for t in raw_title:
                    cleaned = clean_noise_tokens(t)
                    if not cleaned:
                        continue
                    if not primary_title:
                        primary_title = cleaned
                    elif cleaned.lower() != primary_title.lower():
                        aliases.add(cleaned)
            elif isinstance(raw_title, str) and raw_title.strip():
                cleaned = clean_noise_tokens(raw_title)
                if cleaned:
                    if not primary_title:
                        primary_title = cleaned
                    elif cleaned.lower() != primary_title.lower():
                        aliases.add(cleaned)

            rn = e.get("release_name")
            if isinstance(rn, str) and rn.strip():
                cleaned_rn = clean_noise_tokens(rn)
                if cleaned_rn and cleaned_rn.lower() != primary_title.lower():
                    aliases.add(cleaned_rn)

        has_cover = bool(psp_map.get(canon_id))
        clean_aliases = sorted([a for a in aliases if a.lower() != primary_title.lower()])

        games.append({
            "id": canon_id,
            "title": primary_title or canon_id,
            "aliases": clean_aliases,
            "platform": "psp",
            "category": "PSP",
            "hasCover": has_cover
        })

    # -------------------------------------------------------------
    # 2. PSX Platform (Category: PS1)
    # -------------------------------------------------------------
    psx_by_serial: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    for key, item in psx_data.items():
        if not isinstance(item, dict):
            continue
        serial = item.get("serial")
        if not serial:
            # Safely skip entries without serial (Action Replay / promos without serial)
            continue
        canon_id = normalize_game_id(serial, "psx")
        if not canon_id:
            continue
        psx_by_serial[canon_id].append((key, item))

    for canon_id in sorted(psx_by_serial.keys()):
        if canon_id in seen_ids:
            raise ValueError(f"Cross-platform or unexpected duplicate Game ID: {canon_id}")
        seen_ids.add(canon_id)

        entries = psx_by_serial[canon_id]
        primary_title = ""
        aliases: Set[str] = set()

        for key, e in entries:
            t = e.get("title")
            if isinstance(t, str) and t.strip():
                ct = clean_noise_tokens(t)
                if ct:
                    if not primary_title:
                        primary_title = ct
                    elif ct.lower() != primary_title.lower():
                        aliases.add(ct)

            rn = e.get("release_name")
            if isinstance(rn, str) and rn.strip():
                crn = clean_noise_tokens(rn)
                if not primary_title:
                    primary_title = strip_parens(crn) or crn
                elif crn.lower() != primary_title.lower():
                    aliases.add(crn)

                srn = strip_parens(crn)
                if srn and srn.lower() != primary_title.lower():
                    aliases.add(srn)

        has_cover = bool(psx_map.get(canon_id))
        clean_aliases = sorted([a for a in aliases if a.lower() != primary_title.lower()])

        games.append({
            "id": canon_id,
            "title": primary_title or canon_id,
            "aliases": clean_aliases,
            "platform": "psx",
            "category": "PS1",
            "hasCover": has_cover
        })

    # -------------------------------------------------------------
    # 3. Homebrew Platform (Category: Homebrew)
    # -------------------------------------------------------------
    for key in sorted(hb_data.keys()):
        item = hb_data[key]
        if not isinstance(item, dict):
            continue
        serial = item.get("serial") or key
        canon_id = normalize_game_id(serial, "homebrew")
        if not canon_id:
            continue
        if canon_id in seen_ids:
            raise ValueError(f"Cross-platform or unexpected duplicate Game ID: {canon_id}")
        seen_ids.add(canon_id)

        title = clean_noise_tokens(item.get("title", ""))
        has_cover = bool(hb_map.get(key) or hb_map.get(canon_id))

        games.append({
            "id": canon_id,
            "title": title or canon_id,
            "aliases": [],
            "platform": "homebrew",
            "category": "Homebrew",
            "hasCover": has_cover
        })

    # Deterministic sort by platform, then canonical Game ID
    games.sort(key=lambda g: (g["platform"], g["id"]))

    return {
        "version": 1,
        "total_games": len(games),
        "games": games
    }


def serialize_search_index(data: Dict[str, Any], pretty: bool = False) -> str:
    """Serializes index data to JSON string deterministically."""
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


def generate_search_index(
    base_dir: Path = BASE_DIR,
    output_path: Path = SEARCH_INDEX_FILE,
    pretty: bool = False,
    check_only: bool = False
) -> Tuple[bool, str]:
    """
    Generates or verifies the search index.

    If check_only is True, compares current file content with generated output
    without making any filesystem modifications.

    Returns (success: bool, message: str).
    """
    try:
        data = build_search_index_data(base_dir=base_dir)
        serialized = serialize_search_index(data, pretty=pretty)
        serialized_bytes = serialized.encode("utf-8")

        if check_only:
            if not output_path.exists():
                return False, f"Search index missing: {output_path}"
            existing_bytes = output_path.read_bytes()
            if existing_bytes != serialized_bytes:
                return False, (
                    f"Search index at {output_path} is out of date. "
                    f"Expected {len(serialized_bytes)} bytes, found {len(existing_bytes)} bytes."
                )
            return True, f"Search index at {output_path} is up to date and verified ({data['total_games']} games)."

        # Atomic write
        temp_file = output_path.with_suffix(".tmp")
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file.write_bytes(serialized_bytes)
        temp_file.replace(output_path)

        return True, f"Successfully generated search index at {output_path} with {data['total_games']} games."
    except Exception as e:
        return False, f"Failed to generate search index: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate or verify deterministic search index for GameDiary."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify if search index is up to date without modifying files."
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Generate human-readable indented JSON instead of minified JSON."
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(SEARCH_INDEX_FILE),
        help=f"Target output path (default: {SEARCH_INDEX_FILE})"
    )

    args = parser.parse_args()
    out_path = Path(args.output).resolve()

    print("=== SYNCHRONIZING GAME SEARCH INDEX ===")
    success, message = generate_search_index(
        base_dir=BASE_DIR,
        output_path=out_path,
        pretty=args.pretty,
        check_only=args.check
    )

    if success:
        print(f"[OK] {message}")
        sys.exit(0)
    else:
        print(f"[ERROR] {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
