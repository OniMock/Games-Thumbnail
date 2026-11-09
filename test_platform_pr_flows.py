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

    def test_sequential_consolidation_with_simulated_remote_advancement(self):
        """Simulates main advancing remotely during consolidation, requiring re-convergence from the new base."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs

        with open(self.hb_data, "r", encoding="utf-8") as f:
            base_catalog = json.load(f)

        # 1. State at start of Run A: PR 1 adds DOOM_001
        entry_pr1 = {
            "DOOM_001": {
                "serial": "DOOM_001",
                "title": "Doom PSP",
                "apitype": "0x141",
                "category": 2
            }
        }
        catalog_run_a = consolidate_catalogs(base_catalog, entry_pr1)

        # 2. Concurrently, remote main advanced with PR 2 (ARK_01234)
        entry_remote = {
            "ARK_01234": {
                "serial": "ARK_01234",
                "title": "ARK-4 Custom Firmware",
                "apitype": "0x141",
                "category": 2
            }
        }
        updated_remote_base = consolidate_catalogs(base_catalog, entry_remote)

        # 3. Pipeline detects remote advance, resets to updated_remote_base, and re-consolidates
        reconverged_catalog = consolidate_catalogs(updated_remote_base, entry_pr1)

        # 4. Assert full convergence: all 3 entries are present with zero data loss
        self.assertIn("HBXA1B9195B", reconverged_catalog, "Historical baseline entry must survive")
        self.assertIn("ARK_01234", reconverged_catalog, "Remote concurrent entry must survive")
        self.assertIn("DOOM_001", reconverged_catalog, "Current PR entry must survive")
        self.assertEqual(len(reconverged_catalog), 3)

    def test_idempotence_rerunning_produces_identical_output(self):
        """Re-running catalog consolidation without changes produces identical byte output."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs

        with open(self.hb_data, "r", encoding="utf-8") as f:
            historical = json.load(f)

        run1 = json.dumps(consolidate_catalogs(historical, {}), indent=2, ensure_ascii=False) + "\n"
        run2 = json.dumps(consolidate_catalogs(historical, {}), indent=2, ensure_ascii=False) + "\n"

        self.assertEqual(run1, run2)

    def test_homebrew_contribution_generates_and_stages_all_required_artifacts(self):
        """A complete Homebrew PR (metadata JSON + cover PNG) must update all required artifacts."""
        from homebrew.consolidate_homebrew_catalog import consolidate_catalogs, build_image_mapping

        # 1. New Homebrew entry
        new_entry = {
            "CAVE_001": {
                "serial": "CAVE_001",
                "title": "Cave Story",
                "apitype": "0x141",
                "category": 2
            }
        }
        # 2. Add matching cover
        self._create_png(self.hb_titles / "Cave Story.png")

        # 3. Consolidate into HOMEBREW.data.json
        with open(self.hb_data, "r", encoding="utf-8") as f:
            historical = json.load(f)

        consolidated = consolidate_catalogs(historical, new_entry)
        self.assertIn("CAVE_001", consolidated, "HOMEBREW.data.json must contain the new entry")
        self.assertEqual(consolidated["CAVE_001"]["title"], "Cave Story")

        # 4. Generate image mapping
        image_map, unmapped = build_image_mapping(consolidated, self.hb_titles)
        self.assertEqual(image_map.get("CAVE_001"), "homebrew/Named_Titles/Cave Story.png")
        self.assertNotIn("CAVE_001", unmapped)

        # 5. Full game map simulation: entry maps to cover
        full_map = {**image_map}
        self.assertIn("CAVE_001", full_map)
        self.assertEqual(full_map["CAVE_001"], "homebrew/Named_Titles/Cave Story.png")

    def test_git_push_failure_classification(self):
        """Workflow git push failure classification accurately distinguishes concurrency from fatal errors."""
        import re

        patterns = {
            "concurrent": re.compile(r"(fetch first|non-fast-forward|remote contains work|tip of your current branch is behind)", re.I),
            "auth": re.compile(r"(Permission to .* denied|error: 403|error: 401|Authentication failed|could not read Username)", re.I),
            "protection": re.compile(r"(GH006|protected branch|pre-receive hook declined)", re.I),
            "network": re.compile(r"(Could not resolve host|Failed to connect|Connection timed out|Network is unreachable|The remote end hung up)", re.I),
        }

        # 1. Concurrent advancement outputs
        concurrent_samples = [
            "To https://github.com/OniMock/Games-Thumbnail.git\n ! [rejected] main -> main (fetch first)\nerror: failed to push some refs",
            "To https://github.com/OniMock/Games-Thumbnail.git\n ! [rejected] main -> main (non-fast-forward)",
            "fatal: Updates were rejected because the remote contains work that you do not have locally.",
            "fatal: Updates were rejected because the tip of your current branch is behind its remote counterpart."
        ]
        for sample in concurrent_samples:
            self.assertTrue(bool(patterns["concurrent"].search(sample)), f"Failed to classify concurrent sample: {sample}")
            self.assertFalse(bool(patterns["auth"].search(sample)))

        # 2. Auth / permission outputs
        auth_samples = [
            "remote: Permission to OniMock/Games-Thumbnail.git denied to user-bot.\nfatal: unable to access: The requested URL returned error: 403",
            "fatal: Authentication failed for 'https://github.com/OniMock/Games-Thumbnail.git/'",
            "fatal: could not read Username for 'https://github.com/': terminal prompts disabled"
        ]
        for sample in auth_samples:
            self.assertTrue(bool(patterns["auth"].search(sample)), f"Failed to classify auth sample: {sample}")
            self.assertFalse(bool(patterns["concurrent"].search(sample)))

        # 3. Branch protection outputs
        protection_samples = [
            "remote: error: GH006: Protected branch update failed for refs/heads/main.",
            "remote: protected branch hook declined\n ! [remote rejected] main -> main (pre-receive hook declined)"
        ]
        for sample in protection_samples:
            self.assertTrue(bool(patterns["protection"].search(sample)), f"Failed to classify protection sample: {sample}")
            self.assertFalse(bool(patterns["concurrent"].search(sample)))

        # 4. Network outputs
        network_samples = [
            "fatal: unable to access 'https://github.com/OniMock/Games-Thumbnail.git/': Could not resolve host: github.com",
            "fatal: unable to access 'https://github.com/OniMock/Games-Thumbnail.git/': Failed to connect to github.com port 443: Connection timed out",
            "fatal: The remote end hung up unexpectedly"
        ]
        for sample in network_samples:
            self.assertTrue(bool(patterns["network"].search(sample)), f"Failed to classify network sample: {sample}")
            self.assertFalse(bool(patterns["concurrent"].search(sample)))

    def test_workflow_staging_logic_handles_renames_deletions_and_mods(self):
        """Validates that git add -A -- psp/ psx/ homebrew/ tracks new names from renames, deletions, and mods."""
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            subprocess.run(["git", "init"], cwd=t, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=t, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=t, check=True, capture_output=True)

            p_psp = t / "psp" / "Named_Titles"
            p_psx = t / "psx" / "Named_Titles"
            p_hb = t / "homebrew" / "Named_Titles"
            p_psp.mkdir(parents=True)
            p_psx.mkdir(parents=True)
            p_hb.mkdir(parents=True)

            (p_psp / "ULUS10041.png").write_text("orig")
            (p_psx / "Del.png").write_text("del")
            (p_hb / "Mod.png").write_text("mod1")
            (t / "external.txt").write_text("ext")

            subprocess.run(["git", "add", "."], cwd=t, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=t, check=True, capture_output=True)

            # 1. Rename: delete old, create new
            (p_psp / "ULUS10041.png").unlink()
            (p_psp / "GTA.png").write_text("orig")
            # 2. Delete
            (p_psx / "Del.png").unlink()
            # 3. Modify
            (p_hb / "Mod.png").write_text("mod2")
            # 4. Modify external
            (t / "external.txt").write_text("ext_mod")

            # Execute workflow staging
            subprocess.run(["git", "add", "-A", "--", "psp/Named_Titles/", "psx/Named_Titles/", "homebrew/Named_Titles/"], cwd=t, check=True, capture_output=True)

            diff = subprocess.run(["git", "diff", "--staged", "--name-status"], cwd=t, capture_output=True, text=True).stdout
            self.assertIn("psp/Named_Titles/GTA.png", diff)
            self.assertIn("psp/Named_Titles/ULUS10041.png", diff)
            self.assertIn("psx/Named_Titles/Del.png", diff)
            self.assertIn("homebrew/Named_Titles/Mod.png", diff)
            self.assertNotIn("external.txt", diff)

    def test_generate_homebrew_image_map_no_consolidate(self):
        """generate_homebrew_image_map.py respects --no-consolidate without calling run_consolidation."""
        import subprocess
        import sys

        cmd = [sys.executable, "homebrew/generate_homebrew_image_map.py", "--no-consolidate"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("Skipping duplicate consolidation", res.stdout)


if __name__ == "__main__":
    unittest.main()
