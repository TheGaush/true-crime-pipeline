"""Offline tests for the FOIA package stager (Task 035)."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from agent2_evidence.foia_downloader import (
    FoiaPackageDownloader,
    build_fixture_zip_bytes,
    build_scan_pdf_payload,
    build_text_pdf_payload,
    extract_pdf_text,
)

FIXTURE_ZIP = Path(__file__).resolve().parent / "fixtures" / "marlow_foia_package.zip"


@pytest.fixture(scope="session")
def committed_fixture_zip() -> Path:
    FIXTURE_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if not FIXTURE_ZIP.exists():
        FIXTURE_ZIP.write_bytes(build_fixture_zip_bytes())
    assert FIXTURE_ZIP.stat().st_size < 50_000
    return FIXTURE_ZIP


def test_extract_pdf_text_from_minimal_fixture() -> None:
    pdf = build_text_pdf_payload("Sheriff narrative paragraph one.")
    assert extract_pdf_text(pdf) == "Sheriff narrative paragraph one."
    assert not extract_pdf_text(build_scan_pdf_payload())


def test_stage_from_committed_zip_preserves_distinct_filenames(
    committed_fixture_zip: Path, tmp_path: Path
) -> None:
    downloader = FoiaPackageDownloader()
    result = downloader.stage(
        case_id="case_marlow_001",
        jurisdiction="WA",
        source_domain="muckrock.com",
        package_origin="muckrock_completed_request",
        zip_path=committed_fixture_zip,
        staging_parent=tmp_path,
    )

    filenames = [asset.original_filename for asset in result.assets]
    assert filenames.count("officer_bodycam.mp4") == 1
    assert filenames.count("ring_doorbell_neighbor.mp4") == 1

    by_name = {asset.original_filename: asset for asset in result.assets}
    assert by_name["officer_bodycam.mp4"].origin.startswith("state_public_records")
    assert by_name["ring_doorbell_neighbor.mp4"].origin.startswith("third_party_neighbor")
    assert by_name["officer_bodycam.mp4"].staged_path.name == "officer_bodycam.mp4"
    assert by_name["ring_doorbell_neighbor.mp4"].staged_path.name == (
        "ring_doorbell_neighbor.mp4"
    )


def test_stage_from_injected_byte_source(tmp_path: Path) -> None:
    payload = build_fixture_zip_bytes()
    downloader = FoiaPackageDownloader()
    result = downloader.stage(
        case_id="case_injected",
        jurisdiction="Marlow County, WA",
        source_domain="publicrecords.wa.gov",
        package_origin="state_statute_portal",
        zip_bytes_source=lambda: payload,
        staging_parent=tmp_path,
    )
    assert result.staging_root.is_dir()
    assert len(result.assets) >= 4
    assert result.jurisdiction == "Marlow County, WA"


def test_pdf_report_text_and_ocr_fallback(tmp_path: Path) -> None:
    manifest = {"jurisdiction": "OR", "attachments": {}}
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("foia_package_manifest.json", json.dumps(manifest))
        archive.writestr("report.pdf", build_text_pdf_payload("Visible narrative text."))
        archive.writestr("scan_only.pdf", build_scan_pdf_payload())
    payload = buffer.getvalue()

    result = FoiaPackageDownloader().stage(
        case_id="case_pdf",
        jurisdiction="OR",
        source_domain="muckrock.com",
        package_origin="muckrock_zip",
        zip_bytes=payload,
        staging_parent=tmp_path,
    )
    report = next(a for a in result.assets if a.original_filename == "report.pdf")
    scan = next(a for a in result.assets if a.original_filename == "scan_only.pdf")

    assert report.extracted_text == "Visible narrative text."
    assert report.needs_ocr is False
    assert scan.extracted_text in ("", None)
    assert scan.needs_ocr is True


def test_assets_remain_not_cleared(tmp_path: Path) -> None:
    result = FoiaPackageDownloader().stage(
        case_id="case_quarantine",
        jurisdiction="WA",
        source_domain="muckrock.com",
        package_origin="muckrock_zip",
        zip_bytes=build_fixture_zip_bytes(),
        staging_parent=tmp_path,
    )
    assert all(asset.cleared is False for asset in result.assets)
    manifest = json.loads((result.staging_root / "staged_manifest.json").read_text())
    assert manifest["cleared"] is False
    assert all(entry["cleared"] is False for entry in manifest["assets"])


def test_records_jurisdiction_and_sha(tmp_path: Path) -> None:
    result = FoiaPackageDownloader().stage(
        case_id="case_meta",
        jurisdiction="WA",
        source_domain="muckrock.com",
        package_origin="muckrock_zip",
        zip_bytes=build_fixture_zip_bytes(),
        staging_parent=tmp_path,
    )
    for asset in result.assets:
        assert asset.jurisdiction == "Marlow County, WA"
        assert len(asset.sha256) == 64
        assert asset.staged_path.is_file()
        assert asset.asset_id.startswith("foia_")


def test_requires_exactly_one_zip_source() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        FoiaPackageDownloader().stage(
            case_id="case_bad",
            jurisdiction="WA",
            source_domain="muckrock.com",
            package_origin="muckrock_zip",
        )