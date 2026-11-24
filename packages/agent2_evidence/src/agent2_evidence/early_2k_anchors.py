"""Early illustrative 2K plate generation and DRAFT spatial anchors.

No sockets and no paid APIs: callers inject an image client and a vision client.
Clean plates stay untouched on disk; grid grounding runs on a margin-padded inspection
copy only. Part 1 locks coordinates before Agent 3 scripting (Law 4).
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from shared_contracts.grid import grid_cell_to_pixel_and_zoom

ILLUSTRATIVE_DISCLAIMER = "ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO"
GEMINI_IMAGE_PROVIDER_KEY = "gemini_image"
VISION_GRID_ROLE = "vision_grid"
MARGIN_PX = 64
MAX_CLUES_PER_PASS = 8
DEFAULT_WIDTH_PX = 2560
DEFAULT_HEIGHT_PX = 1440
_LOCK_SEQUENCE = ("DRAFT", "IN_REVIEW", "LOCKED")

_COLUMNS = tuple(chr(ord("A") + index) for index in range(10))
_ROWS = tuple(str(index) for index in range(1, 11))


@runtime_checkable
class ImageClient(Protocol):
    """Generates a monochrome illustrative clean plate at ``target_px``."""

    def generate_clean_plate(
        self,
        *,
        episode_id: str,
        clue_names: Sequence[str],
        style_payload: Mapping[str, Any],
        width_px: int,
        height_px: int,
        provider_model_id: str,
    ) -> bytes: ...


@runtime_checkable
class VisionClient(Protocol):
    """Returns grid grounding for each clue on an inspection PNG."""

    def ground_clues(
        self,
        *,
        inspection_png: bytes,
        clue_names: Sequence[str],
        provider_model_id: str,
    ) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class PhysicalClueRef:
    clue_name: str
    cited_fact_id: str | None = None


@dataclass(frozen=True, slots=True)
class StillAssetRecord:
    still_2k_id: str
    episode_id: str
    asset_path: str
    asset_sha256: str
    width_px: int
    height_px: int
    is_illustrative_reconstruction: int
    disclaimer_label_text: str
    clean_png: bytes


@dataclass(frozen=True, slots=True)
class SpatialAnchorRecord:
    anchor_id: str
    episode_id: str
    still_2k_id: str
    clue_name: str
    cited_fact_id: str | None
    grid_cell: str
    span_cols: float
    span_rows: float
    x_px: int
    y_px: int
    target_zoom: float
    travel_axis: str | None
    lock_status: str
    locked_by: str | None = None
    locked_at: int | None = None
    still_asset_sha256: str | None = None
    sub_quadrant: str | None = None


@dataclass(frozen=True, slots=True)
class Early2KPassResult:
    still: StillAssetRecord
    anchors: tuple[SpatialAnchorRecord, ...]
    inspection_png: bytes
    clean_sha256: str


def cluster_physical_clues(
    clues: Sequence[str | PhysicalClueRef],
    *,
    max_per_pass: int = MAX_CLUES_PER_PASS,
) -> list[list[PhysicalClueRef]]:
    """Merge duplicate clue strings and chunk into passes of at most eight clues."""
    if max_per_pass < 1 or max_per_pass > MAX_CLUES_PER_PASS:
        raise ValueError(f"max_per_pass must be 1..{MAX_CLUES_PER_PASS}")
    ordered: list[PhysicalClueRef] = []
    seen: set[str] = set()
    for item in clues:
        if isinstance(item, PhysicalClueRef):
            ref = item
        else:
            ref = PhysicalClueRef(clue_name=str(item))
        key = ref.clue_name.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(PhysicalClueRef(clue_name=ref.clue_name.strip(), cited_fact_id=ref.cited_fact_id))
    if not ordered:
        return []
    batches: list[list[PhysicalClueRef]] = []
    for offset in range(0, len(ordered), max_per_pass):
        batches.append(ordered[offset : offset + max_per_pass])
    return batches


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def resolve_gemini_image_spec(registry: Mapping[str, Any]) -> tuple[str, int, int]:
    """Read official image provider dimensions from ``providers.yaml`` structure."""
    providers = registry.get("providers")
    if not isinstance(providers, Mapping):
        raise ValueError("registry must include providers mapping")
    spec = providers.get(GEMINI_IMAGE_PROVIDER_KEY)
    if not isinstance(spec, Mapping):
        raise ValueError(f"missing provider {GEMINI_IMAGE_PROVIDER_KEY!r}")
    model_id = str(spec.get("model_id") or "")
    if not model_id:
        raise ValueError("gemini_image.model_id is required")
    target = spec.get("target_px", [DEFAULT_WIDTH_PX, DEFAULT_HEIGHT_PX])
    if not isinstance(target, Sequence) or len(target) < 2:
        raise ValueError("gemini_image.target_px must be [width, height]")
    width = int(target[0])
    height = int(target[1])
    if width < 1920 or height < 1080:
        raise ValueError("gemini_image target must be >= 1920x1080")
    return model_id, width, height


def resolve_vision_grid_model_id(registry: Mapping[str, Any]) -> str:
    """Pick the DeepSeek vision-grid model id from the registry (no hardcoded SKU)."""
    providers = registry.get("providers")
    if not isinstance(providers, Mapping):
        raise ValueError("registry must include providers mapping")
    chat = providers.get("deepseek_chat")
    if not isinstance(chat, Mapping):
        raise ValueError("missing deepseek_chat provider")
    models = chat.get("models")
    if not isinstance(models, Sequence):
        raise ValueError("deepseek_chat.models must be a sequence")
    for entry in models:
        if not isinstance(entry, Mapping):
            continue
        roles = entry.get("roles") or []
        if VISION_GRID_ROLE in roles:
            model_id = str(entry.get("id") or "")
            if model_id:
                return model_id
    raise ValueError("no model with vision_grid role in registry")


def build_inspection_png_with_margin(
    clean_png: bytes,
    *,
    width_px: int,
    height_px: int,
    margin_px: int = MARGIN_PX,
) -> bytes:
    """Pad a clean plate for grid labeling without mutating ``clean_png``."""
    if margin_px < 1:
        raise ValueError("margin_px must be positive")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - Pillow present in task venv
        raise RuntimeError("Pillow is required to build inspection margin PNGs") from exc

    with Image.open(io.BytesIO(clean_png)) as plate:
        plate = plate.convert("RGB")
        if plate.size != (width_px, height_px):
            plate = plate.resize((width_px, height_px))

    outer_w = width_px + (margin_px * 2)
    outer_h = height_px + (margin_px * 2)
    canvas = Image.new("RGB", (outer_w, outer_h), "#3A3A3A")
    canvas.paste(plate, (margin_px, margin_px))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:  # noqa: BLE001
        font = None  # type: ignore[assignment]

    # Column letters along top margin; row numbers along left margin.
    for col, label in enumerate(_COLUMNS):
        x = margin_px + int((col + 0.5) * width_px / 10)
        draw.text((x, margin_px // 4), label, fill="#E9E2D2", font=font, anchor="mm")
    for row, label in enumerate(_ROWS):
        y = margin_px + int((row + 0.5) * height_px / 10)
        draw.text((margin_px // 4, y), label, fill="#E9E2D2", font=font, anchor="mm")

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def grounding_to_anchor_fields(
    grounding: Mapping[str, Any],
    *,
    width_px: int,
    height_px: int,
) -> dict[str, Any]:
    grid_cell = str(grounding["grid_cell"])
    span_cols = float(grounding.get("span_cols", 1.0))
    span_rows = float(grounding.get("span_rows", 1.0))
    mapped = grid_cell_to_pixel_and_zoom(
        grid_cell,
        span_cols,
        span_rows,
        width_px,
        height_px,
    )
    return {
        "grid_cell": grid_cell,
        "span_cols": span_cols,
        "span_rows": span_rows,
        "x_px": mapped["x_px"],
        "y_px": mapped["y_px"],
        "target_zoom": mapped["target_zoom"],
        "sub_quadrant": grounding.get("sub_quadrant"),
    }


def assert_lock_transition(current: str, nxt: str) -> None:
    if current == nxt:
        return
    try:
        idx = _LOCK_SEQUENCE.index(current)
        nxt_idx = _LOCK_SEQUENCE.index(nxt)
    except ValueError as exc:
        raise ValueError(f"unknown lock_status {current!r} -> {nxt!r}") from exc
    if nxt_idx != idx + 1:
        raise ValueError(f"invalid lock transition {current!r} -> {nxt!r}")


class Early2KAnchorLockService:
    """Generate illustrative stills, draft spatial anchors, and optional DB rows."""

    def __init__(
        self,
        image_client: ImageClient,
        vision_client: VisionClient,
        *,
        provider_registry: Mapping[str, Any],
    ) -> None:
        self._image = image_client
        self._vision = vision_client
        self._registry = provider_registry

    def run_pass(
        self,
        *,
        episode_id: str,
        still_2k_id: str,
        clue_refs: Sequence[str | PhysicalClueRef],
        style_payload: Mapping[str, Any],
        asset_path: str,
    ) -> Early2KPassResult:
        batches = cluster_physical_clues(clue_refs)
        if len(batches) != 1:
            raise ValueError("run_pass expects a single clustered pass (<=8 clues)")
        batch = batches[0]
        image_model, width_px, height_px = resolve_gemini_image_spec(self._registry)
        vision_model = resolve_vision_grid_model_id(self._registry)
        clue_names = [ref.clue_name for ref in batch]

        clean_png = self._image.generate_clean_plate(
            episode_id=episode_id,
            clue_names=clue_names,
            style_payload=style_payload,
            width_px=width_px,
            height_px=height_px,
            provider_model_id=image_model,
        )
        clean_sha = sha256_hex(clean_png)
        inspection = build_inspection_png_with_margin(
            clean_png,
            width_px=width_px,
            height_px=height_px,
        )
        if sha256_hex(clean_png) != clean_sha:
            raise RuntimeError("clean plate hash changed after inspection copy")

        groundings = self._vision.ground_clues(
            inspection_png=inspection,
            clue_names=clue_names,
            provider_model_id=vision_model,
        )
        if len(groundings) != len(batch):
            raise ValueError("vision grounding count must match clue batch")

        still = StillAssetRecord(
            still_2k_id=still_2k_id,
            episode_id=episode_id,
            asset_path=asset_path,
            asset_sha256=clean_sha,
            width_px=width_px,
            height_px=height_px,
            is_illustrative_reconstruction=1,
            disclaimer_label_text=ILLUSTRATIVE_DISCLAIMER,
            clean_png=clean_png,
        )
        anchors: list[SpatialAnchorRecord] = []
        for ref, grounding in zip(batch, groundings, strict=True):
            fields = grounding_to_anchor_fields(grounding, width_px=width_px, height_px=height_px)
            anchor_id = f"{still_2k_id}_anc_{uuid.uuid4().hex[:8]}"
            anchors.append(
                SpatialAnchorRecord(
                    anchor_id=anchor_id,
                    episode_id=episode_id,
                    still_2k_id=still_2k_id,
                    clue_name=ref.clue_name,
                    cited_fact_id=ref.cited_fact_id,
                    grid_cell=fields["grid_cell"],
                    span_cols=fields["span_cols"],
                    span_rows=fields["span_rows"],
                    x_px=fields["x_px"],
                    y_px=fields["y_px"],
                    target_zoom=fields["target_zoom"],
                    travel_axis=None,
                    lock_status="DRAFT",
                    sub_quadrant=fields.get("sub_quadrant"),
                )
            )
        return Early2KPassResult(
            still=still,
            anchors=tuple(anchors),
            inspection_png=inspection,
            clean_sha256=clean_sha,
        )

    def persist_still_asset(self, conn: sqlite3.Connection, still: StillAssetRecord, *, created_at: int) -> None:
        conn.execute(
            """INSERT INTO still_assets (
                 still_2k_id, episode_id, asset_path, asset_sha256, width_px, height_px,
                 is_illustrative_reconstruction, disclaimer_label_text, created_at
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                still.still_2k_id,
                still.episode_id,
                still.asset_path,
                still.asset_sha256,
                still.width_px,
                still.height_px,
                still.is_illustrative_reconstruction,
                still.disclaimer_label_text,
                created_at,
            ),
        )

    def persist_draft_anchors(self, conn: sqlite3.Connection, anchors: Sequence[SpatialAnchorRecord]) -> None:
        for anchor in anchors:
            conn.execute(
                """INSERT INTO spatial_anchors (
                     anchor_id, episode_id, still_2k_id, clue_name, cited_fact_id,
                     grid_cell, span_cols, span_rows, x_px, y_px, target_zoom, travel_axis, lock_status
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    anchor.anchor_id,
                    anchor.episode_id,
                    anchor.still_2k_id,
                    anchor.clue_name,
                    anchor.cited_fact_id,
                    anchor.grid_cell,
                    anchor.span_cols,
                    anchor.span_rows,
                    anchor.x_px,
                    anchor.y_px,
                    anchor.target_zoom,
                    anchor.travel_axis,
                    anchor.lock_status,
                ),
            )

    def transition_anchor_lock(
        self,
        conn: sqlite3.Connection,
        *,
        anchor_id: str,
        new_status: str,
        locked_by: str | None = None,
        locked_at: int | None = None,
        still_asset_sha256: str | None = None,
    ) -> None:
        row = conn.execute(
            "SELECT lock_status FROM spatial_anchors WHERE anchor_id = ?",
            (anchor_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown anchor_id {anchor_id!r}")
        current = str(row[0])
        assert_lock_transition(current, new_status)
        if new_status == "LOCKED":
            if not locked_by or locked_at is None or not still_asset_sha256:
                raise ValueError("LOCKED anchors require locked_by, locked_at, and still_asset_sha256")
            conn.execute(
                """UPDATE spatial_anchors
                   SET lock_status = ?, locked_by = ?, locked_at = ?, still_asset_sha256 = ?
                   WHERE anchor_id = ?""",
                (new_status, locked_by, locked_at, still_asset_sha256, anchor_id),
            )
        else:
            conn.execute(
                "UPDATE spatial_anchors SET lock_status = ? WHERE anchor_id = ?",
                (new_status, anchor_id),
            )