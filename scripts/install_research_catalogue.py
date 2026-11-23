#!/usr/bin/env python3
"""Verify and install a Shorts-LM research catalogue release archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

ARCHIVE_ROOT = "ShortsLM_Research_Catalogue_v0.1"
ALLOWED_SUFFIXES = {".csv", ".json", ".jsonl", ".md"}
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 300 * 1024 * 1024


class CatalogueArchiveError(ValueError):
    """Raised when a catalogue archive is malformed or unsafe."""


def safe_member_path(name: str) -> Path:
    """Return a safe relative path below the expected archive root."""
    posix = PurePosixPath(name)
    if posix.is_absolute() or ".." in posix.parts or not posix.parts:
        raise CatalogueArchiveError(f"Unsafe archive path: {name!r}")
    if posix.parts[0] != ARCHIVE_ROOT:
        raise CatalogueArchiveError(f"Unexpected archive root: {name!r}")
    relative = Path(*posix.parts[1:])
    if not relative.parts:
        raise CatalogueArchiveError("Archive root directory is not a file")
    if relative.suffix.lower() not in ALLOWED_SUFFIXES:
        raise CatalogueArchiveError(f"Unexpected file type: {name!r}")
    return relative


def verify_archive(archive_path: Path) -> tuple[dict, list[tuple[str, bytes]]]:
    """Verify the archive manifest, file sizes and SHA-256 checksums."""
    if not archive_path.is_file():
        raise CatalogueArchiveError(f"Archive does not exist: {archive_path}")
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CatalogueArchiveError(f"Cannot open ZIP archive: {exc}") from exc

    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        safe = [(info, safe_member_path(info.filename)) for info in infos]
        relative_names = [str(relative) for _, relative in safe]
        if len(relative_names) != len(set(relative_names)):
            raise CatalogueArchiveError("Archive contains duplicate output paths")
        total_size = sum(info.file_size for info, _ in safe)
        if total_size > MAX_TOTAL_BYTES:
            raise CatalogueArchiveError("Archive exceeds the uncompressed size limit")
        if any(info.file_size > MAX_MEMBER_BYTES for info, _ in safe):
            raise CatalogueArchiveError("Archive member exceeds the uncompressed size limit")

        names = {info.filename for info, _ in safe}
        summary_name = f"{ARCHIVE_ROOT}/QA_SUMMARY.json"
        if summary_name not in names:
            raise CatalogueArchiveError("QA_SUMMARY.json is missing from the archive")
        try:
            summary = json.loads(archive.read(summary_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogueArchiveError(f"Invalid QA_SUMMARY.json: {exc}") from exc

        expected = summary.get("files")
        if not isinstance(expected, list) or not expected:
            raise CatalogueArchiveError("QA_SUMMARY.json has no file manifest")
        expected_by_path = {item.get("path"): item for item in expected}
        actual_by_path = {
            str(relative): info.filename
            for info, relative in safe
            if str(relative) != "QA_SUMMARY.json"
        }
        if set(expected_by_path) != set(actual_by_path):
            missing = sorted(set(expected_by_path) - set(actual_by_path))
            unexpected = sorted(set(actual_by_path) - set(expected_by_path))
            raise CatalogueArchiveError(
                f"Manifest mismatch; missing={missing}, unexpected={unexpected}"
            )

        verified: list[tuple[str, bytes]] = []
        for relative, item in expected_by_path.items():
            payload = archive.read(actual_by_path[relative])
            if len(payload) != item.get("size_bytes"):
                raise CatalogueArchiveError(f"Size mismatch for {relative}")
            digest = hashlib.sha256(payload).hexdigest()
            if digest != item.get("sha256"):
                raise CatalogueArchiveError(f"SHA-256 mismatch for {relative}")
            verified.append((relative, payload))
        return summary, verified


def install_archive(
    archive_path: Path,
    destination: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Verify before writing; keep every extracted path within destination."""
    _, files = verify_archive(archive_path)
    if destination.exists() and any(destination.iterdir()) and not overwrite:
        raise CatalogueArchiveError(
            f"Destination is not empty: {destination}. Use --overwrite only after backup."
        )
    if dry_run:
        return [destination / relative for relative, _ in files]

    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    installed: list[Path] = []
    for relative, payload in files:
        target = (destination / relative).resolve()
        if root not in target.parents:
            raise CatalogueArchiveError(f"Resolved output path escaped destination: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        installed.append(target)

    with zipfile.ZipFile(archive_path) as archive:
        summary = archive.read(f"{ARCHIVE_ROOT}/QA_SUMMARY.json")
    summary_path = destination / "QA_SUMMARY.json"
    summary_path.write_bytes(summary)
    return [*installed, summary_path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--destination", type=Path, default=Path("data/research_catalogue/v0.1"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary, _ = verify_archive(args.archive)
        paths = install_archive(
            args.archive, args.destination, overwrite=args.overwrite, dry_run=args.dry_run
        )
    except CatalogueArchiveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Catalogue: {summary.get('release', 'unknown release')}")
    print(f"Files {'planned' if args.dry_run else 'installed'}: {len(paths)}")
    print(f"Counts: {json.dumps(summary.get('counts', {}), sort_keys=True)}")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
