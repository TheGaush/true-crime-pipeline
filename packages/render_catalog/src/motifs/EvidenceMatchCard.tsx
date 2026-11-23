/**
 * Motif 12 — EvidenceMatchCard.
 *
 * Symmetric forensic dossier frames. Each exhibit is drawn with object-fit
 * contain inside a shared box size, so a wide plate and a tall plate stay
 * letterboxed or pillarboxed instead of stretching. Crimson comparison arrows
 * draw on across the gutter. camera_shutter cues use the 48 kHz mix clock
 * (90 ms, -8 dBTP, 60 ms cooldown).
 *
 * The frozen catalog name at slot 12 stays ChapterSlateTransition.
 * MOTIF_REGISTRY_V1 stays the four MVP motifs. This file does not amend that
 * contract. Task 110 and Task 114 stay on their own branches.
 *
 * Safe-zone pixel boundaries used by later callout math: 96px horizontal,
 * 54px vertical. The YouTube insets (108 top, 194 bottom) are stricter on Y.
 */

export const EVIDENCE_MATCH_CARD_ID = "EvidenceMatchCard" as const;
export const EVIDENCE_MATCH_CARD_OWNER = "render_catalog" as const;
export const EVIDENCE_MOTIF_NUMBER = 12 as const;
export const FROZEN_CATALOG_SLOT_12 = "ChapterSlateTransition" as const;
export const SYMMETRIC_FRAMING_INVARIANT = "Symmetric Framing Invariant" as const;

export const CAMERA_SHUTTER_CUE = "camera_shutter" as const;
export const EXHIBIT_OBJECT_FIT = "contain" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;

/** Minimum inset from the 1920x1080 frame edge. Task 146 reads these bounds. */
export const SAFE_MARGIN_X = 96;
export const SAFE_MARGIN_Y = 54;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const END_SCREEN_MASK_H = 48;
export const EXCLUSION_WIDTH_RATIO = 0.22;
export const EXCLUSION_HEIGHT_RATIO = 0.14;

export const GUTTER_W = 160;
export const FRAME_PAD = 16;
export const CAPTION_H = 64;
export const MAX_LABEL_WORDS = 12;
export const ARROW_GAP = 16;
export const ARROW_DRAW_FRAMES = 18;
export const ARROW_THICKNESS = 14;
export const ARROW_HEAD = 12;
export const ARROW_SHAFT = 6;

export const EVIDENCE_CRIMSON = "#C92A2A";
export const PAPER_BG = "#E9E2D2";
export const INK = "#1B1B1D";
export const SLATE = "#3A4F66";
export const MAT = "#C4A574";

export const MIX_SAMPLE_RATE_HZ = 48_000;
export const SAMPLES_PER_FRAME = MIX_SAMPLE_RATE_HZ / FRAME_FPS;
export const COOLDOWN_MS = 60;
export const COOLDOWN_SAMPLES = (COOLDOWN_MS * MIX_SAMPLE_RATE_HZ) / 1_000;
export const CAMERA_SHUTTER_DURATION_MS = 90;
export const CAMERA_SHUTTER_DURATION_SAMPLES = CAMERA_SHUTTER_DURATION_MS * (MIX_SAMPLE_RATE_HZ / 1_000);
export const CAMERA_SHUTTER_DBTP = -8;
export const TRUE_PEAK_CEILING_DBTP = -1;
export const GAIN_UNIT_SCALE = 1_000_000_000;
export const SHUTTER_FRAME_LEFT = 0;
export const SHUTTER_FRAME_RIGHT = 2;

export const CAMERA_SHUTTER_GAIN_UNITS = linearGainUnits(CAMERA_SHUTTER_DBTP);
export const TRUE_PEAK_CEILING_UNITS = linearGainUnits(TRUE_PEAK_CEILING_DBTP);

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const SRC_PATTERN = /^[A-Za-z0-9_./-]{1,200}$/;
const MAX_FRAME = 2_000_000;
const MAX_INTRINSIC = 100_000;

export type CssValue = string | number;
export type Side = "left" | "right";

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type MatchChild = MatchNode | string;

export type MatchNode = {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, CssValue>>;
    readonly children?: MatchChild | readonly MatchChild[];
  };
};

export type ForensicExhibit = {
  readonly exhibit_id: string;
  readonly fact_id: string;
  readonly label: string;
  readonly intrinsic_width: number;
  readonly intrinsic_height: number;
  readonly src: string;
};

export type EvidenceMatchCardProps = {
  readonly left: ForensicExhibit;
  readonly right: ForensicExhibit;
  readonly frame: number;
  readonly sceneId?: string;
  readonly isEndScreen?: boolean;
  readonly shutterFrameLeft?: number;
  readonly shutterFrameRight?: number;
};

export type FittedContain = {
  readonly width: number;
  readonly height: number;
  readonly offsetX: number;
  readonly offsetY: number;
};

export type PlacedExhibit = {
  readonly side: Side;
  readonly exhibit_id: string;
  readonly fact_id: string;
  readonly src: string;
  readonly label: string;
  readonly display: string;
  readonly wordCount: number;
  readonly clamped: boolean;
  readonly intrinsicWidth: number;
  readonly intrinsicHeight: number;
  readonly objectFit: typeof EXHIBIT_OBJECT_FIT;
  readonly frameBox: Rect;
  readonly well: Rect;
  readonly caption: Rect;
  readonly fitted: Rect;
  readonly fittedLocal: FittedContain;
};

export type PlacedArrow = {
  readonly direction: Side;
  readonly box: Rect;
  readonly revealed: number;
  readonly color: typeof EVIDENCE_CRIMSON;
};

export type ShutterCue = {
  readonly cue_id: string;
  readonly cue: typeof CAMERA_SHUTTER_CUE;
  readonly scene_id: string;
  readonly exhibit_id: string;
  readonly side: Side;
  readonly start_sample: number;
  readonly sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  readonly start_frame: number;
  readonly offset_ms: number;
  readonly duration_samples: typeof CAMERA_SHUTTER_DURATION_SAMPLES;
  readonly cooldown_ms: typeof COOLDOWN_MS;
  readonly gain_units: number;
  readonly gain_unit_scale: typeof GAIN_UNIT_SCALE;
  readonly peak_dbtp: number;
  readonly burst: boolean;
  readonly tapered: boolean;
};

export type SuppressedShutter = {
  readonly cue: typeof CAMERA_SHUTTER_CUE;
  readonly exhibit_id: string;
  readonly side: Side;
  readonly start_frame: number;
  readonly start_sample: number;
  readonly reason: "cooldown";
};

export type EvidenceMatchCardLayout = {
  readonly motif: typeof EVIDENCE_MATCH_CARD_ID;
  readonly owner: typeof EVIDENCE_MATCH_CARD_OWNER;
  readonly motifNumber: typeof EVIDENCE_MOTIF_NUMBER;
  readonly frozenCatalogSlot: typeof FROZEN_CATALOG_SLOT_12;
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly gutter: Rect;
  readonly left: PlacedExhibit;
  readonly right: PlacedExhibit;
  readonly arrows: {
    readonly progress: number;
    readonly revealed: number;
    readonly full: number;
    readonly left: PlacedArrow;
    readonly right: PlacedArrow;
  };
  readonly cues: readonly ShutterCue[];
  readonly cuesStarted: readonly ShutterCue[];
  readonly suppressed: readonly SuppressedShutter[];
};

type NormalizedExhibit = {
  readonly side: Side;
  readonly exhibit_id: string;
  readonly fact_id: string;
  readonly src: string;
  readonly label: string;
  readonly display: string;
  readonly wordCount: number;
  readonly clamped: boolean;
  readonly intrinsicWidth: number;
  readonly intrinsicHeight: number;
};

type Prepared = {
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly left: NormalizedExhibit;
  readonly right: NormalizedExhibit;
  readonly cues: readonly ShutterCue[];
  readonly suppressed: readonly SuppressedShutter[];
};

export class EvidenceMatchCardError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvidenceMatchCardError";
  }
}

export function linearGainUnits(dbtp: number): number {
  if (!Number.isFinite(dbtp) || dbtp > TRUE_PEAK_CEILING_DBTP) {
    fail(`nominal peak ${dbtp} dBTP exceeds ${TRUE_PEAK_CEILING_DBTP} dBTP`);
  }
  return Math.floor(10 ** (dbtp / 20) * GAIN_UNIT_SCALE + 1e-6);
}

export function mixOffsetMs(sample: number): number {
  const rate = BigInt(MIX_SAMPLE_RATE_HZ);
  const scaled = BigInt(sample) * 1_000_000_000n;
  const rounded = (scaled + rate / 2n) / rate;
  return Number(rounded) / 1_000_000;
}

export function arrowProgress(frame: number): number {
  const t = Math.min(1, Math.max(0, frame / ARROW_DRAW_FRAMES));
  return t * t * (3 - 2 * t);
}

export function contentRect(isEndScreen: boolean): Rect {
  const y = Math.max(SAFE_PADDING_TOP, SAFE_MARGIN_Y);
  const bottom = isEndScreen ? SAFE_PADDING_BOTTOM + END_SCREEN_MASK_H : SAFE_PADDING_BOTTOM;
  return {
    x: SAFE_MARGIN_X,
    y,
    width: FRAME_WIDTH - SAFE_MARGIN_X * 2,
    height: FRAME_HEIGHT - y - Math.max(bottom, SAFE_MARGIN_Y),
  };
}

export function exclusionRect(): Rect {
  const width = FRAME_WIDTH * EXCLUSION_WIDTH_RATIO;
  const height = FRAME_HEIGHT * EXCLUSION_HEIGHT_RATIO;
  return { x: FRAME_WIDTH - width, y: FRAME_HEIGHT - height, width, height };
}

export function captionBarRect(): Rect {
  return {
    x: 0,
    y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM,
    width: FRAME_WIDTH,
    height: SAFE_PADDING_BOTTOM,
  };
}

export function endScreenMaskRect(): Rect {
  const exclusion = exclusionRect();
  const caption = captionBarRect();
  return {
    x: 0,
    y: caption.y - END_SCREEN_MASK_H,
    width: exclusion.x,
    height: END_SCREEN_MASK_H,
  };
}

export function containFit(wellWidth: number, wellHeight: number, srcWidth: number, srcHeight: number): FittedContain {
  const wider = srcWidth * wellHeight >= srcHeight * wellWidth;
  let width = wider ? wellWidth : Math.max(1, Math.round((wellHeight * srcWidth) / srcHeight));
  let height = wider ? Math.max(1, Math.round((wellWidth * srcHeight) / srcWidth)) : wellHeight;
  if (width > wellWidth) width = wellWidth;
  if (height > wellHeight) height = wellHeight;
  return {
    width,
    height,
    offsetX: Math.floor((wellWidth - width) / 2),
    offsetY: Math.floor((wellHeight - height) / 2),
  };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

export function rectInside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

export function walkMatch(node: MatchChild, into: MatchNode[] = []): MatchNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkMatch(child, into);
  return into;
}

export function clampLabel(text: string): { display: string; words: string[]; clamped: boolean } {
  if (typeof text !== "string") fail("label must be a string");
  const trimmed = text.trim();
  if (trimmed.length < 1 || trimmed.length > 2_000) fail("label must be 1–2000 characters");
  const words = trimmed.split(/\s+/).filter((word) => word.length > 0);
  if (words.length < 1) fail("label must contain a word");
  for (const word of words) {
    if (word.length > 80) fail("label word exceeds 80 characters");
  }
  const clamped = words.length > MAX_LABEL_WORDS;
  const kept = clamped ? words.slice(0, MAX_LABEL_WORDS) : words;
  return { display: kept.join(" "), words: kept, clamped };
}

export function layoutEvidenceMatchCard(props: EvidenceMatchCardProps): EvidenceMatchCardLayout {
  const prepared = prepare(props);
  const content = contentRect(prepared.isEndScreen);
  const boxes = dossierBoxes(content);
  const left = placeExhibit(prepared.left, boxes.left);
  const right = placeExhibit(prepared.right, boxes.right);
  const arrows = placeArrows(prepared.frame, boxes.gutter, left.well);
  const layout: EvidenceMatchCardLayout = {
    motif: EVIDENCE_MATCH_CARD_ID,
    owner: EVIDENCE_MATCH_CARD_OWNER,
    motifNumber: EVIDENCE_MOTIF_NUMBER,
    frozenCatalogSlot: FROZEN_CATALOG_SLOT_12,
    frame: prepared.frame,
    sceneId: prepared.sceneId,
    isEndScreen: prepared.isEndScreen,
    content,
    exclusion: exclusionRect(),
    captionBar: captionBarRect(),
    endScreenMask: prepared.isEndScreen ? endScreenMaskRect() : null,
    gutter: boxes.gutter,
    left,
    right,
    arrows,
    cues: prepared.cues,
    cuesStarted: prepared.cues.filter((cue) => cue.start_frame <= prepared.frame),
    suppressed: prepared.suppressed,
  };
  assertSymmetricFraming(layout);
  return layout;
}

export function assertSymmetricFraming(layout: EvidenceMatchCardLayout): void {
  const content = contentRect(layout.isEndScreen);
  if (!sameRect(layout.content, content)) failInvariant("content box drifted from the safe-zone margins");
  if (layout.content.x < SAFE_MARGIN_X || layout.content.y < SAFE_MARGIN_Y) {
    failInvariant("content crosses the 96px by 54px margin");
  }
  if (
    layout.content.x + layout.content.width > FRAME_WIDTH - SAFE_MARGIN_X ||
    layout.content.y + layout.content.height > FRAME_HEIGHT - SAFE_MARGIN_Y
  ) {
    failInvariant("content crosses the 96px by 54px margin");
  }

  const left = layout.left;
  const right = layout.right;
  if (left.objectFit !== EXHIBIT_OBJECT_FIT || right.objectFit !== EXHIBIT_OBJECT_FIT) {
    failInvariant("exhibit frames must use object-fit contain");
  }
  if (!sameSize(left.frameBox, right.frameBox) || left.frameBox.y !== right.frameBox.y) {
    failInvariant("dossier boxes are different sizes");
  }
  const leftInset = left.frameBox.x - layout.content.x;
  const rightInset = layout.content.x + layout.content.width - (right.frameBox.x + right.frameBox.width);
  if (leftInset !== rightInset) failInvariant("dossier boxes are not mirrored");
  if (!rectInside(left.frameBox, layout.content) || !rectInside(right.frameBox, layout.content)) {
    failInvariant("dossier box leaves the safe zone");
  }
  if (rectsOverlap(left.frameBox, right.frameBox)) failInvariant("dossier boxes overlap");

  const gutter = layout.gutter;
  if (gutter.x !== left.frameBox.x + left.frameBox.width || gutter.x + gutter.width !== right.frameBox.x) {
    failInvariant("gutter does not sit between the dossier boxes");
  }
  if (gutter.y !== left.frameBox.y || gutter.height !== left.frameBox.height || gutter.width < GUTTER_W) {
    failInvariant("gutter is narrower than the comparison channel");
  }

  assertWell(left);
  assertWell(right);
  if (!sameSize(left.well, right.well) || left.well.y !== right.well.y) {
    failInvariant("exhibit wells are different sizes");
  }
  const wellInsetLeft = left.well.x - left.frameBox.x;
  const wellInsetRight = right.frameBox.x + right.frameBox.width - (right.well.x + right.well.width);
  if (wellInsetLeft !== wellInsetRight) failInvariant("exhibit wells are not mirrored");

  assertFitted(left);
  assertFitted(right);
  assertCaption(left);
  assertCaption(right);

  const progress = arrowProgress(layout.frame);
  const full = Math.floor((gutter.width - ARROW_GAP) / 2);
  const revealed = Math.round(full * progress);
  if (layout.arrows.full !== full || layout.arrows.revealed !== revealed || layout.arrows.progress !== progress) {
    failInvariant("arrow draw does not match the frame clock");
  }
  assertArrow(layout.arrows.left, "left", gutter, revealed);
  assertArrow(layout.arrows.right, "right", gutter, revealed);
  const arrowLeftInset = layout.arrows.left.box.x - gutter.x;
  const arrowRightInset = gutter.x + gutter.width - (layout.arrows.right.box.x + layout.arrows.right.box.width);
  if (arrowLeftInset !== arrowRightInset || layout.arrows.left.box.y !== layout.arrows.right.box.y) {
    failInvariant("comparison arrows are not mirrored");
  }
  if (layout.arrows.left.box.width !== layout.arrows.right.box.width) {
    failInvariant("comparison arrows have different lengths");
  }
  for (const arrow of [layout.arrows.left, layout.arrows.right]) {
    if (rectsOverlap(arrow.box, left.frameBox) || rectsOverlap(arrow.box, right.frameBox)) {
      failInvariant("comparison arrow enters a dossier box");
    }
    if (rectsOverlap(arrow.box, left.caption) || rectsOverlap(arrow.box, right.caption)) {
      failInvariant("comparison arrow enters a caption");
    }
  }

  const painted = [
    left.frameBox,
    right.frameBox,
    left.well,
    right.well,
    left.fitted,
    right.fitted,
    left.caption,
    right.caption,
    layout.arrows.left.box,
    layout.arrows.right.box,
  ];
  for (const rect of painted) assertMargin(rect);
  if (rectsOverlap(left.frameBox, layout.captionBar) || rectsOverlap(right.frameBox, layout.captionBar)) {
    failInvariant("dossier box enters the caption bar");
  }
  if (rectsOverlap(left.frameBox, layout.exclusion) || rectsOverlap(right.frameBox, layout.exclusion)) {
    failInvariant("dossier box enters the exclusion");
  }
  if (layout.endScreenMask) {
    if (rectsOverlap(left.frameBox, layout.endScreenMask) || rectsOverlap(right.frameBox, layout.endScreenMask)) {
      failInvariant("dossier box enters the end-screen mask");
    }
  } else if (layout.isEndScreen) {
    failInvariant("end screen is missing its mask");
  }
  assertCues(layout);
}

export function EvidenceMatchCard(props: EvidenceMatchCardProps): MatchNode {
  const layout = layoutEvidenceMatchCard(props);
  const origin = layout.content;
  const layers: MatchChild[] = [
    element(
      { slot: "content" },
      {
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
      },
      [
        exhibitNode(layout.left, origin),
        exhibitNode(layout.right, origin),
        arrowNode(layout.arrows.left, origin, layout.arrows.progress),
        arrowNode(layout.arrows.right, origin, layout.arrows.progress),
        ...layout.cues.map((cue) => shutterNode(cue)),
      ],
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: "22%",
        height: "14%",
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  ];
  if (layout.endScreenMask) {
    layers.push(
      element(
        { mask: "end-screen-card" },
        {
          position: "absolute",
          left: layout.endScreenMask.x,
          top: layout.endScreenMask.y,
          width: layout.endScreenMask.width,
          height: layout.endScreenMask.height,
          overflow: "hidden",
          pointerEvents: "none",
        },
      ),
    );
  }
  return safeZone(layout, layers);
}

function safeZone(layout: EvidenceMatchCardLayout, children: readonly MatchChild[]): MatchNode {
  const paddingBottom = layout.isEndScreen ? SAFE_PADDING_BOTTOM + END_SCREEN_MASK_H : SAFE_PADDING_BOTTOM;
  return element(
    {
      "safe-zone": "css-contained",
      motif: EVIDENCE_MATCH_CARD_ID,
      owner: EVIDENCE_MATCH_CARD_OWNER,
      "motif-number": String(EVIDENCE_MOTIF_NUMBER),
      "frozen-catalog-slot": FROZEN_CATALOG_SLOT_12,
      "end-screen": layout.isEndScreen ? "true" : "false",
      "margin-x": String(SAFE_MARGIN_X),
      "margin-y": String(SAFE_MARGIN_Y),
      "padding-bottom": String(paddingBottom),
      "apply-grade": "true",
      "texture-overlay": "off",
      symmetric: "true",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paddingTop: SAFE_PADDING_TOP,
      paddingBottom,
      paddingLeft: SAFE_MARGIN_X,
      paddingRight: SAFE_MARGIN_X,
      overflow: "hidden",
      background: PAPER_BG,
    },
    children,
  );
}

function exhibitNode(exhibit: PlacedExhibit, origin: Rect): MatchNode {
  return element(
    {
      slot: "dossier",
      side: exhibit.side,
      "exhibit-id": exhibit.exhibit_id,
      "fact-id": exhibit.fact_id,
      "object-fit": EXHIBIT_OBJECT_FIT,
    },
    {
      position: "absolute",
      left: exhibit.frameBox.x - origin.x,
      top: exhibit.frameBox.y - origin.y,
      width: exhibit.frameBox.width,
      height: exhibit.frameBox.height,
      boxSizing: "border-box",
      overflow: "hidden",
      background: PAPER_BG,
      border: `2px solid ${INK}`,
    },
    [
      element(
        { slot: "exhibit-well", side: exhibit.side },
        {
          position: "absolute",
          left: exhibit.well.x - exhibit.frameBox.x,
          top: exhibit.well.y - exhibit.frameBox.y,
          width: exhibit.well.width,
          height: exhibit.well.height,
          overflow: "hidden",
          background: MAT,
        },
        [
          element(
            {
              slot: "exhibit-image",
              side: exhibit.side,
              "exhibit-id": exhibit.exhibit_id,
              "fact-id": exhibit.fact_id,
              src: exhibit.src,
              "object-fit": EXHIBIT_OBJECT_FIT,
              "intrinsic-width": String(exhibit.intrinsicWidth),
              "intrinsic-height": String(exhibit.intrinsicHeight),
              "fitted-width": String(exhibit.fittedLocal.width),
              "fitted-height": String(exhibit.fittedLocal.height),
            },
            {
              position: "absolute",
              left: exhibit.fittedLocal.offsetX,
              top: exhibit.fittedLocal.offsetY,
              width: exhibit.fittedLocal.width,
              height: exhibit.fittedLocal.height,
              objectFit: EXHIBIT_OBJECT_FIT,
              overflow: "hidden",
              background: SLATE,
            },
          ),
        ],
      ),
      element(
        {
          slot: "caption",
          side: exhibit.side,
          "fact-id": exhibit.fact_id,
          "word-count": String(exhibit.wordCount),
          clamped: exhibit.clamped ? "true" : "false",
        },
        {
          position: "absolute",
          left: exhibit.caption.x - exhibit.frameBox.x,
          top: exhibit.caption.y - exhibit.frameBox.y,
          width: exhibit.caption.width,
          height: exhibit.caption.height,
          boxSizing: "border-box",
          overflow: "hidden",
          color: INK,
          fontSize: 22,
          lineHeight: "28px",
          whiteSpace: "nowrap",
        },
        [exhibit.display],
      ),
    ],
  );
}

function arrowNode(arrow: PlacedArrow, origin: Rect, progress: number): MatchNode {
  const children: MatchChild[] = [];
  if (arrow.revealed > 0) {
    const head = arrow.revealed >= ARROW_HEAD ? ARROW_HEAD : 0;
    const shaft = arrow.revealed - head;
    const shaftTop = Math.floor((ARROW_THICKNESS - ARROW_SHAFT) / 2);
    if (arrow.direction === "left") {
      if (head > 0) children.push(arrowHead("left", 0));
      if (shaft > 0) children.push(arrowShaft(head, shaftTop, shaft));
    } else {
      if (shaft > 0) children.push(arrowShaft(0, shaftTop, shaft));
      if (head > 0) children.push(arrowHead("right", shaft));
    }
  }
  return element(
    {
      slot: "comparison-arrow",
      direction: arrow.direction,
      progress: progress.toFixed(3),
      revealed: String(arrow.revealed),
    },
    {
      position: "absolute",
      left: arrow.box.x - origin.x,
      top: arrow.box.y - origin.y,
      width: arrow.box.width,
      height: arrow.box.height,
      overflow: "hidden",
    },
    children,
  );
}

function arrowShaft(left: number, top: number, width: number): MatchNode {
  return element(
    { slot: "arrow-shaft" },
    {
      position: "absolute",
      left,
      top,
      width,
      height: ARROW_SHAFT,
      background: EVIDENCE_CRIMSON,
    },
  );
}

function arrowHead(direction: Side, left: number): MatchNode {
  const style: Record<string, CssValue> =
    direction === "left"
      ? {
          position: "absolute",
          left,
          top: 0,
          width: 0,
          height: 0,
          borderTop: "7px solid transparent",
          borderBottom: "7px solid transparent",
          borderRight: `${ARROW_HEAD}px solid ${EVIDENCE_CRIMSON}`,
        }
      : {
          position: "absolute",
          left,
          top: 0,
          width: 0,
          height: 0,
          borderTop: "7px solid transparent",
          borderBottom: "7px solid transparent",
          borderLeft: `${ARROW_HEAD}px solid ${EVIDENCE_CRIMSON}`,
        };
  return element({ slot: "arrow-head", direction }, style);
}

function shutterNode(cue: ShutterCue): MatchNode {
  return element(
    {
      slot: "camera-shutter",
      cue: CAMERA_SHUTTER_CUE,
      side: cue.side,
      "exhibit-id": cue.exhibit_id,
      "start-frame": String(cue.start_frame),
      "start-sample": String(cue.start_sample),
      tapered: cue.tapered ? "true" : "false",
    },
    {
      position: "absolute",
      left: 0,
      top: 0,
      width: 0,
      height: 0,
      overflow: "hidden",
    },
  );
}

function prepare(props: EvidenceMatchCardProps): Prepared {
  if (props === null || typeof props !== "object") fail("evidence match props must be an object");
  const frame = readFrame(props.frame, "frame");
  const sceneId = props.sceneId === undefined ? "evidence_match_card" : readId(props.sceneId, "scene_id");
  const isEndScreen = props.isEndScreen === undefined ? false : props.isEndScreen;
  if (typeof isEndScreen !== "boolean") fail("isEndScreen must be a boolean");
  const left = readExhibit(props.left, "left");
  const right = readExhibit(props.right, "right");
  if (left.exhibit_id === right.exhibit_id) fail("exhibit ids must differ");
  if (left.fact_id === right.fact_id) fail("fact ids must differ");
  const shutterLeft = props.shutterFrameLeft === undefined ? SHUTTER_FRAME_LEFT : readFrame(props.shutterFrameLeft, "shutterFrameLeft");
  const shutterRight = props.shutterFrameRight === undefined ? SHUTTER_FRAME_RIGHT : readFrame(props.shutterFrameRight, "shutterFrameRight");
  const schedule = scheduleShutters(sceneId, left, shutterLeft, right, shutterRight);
  return { frame, sceneId, isEndScreen, left, right, cues: schedule.cues, suppressed: schedule.suppressed };
}

function readExhibit(value: ForensicExhibit, side: Side): NormalizedExhibit {
  if (value === null || typeof value !== "object") fail(`${side} exhibit must be an object`);
  const exhibitId = readId(value.exhibit_id, "exhibit_id");
  const factId = readId(value.fact_id, "fact_id");
  if (typeof value.src !== "string" || !SRC_PATTERN.test(value.src) || value.src.includes("..") || value.src.includes("//")) {
    fail(`src must be an offline asset id at ${exhibitId}`);
  }
  if (!Number.isInteger(value.intrinsic_width) || value.intrinsic_width < 1 || value.intrinsic_width > MAX_INTRINSIC) {
    fail(`intrinsic_width must be 1–${MAX_INTRINSIC} at ${exhibitId}`);
  }
  if (!Number.isInteger(value.intrinsic_height) || value.intrinsic_height < 1 || value.intrinsic_height > MAX_INTRINSIC) {
    fail(`intrinsic_height must be 1–${MAX_INTRINSIC} at ${exhibitId}`);
  }
  const label = clampLabel(value.label);
  return {
    side,
    exhibit_id: exhibitId,
    fact_id: factId,
    src: value.src,
    label: value.label.trim(),
    display: label.display,
    wordCount: label.words.length,
    clamped: label.clamped,
    intrinsicWidth: value.intrinsic_width,
    intrinsicHeight: value.intrinsic_height,
  };
}

function readId(value: unknown, label: string): string {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) fail(`${label} must match ${ID_PATTERN}`);
  return value;
}

function readFrame(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > MAX_FRAME) {
    fail(`${label} must be an integer from 0 to ${MAX_FRAME}`);
  }
  return value;
}

function scheduleShutters(
  sceneId: string,
  left: NormalizedExhibit,
  leftFrame: number,
  right: NormalizedExhibit,
  rightFrame: number,
): { cues: ShutterCue[]; suppressed: SuppressedShutter[] } {
  if (CAMERA_SHUTTER_DURATION_SAMPLES <= 0) fail("camera_shutter duration must be positive");
  const planned = [
    { exhibit: left, frame: leftFrame },
    { exhibit: right, frame: rightFrame },
  ].sort((a, b) => a.frame - b.frame || (a.exhibit.side === "left" ? -1 : 1));
  const kept: typeof planned = [];
  const suppressed: SuppressedShutter[] = [];
  let lastSample: number | null = null;
  for (const item of planned) {
    const sample = item.frame * SAMPLES_PER_FRAME;
    if (lastSample !== null && sample - lastSample < COOLDOWN_SAMPLES) {
      suppressed.push({
        cue: CAMERA_SHUTTER_CUE,
        exhibit_id: item.exhibit.exhibit_id,
        side: item.exhibit.side,
        start_frame: item.frame,
        start_sample: sample,
        reason: "cooldown",
      });
      continue;
    }
    kept.push(item);
    lastSample = sample;
  }
  const active: { start: number; end: number; units: number }[] = [];
  const cues = kept.map((item) => {
    const sample = item.frame * SAMPLES_PER_FRAME;
    let sum = 0;
    for (const prev of active) {
      if (prev.start <= sample && sample < prev.end) sum += prev.units;
    }
    const gain = Math.min(CAMERA_SHUTTER_GAIN_UNITS, Math.max(0, TRUE_PEAK_CEILING_UNITS - sum));
    active.push({ start: sample, end: sample + CAMERA_SHUTTER_DURATION_SAMPLES, units: gain });
    return toCue(sceneId, item.exhibit, item.frame, sample, gain);
  });
  return { cues, suppressed };
}

function toCue(sceneId: string, exhibit: NormalizedExhibit, frame: number, sample: number, gain: number): ShutterCue {
  if (gain > TRUE_PEAK_CEILING_UNITS) fail("camera_shutter peak exceeds -1.0 dBTP");
  return {
    cue_id: `${sceneId}:${CAMERA_SHUTTER_CUE}:${exhibit.exhibit_id}:${sample}`,
    cue: CAMERA_SHUTTER_CUE,
    scene_id: sceneId,
    exhibit_id: exhibit.exhibit_id,
    side: exhibit.side,
    start_sample: sample,
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    start_frame: frame,
    offset_ms: mixOffsetMs(sample),
    duration_samples: CAMERA_SHUTTER_DURATION_SAMPLES,
    cooldown_ms: COOLDOWN_MS,
    gain_units: gain,
    gain_unit_scale: GAIN_UNIT_SCALE,
    peak_dbtp: gain === CAMERA_SHUTTER_GAIN_UNITS ? CAMERA_SHUTTER_DBTP : roundedDbtp(gain),
    burst: false,
    tapered: gain !== CAMERA_SHUTTER_GAIN_UNITS,
  };
}

function roundedDbtp(units: number): number {
  if (units <= 0) return TRUE_PEAK_CEILING_DBTP;
  return Math.round((20 * Math.log10(units / GAIN_UNIT_SCALE)) * 1000) / 1000;
}

function dossierBoxes(content: Rect): { left: Rect; right: Rect; gutter: Rect } {
  const frameW = Math.floor((content.width - GUTTER_W) / 2);
  const gutterW = content.width - frameW * 2;
  const frameH = content.height;
  if (frameW <= FRAME_PAD * 2 || gutterW < GUTTER_W) fail("dossier frame does not fit the safe zone");
  if (frameH <= CAPTION_H + FRAME_PAD * 2) fail("dossier frame does not fit the safe zone");
  const left = { x: content.x, y: content.y, width: frameW, height: frameH };
  const gutter = { x: content.x + frameW, y: content.y, width: gutterW, height: frameH };
  const right = { x: gutter.x + gutter.width, y: content.y, width: frameW, height: frameH };
  return { left, right, gutter };
}

function placeExhibit(exhibit: NormalizedExhibit, frameBox: Rect): PlacedExhibit {
  const well = {
    x: frameBox.x + FRAME_PAD,
    y: frameBox.y + FRAME_PAD,
    width: frameBox.width - FRAME_PAD * 2,
    height: frameBox.height - CAPTION_H - FRAME_PAD * 2,
  };
  const caption = {
    x: frameBox.x + FRAME_PAD,
    y: frameBox.y + frameBox.height - CAPTION_H,
    width: frameBox.width - FRAME_PAD * 2,
    height: CAPTION_H,
  };
  const local = containFit(well.width, well.height, exhibit.intrinsicWidth, exhibit.intrinsicHeight);
  const fitted = {
    x: well.x + local.offsetX,
    y: well.y + local.offsetY,
    width: local.width,
    height: local.height,
  };
  return {
    side: exhibit.side,
    exhibit_id: exhibit.exhibit_id,
    fact_id: exhibit.fact_id,
    src: exhibit.src,
    label: exhibit.label,
    display: exhibit.display,
    wordCount: exhibit.wordCount,
    clamped: exhibit.clamped,
    intrinsicWidth: exhibit.intrinsicWidth,
    intrinsicHeight: exhibit.intrinsicHeight,
    objectFit: EXHIBIT_OBJECT_FIT,
    frameBox,
    well,
    caption,
    fitted,
    fittedLocal: local,
  };
}

function placeArrows(frame: number, gutter: Rect, well: Rect): EvidenceMatchCardLayout["arrows"] {
  const full = Math.floor((gutter.width - ARROW_GAP) / 2);
  if (full < ARROW_HEAD) fail("comparison gutter cannot hold an arrow");
  const progress = arrowProgress(frame);
  const revealed = Math.round(full * progress);
  const center = gutter.x + Math.floor(gutter.width / 2);
  const inner = Math.floor(ARROW_GAP / 2);
  const y = well.y + Math.floor(well.height / 2) - Math.floor(ARROW_THICKNESS / 2);
  const left: PlacedArrow = {
    direction: "left",
    revealed,
    color: EVIDENCE_CRIMSON,
    box: { x: center - inner - revealed, y, width: revealed, height: ARROW_THICKNESS },
  };
  const right: PlacedArrow = {
    direction: "right",
    revealed,
    color: EVIDENCE_CRIMSON,
    box: { x: center + (ARROW_GAP - inner), y, width: revealed, height: ARROW_THICKNESS },
  };
  return { progress, revealed, full, left, right };
}

function assertWell(exhibit: PlacedExhibit): void {
  if (!rectInside(exhibit.well, exhibit.frameBox)) failInvariant(`${exhibit.side} well leaves its dossier box`);
  if (exhibit.well.width <= 0 || exhibit.well.height <= 0) failInvariant(`${exhibit.side} well has no area`);
}

function assertFitted(exhibit: PlacedExhibit): void {
  const expected = containFit(exhibit.well.width, exhibit.well.height, exhibit.intrinsicWidth, exhibit.intrinsicHeight);
  if (
    exhibit.fittedLocal.width !== expected.width ||
    exhibit.fittedLocal.height !== expected.height ||
    exhibit.fittedLocal.offsetX !== expected.offsetX ||
    exhibit.fittedLocal.offsetY !== expected.offsetY
  ) {
    failInvariant(`${exhibit.side} plate is not object-fit contain`);
  }
  if (
    exhibit.fitted.x !== exhibit.well.x + expected.offsetX ||
    exhibit.fitted.y !== exhibit.well.y + expected.offsetY ||
    exhibit.fitted.width !== expected.width ||
    exhibit.fitted.height !== expected.height
  ) {
    failInvariant(`${exhibit.side} plate is not centered in the well`);
  }
  if (!rectInside(exhibit.fitted, exhibit.well)) failInvariant(`${exhibit.side} plate leaves the well`);
  const padX = exhibit.well.width - exhibit.fitted.width;
  const padY = exhibit.well.height - exhibit.fitted.height;
  if (exhibit.fittedLocal.offsetX !== Math.floor(padX / 2) || exhibit.fittedLocal.offsetY !== Math.floor(padY / 2)) {
    failInvariant(`${exhibit.side} plate is not centered in the well`);
  }
}

function assertCaption(exhibit: PlacedExhibit): void {
  if (exhibit.wordCount < 1 || exhibit.wordCount > MAX_LABEL_WORDS) {
    failInvariant(`${exhibit.side} caption exceeds ${MAX_LABEL_WORDS} words`);
  }
  if (exhibit.display.split(/\s+/).length !== exhibit.wordCount) {
    failInvariant(`${exhibit.side} caption word count drifted`);
  }
  if (!rectInside(exhibit.caption, exhibit.frameBox)) failInvariant(`${exhibit.side} caption leaves the dossier box`);
}

function assertArrow(arrow: PlacedArrow, direction: Side, gutter: Rect, revealed: number): void {
  if (arrow.direction !== direction || arrow.color !== EVIDENCE_CRIMSON) failInvariant("arrow color or direction drifted");
  if (arrow.revealed !== revealed || arrow.box.width !== revealed || arrow.box.height !== ARROW_THICKNESS) {
    failInvariant("arrow length drifted from the draw clock");
  }
  if (arrow.box.x < gutter.x || arrow.box.x + arrow.box.width > gutter.x + gutter.width) {
    failInvariant("arrow leaves the gutter");
  }
  if (arrow.box.y < gutter.y || arrow.box.y + arrow.box.height > gutter.y + gutter.height) {
    failInvariant("arrow leaves the gutter");
  }
}

function assertMargin(rect: Rect): void {
  if (rect.width < 0 || rect.height < 0) failInvariant("painted rect has a negative size");
  if (rect.x < SAFE_MARGIN_X || rect.y < SAFE_MARGIN_Y) failInvariant("painted rect crosses the 96px by 54px margin");
  if (rect.x + rect.width > FRAME_WIDTH - SAFE_MARGIN_X) failInvariant("painted rect crosses the 96px by 54px margin");
  if (rect.y + rect.height > FRAME_HEIGHT - SAFE_MARGIN_Y) failInvariant("painted rect crosses the 96px by 54px margin");
}

function assertCues(layout: EvidenceMatchCardLayout): void {
  let lastSample: number | null = null;
  const active: { start: number; end: number; units: number }[] = [];
  for (const cue of layout.cues) {
    if (cue.cue !== CAMERA_SHUTTER_CUE) failInvariant("cue is not camera_shutter");
    if (cue.scene_id !== layout.sceneId) failInvariant("cue scene drifted");
    if (cue.sample_rate_hz !== MIX_SAMPLE_RATE_HZ) failInvariant("cue sample rate drifted");
    if (cue.start_sample !== cue.start_frame * SAMPLES_PER_FRAME) failInvariant("cue is off the 48 kHz grid");
    if (cue.offset_ms !== mixOffsetMs(cue.start_sample)) failInvariant("cue offset drifted");
    if (cue.duration_samples !== CAMERA_SHUTTER_DURATION_SAMPLES) failInvariant("cue duration drifted");
    if (cue.cooldown_ms !== COOLDOWN_MS) failInvariant("cue cooldown drifted");
    if (cue.gain_units > TRUE_PEAK_CEILING_UNITS || cue.gain_units > CAMERA_SHUTTER_GAIN_UNITS) {
      failInvariant("camera_shutter exceeds -1.0 dBTP");
    }
    if (cue.peak_dbtp > TRUE_PEAK_CEILING_DBTP) failInvariant("camera_shutter exceeds -1.0 dBTP");
    if (lastSample !== null && cue.start_sample - lastSample < COOLDOWN_SAMPLES) {
      failInvariant("camera_shutter cues break the 60 ms cooldown");
    }
    let sum = cue.gain_units;
    for (const prev of active) {
      if (prev.start <= cue.start_sample && cue.start_sample < prev.end) sum += prev.units;
    }
    if (sum > TRUE_PEAK_CEILING_UNITS) failInvariant("camera_shutter sum exceeds -1.0 dBTP");
    active.push({ start: cue.start_sample, end: cue.start_sample + cue.duration_samples, units: cue.gain_units });
    lastSample = cue.start_sample;
  }
  for (const skipped of layout.suppressed) {
    if (skipped.reason !== "cooldown" || skipped.cue !== CAMERA_SHUTTER_CUE) {
      failInvariant("suppressed shutter is missing a cooldown reason");
    }
  }
}

function sameSize(a: Rect, b: Rect): boolean {
  return a.width === b.width && a.height === b.height;
}

function sameRect(a: Rect, b: Rect): boolean {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}

function element(
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, CssValue>>,
  children?: readonly MatchChild[],
): MatchNode {
  if (children !== undefined && children.length > 0) {
    const only = children.length === 1 ? children[0] : children;
    if (only !== undefined) return { type: "div", dataset, props: { style, children: only } };
  }
  return { type: "div", dataset, props: { style } };
}

function failInvariant(message: string): never {
  fail(`${SYMMETRIC_FRAMING_INVARIANT}: ${message}`);
}

function fail(message: string): never {
  throw new EvidenceMatchCardError(message);
}
