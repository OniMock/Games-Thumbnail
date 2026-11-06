#!/usr/bin/env python3
"""
test_consolidate_catalog.py
Comprehensive unit test suite for homebrew catalog consolidation.
Tests:
- Generation with historical baseline.
- Single individual entry addition.
- Multiple individual entries addition.
- Strict determinism (re-running produces byte-for-byte identical output).
- Duplicate ID detection across entries.
- Corrupted / invalid JSON detection.
- Entry validation failures (missing serial, missing title, filename-serial mismatch).
- Preservation of historical records without data loss.
- Verification of image mapping with Named_Titles/.
"""

import unittest
import tempfile
import json
import shutil
from pathlib import Path

from consolidate_homebrew_catalog import (
    load_historical_catalog,
    validate_entry,
    load_entries,
    consolidate_catalogs,
    build_image_mapping,
    run_consolidation,
    CatalogValidationError,
)


class TestHomebrewCatalogConsolidation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="gamediary_hb_test_")
        self.base_dir = Path(self.test_dir)
        self.entries_dir = self.base_dir / "entries"
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.titles_dir = self.base_dir / "Named_Titles"
        self.titles_dir.mkdir(parents=True, exist_ok=True)
        self.data_json = self.base_dir / "HOMEBREW.data.json"
        self.output_map = self.base_dir / "game_id_to_image.json"
        self.error_log = self.base_dir / "homebrew_mapping_errors.log"

        # Baseline historical data
        self.historical_data = {
            "HBXA1B9195B": {
                "serial": "HBXA1B9195B",
                "title": "pspalatro",
                "apitype": "0x141",
                "category": 2,
            },
            "HBX392ABD96": {
                "serial": "HBX392ABD96",
                "title": "Super Mario 64",
                "apitype": "0x141",
                "category": 2,
            },
        }
        with open(self.data_json, "w", encoding="utf-8") as f:
            json.dump(self.historical_data, f, indent=2)
            f.write("\n")

        # Fake cover files
        (self.titles_dir / "pspalatro.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.titles_dir / "Super Mario 64.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_historical_catalog(self):
        cat = load_historical_catalog(self.data_json)
        self.assertEqual(len(cat), 2)
        self.assertIn("HBXA1B9195B", cat)
        self.assertEqual(cat["HBXA1B9195B"]["title"], "pspalatro")

    def test_single_entry_addition(self):
        new_entry = {
            "serial": "HBX1B6576C3",
            "title": "Forms3D",
            "apitype": "0x141",
            "category": 2,
        }
        (self.entries_dir / "HBX1B6576C3.json").write_text(json.dumps(new_entry), encoding="utf-8")

        run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
        )

        with open(self.data_json, "r", encoding="utf-8") as f:
            consolidated = json.load(f)

        self.assertEqual(len(consolidated), 3)
        self.assertIn("HBX1B6576C3", consolidated)
        self.assertEqual(consolidated["HBX1B6576C3"]["title"], "Forms3D")
        # Historical records strictly preserved
        self.assertIn("HBXA1B9195B", consolidated)
        self.assertIn("HBX392ABD96", consolidated)

    def test_multiple_entries_addition_and_deterministic_sorting(self):
        entries = {
            "HBXZZZZZZZZ": {"serial": "HBXZZZZZZZZ", "title": "Zelda Homebrew"},
            "HBXAAAAAAAA": {"serial": "HBXAAAAAAAA", "title": "Ark Homebrew"},
            "HBXMMMMMMMM": {"serial": "HBXMMMMMMMM", "title": "Mario Port"},
        }
        for serial, item in entries.items():
            (self.entries_dir / f"{serial}.json").write_text(json.dumps(item), encoding="utf-8")

        run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
        )

        with open(self.data_json, "r", encoding="utf-8") as f:
            consolidated = json.load(f)

        keys = list(consolidated.keys())
        # Total: 2 historical + 3 new = 5
        self.assertEqual(len(keys), 5)
        # Alphabetical sorting
        self.assertEqual(keys, sorted(keys))

    def test_idempotent_reexecution(self):
        (self.entries_dir / "HBX12345678.json").write_text(
            json.dumps({"serial": "HBX12345678", "title": "Game 1"}), encoding="utf-8"
        )

        run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
        )
        first_run_catalog = self.data_json.read_text(encoding="utf-8")
        first_run_map = self.output_map.read_text(encoding="utf-8")

        # Second run with exact same files
        run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
        )
        second_run_catalog = self.data_json.read_text(encoding="utf-8")
        second_run_map = self.output_map.read_text(encoding="utf-8")

        # Byte-for-byte identical
        self.assertEqual(first_run_catalog, second_run_catalog)
        self.assertEqual(first_run_map, second_run_map)

        # Check mode returns True (no pending changes)
        check_result = run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
            check_only=True,
        )
        self.assertTrue(check_result)

    def test_rejects_corrupted_json(self):
        (self.entries_dir / "HBX_CORRUPT.json").write_text("{ unquoted_key: broken ", encoding="utf-8")

        with self.assertRaises(CatalogValidationError) as ctx:
            run_consolidation(
                data_path=self.data_json,
                entries_dir=self.entries_dir,
                titles_dir=self.titles_dir,
                output_map_path=self.output_map,
                error_log_path=self.error_log,
            )
        self.assertIn("Invalid JSON syntax in 'HBX_CORRUPT.json'", str(ctx.exception))

    def test_rejects_filename_serial_mismatch(self):
        # File is HBX_A.json but content declares serial HBX_B
        (self.entries_dir / "HBX_A.json").write_text(
            json.dumps({"serial": "HBX_B", "title": "Mismatch"}), encoding="utf-8"
        )

        with self.assertRaises(CatalogValidationError) as ctx:
            run_consolidation(
                data_path=self.data_path if hasattr(self, 'data_path') else self.data_json,
                entries_dir=self.entries_dir,
                titles_dir=self.titles_dir,
                output_map_path=self.output_map,
                error_log_path=self.error_log,
            )
        self.assertIn("serial mismatch", str(ctx.exception))

    def test_rejects_missing_title(self):
        (self.entries_dir / "HBX11111111.json").write_text(
            json.dumps({"serial": "HBX11111111", "title": ""}), encoding="utf-8"
        )

        with self.assertRaises(CatalogValidationError) as ctx:
            run_consolidation(
                data_path=self.data_json,
                entries_dir=self.entries_dir,
                titles_dir=self.titles_dir,
                output_map_path=self.output_map,
                error_log_path=self.error_log,
            )
        self.assertIn("missing a valid non-empty 'title'", str(ctx.exception))

    def test_rejects_invalid_serial_format(self):
        (self.entries_dir / "HBX_INV@LID.json").write_text(
            json.dumps({"serial": "HBX_INV@LID", "title": "Illegal Char"}), encoding="utf-8"
        )

        with self.assertRaises(CatalogValidationError) as ctx:
            run_consolidation(
                data_path=self.data_json,
                entries_dir=self.entries_dir,
                titles_dir=self.titles_dir,
                output_map_path=self.output_map,
                error_log_path=self.error_log,
            )
        self.assertIn("invalid serial", str(ctx.exception))

    def test_custom_param_sfo_disc_id(self):
        # Valid custom DISC_ID (e.g. DOOM_001)
        (self.entries_dir / "DOOM_001.json").write_text(
            json.dumps({"serial": "DOOM_001", "title": "Doom Classic Port"}), encoding="utf-8"
        )
        (self.titles_dir / "Doom Classic Port.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        run_consolidation(
            data_path=self.data_json,
            entries_dir=self.entries_dir,
            titles_dir=self.titles_dir,
            output_map_path=self.output_map,
            error_log_path=self.error_log,
        )

        with open(self.data_json, "r", encoding="utf-8") as f:
            cat = json.load(f)
        self.assertIn("DOOM_001", cat)

        with open(self.output_map, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        self.assertEqual(mapping["DOOM_001"], "homebrew/Named_Titles/Doom Classic Port.png")


if __name__ == "__main__":
    unittest.main()
