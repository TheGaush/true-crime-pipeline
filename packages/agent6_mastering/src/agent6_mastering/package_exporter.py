"""Stage an upload folder and rename it only after every file is present."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path


REQUIRED = (
    "final_1080p30.mp4",
    "thumbnails/variant_a.png",
    "thumbnails/variant_b.png",
    "thumbnails/variant_c.png",
    "chapters.txt",
    "seo_metadata.json",
    "provenance_bundle.json",
    "qa_certificate.json",
)


class ExportError(RuntimeError):
    pass


def export_package(root: str, slug: str, files: dict[str, bytes], meta: dict) -> Path:
    base = Path(root)
    staging = base / f".staging_{slug}"
    final = base / slug
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    seo = dict(meta.get("seo", {}))
    seo["youtube_synthetic_disclosure_required"] = True
    payload = {
        "final_1080p30.mp4": files["final_1080p30.mp4"],
        "thumbnails/variant_a.png": files["variant_a"],
        "thumbnails/variant_b.png": files["variant_b"],
        "thumbnails/variant_c.png": files["variant_c"],
        "chapters.txt": files["chapters"],
        "seo_metadata.json": (json.dumps(seo, indent=2) + "\n").encode(),
        "provenance_bundle.json": (json.dumps(meta["provenance"], indent=2) + "\n").encode(),
        "qa_certificate.json": (json.dumps(meta["qa"], indent=2) + "\n").encode(),
    }
    if not meta["qa"].get("passed"):
        raise ExportError("qa certificate is not passing")
    for name, data in payload.items():
        path = staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    checksums = {name: hashlib.sha256((staging / name).read_bytes()).hexdigest() for name in REQUIRED}
    (staging / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n", encoding="utf8")
    if final.exists():
        shutil.rmtree(final)
    os.replace(staging, final)
    if not all((final / name).is_file() for name in REQUIRED):
        raise ExportError("package is incomplete")
    return final
