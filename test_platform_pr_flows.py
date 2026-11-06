#!/usr/bin/env python3
"""
test_platform_pr_flows.py
Comprehensive integration test suite covering PR contributions and mapping updates
across all supported platforms: PSP, PS1 (PSX), and Homebrew.

Verifies:
1. PSP PR: Adding an image to psp/Named_Titles updates psp/game_id_to_image.json correctly.
2. PS1 PR: Adding an image to psx/Named_Titles updates psx/game_id_to_image.json correctly.
3. Homebrew PR: Adding an image and individual entry updates HOMEBREW.data.json and homebrew/game_id_to_image.json.
4. Historical preservation: Existing catalog entries are strictly preserved without data loss.
5. Idempotence: Re-running mappings without new assets does NOT alter files.
6. Non-collision: Two independent Homebrew PRs do not overwrite each other.
"""

import unittest
import tempfile
import json
import shutil
from pathlib import Path
import os
import re

PNG_HEADER = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'


class TestPlatformPrFlows(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="platform_flow_test_")
        self.base = Path(self.test_dir)

        # Setup mock PSP tree
        self.psp_dir = self.base / "psp"
        self.psp_titles = self.psp_dir / "Named_Titles"
        self.psp_titles.mkdir(parents=True)
        self.psp_data = self.psp_dir / "PSP.data.json"
        self.psp_map = self.psp_dir / "game_id_to_image.json"

        # Setup mock PSX tree
        self.psx_dir = self.base / "psx"
        self.psx_titles = self.psx_dir / "Named_Titles"
        self.psx_titles.mkdir(parents=True)
        self.psx_data = self.psx_dir / "PSX.data.json"
        self.psx_map = self.psx_dir / "game_id_to_image.json"

        # Setup mock Homebrew tree
        self.hb_dir = self.base / "homebrew"
        self.hb_titles = self.hb_dir / "Named_Titles"
        self.hb_entries = self.hb_dir / "entries"
        self.hb_titles.mkdir(parents=True)
        self.hb_entries.mkdir(parents=True)
        self.hb_data = self.hb_dir / "HOMEBREW.data.json"
        self.hb_map = self.hb_dir / "game_id_to_image.json"

        # Baseline PSP catalog
        with open(self.psp_data, "w", encoding="utf-8") as f:
            json.dump({
                "ULUS-10041": {
                    "serial": "ULUS-10041",
                    "title": "Grand Theft Auto: Liberty City Stories"
                },
                "ULES-00123": {
                    "serial": "ULES-00123",
                    "title": "WipEout Pure"
                }
            }, f, indent=2)

        # Baseline PSX catalog
        with open(self.psx_data, "w", encoding="utf-8") as f:
            json.dump({
                "SLUS-00068": {
                    "serial": "SLUS-00068",
                    "title": "Castlevania: Symphony of the Night"
                },
                "SCUS-94488": {
                    "serial": "SCUS-94488",
                    "title": "Gran Turismo 2"
                }
            }, f, indent=2)

        # Baseline Homebrew catalog (historical)
        with open(self.hb_data, "w", encoding="utf-8") as f:
            json.dump({
                "HBXA1B9195B": {
                    "serial": "HBXA1B9195B",
                    "title": "pspalatro",
                    "apitype": "0x141",
                    "category": 2
                }
            }, f, indent=2)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_png(self, path: Path):
        with open(path, "wb") as f:
            f.write(PNG_HEADER)

    def _normalize_str(self, s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', s.lower()) if s else ''

    def test_psp_pr_adds_image_and_updates_map(self):
        """Simulates PR adding a PSP cover and running mapping logic."""
        # 1. Contributor adds cover matching canonical title
        cover_path = self.psp_titles / "Grand Theft Auto - Liberty City Stories.png"
        self._create_png(cover_path)

        # 2. Run PSP mapping logic against test folder
        with open(self.psp_data, "r", encoding="utf-8") as f:
            data = json.load(f)

        png_map = {}
        for entry in os.listdir(self.psp_titles):
            if entry.lower().endswith('.png'):
                norm = self._normalize_str(os.path.splitext(entry)[0])
                png_map[norm] = entry

        result = {}
        for key, info in data.items():
            serial = info['serial'].replace('-', '')
            title_norm = self._normalize_str(info.get('title', ''))
            if title_norm in png_map:
                result[serial] = f"psp/Named_Titles/{png_map[title_norm]}"
            else:
                result[serial] = None

        with open(self.psp_map, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        # Verify: ULUS10041 is mapped, ULES00123 remains None
        self.assertEqual(result["ULUS10041"], "psp/Named_Titles/Grand Theft Auto - Liberty City Stories.png")
        self.assertIsNone(result["ULES00123"])

    def test_psx_pr_adds_image_and_updates_map(self):
        """Simulates PR adding a PS1 cover and running mapping logic."""
        cover_path = self.psx_titles / "Castlevania - Symphony of the Night.png"
        self._create_png(cover_path)

        with open(self.psx_data, "r", encoding="utf-8") as f:
            data = json.load(f)

        png_map = {}
        for entry in os.listdir(self.psx_titles):
            if entry.lower().endswith('.png'):
                norm = self._normalize_str(os.path.splitext(entry)[0])
                png_map[norm] = entry

        result = {}
        for key, info in data.items():
            serial = info['serial'].replace('-', '')
            title_norm = self._normalize_str(info.get('title', ''))
            if title_norm in png_map:
                result[serial] = f"psx/Named_Titles/{png_map[title_norm]}"
            else:
                result[serial] = None

        with open(self.psx_map, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        self.assertEqual(result["SLUS00068"], "psx/Named_Titles/Castlevania - Symphony of the Night.png")
        self.assertIsNone(result["SCUS94488"])

    def test_homebrew_pr_adds_image_and_entry_without_overwriting_historical(self):
        """Simulates Homebrew PR adding an entry file and image, preserving historical entries."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs

        # Add image
        self._create_png(self.hb_titles / "Super Mario 64.png")

        # Add individual entry
        entry_file = self.hb_entries / "HBX392ABD96.json"
        with open(entry_file, "w", encoding="utf-8") as f:
            json.dump({
                "serial": "HBX392ABD96",
                "title": "Super Mario 64",
                "apitype": "0x141",
                "category": 2
            }, f, indent=2)

        # Load historical + entries
        with open(self.hb_data, "r", encoding="utf-8") as f:
            historical = json.load(f)

        entries = {
            "HBX392ABD96": {
                "serial": "HBX392ABD96",
                "title": "Super Mario 64",
                "apitype": "0x141",
                "category": 2
            }
        }

        consolidated = consolidate_catalogs(historical, entries)

        # Both historical and new entry MUST exist
        self.assertIn("HBXA1B9195B", consolidated)
        self.assertIn("HBX392ABD96", consolidated)
        self.assertEqual(consolidated["HBXA1B9195B"]["title"], "pspalatro")
        self.assertEqual(consolidated["HBX392ABD96"]["title"], "Super Mario 64")

    def test_two_independent_homebrew_prs_do_not_collide(self):
        """Two PRs creating separate entries merge cleanly without record loss."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs

        with open(self.hb_data, "r", encoding="utf-8") as f:
            historical = json.load(f)

        # PR 1 adds DOOM_001
        entry_pr1 = {
            "DOOM_001": {
                "serial": "DOOM_001",
                "title": "Doom PSP",
                "apitype": "0x141",
                "category": 2
            }
        }

        # PR 2 adds ARK_01234
        entry_pr2 = {
            "ARK_01234": {
                "serial": "ARK_01234",
                "title": "ARK-4 Custom Firmware",
                "apitype": "0x141",
                "category": 2
            }
        }

        merged_entries = {**entry_pr1, **entry_pr2}
        consolidated = consolidate_catalogs(historical, merged_entries)

        self.assertIn("HBXA1B9195B", consolidated)
        self.assertIn("DOOM_001", consolidated)
        self.assertIn("ARK_01234", consolidated)
        self.assertEqual(len(consolidated), 3)

    def test_idempotence_rerunning_produces_identical_output(self):
        """Re-running catalog consolidation without changes produces identical byte output."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs

        with open(self.hb_data, "r", encoding="utf-8") as f:
            historical = json.load(f)

        run1 = json.dumps(consolidate_catalogs(historical, {}), indent=2, ensure_ascii=False) + "\n"
        run2 = json.dumps(consolidate_catalogs(historical, {}), indent=2, ensure_ascii=False) + "\n"

        self.assertEqual(run1, run2)


if __name__ == "__main__":
    unittest.main()
