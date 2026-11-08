#!/usr/bin/env python3
"""
Unit tests for validate_pr.py.
Verifies dimension, aspect ratio, and binary integrity validation
across PSX, PSP, and Homebrew platforms.
"""

import unittest
import tempfile
import struct
import zlib
import shutil
import json
from pathlib import Path

from validate_pr import (
    validate_png_magic_bytes,
    get_png_dimensions,
    validate_png_dimensions_and_ratio,
    validate_contributed_images,
    PNG_MAGIC_BYTES,
)


def create_synthetic_png(width: int, height: int) -> bytes:
    """Generates a valid binary PNG with specified dimensions in IHDR chunk."""
    header = PNG_MAGIC_BYTES
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF)
    ihdr_chunk = struct.pack('>I', 13) + b'IHDR' + ihdr_data + ihdr_crc
    return header + ihdr_chunk


class TestValidatePR(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_val_pr_")
        self.base = Path(self.test_dir)

        self.psx_dir = self.base / "psx" / "Named_Titles"
        self.psx_dir.mkdir(parents=True)

        self.psp_dir = self.base / "psp" / "Named_Titles"
        self.psp_dir.mkdir(parents=True)

        self.hb_dir = self.base / "homebrew" / "Named_Titles"
        self.hb_entries = self.base / "homebrew" / "entries"
        self.hb_dir.mkdir(parents=True)
        self.hb_entries.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_psx_valid_square_dimensions(self):
        img_path = self.psx_dir / "Valid PSX Game.png"
        img_path.write_bytes(create_synthetic_png(272, 272))

        valid, msg = validate_png_dimensions_and_ratio(img_path)
        self.assertTrue(valid, f"Expected 272x272 to pass: {msg}")

        # High-res square also passes
        img_path_hi = self.psx_dir / "Valid PSX HiRes.png"
        img_path_hi.write_bytes(create_synthetic_png(600, 600))
        valid_hi, msg_hi = validate_png_dimensions_and_ratio(img_path_hi)
        self.assertTrue(valid_hi, f"Expected 600x600 to pass: {msg_hi}")

    def test_psx_rejects_non_square_aspect_ratio(self):
        # 16:9 ratio in PSX directory
        img_wide = self.psx_dir / "Wide PSX.png"
        img_wide.write_bytes(create_synthetic_png(480, 272))
        valid, msg = validate_png_dimensions_and_ratio(img_wide)
        self.assertFalse(valid)
        self.assertIn("must have a 1:1 aspect ratio", msg)

        # 2:3 vertical ratio in PSX directory
        img_tall = self.psx_dir / "Tall PSX.png"
        img_tall.write_bytes(create_synthetic_png(200, 300))
        valid, msg = validate_png_dimensions_and_ratio(img_tall)
        self.assertFalse(valid)
        self.assertIn("must have a 1:1 aspect ratio", msg)

    def test_psx_rejects_undersized_image(self):
        img_tiny = self.psx_dir / "Tiny PSX.png"
        img_tiny.write_bytes(create_synthetic_png(50, 50))
        valid, msg = validate_png_dimensions_and_ratio(img_tiny)
        self.assertFalse(valid)
        self.assertIn("too small", msg)

    def test_psp_valid_horizontal_aspect_ratio(self):
        # Standard PSP title banner (480x272)
        img_path = self.psp_dir / "PSP Game 480.png"
        img_path.write_bytes(create_synthetic_png(480, 272))
        valid, msg = validate_png_dimensions_and_ratio(img_path)
        self.assertTrue(valid, f"Expected 480x272 to pass: {msg}")

        # Standard compact 144x80
        img_path_sm = self.psp_dir / "PSP Game 144.png"
        img_path_sm.write_bytes(create_synthetic_png(144, 80))
        valid_sm, msg_sm = validate_png_dimensions_and_ratio(img_path_sm)
        self.assertTrue(valid_sm, f"Expected 144x80 to pass: {msg_sm}")

    def test_psp_rejects_square_or_vertical_aspect_ratio(self):
        # 1:1 square in PSP directory
        img_sq = self.psp_dir / "Square PSP.png"
        img_sq.write_bytes(create_synthetic_png(272, 272))
        valid, msg = validate_png_dimensions_and_ratio(img_sq)
        self.assertFalse(valid)
        self.assertIn("approximately a 1.8:1 aspect ratio", msg)

    def test_homebrew_valid_horizontal_aspect_ratio(self):
        img_hb = self.hb_dir / "Cool Homebrew.png"
        img_hb.write_bytes(create_synthetic_png(144, 80))
        valid, msg = validate_png_dimensions_and_ratio(img_hb)
        self.assertTrue(valid, f"Expected 144x80 to pass: {msg}")

    def test_homebrew_rejects_invalid_aspect_ratio(self):
        img_hb_sq = self.hb_dir / "Square Homebrew.png"
        img_hb_sq.write_bytes(create_synthetic_png(272, 272))
        valid, msg = validate_png_dimensions_and_ratio(img_hb_sq)
        self.assertFalse(valid)
        self.assertIn("approximately a 1.8:1 aspect ratio", msg)

    def test_corrupt_png_rejected(self):
        img_corrupt = self.psx_dir / "Corrupt.png"
        img_corrupt.write_bytes(b'\x89PNG\r\n\x1a\nNotAValidChunk')
        valid, msg = validate_png_dimensions_and_ratio(img_corrupt)
        self.assertFalse(valid)

    def test_fake_png_magic_bytes_rejected(self):
        img_fake = self.psx_dir / "Fake.png"
        img_fake.write_bytes(b'GIF89aSomeFakeData')
        valid, msg = validate_png_magic_bytes(img_fake)
        self.assertFalse(valid)
        self.assertIn("not a valid binary PNG", msg)


class TestValidationSideEffectFree(unittest.TestCase):
    """
    Regression test ensuring that running PR validation (including consolidation dry-run)
    does NOT alter, rewrite, reformat, or modify bytes of any tracked checkout files,
    especially homebrew/game_id_to_image.json.
    """

    def test_validation_does_not_modify_checkout_files(self):
        base_dir = Path(__file__).resolve().parent

        files_to_track = [
            base_dir / "homebrew" / "game_id_to_image.json",
            base_dir / "homebrew" / "HOMEBREW.data.json",
            base_dir / "full_game_map.json",
            base_dir / "psp" / "game_id_to_image.json",
            base_dir / "psx" / "game_id_to_image.json",
            base_dir / "by-id" / "path-layout.json",
            base_dir / "by-id" / ".manifest.json",
        ]

        # 1. Record byte contents before validation
        before_bytes = {}
        for f in files_to_track:
            if f.exists():
                before_bytes[f] = f.read_bytes()

        self.assertIn(
            base_dir / "homebrew" / "game_id_to_image.json",
            before_bytes,
            "homebrew/game_id_to_image.json must exist and be tracked"
        )

        # 2. Execute validation flow (Homebrew validation + dry-run consolidation)
        from validate_pr import dry_run_catalog_consolidation, validate_homebrew_entries
        hb_errors = validate_homebrew_entries()
        self.assertEqual(len(hb_errors), 0, f"Expected 0 Homebrew entry errors: {hb_errors}")

        map_errors = dry_run_catalog_consolidation()
        self.assertEqual(len(map_errors), 0, f"Expected 0 dry-run errors: {map_errors}")

        # 3. Compare bytes after execution
        modified = []
        for f, original_data in before_bytes.items():
            current_data = f.read_bytes()
            if current_data != original_data:
                modified.append((str(f.relative_to(base_dir)), len(original_data), len(current_data)))

        # 4. Fail if any original file was modified
        self.assertEqual(
            len(modified), 0,
            f"Validation modified tracked file(s) on disk: {modified}"
        )


if __name__ == '__main__':
    unittest.main()
