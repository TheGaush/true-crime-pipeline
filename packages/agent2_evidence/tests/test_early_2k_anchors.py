"""Offline tests for early illustrative 2K anchor lock."""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image

from agent2_evidence.early_2k_anchors import (
    ILLUSTRATIVE_DISCLAIMER,
    MARGIN_PX,
    Early2KAnchorLockService,
    PhysicalClueRef,
    build_inspection_png_with_margin,
    cluster_physical_clues,
    grounding_to_anchor_fields,
    resolve_gemini_image_spec,
    sha256_hex,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = yaml.safe_load((ROOT / "providers.yaml").read_text(encoding="utf-8"))


def _tiny_png(width: int, height: int, color: tuple[int, int, int] = (27, 27, 29)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class MockImageClient:
    def __init__(self, *, calls: list[dict[str, Any]] | None = None) -> None:
        self.calls = calls if calls is not None else []

    def generate_clean_plate(
        self,
        *,
        episode_id: str,
        clue_names,
        style_payload,
        width_px: int,
        height_px: int,
        provider_model_id: str,
    ) -> bytes:
        self.calls.append(
            {
                "episode_id": episode_id,
                "clue_names": list(clue_names),
                "width_px": width_px,
                "height_px": height_px,
                "provider_model_id": provider_model_id,
                "style": dict(style_payload),
            }
        )
        return _tiny_png(width_px, height_px)


class MockVisionClient:
    def __init__(self, groundings: list[dict[str, Any]], *, calls: list[dict[str, Any]] | None = None) -> None:
        self.groundings = groundings
        self.calls = calls if calls is not None else []

    def ground_clues(self, *, inspection_png: bytes, clue_names, provider_model_id: str):
        self.calls.append(
            {
                "inspection_len": len(inspection_png),
                "clue_names": list(clue_names),
                "provider_model_id": provider_model_id,
            }
        )
        return self.groundings


def test_cluster_physical_clues_caps_at_eight_unique() -> None:
    clues = [f"clue_{index}" for index in range(12)]
    batches = cluster_physical_clues(clues)
    assert len(batches) == 2
    assert len(batches[0]) == 8
    assert len(batches[1]) == 4
    assert batches[0][0].clue_name == "clue_0"


def test_inspection_margin_preserves_clean_sha256() -> None:
    clean = _tiny_png(2560, 1440)
    before = sha256_hex(clean)
    inspection = build_inspection_png_with_margin(clean, width_px=2560, height_px=1440)
    after = sha256_hex(clean)
    assert before == after
    with Image.open(io.BytesIO(inspection)) as outer:
        assert outer.size == (2560 + MARGIN_PX * 2, 1440 + MARGIN_PX * 2)


def test_span_two_cols_zoom_between_16_and_18() -> None:
    mapped = grounding_to_anchor_fields(
        {"grid_cell": "D4", "span_cols": 2.0, "span_rows": 4.5},
        width_px=2560,
        height_px=1440,
    )
    assert mapped["target_zoom"] >= 1.6
    assert mapped["target_zoom"] <= 1.8
    assert mapped["x_px"] == grid_expected_x("D4", 2560)
    assert mapped["y_px"] == grid_expected_y("4", 1440)


def grid_expected_x(grid_cell: str, width: int) -> int:
    col_index = ord(grid_cell[0]) - ord("A")
    return ((2 * col_index + 1) * width + 10) // 20


def grid_expected_y(row_label: str, height: int) -> int:
    row_index = int(row_label) - 1
    return ((2 * row_index + 1) * height + 10) // 20


def test_run_pass_illustrative_still_and_draft_anchors() -> None:
    image_model, width_px, height_px = resolve_gemini_image_spec(REGISTRY)
    image = MockImageClient()
    vision = MockVisionClient(
        [
            {
                "grid_cell": "E5",
                "sub_quadrant": "SW",
                "span_cols": 1.0,
                "span_rows": 1.0,
            }
        ]
    )
    service = Early2KAnchorLockService(image, vision, provider_registry=REGISTRY)
    style = {"ink_hex": "#1B1B1D", "paper_bg_hex": "#E9E2D2"}

    result = service.run_pass(
        episode_id="ep_test",
        still_2k_id="still_test",
        clue_refs=[PhysicalClueRef("overturned table", cited_fact_id="fact_1")],
        style_payload=style,
        asset_path="artifacts/still_test.png",
    )

    assert result.still.is_illustrative_reconstruction == 1
    assert result.still.disclaimer_label_text == ILLUSTRATIVE_DISCLAIMER
    assert result.still.asset_sha256 == sha256_hex(result.still.clean_png)
    assert len(result.anchors) == 1
    anchor = result.anchors[0]
    assert anchor.lock_status == "DRAFT"
    assert anchor.locked_by is None
    assert 1.6 <= anchor.target_zoom <= 3.8
    assert image.calls[0]["provider_model_id"] == image_model
    assert image.calls[0]["width_px"] == width_px
    assert vision.calls[0]["inspection_len"] > len(result.still.clean_png)


def test_sqlite_lock_transition_requires_proof() -> None:
    schema_path = ROOT / "schema" / "pipeline.sql"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        """INSERT INTO cases (
             case_id, defendant_name, incident_year, jurisdiction, verification_source,
             disposition_status, conviction_confirmed, created_at, updated_at
           ) VALUES ('case_1','Jane Doe',2020,'OH','courtlistener','AFFIRMED',1,1,1)"""
    )
    conn.execute(
        """INSERT INTO episodes (
             episode_id, case_id, state, cold_open_archetype, updated_at, created_at
           ) VALUES ('ep_1','case_1','EVIDENCE_AND_2K_LOCKED','ALIBI_THAT_CRACKED',1,1)"""
    )

    image = MockImageClient()
    vision = MockVisionClient(
        [{"grid_cell": "B2", "span_cols": 1.0, "span_rows": 1.0}],
    )
    service = Early2KAnchorLockService(image, vision, provider_registry=REGISTRY)
    outcome = service.run_pass(
        episode_id="ep_1",
        still_2k_id="still_1",
        clue_refs=["broken chair"],
        style_payload={"paper_bg_hex": "#E9E2D2"},
        asset_path="still_1.png",
    )
    service.persist_still_asset(conn, outcome.still, created_at=100)
    service.persist_draft_anchors(conn, outcome.anchors)
    conn.commit()

    anchor_id = outcome.anchors[0].anchor_id
    assert conn.execute(
        "SELECT lock_status FROM spatial_anchors WHERE anchor_id = ?",
        (anchor_id,),
    ).fetchone()["lock_status"] == "DRAFT"

    with pytest.raises(sqlite3.Error):
        conn.execute(
            "UPDATE spatial_anchors SET lock_status = 'LOCKED' WHERE anchor_id = ?",
            (anchor_id,),
        )
        conn.commit()

    service.transition_anchor_lock(
        conn,
        anchor_id=anchor_id,
        new_status="IN_REVIEW",
    )
    service.transition_anchor_lock(
        conn,
        anchor_id=anchor_id,
        new_status="LOCKED",
        locked_by="editor_a",
        locked_at=200,
        still_asset_sha256=outcome.still.asset_sha256,
    )
    conn.commit()
    locked = conn.execute(
        "SELECT lock_status, still_asset_sha256 FROM spatial_anchors WHERE anchor_id = ?",
        (anchor_id,),
    ).fetchone()
    assert locked["lock_status"] == "LOCKED"
    assert locked["still_asset_sha256"] == outcome.still.asset_sha256
    conn.close()