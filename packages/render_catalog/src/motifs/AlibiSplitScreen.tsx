/**
 * Motif 11 — AlibiSplitScreen.
 *
 * Suspect claim on the left, primary record on the right, and a crimson
 * CONFLICT stamp that lands on an integer narration millisecond. The
 * `conflict_stamp` cue uses that same millisecond at 48 kHz (48 samples
 * per ms). The stamp frame is the 30 fps frame that contains the
 * millisecond. The cue does not snap to the frame boundary.
 *
 * The package tsconfig has no `jsx` flag (Task 001), so this file builds
 * an element tree. Task 101's `safe_zone.tsx` and Task 110's `SfxRegistry.ts`
 * are other branches. They are not copied here. `<SafeZoneLayout>` below is
 * the local frame: 1920×1080, padding 108 / 194, bottom-right exclusion
 * 22% × 14%. Shake is a transform on the inner graphic only, clamped to a
 * 6 px Euclidean step, and the graphic is inset by 6 px so the step cannot
 * carry type into the caption bar or the exclusion box.
 *
 * The frozen SQL catalog's eleventh Remotion name is `EvidenceGridMatrix`.
 * Slot 8 remains `SplitScreenComparison`. `MOTIF_REGISTRY_V1` stays the four
 * MVP motifs. This file does not amend that contract. Task 125 still owns
 * this component as motif 11.
 *
 * `conflict_stamp` matches the Task 110 duration table (400 ms, −6 dBTP)
 * as numbers. One stamp per scene, so the 400 ms envelope does not stack.
 */

export const ALIBI_SPLIT_SCREEN_ID = "AlibiSplitScreen" as const;
export const ALIBI_SPLIT_SCREEN_OWNER = "render_catalog" as const;
export const ALIBI_MOTIF_NUMBER = 11 as const;
export const CONFLICT_LABEL = "CONFLICT" as const;
export const CONFLICT_STAMP_CUE = "conflict_stamp" as const;
export const CLAIM_HEADER = "SUSPECT CLAIM" as const;
export const EVIDENCE_HEADER = "PRIMARY EVIDENCE" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const END_SCREEN_MASK_H = 48;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";
export const MAX_SHAKE_PX = 6;
export const MAX_WORDS = 12;

export const MIX_SAMPLE_RATE_HZ = 48_000;
export const SAMPLES_PER_MS = MIX_SAMPLE_RATE_HZ / 1_000;
export const SAMPLES_PER_FRAME = MIX_SAMPLE_RATE_HZ / FRAME_FPS;
export const COOLDOWN_MS = 60;
export const CONFLICT_STAMP_DURATION_MS = 400;
export const CONFLICT_STAMP_DURATION_SAMPLES = CONFLICT_STAMP_DURATION_MS * SAMPLES_PER_MS;
export const CONFLICT_STAMP_DBTP = -6;
export const TRUE_PEAK_CEILING_DBTP = -1;
export const GAIN_UNIT_SCALE = 1_000_000_000;
export const STAMP_HOLD_FRAMES = (CONFLICT_STAMP_DURATION_MS * FRAME_FPS) / 1_000;

export const STAMP_W = 280;
export const STAMP_H = 88;
export const PANE_PAD = 20;
export const HEADER_H = 32;
export const CITE_H = 24;
export const LINE_H = 32;
export const CHAR_PX = 13;

export const EVIDENCE_CRIMSON = "#C92A2A";
export const PAPER_BG = "#E9E2D2";
export const INK = "#1B1B1D";
export const SLATE = "#5E6A72";
export const CLAIM_BG = "#EFE6D4";
export const EVIDENCE_BG = "#E4D8C4";

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const MAX_TEXT = 400;
const MAX_CITATION = 120;

const SHAKE_SIGNS = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
] as const;

export const CLAIM_SOURCES = ["suspect_statement", "news_report"] as const;
export const EVIDENCE_SOURCES = ["police_affidavit", "court_ruling"] as const;

export type ClaimSource = (typeof CLAIM_SOURCES)[number];
export type EvidenceSource = (typeof EVIDENCE_SOURCES)[number];

export type CssValue = string | number;

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type Shake = {
  readonly x: number;
  readonly y: number;
};

export type SplitChild = SplitNode | string;

export type SplitNode = {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, CssValue>>;
    readonly children?: SplitChild | readonly SplitChild[];
  };
};

export type ClaimPane = {
  readonly fact_id: string;
  readonly source_type: ClaimSource;
  readonly text: string;
  readonly citation: string;
};

export type EvidencePane = {
  readonly fact_id: string;
  readonly source_type: EvidenceSource;
  readonly text: string;
  readonly citation: string;
};

export type AlibiSplitScreenProps = {
  readonly sceneId: string;
  readonly frame: number;
  readonly stampAtMs: number;
  readonly claim: ClaimPane;
  readonly evidence: EvidencePane;
  readonly shakePx?: number;
  readonly isEndScreen?: boolean;
};

export type StampSync = {
  readonly offset_ms: number;
  readonly start_sample: number;
  readonly start_frame: number;
};

export type ConflictStampCue = {
  readonly cue_id: string;
  readonly cue: typeof CONFLICT_STAMP_CUE;
  readonly scene_id: string;
  readonly start_sample: number;
  readonly sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  readonly start_frame: number;
  readonly offset_ms: number;
  readonly duration_samples: number;
  readonly cooldown_ms: typeof COOLDOWN_MS;
  readonly gain_units: number;
  readonly gain_unit_scale: typeof GAIN_UNIT_SCALE;
  readonly peak_dbtp: typeof CONFLICT_STAMP_DBTP;
  readonly burst: false;
  readonly tapered: false;
};

export type PlacedText = {
  readonly fact_id: string;
  readonly source_type: ClaimSource | EvidenceSource;
  readonly header: string;
  readonly text: string;
  readonly display: string;
  readonly citation: string;
  readonly lines: readonly string[];
  readonly truncated: boolean;
  readonly wordCount: number;
  readonly box: Rect;
  readonly page: Rect;
  readonly bodyPage: Rect;
  readonly citationPage: Rect;
};

export type PlacedStamp = {
  readonly label: typeof CONFLICT_LABEL;
  readonly box: Rect;
  readonly page: Rect;
};

export type AlibiSplitLayout = {
  readonly motif: typeof ALIBI_SPLIT_SCREEN_ID;
  readonly owner: typeof ALIBI_SPLIT_SCREEN_OWNER;
  readonly motifNumber: typeof ALIBI_MOTIF_NUMBER;
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly graphic: Rect;
  readonly shake: Shake;
  readonly shakePx: number;
  readonly sync: StampSync;
  readonly claim: PlacedText;
  readonly evidence: PlacedText;
  readonly rule: Rect;
  readonly rulePage: Rect;
  readonly stamp: PlacedStamp | null;
  readonly cues: readonly ConflictStampCue[];
  readonly cuesStarted: readonly ConflictStampCue[];
};

type PreparedPane = {
  readonly fact_id: string;
  readonly source_type: ClaimSource | EvidenceSource;
  readonly text: string;
  readonly display: string;
  readonly words: readonly string[];
  readonly citation: string;
  readonly truncated: boolean;
};

type Prepared = {
  readonly sceneId: string;
  readonly frame: number;
  readonly isEndScreen: boolean;
  readonly shakePx: number;
  readonly claim: PreparedPane;
  readonly evidence: PreparedPane;
  readonly sync: StampSync;
  readonly cue: ConflictStampCue;
};

export class AlibiSplitScreenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AlibiSplitScreenError";
  }
}

export function linearGainUnits(dbtp: number): number {
  if (!Number.isFinite(dbtp) || dbtp > TRUE_PEAK_CEILING_DBTP) {
    fail(`nominal peak ${dbtp} dBTP exceeds ${TRUE_PEAK_CEILING_DBTP} dBTP`);
  }
  return Math.floor(10 ** (dbtp / 20) * GAIN_UNIT_SCALE + 1e-6);
}

export const CONFLICT_STAMP_GAIN_UNITS = linearGainUnits(CONFLICT_STAMP_DBTP);
export const TRUE_PEAK_CEILING_UNITS = linearGainUnits(TRUE_PEAK_CEILING_DBTP);

export function frameForOffsetMs(offsetMs: number): number {
  assertOffsetMs(offsetMs);
  return Math.floor((offsetMs * FRAME_FPS) / 1_000);
}

export function mixSampleForOffsetMs(offsetMs: number): number {
  assertOffsetMs(offsetMs);
  return offsetMs * SAMPLES_PER_MS;
}

export function stampSync(offsetMs: number): StampSync {
  const start_frame = frameForOffsetMs(offsetMs);
  const start_sample = mixSampleForOffsetMs(offsetMs);
  const sync = { offset_ms: offsetMs, start_sample, start_frame };
  assertMillisecondStampSync(sync);
  return sync;
}

export function assertMillisecondStampSync(sync: StampSync): void {
  if (sync.start_sample !== sync.offset_ms * SAMPLES_PER_MS) fail("stamp sample drifted from the millisecond");
  const product = sync.offset_ms * FRAME_FPS;
  if (product < sync.start_frame * 1_000 || product >= (sync.start_frame + 1) * 1_000) {
    fail("stamp frame does not contain the millisecond");
  }
  if (sync.start_frame !== Math.floor(sync.start_sample / SAMPLES_PER_FRAME)) {
    fail("stamp frame does not match the mix sample");
  }
}

export function microShake(frame: number, stampFrame: number, requestedPx: number): Shake {
  if (!Number.isInteger(frame) || frame < 0) fail("frame must be a non-negative integer");
  if (!Number.isInteger(stampFrame) || stampFrame < 0) fail("stamp frame must be a non-negative integer");
  const amplitude = clampedAmplitude(requestedPx);
  const elapsed = frame - stampFrame;
  if (elapsed < 0 || elapsed >= STAMP_HOLD_FRAMES || amplitude === 0) return { x: 0, y: 0 };
  const decayed = Math.max(1, Math.ceil((amplitude * (STAMP_HOLD_FRAMES - elapsed)) / STAMP_HOLD_FRAMES));
  const magnitude = Math.min(MAX_SHAKE_PX, decayed);
  const sign = SHAKE_SIGNS[elapsed];
  if (!sign) fail("shake frame is outside the stamp");
  const x = clampAxis(sign[0] * magnitude);
  const y = clampAxis(sign[1] * magnitude);
  assertShakeDistance({ x, y });
  return { x, y };
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

export function translateRect(rect: Rect, dx: number, dy: number): Rect {
  return { x: rect.x + dx, y: rect.y + dy, width: rect.width, height: rect.height };
}

export function walkSplit(node: SplitChild, into: SplitNode[] = []): SplitNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkSplit(child, into);
  return into;
}

export function layoutAlibiSplitScreen(props: AlibiSplitScreenProps): AlibiSplitLayout {
  const prepared = prepare(props);
  const content = contentRect(prepared.isEndScreen);
  const exclusion = exclusionRect();
  const captionBar = captionBarRect();
  const endScreenMask = prepared.isEndScreen ? endScreenMaskRect() : null;
  const graphic = graphicRect(content);
  const shake = microShake(prepared.frame, prepared.sync.start_frame, prepared.shakePx);
  const columns = textColumns(graphic.width);
  const maxLines = maxBodyLines(graphic.height);
  const claim = placePane(prepared.claim, CLAIM_HEADER, 0, claimWidth(graphic.width), graphic, shake, columns, maxLines);
  const evidenceX = claim.box.width + STAMP_W;
  const evidence = placePane(
    prepared.evidence,
    EVIDENCE_HEADER,
    evidenceX,
    graphic.width - evidenceX,
    graphic,
    shake,
    columns,
    maxLines,
  );
  const rule = ruleRect(claim.box.width, graphic.height);
  const rulePage = pageOf(graphic, shake, rule);
  const visible = prepared.frame >= prepared.sync.start_frame;
  const stamp = visible ? placeStamp(claim.box.width, graphic, shake) : null;
  const layout: AlibiSplitLayout = {
    motif: ALIBI_SPLIT_SCREEN_ID,
    owner: ALIBI_SPLIT_SCREEN_OWNER,
    motifNumber: ALIBI_MOTIF_NUMBER,
    frame: prepared.frame,
    sceneId: prepared.sceneId,
    isEndScreen: prepared.isEndScreen,
    content,
    exclusion,
    captionBar,
    endScreenMask,
    graphic,
    shake,
    shakePx: clampedAmplitude(prepared.shakePx),
    sync: prepared.sync,
    claim,
    evidence,
    rule,
    rulePage,
    stamp,
    cues: [prepared.cue],
    cuesStarted: prepared.frame >= prepared.sync.start_frame ? [prepared.cue] : [],
  };
  assertContained(layout);
  return layout;
}

export function AlibiSplitScreen(props: AlibiSplitScreenProps): SplitNode {
  const layout = layoutAlibiSplitScreen(props);
  const origin = layout.content;
  const claimNode = paneNode(layout.claim, "claim", CLAIM_BG);
  const evidenceNode = paneNode(layout.evidence, "evidence", EVIDENCE_BG);
  const graphicChildren: SplitChild[] = [
    claimNode,
    evidenceNode,
    element(
      { slot: "split-rule" },
      {
        position: "absolute",
        left: layout.rule.x,
        top: layout.rule.y,
        width: layout.rule.width,
        height: layout.rule.height,
        overflow: "hidden",
        background: SLATE,
      },
    ),
  ];
  if (layout.stamp) {
    graphicChildren.push(
      element(
        {
          slot: "conflict-stamp",
          cue: CONFLICT_STAMP_CUE,
          label: CONFLICT_LABEL,
          "offset-ms": String(layout.sync.offset_ms),
          "start-sample": String(layout.sync.start_sample),
          "start-frame": String(layout.sync.start_frame),
        },
        {
          position: "absolute",
          left: layout.stamp.box.x,
          top: layout.stamp.box.y,
          width: layout.stamp.box.width,
          height: layout.stamp.box.height,
          boxSizing: "border-box",
          overflow: "hidden",
          border: `4px solid ${EVIDENCE_CRIMSON}`,
          background: PAPER_BG,
          color: EVIDENCE_CRIMSON,
          fontFamily: "Courier New, Courier, monospace",
          fontSize: 32,
          fontWeight: 700,
          letterSpacing: 4,
          lineHeight: `${STAMP_H}px`,
          textAlign: "center",
        },
        [CONFLICT_LABEL],
      ),
    );
  }
  const cue = layout.cues[0];
  if (!cue) fail("conflict_stamp cue missing");
  const layers: SplitChild[] = [
    element(
      { slot: "content" },
      {
        position: "relative",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      [
        element(
          {
            slot: "graphic",
            motif: ALIBI_SPLIT_SCREEN_ID,
            "shake-x": String(layout.shake.x),
            "shake-y": String(layout.shake.y),
          },
          {
            position: "absolute",
            left: layout.graphic.x - origin.x,
            top: layout.graphic.y - origin.y,
            width: layout.graphic.width,
            height: layout.graphic.height,
            boxSizing: "border-box",
            overflow: "hidden",
            transform: `translate(${layout.shake.x}px, ${layout.shake.y}px)`,
          },
          graphicChildren,
        ),
        element(
          {
            slot: "conflict-stamp-cue",
            cue: CONFLICT_STAMP_CUE,
            "offset-ms": String(cue.offset_ms),
            "start-sample": String(cue.start_sample),
            "start-frame": String(cue.start_frame),
            "duration-samples": String(cue.duration_samples),
          },
          {
            position: "absolute",
            left: 0,
            top: 0,
            width: 0,
            height: 0,
            overflow: "hidden",
          },
        ),
      ],
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: EXCLUSION_WIDTH,
        height: EXCLUSION_HEIGHT,
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
  return SafeZoneLayout({ isEndScreen: layout.isEndScreen, children: layers });
}

function SafeZoneLayout(props: { readonly isEndScreen: boolean; readonly children: readonly SplitChild[] }): SplitNode {
  return element(
    {
      "safe-zone": "css-contained",
      motif: ALIBI_SPLIT_SCREEN_ID,
      owner: ALIBI_SPLIT_SCREEN_OWNER,
      "motif-number": String(ALIBI_MOTIF_NUMBER),
      "end-screen": props.isEndScreen ? "true" : "false",
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
      paddingBottom: SAFE_PADDING_BOTTOM,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
      background: PAPER_BG,
    },
    props.children,
  );
}

function prepare(props: AlibiSplitScreenProps): Prepared {
  if (props === null || typeof props !== "object") fail("alibi split props must be an object");
  if (!Number.isInteger(props.frame) || props.frame < 0) fail("frame must be a non-negative integer");
  const sync = stampSync(props.stampAtMs);
  const sceneId = readId(props.sceneId, "sceneId");
  if (typeof props.isEndScreen !== "boolean" && props.isEndScreen !== undefined) fail("isEndScreen must be a boolean");
  const isEndScreen = props.isEndScreen === true;
  const requested = props.shakePx === undefined ? MAX_SHAKE_PX : props.shakePx;
  clampedAmplitude(requested);
  const claim = readClaim(props.claim);
  const evidence = readEvidence(props.evidence);
  if (claim.fact_id === evidence.fact_id) fail("claim and evidence must cite different facts");
  const cue = toCue(sceneId, sync);
  assertMillisecondStampSync(cue);
  if (cue.duration_samples !== CONFLICT_STAMP_DURATION_SAMPLES) fail("conflict_stamp duration drifted");
  if (cue.gain_units !== CONFLICT_STAMP_GAIN_UNITS || cue.gain_units >= TRUE_PEAK_CEILING_UNITS) {
    fail("conflict_stamp peak exceeds the ceiling");
  }
  return { sceneId, frame: props.frame, isEndScreen, shakePx: requested, claim, evidence, sync, cue };
}

function readClaim(value: ClaimPane): PreparedPane {
  if (value === null || typeof value !== "object") fail("claim must be an object");
  const source = value.source_type;
  if (source !== "suspect_statement" && source !== "news_report") {
    fail("claim source must be suspect_statement or news_report");
  }
  return readPane(value.fact_id, source, value.text, value.citation, "claim");
}

function readEvidence(value: EvidencePane): PreparedPane {
  if (value === null || typeof value !== "object") fail("evidence must be an object");
  const source = value.source_type;
  if (source !== "police_affidavit" && source !== "court_ruling") {
    fail("evidence source must be police_affidavit or court_ruling");
  }
  return readPane(value.fact_id, source, value.text, value.citation, "evidence");
}

function readPane(
  factId: unknown,
  source: ClaimSource | EvidenceSource,
  text: unknown,
  citation: unknown,
  label: string,
): PreparedPane {
  const id = readId(factId, `${label} fact_id`);
  const body = readLine(text, `${label} text`, MAX_TEXT);
  const cite = readLine(citation, `${label} citation`, MAX_CITATION);
  const all = body.split(/\s+/).filter((word) => word.length > 0);
  if (all.length === 0) fail(`${label} text must contain a word`);
  const truncated = all.length > MAX_WORDS;
  const words = truncated ? all.slice(0, MAX_WORDS) : all;
  return {
    fact_id: id,
    source_type: source,
    text: body,
    display: words.join(" "),
    words,
    citation: cite,
    truncated,
  };
}

function toCue(sceneId: string, sync: StampSync): ConflictStampCue {
  return {
    cue_id: `${sceneId}:${CONFLICT_STAMP_CUE}:${sync.start_sample}`,
    cue: CONFLICT_STAMP_CUE,
    scene_id: sceneId,
    start_sample: sync.start_sample,
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    start_frame: sync.start_frame,
    offset_ms: sync.offset_ms,
    duration_samples: CONFLICT_STAMP_DURATION_SAMPLES,
    cooldown_ms: COOLDOWN_MS,
    gain_units: CONFLICT_STAMP_GAIN_UNITS,
    gain_unit_scale: GAIN_UNIT_SCALE,
    peak_dbtp: CONFLICT_STAMP_DBTP,
    burst: false,
    tapered: false,
  };
}

function contentRect(isEndScreen: boolean): Rect {
  const caption = captionBarRect();
  const bottom = isEndScreen ? caption.y - END_SCREEN_MASK_H : caption.y;
  return {
    x: 0,
    y: SAFE_PADDING_TOP,
    width: FRAME_WIDTH,
    height: bottom - SAFE_PADDING_TOP,
  };
}

function exclusionRect(): Rect {
  const width = FRAME_WIDTH * 0.22;
  const height = FRAME_HEIGHT * 0.14;
  return { x: FRAME_WIDTH - width, y: FRAME_HEIGHT - height, width, height };
}

function captionBarRect(): Rect {
  return { x: 0, y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM, width: FRAME_WIDTH, height: SAFE_PADDING_BOTTOM };
}

function endScreenMaskRect(): Rect {
  const caption = captionBarRect();
  const exclusion = exclusionRect();
  return { x: 0, y: caption.y - END_SCREEN_MASK_H, width: exclusion.x, height: END_SCREEN_MASK_H };
}

function graphicRect(content: Rect): Rect {
  return {
    x: content.x + MAX_SHAKE_PX,
    y: content.y + MAX_SHAKE_PX,
    width: content.width - MAX_SHAKE_PX * 2,
    height: content.height - MAX_SHAKE_PX * 2,
  };
}

function claimWidth(graphicWidth: number): number {
  return Math.floor((graphicWidth - STAMP_W) / 2);
}

function ruleRect(claimW: number, graphicHeight: number): Rect {
  return {
    x: claimW + Math.floor(STAMP_W / 2) - 2,
    y: 0,
    width: 4,
    height: graphicHeight,
  };
}

function placeStamp(claimW: number, graphic: Rect, shake: Shake): PlacedStamp {
  const box: Rect = {
    x: claimW,
    y: Math.floor((graphic.height - STAMP_H) / 2),
    width: STAMP_W,
    height: STAMP_H,
  };
  return { label: CONFLICT_LABEL, box, page: pageOf(graphic, shake, box) };
}

function placePane(
  pane: PreparedPane,
  header: string,
  x: number,
  width: number,
  graphic: Rect,
  shake: Shake,
  columns: number,
  maxLines: number,
): PlacedText {
  const box: Rect = { x, y: 0, width, height: graphic.height };
  const wrapped = wrapWords(pane.words, columns, maxLines);
  const body: Rect = {
    x: x + PANE_PAD,
    y: PANE_PAD + HEADER_H + 8,
    width: width - PANE_PAD * 2,
    height: wrapped.lines.length * LINE_H,
  };
  const citation: Rect = {
    x: x + PANE_PAD,
    y: graphic.height - PANE_PAD - CITE_H,
    width: width - PANE_PAD * 2,
    height: CITE_H,
  };
  return {
    fact_id: pane.fact_id,
    source_type: pane.source_type,
    header,
    text: pane.text,
    display: pane.display,
    citation: pane.citation,
    lines: wrapped.lines,
    truncated: pane.truncated || wrapped.truncated,
    wordCount: pane.words.length,
    box,
    page: pageOf(graphic, shake, box),
    bodyPage: pageOf(graphic, shake, body),
    citationPage: pageOf(graphic, shake, citation),
  };
}

function textColumns(graphicWidth: number): number {
  const inner = claimWidth(graphicWidth) - PANE_PAD * 2;
  const columns = Math.floor(inner / CHAR_PX);
  if (columns < 8) fail("pane is too narrow for a claim");
  return columns;
}

function maxBodyLines(graphicHeight: number): number {
  const available = graphicHeight - PANE_PAD - HEADER_H - 8 - 8 - PANE_PAD - CITE_H;
  const lines = Math.floor(available / LINE_H);
  if (lines < 1) fail("pane is too short for a claim");
  return lines;
}

function wrapWords(
  words: readonly string[],
  columns: number,
  maxLines: number,
): { lines: string[]; truncated: boolean } {
  const tokens: string[] = [];
  for (const word of words) {
    if (word.length <= columns) {
      tokens.push(word);
      continue;
    }
    for (let index = 0; index < word.length; index += columns) tokens.push(word.slice(index, index + columns));
  }
  const lines: string[] = [];
  let current = "";
  let used = 0;
  for (; used < tokens.length; used += 1) {
    const token = tokens[used] ?? "";
    const next = current.length === 0 ? token : `${current} ${token}`;
    if (next.length <= columns) {
      current = next;
      continue;
    }
    if (lines.length + 1 === maxLines) break;
    if (current.length > 0) lines.push(current);
    current = token;
  }
  if (used < tokens.length) {
    const room = Math.max(1, columns - 1);
    const base = current.length > 0 ? current : (lines[lines.length - 1] ?? "");
    const ellipsis = `${base.slice(0, room).trimEnd()}…`;
    if (current.length > 0 || lines.length === 0) lines.push(ellipsis);
    else lines[lines.length - 1] = ellipsis;
    return { lines: lines.slice(0, maxLines), truncated: true };
  }
  if (current.length > 0) lines.push(current);
  return { lines, truncated: false };
}

function pageOf(graphic: Rect, shake: Shake, local: Rect): Rect {
  return {
    x: graphic.x + shake.x + local.x,
    y: graphic.y + shake.y + local.y,
    width: local.width,
    height: local.height,
  };
}

function assertContained(layout: AlibiSplitLayout): void {
  assertMillisecondStampSync(layout.sync);
  assertShakeDistance(layout.shake);
  const shaken = translateRect(layout.graphic, layout.shake.x, layout.shake.y);
  if (!rectInside(layout.graphic, layout.content)) fail("graphic is not inset inside the safe zone");
  if (layout.graphic.x !== layout.content.x + MAX_SHAKE_PX || layout.graphic.y !== layout.content.y + MAX_SHAKE_PX) {
    fail("graphic inset is not the 6 px shake clamp");
  }
  if (!rectInside(shaken, layout.content)) fail("shake leaves the safe zone");
  if (rectsOverlap(shaken, layout.captionBar)) fail("shake enters the caption bar");
  if (rectsOverlap(shaken, layout.exclusion)) fail("shake enters the exclusion box");
  if (layout.endScreenMask && rectsOverlap(shaken, layout.endScreenMask)) fail("shake enters the end-screen mask");
  if (!rectInside(layout.claim.page, shaken) || !rectInside(layout.evidence.page, shaken)) {
    fail("pane leaves the graphic");
  }
  if (!rectInside(layout.claim.bodyPage, layout.claim.page) || !rectInside(layout.evidence.bodyPage, layout.evidence.page)) {
    fail("claim text leaves its pane");
  }
  if (
    !rectInside(layout.claim.citationPage, layout.claim.page) ||
    !rectInside(layout.evidence.citationPage, layout.evidence.page)
  ) {
    fail("citation leaves its pane");
  }
  if (rectsOverlap(layout.claim.box, layout.evidence.box)) fail("claim overlaps the evidence pane");
  if (!rectInside(layout.rulePage, shaken)) fail("split rule leaves the graphic");
  if (layout.stamp && !rectInside(layout.stamp.page, shaken)) fail("CONFLICT stamp leaves the graphic");
  if (layout.stamp && rectsOverlap(layout.stamp.box, layout.claim.box)) fail("CONFLICT stamp covers the claim");
  if (layout.stamp && rectsOverlap(layout.stamp.box, layout.evidence.box)) fail("CONFLICT stamp covers the evidence");
  if (layout.cues.length !== 1 || layout.cues[0]?.cue !== CONFLICT_STAMP_CUE) fail("scene must emit one conflict_stamp");
  const cue = layout.cues[0];
  if (!cue) fail("conflict_stamp cue missing");
  if (cue.offset_ms !== layout.sync.offset_ms || cue.start_sample !== layout.sync.start_sample) {
    fail("conflict_stamp cue is not on the stamp millisecond");
  }
  if (cue.start_frame !== layout.sync.start_frame) fail("conflict_stamp cue frame drifted");
}

function assertShakeDistance(shake: Shake): void {
  if (!Number.isInteger(shake.x) || !Number.isInteger(shake.y)) fail("shake must be whole pixels");
  if (Math.abs(shake.x) > MAX_SHAKE_PX || Math.abs(shake.y) > MAX_SHAKE_PX) fail("shake exceeds 6 px");
  if (shake.x * shake.x + shake.y * shake.y > MAX_SHAKE_PX * MAX_SHAKE_PX) fail("shake exceeds 6 px");
}

function clampedAmplitude(px: number): number {
  if (!Number.isFinite(px) || px < 0) fail("shakePx must be a non-negative finite number");
  return Math.min(MAX_SHAKE_PX, Math.floor(px));
}

function clampAxis(value: number): number {
  if (value > MAX_SHAKE_PX) return MAX_SHAKE_PX;
  if (value < -MAX_SHAKE_PX) return -MAX_SHAKE_PX;
  return value;
}

function assertOffsetMs(offsetMs: number): void {
  if (!Number.isInteger(offsetMs) || offsetMs < 0) fail("stampAtMs must be a non-negative integer");
}

function readId(value: unknown, label: string): string {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) fail(`${label} must match ${ID_PATTERN}`);
  return value;
}

function readLine(value: unknown, label: string, max: number): string {
  if (typeof value !== "string") fail(`${label} must be 1–${max} characters`);
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed.length > max) fail(`${label} must be 1–${max} characters`);
  if (/[\u0000-\u001f<>]/.test(trimmed)) fail(`${label} must be a single plain line`);
  return trimmed;
}

function paneNode(pane: PlacedText, slot: "claim" | "evidence", background: string): SplitNode {
  return element(
    {
      slot,
      "fact-id": pane.fact_id,
      "source-type": pane.source_type,
      truncated: pane.truncated ? "true" : "false",
      words: String(pane.wordCount),
    },
    {
      position: "absolute",
      left: pane.box.x,
      top: pane.box.y,
      width: pane.box.width,
      height: pane.box.height,
      boxSizing: "border-box",
      overflow: "hidden",
      background,
    },
    [
      element(
        { slot: `${slot}-header` },
        {
          position: "absolute",
          left: PANE_PAD,
          top: PANE_PAD,
          width: pane.box.width - PANE_PAD * 2,
          height: HEADER_H,
          overflow: "hidden",
          color: INK,
          fontSize: 18,
          letterSpacing: 1,
          lineHeight: `${HEADER_H}px`,
        },
        [pane.header],
      ),
      element(
        { slot: `${slot}-body`, citation: pane.citation },
        {
          position: "absolute",
          left: PANE_PAD,
          top: PANE_PAD + HEADER_H + 8,
          width: pane.box.width - PANE_PAD * 2,
          height: pane.lines.length * LINE_H,
          overflow: "hidden",
          color: INK,
          fontSize: 28,
          lineHeight: `${LINE_H}px`,
          whiteSpace: "pre",
        },
        [pane.lines.join("\n")],
      ),
      element(
        { slot: `${slot}-citation` },
        {
          position: "absolute",
          left: PANE_PAD,
          top: pane.box.height - PANE_PAD - CITE_H,
          width: pane.box.width - PANE_PAD * 2,
          height: CITE_H,
          overflow: "hidden",
          color: INK,
          fontSize: 16,
          lineHeight: `${CITE_H}px`,
        },
        [pane.citation],
      ),
    ],
  );
}

function element(
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, CssValue>>,
  children?: readonly SplitChild[],
): SplitNode {
  if (children !== undefined && children.length > 0) {
    const only = children.length === 1 ? children[0] : children;
    if (only !== undefined) return { type: "div", dataset, props: { style, children: only } };
  }
  return { type: "div", dataset, props: { style } };
}

function fail(message: string): never {
  throw new AlibiSplitScreenError(message);
}

if (STAMP_HOLD_FRAMES !== 12 || !Number.isInteger(STAMP_HOLD_FRAMES)) {
  throw new AlibiSplitScreenError("conflict stamp hold must be 12 frames");
}
if (SHAKE_SIGNS.length !== STAMP_HOLD_FRAMES) {
  throw new AlibiSplitScreenError("shake pattern must cover the stamp hold");
}
if (CONFLICT_STAMP_DURATION_SAMPLES !== 19_200) {
  throw new AlibiSplitScreenError("conflict_stamp duration drifted");
}
if (CONFLICT_STAMP_GAIN_UNITS !== 501_187_233) {
  throw new AlibiSplitScreenError("conflict_stamp gain drifted");
}
if (SAMPLES_PER_FRAME !== 1_600 || SAMPLES_PER_MS !== 48) {
  throw new AlibiSplitScreenError("mix clock drifted");
}
