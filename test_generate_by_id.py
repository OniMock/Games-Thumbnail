#!/usr/bin/env python3
"""
Unit and integration tests for generate_by_id_aliases.py.
Verifies:
1. Normalization rules across PSP, PSX, and Homebrew.
2. Path resolution and prefix partitioning rules according to path-layout.json.
3. Fail-closed behavior on missing files, path traversals, and destination collisions.
4. Idempotence, zero modifications on rerun, and timestamp preservation.
5. Content integrity via byte-for-byte SHA-256 validation.
6. PNG magic bytes verification.
7. Safe orphan deletion via .manifest.json without touching unmanaged files.
8. Directory distribution limits.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path

# Import functions from generate_by_id_aliases
from generate_by_id_aliases import (
    compute_sha256,
    normalize_psp_id,
    normalize_psx_id,
    normalize_homebrew_id,
    normalize_game_id,
    get_homebrew_family,
    resolve_alias_rel_path,
    load_and_validate_sources,
    load_manifest,
    write_atomic_file,
    sync_aliases,
    AliasValidationError,
    PSP_PREFIX_LENGTH,
    PSX_PREFIX_LENGTH,
)

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"


def make_dummy_png(content: bytes = b"test_payload_12345") -> bytes:
    """Creates a valid dummy PNG with magic bytes for testing."""
    return PNG_MAGIC_BYTES + content


class TestNormalizationAndPaths(unittest.TestCase):
    """Tests ID normalization and destination path calculation."""

    def test_psp_normalization(self):
        # Strips hyphens, strips whitespace, uppercases
        self.assertEqual(normalize_psp_id("  ulus-10293  "), "ULUS10293")
        self.assertEqual(normalize_psp_id("UCES-00001"), "UCES00001")
        self.assertEqual(normalize_psp_id("NPJH-50001"), "NPJH50001")

    def test_psx_normalization(self):
        # Strips hyphens, strips whitespace, uppercases
        self.assertEqual(normalize_psx_id("  slus-00068  "), "SLUS00068")
        self.assertEqual(normalize_psx_id("SCES-00001"), "SCES00001")
        self.assertEqual(normalize_psx_id("SLPS-00004"), "SLPS00004")

    def test_homebrew_normalization(self):
        # Preserves hyphens and underscores, uppercases, strips surrounding whitespace
        self.assertEqual(normalize_homebrew_id("  hbx-01a2b3c4  "), "HBX-01A2B3C4")
        self.assertEqual(normalize_homebrew_id("my_cool-game"), "MY_COOL-GAME")
        self.assertEqual(normalize_homebrew_id("  ark_menu_v1  "), "ARK_MENU_V1")

    def test_homebrew_family_extraction(self):
        # HBX hash family
        self.assertEqual(get_homebrew_family("HBX01A2B3C4"), "hbx")
        # Alphabetic family before digits or punctuation
        self.assertEqual(get_homebrew_family("ARK_4"), "ark")
        self.assertEqual(get_homebrew_family("MY_COOL-GAME"), "my")
        self.assertEqual(get_homebrew_family("DOOM-PSP"), "doom")
        # Leading digits or symbols fallback to 'misc'
        self.assertEqual(get_homebrew_family("123_GAME"), "misc")
        self.assertEqual(get_homebrew_family("_CUSTOM"), "misc")

    def test_path_resolution(self):
        # PSP: 4-char prefix, lowercase
        self.assertEqual(
            resolve_alias_rel_path("psp", "ULUS10293"),
            "psp/ulus/ulus10293.png"
        )
        # PSX: 6-char prefix, lowercase
        self.assertEqual(
            resolve_alias_rel_path("psx", "SLUS00068"),
            "psx/slus00/slus00068.png"
        )
        self.assertEqual(
            resolve_alias_rel_path("psx", "SLPS00004"),
            "psx/slps00/slps00004.png"
        )
        # Homebrew: family folder, lowercase filename preserving separators
        self.assertEqual(
            resolve_alias_rel_path("homebrew", "ARK_4"),
            "homebrew/ark/ark_4.png"
        )
        self.assertEqual(
            resolve_alias_rel_path("homebrew", "MY_COOL-GAME"),
            "homebrew/my/my_cool-game.png"
        )
        self.assertEqual(
            resolve_alias_rel_path("homebrew", "123_TEST"),
            "homebrew/misc/123_test.png"
        )


class TestFailClosedValidation(unittest.TestCase):
    """Tests pre-flight integrity checks and fail-closed security guarantees."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_alias_val_")
        self.base = Path(self.test_dir)

        # Setup directory structures
        self.psp_named = self.base / "psp" / "Named_Titles"
        self.psp_named.mkdir(parents=True)
        self.psx_named = self.base / "psx" / "Named_Titles"
        self.psx_named.mkdir(parents=True)
        self.hb_named = self.base / "homebrew" / "Named_Titles"
        self.hb_named.mkdir(parents=True)

        self.maps = {
            "psp": self.base / "psp" / "game_id_to_image.json",
            "psx": self.base / "psx" / "game_id_to_image.json",
            "homebrew": self.base / "homebrew" / "game_id_to_image.json"
        }

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_missing_source_image_fails_closed(self):
        # Register a game whose image doesn't exist on disk
        self.maps["psp"].write_text(json.dumps({"ULUS-10001": "psp/Named_Titles/nonexistent.png"}), encoding="utf-8")
        self.maps["psx"].write_text(json.dumps({}), encoding="utf-8")
        self.maps["homebrew"].write_text(json.dumps({}), encoding="utf-8")

        with self.assertRaises(AliasValidationError) as ctx:
            load_and_validate_sources(self.maps, self.base)
        self.assertIn("Missing source image file", str(ctx.exception))

    def test_destination_collision_fails_closed(self):
        # Create a valid test image
        test_img = self.psp_named / "Test.png"
        test_img.write_bytes(make_dummy_png())

        # Two different raw IDs normalizing to the exact same alias
        self.maps["psp"].write_text(json.dumps({
            "ULUS-10001": "psp/Named_Titles/Test.png",
            "ULUS10001": "psp/Named_Titles/Test.png"
        }), encoding="utf-8")
        self.maps["psx"].write_text(json.dumps({}), encoding="utf-8")
        self.maps["homebrew"].write_text(json.dumps({}), encoding="utf-8")

        # Note: In our current logic, destination collisions between different raw IDs trigger an error
        # Verify that collision detection catches this
        with self.assertRaises(AliasValidationError) as ctx:
            load_and_validate_sources(self.maps, self.base)
        self.assertIn("Collision detected", str(ctx.exception))

    def test_path_traversal_fails_closed(self):
        # Attempt to escape Named_Titles via ../
        outside_file = self.base / "secret.png"
        outside_file.write_bytes(make_dummy_png())

        self.maps["psp"].write_text(json.dumps({
            "ULUS-10001": "psp/Named_Titles/../../secret.png"
        }), encoding="utf-8")
        self.maps["psx"].write_text(json.dumps({}), encoding="utf-8")
        self.maps["homebrew"].write_text(json.dumps({}), encoding="utf-8")

        with self.assertRaises(AliasValidationError) as ctx:
            load_and_validate_sources(self.maps, self.base)
        self.assertTrue(
            "Path traversal" in str(ctx.exception) or "outside" in str(ctx.exception),
            f"Expected traversal error, got: {ctx.exception}"
        )

    def test_unmapped_games_gracefully_skipped(self):
        # Unmapped games with None or empty string must not raise error and not generate aliases
        self.maps["psp"].write_text(json.dumps({
            "ULUS-10001": None,
            "ULUS-10002": ""
        }), encoding="utf-8")
        self.maps["psx"].write_text(json.dumps({}), encoding="utf-8")
        self.maps["homebrew"].write_text(json.dumps({}), encoding="utf-8")

        expected = load_and_validate_sources(self.maps, self.base)
        self.assertEqual(len(expected), 0)


class TestSyncAndIdempotence(unittest.TestCase):
    """Tests file generation, byte-for-byte fidelity, idempotence, and orphan cleanup."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_alias_sync_")
        self.base = Path(self.test_dir)
        self.by_id_dir = self.base / "by-id"
        self.manifest_path = self.by_id_dir / ".manifest.json"

        # Platform folders
        (self.base / "psp" / "Named_Titles").mkdir(parents=True)
        (self.base / "psx" / "Named_Titles").mkdir(parents=True)
        (self.base / "homebrew" / "Named_Titles").mkdir(parents=True)

        self.maps = {
            "psp": self.base / "psp" / "game_id_to_image.json",
            "psx": self.base / "psx" / "game_id_to_image.json",
            "homebrew": self.base / "homebrew" / "game_id_to_image.json"
        }

        # Create 2 source images
        self.src_psp = self.base / "psp" / "Named_Titles" / "Crisis Core.png"
        self.psp_bytes = make_dummy_png(b"crisis_core_payload_data_psp")
        self.src_psp.write_bytes(self.psp_bytes)

        self.src_psx = self.base / "psx" / "Named_Titles" / "Castlevania.png"
        self.psx_bytes = make_dummy_png(b"castlevania_sotn_payload_data_psx")
        self.src_psx.write_bytes(self.psx_bytes)

        # Setup maps
        self.maps["psp"].write_text(json.dumps({"ULUS-10336": "psp/Named_Titles/Crisis Core.png"}))
        self.maps["psx"].write_text(json.dumps({"SLUS-00067": "psx/Named_Titles/Castlevania.png"}))
        self.maps["homebrew"].write_text(json.dumps({}))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_first_run_generates_valid_aliases(self):
        stats = sync_aliases(
            check_mode=False,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )
        self.assertEqual(stats["created"], 2)
        self.assertEqual(stats["total_expected"], 2)
        self.assertEqual(stats["out_of_sync"], 2)

        # Verify physical files
        alias_psp = self.by_id_dir / "psp" / "ulus" / "ulus10336.png"
        alias_psx = self.by_id_dir / "psx" / "slus00" / "slus00067.png"

        self.assertTrue(alias_psp.exists())
        self.assertTrue(alias_psx.exists())

        # Verify PNG magic bytes
        self.assertTrue(alias_psp.read_bytes().startswith(PNG_MAGIC_BYTES))
        self.assertTrue(alias_psx.read_bytes().startswith(PNG_MAGIC_BYTES))

        # Verify byte-for-byte SHA-256 match
        self.assertEqual(compute_sha256(alias_psp), compute_sha256(self.src_psp))
        self.assertEqual(compute_sha256(alias_psx), compute_sha256(self.src_psx))

        # Verify manifest was written
        self.assertTrue(self.manifest_path.exists())
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertIn("psp/ulus/ulus10336.png", manifest["managed_aliases"])
        self.assertIn("psx/slus00/slus00067.png", manifest["managed_aliases"])

    def test_idempotence_and_timestamp_preservation(self):
        # 1. Initial generation
        sync_aliases(
            check_mode=False,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )

        alias_psp = self.by_id_dir / "psp" / "ulus" / "ulus10336.png"
        alias_psx = self.by_id_dir / "psx" / "slus00" / "slus00067.png"

        # Record initial timestamps
        mtime_psp_1 = alias_psp.stat().st_mtime_ns
        mtime_psx_1 = alias_psx.stat().st_mtime_ns

        # Small sleep to ensure clock ticks
        time.sleep(0.05)

        # 2. Check mode: should report 0 out of sync
        check_stats = sync_aliases(
            check_mode=True,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )
        self.assertEqual(check_stats["out_of_sync"], 0)
        self.assertEqual(check_stats["kept"], 2)

        # 3. Second run in write mode: should keep 2, create 0, update 0
        stats2 = sync_aliases(
            check_mode=False,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )
        self.assertEqual(stats2["kept"], 2)
        self.assertEqual(stats2["created"], 0)
        self.assertEqual(stats2["updated"], 0)
        self.assertEqual(stats2["out_of_sync"], 0)

        # Verify timestamps are 100% UNTOUCHED
        self.assertEqual(alias_psp.stat().st_mtime_ns, mtime_psp_1)
        self.assertEqual(alias_psx.stat().st_mtime_ns, mtime_psx_1)

    def test_orphan_cleanup_managed_vs_unmanaged(self):
        # 1. Generate aliases
        sync_aliases(
            check_mode=False,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )

        # 2. Introduce an UNMANAGED file into by-id/psp/ulus/
        unmanaged_file = self.by_id_dir / "psp" / "ulus" / "custom_manual.png"
        unmanaged_file.write_bytes(make_dummy_png(b"manual_file"))

        # 3. Remove ULUS-10336 from catalog (making its alias obsolete)
        self.maps["psp"].write_text(json.dumps({}))

        # 4. Sync again
        stats = sync_aliases(
            check_mode=False,
            base_dir=self.base,
            by_id_dir=self.by_id_dir,
            platform_maps=self.maps,
            manifest_path=self.manifest_path
        )

        # Managed obsolete alias should be DELETED
        alias_psp = self.by_id_dir / "psp" / "ulus" / "ulus10336.png"
        self.assertFalse(alias_psp.exists(), "Obsolete managed alias should have been deleted")
        self.assertEqual(stats["deleted"], 1)

        # Unmanaged file MUST BE PRESERVED
        self.assertTrue(unmanaged_file.exists(), "Unmanaged file must NOT be deleted")
        self.assertEqual(stats["unmanaged_skipped"], 1)


class TestPathLayoutSpecification(unittest.TestCase):
    """Validates that path-layout.json exists and adheres to the architectural rules."""

    def test_path_layout_file(self):
        base_dir = Path(__file__).resolve().parent
        layout_path = base_dir / "by-id" / "path-layout.json"
        self.assertTrue(layout_path.exists(), "path-layout.json must exist in by-id/")

        data = json.loads(layout_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("version"), 1)
        self.assertIn("platforms", data)

        psp = data["platforms"]["psp"]
        self.assertEqual(psp["prefix_length"], PSP_PREFIX_LENGTH)
        self.assertEqual(psp["path_pattern"], "by-id/psp/{prefix4}/{canonical_id_lowercase}.png")

        psx = data["platforms"]["psx"]
        self.assertEqual(psx["prefix_length"], PSX_PREFIX_LENGTH)
        self.assertEqual(psx["path_pattern"], "by-id/psx/{prefix6}/{canonical_id_lowercase}.png")

        hb = data["platforms"]["homebrew"]
        self.assertEqual(hb["path_pattern"], "by-id/homebrew/{family}/{canonical_id_lowercase}.png")


class TestRealRepoIntegrity(unittest.TestCase):
    """Integration checks running against real repository checkouts."""

    def setUp(self):
        self.base_dir = Path(__file__).resolve().parent
        self.by_id_dir = self.base_dir / "by-id"
        self.manifest_path = self.by_id_dir / ".manifest.json"

    def test_manifest_exists_and_matches_expected_count(self):
        self.assertTrue(self.manifest_path.exists(), ".manifest.json must exist in by-id/")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        managed = manifest.get("managed_aliases", {})
        self.assertEqual(len(managed), 13238, f"Expected 13,238 aliases in manifest, got {len(managed)}")

    def test_directory_distribution_limits(self):
        # PSP: Prefix length 4, no directory exceeding 3,000 images
        psp_dir = self.by_id_dir / "psp"
        if psp_dir.exists():
            for d in psp_dir.iterdir():
                if d.is_dir():
                    count = len(list(d.glob("*.png")))
                    self.assertLessEqual(count, 3000, f"PSP directory '{d.name}' exceeds 3,000: {count}")

        # PSX: Prefix length 6, no directory exceeding 1,500 images (slps00 has ~948)
        psx_dir = self.by_id_dir / "psx"
        if psx_dir.exists():
            for d in psx_dir.iterdir():
                if d.is_dir():
                    count = len(list(d.glob("*.png")))
                    self.assertLessEqual(count, 1500, f"PSX directory '{d.name}' exceeds limit: {count}")

        # Homebrew: Prefix family, very small count
        hb_dir = self.by_id_dir / "homebrew"
        if hb_dir.exists():
            for d in hb_dir.iterdir():
                if d.is_dir():
                    count = len(list(d.glob("*.png")))
                    self.assertLessEqual(count, 50, f"Homebrew directory '{d.name}' exceeds limit: {count}")

    def test_real_repo_sample_magic_bytes_and_sha(self):
        # Spot check sample aliases across platforms
        samples = [
            ("psp/ulus/ulus10041.png", "psp/Named_Titles/Ape Escape - On the Loose.png"),
            ("psx/slus00/slus00068.png", "psx/Named_Titles/AeroGauge.png"),
            ("homebrew/hbx/hbx01a2b3c4.png", None)
        ]
        for rel_alias, expected_src in samples:
            alias_path = self.by_id_dir / rel_alias
            if alias_path.exists():
                data = alias_path.read_bytes()
                self.assertTrue(data.startswith(PNG_MAGIC_BYTES), f"{rel_alias} has invalid PNG magic bytes")
                if expected_src:
                    src_path = self.base_dir / expected_src
                    if src_path.exists():
                        self.assertEqual(compute_sha256(alias_path), compute_sha256(src_path))


if __name__ == "__main__":
    unittest.main()
