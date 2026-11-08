#!/usr/bin/env python3
"""
generate_by_id_aliases.py
Generates and synchronizes deterministic cover aliases in by-id/
for PSP, PSX, and Homebrew platforms.

Layout:
  by-id/psp/<prefix4>/<canonical_id_lowercase>.png
  by-id/psx/<prefix6>/<canonical_id_lowercase>.png
  by-id/homebrew/<family>/<canonical_id_lowercase>.png

Guarantees:
1. Strict pre-flight validation of all sources (fail-closed).
2. Deterministic normalization respecting platform rules.
3. Content integrity via SHA-256 byte-for-byte comparison.
4. Idempotence: zero re-writes or timestamp modifications if content matches.
5. Atomic per-file writing via temporary files and os.replace.
6. Safe cleanup of obsolete aliases using an ownership manifest (by-id/.manifest.json).
7. Zero modification of original images or source catalogs.
"""

import os
import sys
import json
import re
import hashlib
import tempfile
import argparse
from pathlib import Path
from typing import Dict, Tuple, Set, Optional, Any, List

BASE_DIR = Path(__file__).resolve().parent
BY_ID_DIR = BASE_DIR / "by-id"
MANIFEST_PATH = BY_ID_DIR / ".manifest.json"
LAYOUT_PATH = BY_ID_DIR / "path-layout.json"

PLATFORM_MAPS = {
    "psp": BASE_DIR / "psp" / "game_id_to_image.json",
    "psx": BASE_DIR / "psx" / "game_id_to_image.json",
    "homebrew": BASE_DIR / "homebrew" / "game_id_to_image.json"
}

ALLOWED_SOURCE_DIRS = {
    "psp": BASE_DIR / "psp" / "Named_Titles",
    "psx": BASE_DIR / "psx" / "Named_Titles",
    "homebrew": BASE_DIR / "homebrew" / "Named_Titles"
}

# Prefix lengths defined in path-layout.json
PSP_PREFIX_LENGTH = 4
PSX_PREFIX_LENGTH = 6


def compute_sha256(filepath: Path) -> str:
    """Computes SHA-256 hex digest using 64KB chunk streaming."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_psp_id(raw_id: str) -> str:
    """PSP: strip external spaces, remove hyphens, uppercase."""
    return raw_id.replace("-", "").strip().upper()


def normalize_psx_id(raw_id: str) -> str:
    """PSX: strip external spaces, remove hyphens, uppercase."""
    return raw_id.replace("-", "").strip().upper()


def normalize_homebrew_id(raw_id: str) -> str:
    """Homebrew: strip external spaces, preserve hyphens and underscores, uppercase."""
    return raw_id.strip().upper()


def normalize_game_id(platform: str, raw_id: str) -> str:
    """Normalizes a Game ID according to platform rules."""
    p = platform.lower()
    if p == "psp":
        return normalize_psp_id(raw_id)
    elif p == "psx":
        return normalize_psx_id(raw_id)
    elif p == "homebrew":
        return normalize_homebrew_id(raw_id)
    else:
        raise ValueError(f"Unknown platform: {platform}")


def get_homebrew_family(clean_id: str) -> str:
    """
    Extracts the family prefix folder for Homebrew:
    1. If standard generated HBX hash (HBX + 8 hex chars): 'hbx'
    2. Leading alphabetic sequence before digits or separators: lowercased
    3. Fallback: 'misc'
    """
    if clean_id.startswith("HBX") and len(clean_id) == 11:
        return "hbx"
    m = re.match(r"^([a-zA-Z]+)", clean_id)
    if m:
        return m.group(1).lower()
    return "misc"


def resolve_alias_rel_path(platform: str, clean_id: str) -> str:
    """
    Resolves the destination path relative to by-id/.
    Returns format: '<platform>/<prefix>/<canonical_id_lowercase>.png'
    """
    p = platform.lower()
    clean_lower = clean_id.lower()

    if p == "psp":
        prefix = clean_lower[:PSP_PREFIX_LENGTH] if len(clean_lower) >= PSP_PREFIX_LENGTH else clean_lower
        return f"psp/{prefix}/{clean_lower}.png"
    elif p == "psx":
        prefix = clean_lower[:PSX_PREFIX_LENGTH] if len(clean_lower) >= PSX_PREFIX_LENGTH else clean_lower
        return f"psx/{prefix}/{clean_lower}.png"
    elif p == "homebrew":
        prefix = get_homebrew_family(clean_id)
        return f"homebrew/{prefix}/{clean_lower}.png"
    else:
        raise ValueError(f"Unknown platform: {platform}")


class AliasValidationError(Exception):
    """Raised when source catalog validation fails."""
    pass


def load_and_validate_sources(
    platform_maps: Dict[str, Path] = PLATFORM_MAPS,
    base_dir: Path = BASE_DIR
) -> Dict[str, Tuple[str, Path, Path]]:
    """
    Fails closed: inspects all platform maps, validates paths, checks physical file existence,
    and ensures zero destination collisions before any files are written.

    Returns:
      dict: rel_alias_path -> (platform, clean_id, absolute_source_path)
    """
    expected_aliases: Dict[str, Tuple[str, Path, Path]] = {}
    dest_to_original_ids: Dict[str, List[Tuple[str, str]]] = {}
    errors: List[str] = []

    # Cache of validated source paths to avoid redundant filesystem calls for shared images
    validated_sources: Dict[str, Tuple[bool, Optional[str]]] = {}

    for platform, map_path in platform_maps.items():
        if not map_path.exists():
            errors.append(f"Missing mapping file for platform '{platform}': {map_path}")
            continue

        try:
            with open(map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"Failed to parse JSON in {map_path}: {e}")
            continue

        if not isinstance(data, dict):
            errors.append(f"Root of {map_path} must be a JSON object.")
            continue

        allowed_prefix = f"{platform}/Named_Titles/"

        for raw_id, rel_img in data.items():
            if not rel_img:
                # Unmapped game without cover: valid, skip cleanly
                continue

            clean_id = normalize_game_id(platform, raw_id)
            try:
                rel_alias = resolve_alias_rel_path(platform, clean_id)
            except Exception as e:
                errors.append(f"Failed to resolve alias path for {platform}:{raw_id}: {e}")
                continue

            # Check for destination collisions between different raw IDs
            if rel_alias in dest_to_original_ids:
                existing_p, existing_raw = dest_to_original_ids[rel_alias][0]
                if existing_raw != raw_id or existing_p != platform:
                    errors.append(
                        f"Collision detected! '{platform}:{raw_id}' and '{existing_p}:{existing_raw}' "
                        f"resolve to the same alias path: '{rel_alias}'"
                    )
            else:
                dest_to_original_ids[rel_alias] = []
            dest_to_original_ids[rel_alias].append((platform, raw_id))

            # Validate source file boundaries and existence (cached per unique relative image)
            if rel_img not in validated_sources:
                norm_rel = os.path.normpath(rel_img).replace("\\", "/")
                if norm_rel.startswith("..") or os.path.isabs(norm_rel):
                    validated_sources[rel_img] = (False, f"Path traversal attempt: '{rel_img}'")
                elif not (norm_rel + "/").startswith(allowed_prefix) and norm_rel != allowed_prefix.rstrip("/"):
                    validated_sources[rel_img] = (
                        False,
                        f"Unauthorized source image path: '{rel_img}' is outside '{allowed_prefix}'"
                    )
                else:
                    source_path = base_dir / rel_img
                    try:
                        st = source_path.stat()
                        if st.st_size == 0:
                            validated_sources[rel_img] = (False, f"Source image file is empty (0 bytes): '{rel_img}'")
                        else:
                            validated_sources[rel_img] = (True, None)
                    except FileNotFoundError:
                        validated_sources[rel_img] = (False, f"Missing source image file: '{rel_img}' not found on disk.")
                    except OSError as e:
                        validated_sources[rel_img] = (False, f"OS error accessing source image '{rel_img}': {e}")

            is_valid, err_msg = validated_sources[rel_img]
            if not is_valid:
                errors.append(f"{platform}:{raw_id} -> {err_msg}")
                continue

            expected_aliases[rel_alias] = (platform, clean_id, base_dir / rel_img)

    if errors:
        raise AliasValidationError(
            f"Pre-flight validation failed with {len(errors)} error(s):\n" + "\n".join(f"  - {err}" for err in errors[:20])
        )

    return expected_aliases


def load_manifest(manifest_path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    """Loads existing .manifest.json if available, or returns empty template."""
    if not manifest_path.exists():
        return {"generator": "generate_by_id_aliases.py", "version": 1, "managed_aliases": {}}
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "managed_aliases" in data:
                return data
    except Exception:
        pass
    return {"generator": "generate_by_id_aliases.py", "version": 1, "managed_aliases": {}}


def write_atomic_file(target_path: Path, source_path: Path, expected_sha: str) -> None:
    """
    Writes source bytes to temporary file in the target directory,
    validates SHA-256, and atomically replaces target.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_path.with_name(f"{target_path.name}.tmp.{os.getpid()}")
    try:
        with open(source_path, "rb") as src, open(temp_file, "wb") as dst:
            while chunk := src.read(65536):
                dst.write(chunk)
            dst.flush()

        # Validate temporary file integrity
        written_sha = compute_sha256(temp_file)
        if written_sha != expected_sha:
            raise IOError(f"SHA-256 verification failed writing {temp_file}: {written_sha} != {expected_sha}")

        # Atomic replace
        os.replace(temp_file, target_path)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


def sync_aliases(
    check_mode: bool = False,
    verbose: bool = False,
    base_dir: Path = BASE_DIR,
    by_id_dir: Path = BY_ID_DIR,
    platform_maps: Dict[str, Path] = PLATFORM_MAPS,
    manifest_path: Path = MANIFEST_PATH
) -> Dict[str, int]:
    """
    Synchronizes by-id/ aliases against existing platform mapping files.
    If check_mode is True, only verifies whether state is in sync without writing.
    """
    by_id_dir.mkdir(parents=True, exist_ok=True)

    # 1. Pre-flight validation (Fail-closed)
    expected_aliases = load_and_validate_sources(platform_maps, base_dir)

    # 2. Load previous manifest for managed orphan detection
    manifest = load_manifest(manifest_path)
    prev_managed: Dict[str, str] = manifest.get("managed_aliases", {})

    stats = {
        "total_expected": len(expected_aliases),
        "kept": 0,
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "unmanaged_skipped": 0,
        "out_of_sync": 0
    }

    new_managed: Dict[str, str] = {}
    source_hashes: Dict[Path, str] = {}

    def get_source_sha(source_path: Path) -> str:
        if source_path not in source_hashes:
            source_hashes[source_path] = compute_sha256(source_path)
        return source_hashes[source_path]

    # 3. Synchronize aliases
    for rel_alias, (platform, clean_id, source_path) in expected_aliases.items():
        target_path = by_id_dir / rel_alias

        target_stat = None
        try:
            target_stat = target_path.stat()
        except OSError:
            pass

        if target_stat is not None:
            # Check size first
            if target_stat.st_size == source_path.stat().st_size:
                target_sha = compute_sha256(target_path)
                source_sha = get_source_sha(source_path)
                if target_sha == source_sha:
                    stats["kept"] += 1
                    new_managed[rel_alias] = source_sha
                    continue

            # Content differs (either size differs or SHA differs)
            stats["out_of_sync"] += 1
            if not check_mode:
                source_sha = get_source_sha(source_path)
                write_atomic_file(target_path, source_path, source_sha)
                stats["updated"] += 1
                new_managed[rel_alias] = source_sha
                if verbose:
                    print(f"  [UPDATED] {rel_alias}")
        else:
            # File missing
            stats["out_of_sync"] += 1
            if not check_mode:
                source_sha = get_source_sha(source_path)
                write_atomic_file(target_path, source_path, source_sha)
                stats["created"] += 1
                new_managed[rel_alias] = source_sha
                if verbose:
                    print(f"  [CREATED] {rel_alias}")

    # 4. Safe Orphan Cleanup (Only removes files previously in manifest)
    for platform in platform_maps.keys():
        plat_dir = by_id_dir / platform
        if not plat_dir.exists():
            continue

        for existing_file in plat_dir.rglob("*.png"):
            rel_existing = existing_file.relative_to(by_id_dir).as_posix()
            if rel_existing not in expected_aliases:
                if rel_existing in prev_managed:
                    # File was managed by this script and is now obsolete
                    stats["out_of_sync"] += 1
                    if not check_mode:
                        try:
                            existing_file.unlink()
                            stats["deleted"] += 1
                            if verbose:
                                print(f"  [DELETED OBSOLETE] {rel_existing}")
                        except OSError as e:
                            print(f"[!] Warning: Failed to delete obsolete alias {rel_existing}: {e}")
                else:
                    # Unmanaged file: protect from accidental deletion
                    stats["unmanaged_skipped"] += 1
                    if verbose:
                        print(f"  [WARN] Skipping unmanaged file: {rel_existing}")

        # Clean up empty parent directories inside by-id/<platform>/
        if not check_mode:
            for dirpath, dirnames, filenames in os.walk(plat_dir, topdown=False):
                p = Path(dirpath)
                if p != plat_dir and not os.listdir(dirpath):
                    try:
                        p.rmdir()
                    except OSError:
                        pass

    # 5. Write updated manifest atomically
    if not check_mode:
        updated_manifest = {
            "generator": "generate_by_id_aliases.py",
            "version": 1,
            "total_aliases": len(new_managed),
            "managed_aliases": dict(sorted(new_managed.items()))
        }
        temp_manifest = manifest_path.with_name(f".manifest.tmp.{os.getpid()}")
        try:
            with open(temp_manifest, "w", encoding="utf-8") as f:
                json.dump(updated_manifest, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(temp_manifest, manifest_path)
        finally:
            if temp_manifest.exists():
                try:
                    temp_manifest.unlink()
                except OSError:
                    pass

    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate deterministic cover aliases by Game ID.")
    parser.add_argument("--check", action="store_true", help="Verify if aliases are up to date without writing.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed file operations.")
    args = parser.parse_args()

    print("=== SYNCHRONIZING BY-ID COVER ALIASES ===")
    try:
        stats = sync_aliases(check_mode=args.check, verbose=args.verbose)
    except AliasValidationError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[FATAL] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        if stats["out_of_sync"] == 0:
            print(f"[OK] All {stats['total_expected']} by-id aliases are up to date and verified.")
            sys.exit(0)
        else:
            print(f"[OUT OF SYNC] Found {stats['out_of_sync']} aliases requiring update/creation/deletion.")
            sys.exit(1)
    else:
        print(
            f"[COMPLETE] Aliases synchronized: {stats['total_expected']} total "
            f"({stats['created']} created, {stats['updated']} updated, {stats['kept']} kept, "
            f"{stats['deleted']} deleted, {stats['unmanaged_skipped']} unmanaged skipped)."
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
