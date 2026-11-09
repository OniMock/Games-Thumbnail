#!/usr/bin/env python3
"""
Unit and integration test suite for generate_search_index.py.
Validates normalization, platform coverage, alternative titles, deduplication,
absence of side effects, JSON integrity, and searchability.
"""

import unittest
import json
import hashlib
import tempfile
import shutil
from pathlib import Path

from generate_search_index import (
    BASE_DIR,
    SEARCH_INDEX_FILE,
    normalize_game_id,
    clean_noise_tokens,
    strip_parens,
    build_search_index_data,
    generate_search_index,
    serialize_search_index,
)


class TestIdNormalization(unittest.TestCase):
    """Validates platform-specific Game ID normalization rules."""

    def test_psp_normalization(self):
        self.assertEqual(normalize_game_id("ULUS-10041", "psp"), "ULUS10041")
        self.assertEqual(normalize_game_id("ulus-10041", "psp"), "ULUS10041")
        self.assertEqual(normalize_game_id("  NPJH 50006 ", "psp"), "NPJH50006")
        self.assertEqual(normalize_game_id("04081UJ", "psp"), "04081UJ")

    def test_psx_normalization(self):
        self.assertEqual(normalize_game_id("SLUS-00068", "psx"), "SLUS00068")
        self.assertEqual(normalize_game_id("slus-00068", "psx"), "SLUS00068")
        self.assertEqual(normalize_game_id("SLPS-00004-R1", "psx"), "SLPS00004R1")
        self.assertEqual(normalize_game_id("  SCES-00001  ", "psx"), "SCES00001")

    def test_homebrew_normalization(self):
        self.assertEqual(normalize_game_id("hbx1b6576c3", "homebrew"), "HBX1B6576C3")
        self.assertEqual(normalize_game_id("ARK_01234", "homebrew"), "ARK_01234")
        self.assertEqual(normalize_game_id("  ark_01234  ", "homebrew"), "ARK_01234")

    def test_empty_or_none(self):
        self.assertEqual(normalize_game_id("", "psp"), "")
        self.assertEqual(normalize_game_id("   ", "psx"), "")


class TestNoiseCleaning(unittest.TestCase):
    """Validates string and token cleaning."""

    def test_strip_parens(self):
        self.assertEqual(strip_parens("Crash Bandicoot (USA)"), "Crash Bandicoot")
        self.assertEqual(strip_parens("Game (Japan) (Disc 1)"), "Game")
        self.assertEqual(strip_parens("Simple Title"), "Simple Title")

    def test_clean_noise_tokens(self):
        self.assertEqual(clean_noise_tokens("Game Name [E]"), "Game Name")
        self.assertEqual(clean_noise_tokens("Apache Overkill/td>"), "Apache Overkill")
        self.assertEqual(clean_noise_tokens("Title [J] [En,Ja]"), "Title")
        self.assertEqual(clean_noise_tokens(""), "")


class TestPlatformCoverageAndMetrics(unittest.TestCase):
    """Validates coverage across PSP, PSX, and Homebrew catalogs."""

    @classmethod
    def setUpClass(cls):
        cls.data = build_search_index_data(BASE_DIR)
        cls.games = cls.data["games"]

    def test_total_counts(self):
        self.assertEqual(self.data["version"], 1)
        self.assertEqual(self.data["total_games"], 19443)
        self.assertEqual(len(self.games), 19443)

    def test_per_platform_distribution(self):
        psp = [g for g in self.games if g["platform"] == "psp"]
        psx = [g for g in self.games if g["platform"] == "psx"]
        hb = [g for g in self.games if g["platform"] == "homebrew"]

        self.assertEqual(len(psp), 7680, "Expected exactly 7,680 PSP games")
        self.assertEqual(len(psx), 11753, "Expected exactly 11,753 PSX games")
        self.assertEqual(len(hb), 10, "Expected exactly 10 Homebrew games")

    def test_categories(self):
        for g in self.games:
            if g["platform"] == "psp":
                self.assertEqual(g["category"], "PSP")
            elif g["platform"] == "psx":
                self.assertEqual(g["category"], "PS1")
            elif g["platform"] == "homebrew":
                self.assertEqual(g["category"], "Homebrew")


class TestDuplicatesAndConsolidation(unittest.TestCase):
    """Validates handling of duplicate releases and alternative titles."""

    @classmethod
    def setUpClass(cls):
        cls.data = build_search_index_data(BASE_DIR)
        cls.games_by_id = {g["id"]: g for g in cls.data["games"]}

    def test_slps00004_consolidation(self):
        # SLPS00004 had 2 releases in PSX catalog: Evolution and Evolution (Rev 1)
        self.assertIn("SLPS00004", self.games_by_id)
        entry = self.games_by_id["SLPS00004"]
        self.assertEqual(entry["title"], "A Ressha de Ikou 4: Evolution")
        self.assertTrue(entry["hasCover"])

        # Aliases must capture alternative titles from both entries
        aliases = entry["aliases"]
        self.assertTrue(any("Rev 1" in a for a in aliases), "Rev 1 release must be present in aliases")
        self.assertTrue(any("Japan" in a for a in aliases), "Japan release name must be present in aliases")

    def test_no_id_collisions(self):
        ids = [g["id"] for g in self.data["games"]]
        self.assertEqual(len(ids), len(set(ids)), "All 19,443 Game IDs must be globally unique")


class TestRecordsWithoutSerial(unittest.TestCase):
    """Ensures entries lacking serials are safely omitted without inventing synthetic IDs."""

    def test_no_synthetic_ids(self):
        data = build_search_index_data(BASE_DIR)
        for g in data["games"]:
            # Ensure no dummy/placeholder IDs exist
            self.assertFalse(g["id"].startswith("UNKNOWN"))
            self.assertFalse(g["id"].startswith("SYNTHETIC"))
            self.assertGreater(len(g["id"]), 2)


class TestHasCoverConsistency(unittest.TestCase):
    """Verifies hasCover field perfectly aligns with existing aliases and full_game_map."""

    @classmethod
    def setUpClass(cls):
        cls.data = build_search_index_data(BASE_DIR)
        cls.full_map = json.loads((BASE_DIR / "full_game_map.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((BASE_DIR / "by-id" / ".manifest.json").read_text(encoding="utf-8"))
        cls.managed_aliases = cls.manifest.get("managed_aliases", {})

    def test_has_cover_totals(self):
        games = self.data["games"]
        with_cover = [g for g in games if g["hasCover"]]
        without_cover = [g for g in games if not g["hasCover"]]

        self.assertEqual(len(with_cover), 13239, "Expected exactly 13,239 games with cover")
        self.assertEqual(len(without_cover), 6204, "Expected exactly 6,204 games without cover")

    def test_has_cover_matches_full_map_and_manifest(self):
        games = self.data["games"]
        for g in games:
            gid = g["id"]
            if g["hasCover"]:
                self.assertIn(gid, self.full_map, f"Game {gid} marked with hasCover=true but missing in full_game_map")
            else:
                self.assertNotIn(gid, self.full_map, f"Game {gid} marked with hasCover=false but present in full_game_map")


class TestDeterminismAndIdempotence(unittest.TestCase):
    """Verifies that generation is strictly deterministic and idempotent."""

    def test_deterministic_output(self):
        run1 = build_search_index_data(BASE_DIR)
        run2 = build_search_index_data(BASE_DIR)

        ser1 = serialize_search_index(run1, pretty=False)
        ser2 = serialize_search_index(run2, pretty=False)

        self.assertEqual(ser1, ser2, "Consecutive serializations must be byte-for-byte identical")

    def test_check_mode(self):
        # Verify check mode on real search-index.json
        if SEARCH_INDEX_FILE.exists():
            success, msg = generate_search_index(BASE_DIR, SEARCH_INDEX_FILE, check_only=True)
            self.assertTrue(success, f"Check mode failed: {msg}")


class TestJsonSchemaAndStructure(unittest.TestCase):
    """Validates JSON schema, envelope structure, and field data types."""

    @classmethod
    def setUpClass(cls):
        cls.data = build_search_index_data(BASE_DIR)

    def test_envelope_fields(self):
        self.assertIn("version", self.data)
        self.assertIn("total_games", self.data)
        self.assertIn("games", self.data)
        self.assertEqual(self.data["version"], 1)

    def test_game_record_fields(self):
        for g in self.data["games"]:
            self.assertIsInstance(g["id"], str)
            self.assertIsInstance(g["title"], str)
            self.assertIsInstance(g["aliases"], list)
            self.assertIn(g["platform"], ("psp", "psx", "homebrew"))
            self.assertIn(g["category"], ("PSP", "PS1", "Homebrew"))
            self.assertIsInstance(g["hasCover"], bool)

            # Title must not be in aliases
            self.assertNotIn(g["title"], g["aliases"])


class TestCatalogPurity(unittest.TestCase):
    """Verifies source catalogs and existing image maps are strictly read-only."""

    def test_source_catalogs_unmodified(self):
        sources = [
            BASE_DIR / "psp" / "PSP.data.json",
            BASE_DIR / "psx" / "PSX.data.json",
            BASE_DIR / "homebrew" / "HOMEBREW.data.json",
            BASE_DIR / "psp" / "game_id_to_image.json",
            BASE_DIR / "psx" / "game_id_to_image.json",
            BASE_DIR / "homebrew" / "game_id_to_image.json",
            BASE_DIR / "full_game_map.json",
            BASE_DIR / "by-id" / "path-layout.json",
            BASE_DIR / "by-id" / ".manifest.json",
        ]

        # Calculate initial hashes
        hashes_before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}

        # Run generator to a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_output = Path(tmpdir) / "search-index.json"
            success, msg = generate_search_index(
                base_dir=BASE_DIR,
                output_path=temp_output,
                check_only=False
            )
            self.assertTrue(success, f"Generation failed: {msg}")
            self.assertTrue(temp_output.exists())

        # Verify hashes after
        for p in sources:
            hash_after = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertEqual(
                hashes_before[p],
                hash_after,
                f"Source catalog/map modified during search index generation: {p}"
            )


class TestSearchScenarios(unittest.TestCase):
    """Simulates real-world search queries across names, aliases, and serial formats."""

    @classmethod
    def setUpClass(cls):
        cls.data = build_search_index_data(BASE_DIR)
        cls.games = cls.data["games"]

    def _search(self, query: str):
        import re
        q_norm = re.sub(r'[^a-z0-9]', '', query.lower())
        results = []
        for g in self.games:
            gid_norm = re.sub(r'[^a-z0-9]', '', g["id"].lower())
            title_norm = re.sub(r'[^a-z0-9]', '', g["title"].lower())

            # ID exact or substring match (min 4 chars)
            if q_norm == gid_norm or (len(q_norm) >= 4 and q_norm in gid_norm):
                results.append((g, "id_match"))
                continue

            # Title match
            if q_norm in title_norm:
                results.append((g, "title_match"))
                continue

            # Alias match
            for a in g["aliases"]:
                if q_norm in re.sub(r'[^a-z0-9]', '', a.lower()):
                    results.append((g, "alias_match"))
                    break
        return results

    def test_search_by_game_id(self):
        # Exact clean ID
        res = self._search("SLUS00068")
        self.assertTrue(any(r[0]["id"] == "SLUS00068" for r in res))

        # Hyphenated ID
        res = self._search("SLUS-00068")
        self.assertTrue(any(r[0]["id"] == "SLUS00068" for r in res))

        # Lowercase hyphenated ID
        res = self._search("slus-00068")
        self.assertTrue(any(r[0]["id"] == "SLUS00068" for r in res))

        # PSP ID
        res = self._search("ULUS-10041")
        self.assertTrue(any(r[0]["id"] == "ULUS10041" for r in res))

    def test_search_by_title(self):
        res = self._search("Resident Evil 2")
        self.assertGreater(len(res), 0)
        self.assertTrue(any("Resident Evil" in r[0]["title"] for r in res))

    def test_search_by_alias(self):
        # Evolution (Rev 1) is an alias for SLPS00004
        res = self._search("Evolution Rev 1")
        self.assertTrue(any(r[0]["id"] == "SLPS00004" for r in res))

    def test_search_homebrew(self):
        res = self._search("ARK_01234")
        self.assertTrue(any(r[0]["id"] == "HBXA1359E7C" for r in res))


if __name__ == "__main__":
    unittest.main()
