"""Stage local FOIA release ZIPs into ``raw_foia/`` for Agent 3 review.

No network I/O: callers supply a filesystem path or inject zip bytes. PDF text
uses a tiny stdlib extractor; empty output sets ``needs_ocr`` without pulling
in a heavyweight OCR stack.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

FOIA_MANIFEST_NAME = "foia_package_manifest.json"

_MEDIA_KIND_BY_SUFFIX: dict[str, str] = {
    ".mp4": "bodycam_mp4",
    ".wav": "call_911_wav",
    ".pdf": "foia_pdf",
    ".jpg": "photo_cc0",
    ".jpeg": "photo_cc0",
    ".png": "photo_cc0",
}


@dataclass(frozen=True)
class FoiaStagedAsset:
    asset_id: str
    case_id: str
    original_filename: str
    origin: str
    jurisdiction: str
    staged_path: Path
    media_kind: str
    cleared: bool
    sha256: str
    extracted_text: str | None = None
    needs_ocr: bool = False


@dataclass(frozen=True)
class FoiaPackageStageResult:
    case_id: str
    jurisdiction: str
    source_domain: str
    package_origin: str
    staging_root: Path
    assets: tuple[FoiaStagedAsset, ...]


ZipBytesSource = Callable[[], bytes]


class FoiaPackageDownloader:
    """Unpack FOIA ZIP attachments into a quarantined ``raw_foia`` tree."""

    def stage(
        self,
        *,
        case_id: str,
        jurisdiction: str,
        source_domain: str,
        package_origin: str,
        zip_path: Path | str | None = None,
        zip_bytes: bytes | None = None,
        zip_bytes_source: ZipBytesSource | None = None,
        staging_parent: Path | str | None = None,
    ) -> FoiaPackageStageResult:
        payload = self._read_zip_payload(zip_path, zip_bytes, zip_bytes_source)
        parent = Path(staging_parent) if staging_parent is not None else Path.cwd()
        staging_root = parent / "raw_foia" / case_id
        staging_root.mkdir(parents=True, exist_ok=True)

        effective_jurisdiction = jurisdiction
        assets: list[FoiaStagedAsset] = []

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = self._read_manifest(archive)
            if manifest.get("jurisdiction"):
                effective_jurisdiction = str(manifest["jurisdiction"])

            for info in archive.infolist():
                if info.is_dir():
                    continue
                member = PurePosixPath(info.filename)
                if member.name == FOIA_MANIFEST_NAME:
                    continue

                data = archive.read(info.filename)
                original_filename = member.name
                origin = self._origin_label(info.filename, manifest, package_origin)
                staged_path = self._unique_staged_path(staging_root, original_filename, origin)
                staged_path.write_bytes(data)

                media_kind = self._infer_media_kind(original_filename)
                sha = hashlib.sha256(data).hexdigest()
                asset_id = self._asset_id(case_id, original_filename, origin)

                extracted_text: str | None = None
                needs_ocr = False
                if original_filename.lower().endswith(".pdf"):
                    extracted_text = extract_pdf_text(data)
                    if not extracted_text:
                        needs_ocr = True

                assets.append(
                    FoiaStagedAsset(
                        asset_id=asset_id,
                        case_id=case_id,
                        original_filename=original_filename,
                        origin=origin,
                        jurisdiction=effective_jurisdiction,
                        staged_path=staged_path,
                        media_kind=media_kind,
                        cleared=False,
                        sha256=sha,
                        extracted_text=extracted_text,
                        needs_ocr=needs_ocr,
                    )
                )

        self._write_stage_manifest(
            staging_root,
            case_id=case_id,
            jurisdiction=effective_jurisdiction,
            source_domain=source_domain,
            package_origin=package_origin,
            assets=assets,
        )
        return FoiaPackageStageResult(
            case_id=case_id,
            jurisdiction=effective_jurisdiction,
            source_domain=source_domain,
            package_origin=package_origin,
            staging_root=staging_root,
            assets=tuple(assets),
        )

    def _read_zip_payload(
        self,
        zip_path: Path | str | None,
        zip_bytes: bytes | None,
        zip_bytes_source: ZipBytesSource | None,
    ) -> bytes:
        sources = [zip_path is not None, zip_bytes is not None, zip_bytes_source is not None]
        if sum(sources) != 1:
            raise ValueError("Provide exactly one of zip_path, zip_bytes, or zip_bytes_source")

        if zip_path is not None:
            return Path(zip_path).read_bytes()
        if zip_bytes is not None:
            return zip_bytes
        assert zip_bytes_source is not None
        return zip_bytes_source()

    def _read_manifest(self, archive: zipfile.ZipFile) -> dict[str, Any]:
        try:
            raw = archive.read(FOIA_MANIFEST_NAME)
        except KeyError:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _origin_label(
        self, member_name: str, manifest: dict[str, Any], package_origin: str
    ) -> str:
        attachments = manifest.get("attachments")
        if isinstance(attachments, dict) and member_name in attachments:
            return str(attachments[member_name])
        if isinstance(attachments, dict):
            basename = PurePosixPath(member_name).name
            if basename in attachments:
                return str(attachments[basename])
        return f"{package_origin}:{member_name}"

    def _unique_staged_path(
        self, staging_root: Path, original_filename: str, origin: str
    ) -> Path:
        target = staging_root / original_filename
        if not target.exists():
            return target
        digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()[:8]
        return staging_root / f"{digest}_{original_filename}"

    def _infer_media_kind(self, original_filename: str) -> str:
        lowered = original_filename.lower()
        if "ring" in lowered and lowered.endswith(".mp4"):
            return "dashcam_mp4"
        if "bodycam" in lowered or "bwc" in lowered:
            return "bodycam_mp4"
        if "dashcam" in lowered:
            return "dashcam_mp4"
        if "911" in lowered or lowered.endswith(".wav"):
            return "call_911_wav"
        suffix = PurePosixPath(lowered).suffix
        return _MEDIA_KIND_BY_SUFFIX.get(suffix, "foia_attachment")

    def _asset_id(self, case_id: str, original_filename: str, origin: str) -> str:
        digest = hashlib.sha256(
            f"{case_id}\0{original_filename}\0{origin}".encode("utf-8")
        ).hexdigest()[:16]
        return f"foia_{digest}"

    def _write_stage_manifest(
        self,
        staging_root: Path,
        *,
        case_id: str,
        jurisdiction: str,
        source_domain: str,
        package_origin: str,
        assets: list[FoiaStagedAsset],
    ) -> None:
        manifest = {
            "case_id": case_id,
            "jurisdiction": jurisdiction,
            "source_domain": source_domain,
            "package_origin": package_origin,
            "cleared": False,
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "original_filename": asset.original_filename,
                    "origin": asset.origin,
                    "jurisdiction": asset.jurisdiction,
                    "staged_path": str(asset.staged_path),
                    "media_kind": asset.media_kind,
                    "cleared": asset.cleared,
                    "sha256": asset.sha256,
                    "extracted_text": asset.extracted_text,
                    "needs_ocr": asset.needs_ocr,
                }
                for asset in assets
            ],
        }
        (staging_root / "staged_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Best-effort text pull from tiny FOIA PDFs (no OCR dependency)."""
    if not pdf_bytes.startswith(b"%PDF"):
        return ""

    chunks: list[str] = []
    literal_pattern = re.compile(rb"\(([^\\)]*(?:\\.[^\\)]*)*)\)\s*Tj")
    for match in literal_pattern.finditer(pdf_bytes):
        chunks.append(_decode_pdf_literal(match.group(1)))

    array_pattern = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
    for match in array_pattern.finditer(pdf_bytes):
        segment = match.group(1)
        for inner in literal_pattern.finditer(segment):
            chunks.append(_decode_pdf_literal(inner.group(1)))

    return " ".join(part for part in chunks if part).strip()


def _decode_pdf_literal(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text.strip()


def build_text_pdf_payload(text: str) -> bytes:
    """Build a minimal valid PDF with a single ``Tj`` string (tests & fixtures)."""
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_scan_pdf_payload() -> bytes:
    """PDF shell with no text operators (forces ``needs_ocr``)."""
    stream = b"0 0 0 rg 0 0 612 792 re f"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_fixture_zip_bytes() -> bytes:
    """Synthetic FOIA package for offline tests (no live downloads)."""
    manifest = {
        "jurisdiction": "Marlow County, WA",
        "attachments": {
            "officer_bodycam.mp4": "state_public_records:agency_bwc_primary",
            "ring_doorbell_neighbor.mp4": "third_party_neighbor:ring_doorbell_submission",
            "report.pdf": "state_public_records:investigator_summary",
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(FOIA_MANIFEST_NAME, json.dumps(manifest, indent=2))
        archive.writestr("officer_bodycam.mp4", b"ftypisom" + b"\x00" * 32)
        archive.writestr("ring_doorbell_neighbor.mp4", b"ftypisom" + b"\x01" * 32)
        archive.writestr(
            "report.pdf",
            build_text_pdf_payload("Incident occurred at 1200 Block Elm."),
        )
        archive.writestr("scan_attachment.pdf", build_scan_pdf_payload())
        archive.writestr("dispatch_911.wav", b"RIFF" + b"\x00" * 28 + b"WAVEfmt ")
    return buffer.getvalue()