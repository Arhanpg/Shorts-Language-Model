"""Tests for safe, checksum-verified catalogue archive installation."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.install_research_catalogue import (
    CatalogueArchiveError,
    install_archive,
    safe_member_path,
    verify_archive,
)

ROOT = "ShortsLM_Research_Catalogue_v0.1"


def make_archive(
    path: Path, *, payload: bytes = b"hello", expected_hash: str | None = None
) -> None:
    digest = expected_hash or hashlib.sha256(payload).hexdigest()
    summary = {
        "release": "test",
        "counts": {},
        "files": [
            {"path": "README.md", "size_bytes": len(payload), "sha256": digest}
        ],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{ROOT}/README.md", payload)
        archive.writestr(f"{ROOT}/QA_SUMMARY.json", json.dumps(summary))


def test_safe_member_path_rejects_traversal() -> None:
    with pytest.raises(CatalogueArchiveError):
        safe_member_path(f"{ROOT}/../escape.csv")


def test_installer_checks_hashes_before_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "catalogue.zip"
    make_archive(archive)
    destination = tmp_path / "installed"
    installed = install_archive(archive, destination)
    assert (destination / "README.md").read_bytes() == b"hello"
    assert (destination / "QA_SUMMARY.json").is_file()
    assert len(installed) == 2


def test_installer_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    make_archive(archive, expected_hash="0" * 64)
    with pytest.raises(CatalogueArchiveError, match="SHA-256 mismatch"):
        verify_archive(archive)


def test_installer_requires_explicit_overwrite(tmp_path: Path) -> None:
    archive = tmp_path / "catalogue.zip"
    make_archive(archive)
    destination = tmp_path / "installed"
    destination.mkdir()
    (destination / "keep.txt").write_text("backup", encoding="utf-8")
    with pytest.raises(CatalogueArchiveError, match="Destination is not empty"):
        install_archive(archive, destination)


def test_safe_member_path_rejects_absolute_and_wrong_root() -> None:
    with pytest.raises(CatalogueArchiveError):
        safe_member_path("/tmp/escape.csv")
    with pytest.raises(CatalogueArchiveError):
        safe_member_path("other-root/README.md")


def test_safe_member_path_rejects_unexpected_extension() -> None:
    with pytest.raises(CatalogueArchiveError, match="Unexpected file type"):
        safe_member_path(f"{ROOT}/media.mp4")


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    archive = tmp_path / "catalogue.zip"
    make_archive(archive)
    destination = tmp_path / "not-created"
    planned = install_archive(archive, destination, dry_run=True)
    assert planned == [destination / "README.md"]
    assert not destination.exists()


def test_installer_rejects_duplicate_output_paths(tmp_path: Path) -> None:
    archive = tmp_path / "duplicate.zip"
    summary = {
        "release": "test",
        "counts": {},
        "files": [
            {
                "path": "README.md",
                "size_bytes": 1,
                "sha256": hashlib.sha256(b"x").hexdigest(),
            }
        ],
    }
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as stream:
        stream.writestr(f"{ROOT}/README.md", b"x")
        stream.writestr(f"{ROOT}/sub/../README.md", b"x")
        stream.writestr(f"{ROOT}/QA_SUMMARY.json", json.dumps(summary))
    with pytest.raises(CatalogueArchiveError):
        verify_archive(archive)
