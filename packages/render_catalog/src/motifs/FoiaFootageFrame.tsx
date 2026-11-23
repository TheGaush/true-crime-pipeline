/**
 * Motif #4 — FoiaFootageFrame.
 *
 * Plays a rights-cleared, PII-scrubbed CFR 30 fps FOIA MP4 inside the
 * 1920×1080 frame. A 16:9 clip fills the frame. A 9:16 phone clip stays
 * in a pillarboxed column and the leftover width is a dossier sidebar.
 * Provenance HUD, callout zoom, and an optional StickFigure PiP are
 * editorial overlays. They are not baked into the footage.
 *
 * The footage stays `apply_grade: false` in `scene_grade_manifest.json`.
 * This file does not apply paper grain, vignette, or SVG turbulence.
 * Task 109 owns the shared grade builder and Task 114 owns the stick rig.
 * Neither file is copied here. Pass `gradeDelegate` to use Task 109, and
 * pass `pip.figure` to mount the rig's StickFigure node.
 */

export const MOTIF_COMPONENT = "FoiaFootageFrame" as const;
export const VISUAL_ENGINE = "FOIA_REAL_FOOTAGE" as const;
export const SCENE_GRADE_MANIFEST_FILENAME = "scene_grade_manifest.json" as const;
export const GRADE_MANIFEST_SCHEMA = "scene_grade_manifest.v1" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SAFE_TOP = 108;
export const SAFE_BOTTOM = 194;
export const EXCLUSION_WIDTH_RATIO = 0.22;
export const EXCLUSION_HEIGHT_RATIO = 0.14;
export const ZOOM_MIN_FACTOR = 1.15;
export const CALLOUT_WORD_LIMIT = 12;

export const SAFE_RECT: Rect = {
  x: 0,
  y: SAFE_TOP,
  width: FRAME_WIDTH,
  height: FRAME_HEIGHT - SAFE_TOP - SAFE_BOTTOM,
};

export const EXCLUSION_RECT: Rect = {
  x: FRAME_WIDTH * (1 - EXCLUSION_WIDTH_RATIO),
  y: FRAME_HEIGHT * (1 - EXCLUSION_HEIGHT_RATIO),
  width: FRAME_WIDTH * EXCLUSION_WIDTH_RATIO,
  height: FRAME_HEIGHT * EXCLUSION_HEIGHT_RATIO,
};

/** Task 106 pose ids. The solver stays in that task. */
export const STICK_POSES = [
  "idle",
  "walk_loop",
  "run_loop",
  "pointing",
  "seated",
  "evidence_hold",
  "doorway_entry",
  "listening",
  "writing",
  "phone_call",
  "arms_crossed",
  "handcuffed",
  "kneeling",
  "slumped",
] as const;

export type StickPoseId = (typeof STICK_POSES)[number];

export const VIDEO_KINDS = ["bodycam_mp4", "dashcam_mp4", "court_mp4"] as const;
export type FoiaVideoKind = (typeof VIDEO_KINDS)[number];

export const LICENSE_BASES = [
  "US_FED_EMPLOYEE_17USC105",
  "STATE_PUBLIC_RECORD_PERMITTED",
  "CC0_PUBLIC_DOMAIN",
  "EXPLICIT_LICENSE_GRANT",
  "FAIR_USE_REVIEW_REQUIRED",
  "RESTRICTED_NO_REUSE",
] as const;

export type LicenseBasis = (typeof LICENSE_BASES)[number];

export type FoiaFootageCode =
  | "MP4"
  | "NO_VIDEO"
  | "NOT_CFR_30"
  | "ASPECT"
  | "SCRUB"
  | "RIGHTS"
  | "PII"
  | "CALLOUT"
  | "FRAME"
  | "POSE"
  | "GRADE"
  | "LAYOUT";

export class FoiaFootageError extends Error {
  readonly code: FoiaFootageCode;

  constructor(code: FoiaFootageCode, message: string) {
    super(message);
    this.name = "FoiaFootageError";
    this.code = code;
  }
}

export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface CfrVideoProbe {
  readonly width: number;
  readonly height: number;
  readonly fps: 30;
  readonly cfr: true;
  readonly timescale: number;
  readonly sampleDelta: number;
  readonly sampleCount: number;
  readonly duration: number;
  readonly aspect: "16:9" | "9:16";
}

export interface FoiaProvenance {
  readonly asset_id: string;
  readonly creator_entity: string;
  readonly rights_holder: string;
  readonly license_basis: LicenseBasis;
  readonly rights_review_status: "NOT_STARTED" | "IN_REVIEW" | "APPROVED" | "REJECTED";
  readonly contains_third_party_attach: 0 | 1;
  readonly media_kind: string;
  readonly scrubbed_path: string;
  readonly normalized_cfr_30fps_48k: 0 | 1;
  readonly visual_pii_blurred: 0 | 1;
  readonly spoken_pii_bleeped: 0 | 1;
  /** Kept off the frame. Never drawn and never fetched. */
  readonly raw_path?: string;
  readonly source_domain?: string;
}

export interface CalloutZoom {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly label: string;
  readonly fact_id: string;
}

export interface StickFigurePip {
  readonly pose: StickPoseId;
  readonly facing?: "left" | "right";
  /** Node from the stick rig. This motif does not draw the skeleton. */
  readonly figure?: unknown;
}

export interface GradeSceneInput {
  readonly scene_id: string;
  readonly visual_engine: typeof VISUAL_ENGINE;
  readonly motif_component: typeof MOTIF_COMPONENT;
  readonly bodycam_inset: Rect;
  readonly narrator_pip: Rect | null;
}

export interface UngradedMask extends Rect {
  readonly kind: "bodycam_inset";
  readonly apply_grade: false;
  readonly needs_grade: false;
  readonly exempt_from_grain: true;
}

export interface StylizedOverlay extends Rect {
  readonly kind: "narrator_pip_border";
  readonly apply_grade: true;
  readonly needs_grade: true;
  readonly exempt_from_grain: false;
  readonly ungraded_holes: readonly Rect[];
}

export interface SceneGradeRecord {
  readonly timeline_index: number;
  readonly scene_id: string;
  readonly visual_engine: typeof VISUAL_ENGINE;
  readonly motif_component: typeof MOTIF_COMPONENT;
  readonly apply_grade: false;
  readonly needs_grade: false;
  readonly is_foia: true;
  readonly exempt_from_grain: true;
  readonly remotion_grain_applied: false;
  readonly remotion_vignette_applied: false;
  readonly paper_grain: 0;
  readonly vignette: 0;
  readonly grain_phase: null;
  readonly grade_owner: "none";
  readonly ungraded_masks: readonly UngradedMask[];
  readonly stylized_overlays: readonly StylizedOverlay[];
}

export interface SceneGradeManifest {
  readonly filename: typeof SCENE_GRADE_MANIFEST_FILENAME;
  readonly schema: typeof GRADE_MANIFEST_SCHEMA;
  readonly contract_version: "v4";
  readonly fps: typeof FRAME_FPS;
  readonly width_px: typeof FRAME_WIDTH;
  readonly height_px: typeof FRAME_HEIGHT;
  readonly remotion_grain_applied: false;
  readonly remotion_vignette_applied: false;
  readonly paper_grain: 0;
  readonly vignette: 0;
  readonly grain_phase: null;
  readonly grade_owner: "agent6_single_pass";
  readonly episode_id?: string;
  readonly scenes: readonly SceneGradeRecord[];
}

export type GradeDelegate = (
  scenes: readonly GradeSceneInput[],
  episodeId?: string,
) => SceneGradeManifest;

export type FoiaLayout = "full-bleed" | "dossier-sidebar";

export type FoiaChild = FoiaNode | string;

export interface FoiaNode {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, string | number>>;
    readonly children?: readonly FoiaChild[];
  };
  readonly stickFigure?: unknown;
}

export interface FoiaGradeDocument {
  readonly filename: typeof SCENE_GRADE_MANIFEST_FILENAME;
  readonly json: string;
  readonly manifest: SceneGradeManifest;
  readonly source: "local" | "delegate";
}

export interface FoiaFootageModel {
  readonly motif: typeof MOTIF_COMPONENT;
  readonly visualEngine: typeof VISUAL_ENGINE;
  readonly applyGrade: false;
  readonly fps: typeof FRAME_FPS;
  readonly cfr: true;
  readonly layout: FoiaLayout;
  readonly probe: CfrVideoProbe;
  readonly frame: number;
  readonly timestampMs: number;
  readonly videoRect: Rect;
  readonly sidebarRect: Rect | null;
  readonly hudRect: Rect;
  readonly calloutOutlineRect: Rect;
  readonly zoomRect: Rect;
  readonly zoomFactor: number;
  readonly pipRect: Rect | null;
  readonly element: FoiaNode;
  readonly grade: FoiaGradeDocument;
}

interface LayoutPlan {
  readonly layout: FoiaLayout;
  readonly videoRect: Rect;
  readonly sidebarRect: Rect | null;
  readonly hudRect: Rect;
  readonly zoomRect: Rect;
  readonly pipRect: Rect;
}

const POSE_SET: ReadonlySet<string> = new Set(STICK_POSES);
const VIDEO_KIND_SET: ReadonlySet<string> = new Set(VIDEO_KINDS);
const ID_PATTERN = /^[A-Za-z0-9_-]+$/;
const ASPECT_TOLERANCE = 0.01;

export function probeFoiaMp4(bytes: Uint8Array): CfrVideoProbe {
  if (!(bytes instanceof Uint8Array) || bytes.length < 8) {
    throw new FoiaFootageError("MP4", "FOIA footage requires an MP4 byte box");
  }
  const root = readBoxes(bytes);
  const moov = oneBox(root, "moov");
  if (!moov) throw new FoiaFootageError("MP4", "FOIA footage requires a moov box");
  const traks = childBoxes(moov.data).filter((box) => box.type === "trak");
  const videos = traks.filter((trak) => handlerOf(trak) === "vide");
  if (videos.length === 0) {
    throw new FoiaFootageError("NO_VIDEO", "FOIA footage requires a video track");
  }
  if (videos.length > 1) {
    throw new FoiaFootageError("MP4", "FOIA footage requires a single video track");
  }
  const trak = videos[0];
  if (!trak) throw new FoiaFootageError("NO_VIDEO", "FOIA footage requires a video track");
  const trakBoxes = childBoxes(trak.data);
  if (trakBoxes.some((box) => box.type === "edts")) {
    throw new FoiaFootageError("NOT_CFR_30", "edit lists are not constant 30 fps");
  }
  const { width, height } = trackSize(trakBoxes);
  const timing = trackTiming(trakBoxes);
  if (timing.timescale % timing.sampleDelta !== 0 || timing.timescale / timing.sampleDelta !== FRAME_FPS) {
    throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  }
  if (timing.duration !== timing.sampleCount * timing.sampleDelta) {
    throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  }
  return {
    width,
    height,
    fps: FRAME_FPS,
    cfr: true,
    timescale: timing.timescale,
    sampleDelta: timing.sampleDelta,
    sampleCount: timing.sampleCount,
    duration: timing.duration,
    aspect: classifyAspect(width, height),
  };
}

export function gradeTargetAt(record: SceneGradeRecord, x: number, y: number): "exempt" | "agent6" {
  const masks = record.ungraded_masks ?? [];
  const overlays = record.stylized_overlays ?? [];
  for (const mask of masks) {
    if (contains(mask, x, y)) return "exempt";
  }
  for (const overlay of overlays) {
    if (!contains(overlay, x, y)) continue;
    if ((overlay.ungraded_holes ?? []).some((hole) => contains(hole, x, y))) return "exempt";
    return overlay.apply_grade ? "agent6" : "exempt";
  }
  return record.apply_grade ? "agent6" : "exempt";
}

export function rectInside(inner: Rect, outer: Rect, epsilon = 1e-6): boolean {
  return (
    inner.x >= outer.x - epsilon &&
    inner.y >= outer.y - epsilon &&
    inner.x + inner.width <= outer.x + outer.width + epsilon &&
    inner.y + inner.height <= outer.y + outer.height + epsilon
  );
}

export function rectsOverlap(a: Rect, b: Rect, epsilon = 1e-6): boolean {
  return (
    a.x + a.width > b.x + epsilon &&
    b.x + b.width > a.x + epsilon &&
    a.y + a.height > b.y + epsilon &&
    b.y + b.height > a.y + epsilon
  );
}

export function walkFoia(node: FoiaChild, into: FoiaNode[] = []): FoiaNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (!children) return into;
  for (const child of children) walkFoia(child, into);
  return into;
}

export interface FoiaFootageInput {
  readonly sceneId: string;
  readonly episodeId?: string;
  readonly bytes: Uint8Array;
  readonly provenance: FoiaProvenance;
  readonly callout: CalloutZoom;
  readonly frame?: number;
  readonly pip?: StickFigurePip | null;
  readonly isEndScreen?: boolean;
  readonly gradeDelegate?: GradeDelegate;
}

export function FoiaFootageFrame(input: FoiaFootageInput): FoiaFootageModel {
  assertSceneId(input.sceneId);
  if (input.episodeId !== undefined) assertSceneId(input.episodeId);
  const probe = probeFoiaMp4(input.bytes);
  assertProvenance(input.provenance);
  const frame = input.frame ?? 0;
  if (!Number.isInteger(frame) || frame < 0 || frame >= probe.sampleCount) {
    throw new FoiaFootageError("FRAME", "frame must be an integer inside the CFR clip");
  }
  assertCallout(input.callout, probe);
  const pip = input.pip ?? null;
  if (pip) assertPip(pip);
  const plan = layoutFor(probe);
  const outline = mapCallout(input.callout, probe, plan.videoRect);
  if (!rectInside(outline, SAFE_RECT) || rectsOverlap(outline, EXCLUSION_RECT)) {
    throw new FoiaFootageError("CALLOUT", "callout outline must stay inside the safe zone");
  }
  const zoomFactor = magnification(input.callout, outline, plan.zoomRect);
  if (!(zoomFactor > ZOOM_MIN_FACTOR)) {
    throw new FoiaFootageError("CALLOUT", "callout zoom must magnify the source rect");
  }
  const pipRect = pip ? plan.pipRect : null;
  assertPlaced(plan, outline, pipRect);
  const grade = gradeDocument(input, plan.videoRect, pipRect);
  const element = renderTree({
    input,
    probe,
    plan,
    outline,
    zoomFactor,
    pipRect,
    frame,
  });
  assertClean(element);
  const model: FoiaFootageModel = {
    motif: MOTIF_COMPONENT,
    visualEngine: VISUAL_ENGINE,
    applyGrade: false,
    fps: FRAME_FPS,
    cfr: true,
    layout: plan.layout,
    probe,
    frame,
    timestampMs: Math.round((frame * 1000) / FRAME_FPS),
    videoRect: plan.videoRect,
    sidebarRect: plan.sidebarRect,
    hudRect: plan.hudRect,
    calloutOutlineRect: outline,
    zoomRect: plan.zoomRect,
    zoomFactor,
    pipRect,
    element,
    grade,
  };
  assertFootageSamples(model.grade.manifest, input.sceneId, plan.videoRect);
  return model;
}

function gradeDocument(input: FoiaFootageInput, video: Rect, pip: Rect | null): FoiaGradeDocument {
  const scene: GradeSceneInput = {
    scene_id: input.sceneId,
    visual_engine: VISUAL_ENGINE,
    motif_component: MOTIF_COMPONENT,
    bodycam_inset: video,
    narrator_pip: pip,
  };
  const local = localManifest(input.sceneId, input.episodeId, video, pip);
  const delegated = input.gradeDelegate ? callDelegate(input.gradeDelegate, scene, input.episodeId) : null;
  const manifest = delegated ?? local;
  assertFootageSamples(manifest, input.sceneId, video);
  return {
    filename: SCENE_GRADE_MANIFEST_FILENAME,
    json: `${JSON.stringify(manifest, null, 2)}\n`,
    manifest,
    source: delegated ? "delegate" : "local",
  };
}

function callDelegate(
  delegate: GradeDelegate,
  scene: GradeSceneInput,
  episodeId: string | undefined,
): SceneGradeManifest {
  const manifest = episodeId === undefined ? delegate([scene]) : delegate([scene], episodeId);
  if (!manifest || manifest.filename !== SCENE_GRADE_MANIFEST_FILENAME) {
    throw new FoiaFootageError("GRADE", "grade delegate must write scene_grade_manifest.json");
  }
  return manifest;
}

function localManifest(
  sceneId: string,
  episodeId: string | undefined,
  video: Rect,
  pip: Rect | null,
): SceneGradeManifest {
  const mask: UngradedMask = {
    kind: "bodycam_inset",
    apply_grade: false,
    needs_grade: false,
    exempt_from_grain: true,
    x: video.x,
    y: video.y,
    width: video.width,
    height: video.height,
  };
  const overlays: StylizedOverlay[] = [];
  if (pip && !rectsOverlap(pip, video)) {
    overlays.push({
      kind: "narrator_pip_border",
      apply_grade: true,
      needs_grade: true,
      exempt_from_grain: false,
      x: pip.x,
      y: pip.y,
      width: pip.width,
      height: pip.height,
      ungraded_holes: [],
    });
  }
  const record: SceneGradeRecord = {
    timeline_index: 0,
    scene_id: sceneId,
    visual_engine: VISUAL_ENGINE,
    motif_component: MOTIF_COMPONENT,
    apply_grade: false,
    needs_grade: false,
    is_foia: true,
    exempt_from_grain: true,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: "none",
    ungraded_masks: [mask],
    stylized_overlays: overlays,
  };
  const manifest: SceneGradeManifest = {
    filename: SCENE_GRADE_MANIFEST_FILENAME,
    schema: GRADE_MANIFEST_SCHEMA,
    contract_version: "v4",
    fps: FRAME_FPS,
    width_px: FRAME_WIDTH,
    height_px: FRAME_HEIGHT,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: "agent6_single_pass",
    scenes: [record],
  };
  if (episodeId === undefined) return manifest;
  return { ...manifest, episode_id: episodeId };
}

function assertFootageSamples(manifest: SceneGradeManifest, sceneId: string, video: Rect): void {
  if (manifest.remotion_grain_applied || manifest.remotion_vignette_applied) {
    throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
  }
  if (manifest.paper_grain !== 0 || manifest.vignette !== 0 || manifest.grain_phase !== null) {
    throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
  }
  const scene = manifest.scenes.find((item) => item.scene_id === sceneId);
  if (!scene || scene.motif_component !== MOTIF_COMPONENT || scene.visual_engine !== VISUAL_ENGINE) {
    throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
  }
  if (scene.apply_grade !== false || scene.needs_grade !== false || scene.is_foia !== true) {
    throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
  }
  if (scene.paper_grain !== 0 || scene.vignette !== 0 || scene.remotion_grain_applied || scene.remotion_vignette_applied) {
    throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
  }
  const samples = [
    [video.x + video.width / 2, video.y + video.height / 2],
    [video.x + 0.5, video.y + 0.5],
    [video.x + video.width - 0.5, video.y + 0.5],
    [video.x + 0.5, video.y + video.height - 0.5],
    [video.x + video.width - 0.5, video.y + video.height - 0.5],
  ];
  for (const sample of samples) {
    const x = sample[0];
    const y = sample[1];
    if (x === undefined || y === undefined || gradeTargetAt(scene, x, y) !== "exempt") {
      throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
    }
  }
  for (const overlay of scene.stylized_overlays ?? []) {
    if (!overlay.apply_grade) continue;
    const overlap = intersection(overlay, video);
    if (!overlap) continue;
    const x = overlap.x + overlap.width / 2;
    const y = overlap.y + overlap.height / 2;
    if (gradeTargetAt(scene, x, y) !== "exempt") {
      throw new FoiaFootageError("GRADE", "FOIA footage must stay apply_grade false");
    }
  }
}

function intersection(a: Rect, b: Rect): Rect | null {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

interface RenderArgs {
  readonly input: FoiaFootageInput;
  readonly probe: CfrVideoProbe;
  readonly plan: LayoutPlan;
  readonly outline: Rect;
  readonly zoomFactor: number;
  readonly pipRect: Rect | null;
  readonly frame: number;
}

function renderTree(args: RenderArgs): FoiaNode {
  const { input, probe, plan, outline, zoomFactor, pipRect, frame } = args;
  const provenance = input.provenance;
  const flat = {
    position: "absolute",
    overflow: "hidden",
    filter: "none",
    backgroundImage: "none",
    boxShadow: "none",
  };
  const footage = node(
    {
      role: "foia-footage",
      src: provenance.scrubbed_path,
      "apply-grade": "false",
      fps: String(FRAME_FPS),
      cfr: "true",
      frame: String(frame),
      "timestamp-ms": String(Math.round((frame * 1000) / FRAME_FPS)),
      "sample-count": String(probe.sampleCount),
      "clip-width": String(probe.width),
      "clip-height": String(probe.height),
      "object-fit": "contain",
      "paper-grain": "0",
      vignette: "0",
    },
    { ...flat, ...boxStyle(plan.videoRect), backgroundColor: "transparent" },
  );
  const outlineNode = node(
    {
      role: "callout-outline",
      "fact-id": input.callout.fact_id,
    },
    {
      ...flat,
      ...boxStyle(outline),
      border: "2px solid currentColor",
      backgroundColor: "transparent",
      pointerEvents: "none",
    },
  );
  const hud = node(
    { role: "provenance-hud", "apply-grade": "false" },
    { ...flat, ...boxStyle(plan.hudRect), overflow: "hidden" },
    [
      "FOIA SCRUBBED CFR 30",
      provenance.creator_entity,
      provenance.rights_holder,
      provenance.license_basis,
      provenance.asset_id,
      provenance.media_kind,
      "apply_grade false",
    ],
  );
  const zoom = node(
    {
      role: "callout-zoom",
      "fact-id": input.callout.fact_id,
      "zoom-factor": String(zoomFactor),
      "source-x": String(input.callout.x),
      "source-y": String(input.callout.y),
      "source-width": String(input.callout.width),
      "source-height": String(input.callout.height),
    },
    { ...flat, ...boxStyle(plan.zoomRect), overflow: "hidden", border: "2px solid currentColor" },
    [input.callout.label, input.callout.fact_id],
  );
  const children: FoiaChild[] = [];
  if (plan.sidebarRect) {
    children.push(
      node(
        { role: "dossier-sidebar", pillarbox: "true" },
        { ...flat, ...boxStyle(plan.sidebarRect), backgroundColor: "transparent" },
      ),
    );
  }
  children.push(footage, outlineNode, hud, zoom);
  if (pipRect && input.pip) {
    const pipDataset: Record<string, string> = {
      role: "pip-stick-figure",
      component: "StickFigure",
      pose: input.pip.pose,
      facing: input.pip.facing ?? "right",
      mounted: input.pip.figure === undefined ? "slot" : "figure",
    };
    children.push(
      node(
        pipDataset,
        { ...flat, ...boxStyle(pipRect), overflow: "hidden" },
        [],
        input.pip.figure,
      ),
    );
  }
  return node(
    {
      role: "foia-footage-frame",
      motif: MOTIF_COMPONENT,
      "visual-engine": VISUAL_ENGINE,
      "apply-grade": "false",
      layout: plan.layout,
      pillarbox: plan.layout === "dossier-sidebar" ? "true" : "false",
      fps: String(FRAME_FPS),
      cfr: "true",
      "paper-grain": "0",
      vignette: "0",
      "end-screen": input.isEndScreen === true ? "true" : "false",
    },
    {
      ...flat,
      position: "relative",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      left: 0,
      top: 0,
      backgroundColor: "transparent",
    },
    children,
  );
}

function layoutFor(probe: CfrVideoProbe): LayoutPlan {
  if (probe.aspect === "16:9") return fullBleedLayout();
  return dossierLayout(probe);
}

function fullBleedLayout(): LayoutPlan {
  const videoRect: Rect = { x: 0, y: 0, width: FRAME_WIDTH, height: FRAME_HEIGHT };
  const hudRect: Rect = { x: 32, y: SAFE_TOP, width: 900, height: 72 };
  const zoomRect: Rect = { x: FRAME_WIDTH - 32 - 520, y: 200, width: 520, height: 292 };
  const pipRect: Rect = { x: 32, y: SAFE_RECT.y + SAFE_RECT.height - 16 - 280, width: 240, height: 280 };
  return { layout: "full-bleed", videoRect, sidebarRect: null, hudRect, zoomRect, pipRect };
}

function dossierLayout(probe: CfrVideoProbe): LayoutPlan {
  const phoneHeight = SAFE_RECT.height;
  const phoneWidth = phoneHeight * (probe.width / probe.height);
  const videoRect: Rect = { x: SAFE_RECT.x, y: SAFE_RECT.y, width: phoneWidth, height: phoneHeight };
  const gutter = 28;
  const sideX = videoRect.x + videoRect.width + gutter;
  const sidebarRect: Rect = {
    x: sideX,
    y: SAFE_RECT.y,
    width: SAFE_RECT.x + SAFE_RECT.width - sideX,
    height: SAFE_RECT.height,
  };
  if (sidebarRect.width < 320) {
    throw new FoiaFootageError("LAYOUT", "9:16 dossier sidebar does not fit the 16:9 frame");
  }
  const innerX = sidebarRect.x + 16;
  const innerW = sidebarRect.width - 32;
  const hudRect: Rect = { x: innerX, y: sidebarRect.y + 16, width: innerW, height: 120 };
  const zoomRect: Rect = { x: innerX, y: hudRect.y + hudRect.height + 16, width: innerW, height: 280 };
  const pipRect: Rect = {
    x: innerX,
    y: sidebarRect.y + sidebarRect.height - 16 - 260,
    width: 260,
    height: 260,
  };
  return { layout: "dossier-sidebar", videoRect, sidebarRect, hudRect, zoomRect, pipRect };
}

function assertPlaced(plan: LayoutPlan, outline: Rect, pip: Rect | null): void {
  const overlays = [plan.hudRect, plan.zoomRect];
  if (pip) overlays.push(pip);
  for (const rect of overlays) {
    if (!rectInside(rect, SAFE_RECT) || rectsOverlap(rect, EXCLUSION_RECT)) {
      throw new FoiaFootageError("LAYOUT", "editorial overlay left the safe zone");
    }
  }
  if (plan.layout === "dossier-sidebar") {
    if (!plan.sidebarRect) throw new FoiaFootageError("LAYOUT", "9:16 frame is missing its dossier sidebar");
    if (rectsOverlap(plan.videoRect, plan.sidebarRect)) {
      throw new FoiaFootageError("LAYOUT", "dossier sidebar overlaps the FOIA picture");
    }
    if (!rectInside(plan.videoRect, SAFE_RECT)) {
      throw new FoiaFootageError("LAYOUT", "9:16 picture left the safe zone");
    }
  }
  if (rectsOverlap(plan.hudRect, plan.zoomRect)) {
    throw new FoiaFootageError("LAYOUT", "provenance HUD overlaps the callout zoom");
  }
  if (pip && (rectsOverlap(pip, plan.hudRect) || rectsOverlap(pip, plan.zoomRect))) {
    throw new FoiaFootageError("LAYOUT", "StickFigure PiP overlaps another overlay");
  }
  if (!rectInside(outline, plan.videoRect)) {
    throw new FoiaFootageError("CALLOUT", "callout outline must sit on the footage");
  }
}

function mapCallout(callout: CalloutZoom, probe: CfrVideoProbe, video: Rect): Rect {
  return {
    x: video.x + (callout.x / probe.width) * video.width,
    y: video.y + (callout.y / probe.height) * video.height,
    width: (callout.width / probe.width) * video.width,
    height: (callout.height / probe.height) * video.height,
  };
}

function magnification(callout: CalloutZoom, outline: Rect, zoom: Rect): number {
  const fit = Math.min(zoom.width / callout.width, zoom.height / callout.height);
  const magnified = callout.width * fit;
  if (outline.width <= 0) return 0;
  return magnified / outline.width;
}

function assertCallout(callout: CalloutZoom, probe: CfrVideoProbe): void {
  if (!callout || typeof callout !== "object") {
    throw new FoiaFootageError("CALLOUT", "callout zoom box is required");
  }
  for (const value of [callout.x, callout.y, callout.width, callout.height]) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new FoiaFootageError("CALLOUT", "callout rect must be finite");
    }
  }
  if (callout.width <= 0 || callout.height <= 0) {
    throw new FoiaFootageError("CALLOUT", "callout rect must have area");
  }
  if (callout.x < 0 || callout.y < 0 || callout.x + callout.width > probe.width || callout.y + callout.height > probe.height) {
    throw new FoiaFootageError("CALLOUT", "callout rect must sit inside the clip");
  }
  const words = callout.label.trim().split(/\s+/).filter((word) => word.length > 0);
  if (words.length < 1 || words.length > CALLOUT_WORD_LIMIT) {
    throw new FoiaFootageError("CALLOUT", `callout label must be 1 to ${CALLOUT_WORD_LIMIT} words`);
  }
  if (!ID_PATTERN.test(callout.fact_id)) {
    throw new FoiaFootageError("CALLOUT", "fact_id must match ^[A-Za-z0-9_-]+$");
  }
}

function assertPip(pip: StickFigurePip): void {
  if (!POSE_SET.has(pip.pose)) {
    throw new FoiaFootageError("POSE", `unknown StickFigure pose: ${pip.pose}`);
  }
  if (pip.facing !== undefined && pip.facing !== "left" && pip.facing !== "right") {
    throw new FoiaFootageError("POSE", 'StickFigure facing must be "left" or "right"');
  }
}

function assertProvenance(provenance: FoiaProvenance): void {
  if (!provenance || typeof provenance !== "object") {
    throw new FoiaFootageError("SCRUB", "FOIA provenance is required");
  }
  if (!ID_PATTERN.test(provenance.asset_id)) {
    throw new FoiaFootageError("SCRUB", "asset_id must match ^[A-Za-z0-9_-]+$");
  }
  if (!nonEmpty(provenance.creator_entity) || !nonEmpty(provenance.rights_holder)) {
    throw new FoiaFootageError("SCRUB", "creator_entity and rights_holder are required");
  }
  if (!(LICENSE_BASES as readonly string[]).includes(provenance.license_basis)) {
    throw new FoiaFootageError("RIGHTS", "license_basis is not a known FOIA basis");
  }
  if (provenance.license_basis === "RESTRICTED_NO_REUSE") {
    throw new FoiaFootageError("RIGHTS", "RESTRICTED_NO_REUSE footage cannot be framed");
  }
  if (provenance.rights_review_status !== "APPROVED") {
    throw new FoiaFootageError("RIGHTS", "FOIA footage requires rights_review_status APPROVED");
  }
  if (provenance.contains_third_party_attach !== 0) {
    throw new FoiaFootageError("RIGHTS", "third-party attachments stay out of the FOIA frame");
  }
  if (!VIDEO_KIND_SET.has(provenance.media_kind)) {
    throw new FoiaFootageError("RIGHTS", "FOIA frame media_kind must be bodycam, dashcam, or court mp4");
  }
  if (provenance.normalized_cfr_30fps_48k !== 1) {
    throw new FoiaFootageError("SCRUB", "FOIA footage requires normalized_cfr_30fps_48k = 1");
  }
  if (provenance.visual_pii_blurred !== 1 || provenance.spoken_pii_bleeped !== 1) {
    throw new FoiaFootageError("PII", "FOIA footage must be visually blurred and spoken-PII bleeped");
  }
  const path = provenance.scrubbed_path;
  if (!nonEmpty(path) || path.includes("://") || path.startsWith("//")) {
    throw new FoiaFootageError("SCRUB", "scrubbed_path must be a local scrubbed file");
  }
}

function assertSceneId(value: string): void {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) {
    throw new FoiaFootageError("FRAME", "scene id must match ^[A-Za-z0-9_-]+$");
  }
}

function nonEmpty(value: string): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function classifyAspect(width: number, height: number): "16:9" | "9:16" {
  if (width <= 0 || height <= 0) {
    throw new FoiaFootageError("ASPECT", "FOIA frame aspect must be 16:9 or 9:16");
  }
  const ratio = width / height;
  const wide = 16 / 9;
  const tall = 9 / 16;
  const wideError = Math.abs(ratio - wide) / wide;
  const tallError = Math.abs(ratio - tall) / tall;
  if (wideError <= ASPECT_TOLERANCE && wideError <= tallError) return "16:9";
  if (tallError <= ASPECT_TOLERANCE) return "9:16";
  throw new FoiaFootageError("ASPECT", "FOIA frame aspect must be 16:9 or 9:16");
}

function assertClean(element: FoiaNode): void {
  const text = JSON.stringify(element);
  if (text.includes("feTurbulence") || text.includes("feDisplacementMap")) {
    throw new FoiaFootageError("GRADE", "FOIA frame cannot apply SVG turbulence");
  }
  for (const node of walkFoia(element)) {
    const filter = node.props.style.filter;
    const image = node.props.style.backgroundImage;
    if (filter !== "none" || image !== "none") {
      throw new FoiaFootageError("GRADE", "FOIA frame cannot apply grain or vignette");
    }
  }
}

interface Box {
  readonly type: string;
  readonly data: Uint8Array;
}

function readBoxes(bytes: Uint8Array): Box[] {
  const out: Box[] = [];
  let offset = 0;
  while (offset + 8 <= bytes.length) {
    const size32 = u32(bytes, offset);
    const type = ascii(bytes, offset + 4, 4);
    let header = 8;
    let size = size32;
    if (size32 === 1) {
      size = u64(bytes, offset + 8);
      header = 16;
    } else if (size32 === 0) {
      size = bytes.length - offset;
    }
    if (size < header || offset + size > bytes.length) {
      throw new FoiaFootageError("MP4", `truncated ${type} box`);
    }
    out.push({ type, data: bytes.subarray(offset + header, offset + size) });
    offset += size;
  }
  if (offset !== bytes.length) throw new FoiaFootageError("MP4", "trailing bytes after boxes");
  return out;
}

function childBoxes(data: Uint8Array): Box[] {
  return readBoxes(data);
}

function oneBox(list: readonly Box[], type: string): Box | null {
  const found = list.filter((box) => box.type === type);
  if (found.length > 1) throw new FoiaFootageError("MP4", `duplicate ${type} box`);
  return found[0] ?? null;
}

function handlerOf(trak: Box): string {
  const mdia = oneBox(childBoxes(trak.data), "mdia");
  if (!mdia) throw new FoiaFootageError("MP4", "video track is missing mdia");
  const hdlr = oneBox(childBoxes(mdia.data), "hdlr");
  if (!hdlr || hdlr.data.length < 12 || hdlr.data[0] !== 0) {
    throw new FoiaFootageError("MP4", "video track is missing hdlr");
  }
  return ascii(hdlr.data, 8, 4);
}

function trackSize(trakBoxes: readonly Box[]): { width: number; height: number } {
  const tkhd = oneBox(trakBoxes, "tkhd");
  if (!tkhd || tkhd.data.length < 8) throw new FoiaFootageError("MP4", "video track is missing tkhd");
  const end = tkhd.data.length;
  const width = fixed1616(tkhd.data, end - 8);
  const height = fixed1616(tkhd.data, end - 4);
  if (width <= 0 || height <= 0) {
    throw new FoiaFootageError("ASPECT", "FOIA frame aspect must be 16:9 or 9:16");
  }
  return { width, height };
}

interface Timing {
  readonly timescale: number;
  readonly duration: number;
  readonly sampleCount: number;
  readonly sampleDelta: number;
}

function trackTiming(trakBoxes: readonly Box[]): Timing {
  const mdia = oneBox(trakBoxes, "mdia");
  if (!mdia) throw new FoiaFootageError("MP4", "video track is missing mdia");
  const media = childBoxes(mdia.data);
  const mdhd = oneBox(media, "mdhd");
  const minf = oneBox(media, "minf");
  if (!mdhd || !minf) throw new FoiaFootageError("MP4", "video track is missing timing");
  const { timescale, duration } = readMdhd(mdhd.data);
  const stbl = oneBox(childBoxes(minf.data), "stbl");
  if (!stbl) throw new FoiaFootageError("MP4", "video track is missing stbl");
  const stts = oneBox(childBoxes(stbl.data), "stts");
  if (!stts) throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  const samples = readStts(stts.data);
  if (timescale <= 0 || samples.sampleCount <= 0 || samples.sampleDelta <= 0) {
    throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  }
  return { timescale, duration, sampleCount: samples.sampleCount, sampleDelta: samples.sampleDelta };
}

function readMdhd(data: Uint8Array): { timescale: number; duration: number } {
  const version = data[0];
  if (version === 0) {
    if (data.length < 20) throw new FoiaFootageError("MP4", "truncated mdhd");
    return { timescale: u32(data, 12), duration: u32(data, 16) };
  }
  if (version === 1) {
    if (data.length < 32) throw new FoiaFootageError("MP4", "truncated mdhd");
    return { timescale: u32(data, 20), duration: u64(data, 24) };
  }
  throw new FoiaFootageError("MP4", "unsupported mdhd version");
}

function readStts(data: Uint8Array): { sampleCount: number; sampleDelta: number } {
  if (data.length < 8 || data[0] !== 0) {
    throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  }
  const entryCount = u32(data, 4);
  if (entryCount < 1 || 8 + entryCount * 8 > data.length) {
    throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
  }
  let sampleCount = 0;
  let sampleDelta = 0;
  for (let index = 0; index < entryCount; index += 1) {
    const count = u32(data, 8 + index * 8);
    const delta = u32(data, 12 + index * 8);
    if (count <= 0 || delta <= 0) {
      throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
    }
    if (index === 0) sampleDelta = delta;
    else if (delta !== sampleDelta) {
      throw new FoiaFootageError("NOT_CFR_30", "FOIA footage must be constant 30 fps");
    }
    sampleCount += count;
  }
  return { sampleCount, sampleDelta };
}

function fixed1616(data: Uint8Array, offset: number): number {
  const raw = u32(data, offset);
  if ((raw & 0xffff) !== 0) {
    throw new FoiaFootageError("ASPECT", "FOIA frame size must be a whole number of pixels");
  }
  return raw >>> 16;
}

function u32(bytes: Uint8Array, offset: number): number {
  if (offset < 0 || offset + 4 > bytes.length) throw new FoiaFootageError("MP4", "truncated box");
  return (
    (bytes[offset] ?? 0) * 16777216 +
    ((bytes[offset + 1] ?? 0) << 16) +
    ((bytes[offset + 2] ?? 0) << 8) +
    (bytes[offset + 3] ?? 0)
  );
}

function u64(bytes: Uint8Array, offset: number): number {
  const hi = u32(bytes, offset);
  const lo = u32(bytes, offset + 4);
  const value = hi * 2 ** 32 + lo;
  if (!Number.isSafeInteger(value)) throw new FoiaFootageError("MP4", "integer too large");
  return value;
}

function ascii(bytes: Uint8Array, offset: number, length: number): string {
  let out = "";
  for (let index = 0; index < length; index += 1) {
    out += String.fromCharCode(bytes[offset + index] ?? 0);
  }
  return out;
}

function boxStyle(rect: Rect): Record<string, number> {
  return { left: rect.x, top: rect.y, width: rect.width, height: rect.height };
}

function node(
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, string | number>>,
  children: readonly FoiaChild[] = [],
  stickFigure?: unknown,
): FoiaNode {
  const props: FoiaNode["props"] = children.length > 0 ? { style, children } : { style };
  if (stickFigure !== undefined) return { type: "div", dataset, props, stickFigure };
  return { type: "div", dataset, props };
}

function contains(rect: Rect, x: number, y: number): boolean {
  return x >= rect.x && y >= rect.y && x < rect.x + rect.width && y < rect.y + rect.height;
}
