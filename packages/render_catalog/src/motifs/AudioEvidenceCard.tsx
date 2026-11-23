/**
 * MVP motif #3 — AudioEvidenceCard.
 *
 * A 1920×1080 @ 30 fps noir 911 booth: log-scaled FFT bars, a Law 6
 * 0.6–1.0s visual lead-in, and one unambiguous audio badge.
 * Archival FOIA playback and a TTS transcript reading never share a label.
 *
 * Remotion paints this plate flat. No paper grain, vignette, or SVG turbulence.
 * Safe-zone insets match the catalog (top 108px, bottom 194px). Task 101's
 * SafeZoneLayout and Task 111's SafeCallout are not copied onto this branch.
 */

export const MOTIF_COMPONENT = "AudioEvidenceCard";
export const VISUAL_ENGINE = "AUDIO_EVIDENCE_CARD";
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FPS = 30;
export const SAFE_PADDING_TOP_PX = 108;
export const SAFE_PADDING_BOTTOM_PX = 194;
export const L_CUT_MIN_MS = 600;
export const L_CUT_MAX_MS = 1000;
export const DRAMATIZATION_BADGE = "TRANSCRIPT DRAMATIZATION · TTS READING";
export const ARCHIVAL_BADGE = "ARCHIVAL 911 AUDIO (FOIA)";

/** Peak-normalized magnitudes at or below this floor sit on the bottom of the meter. */
export const LOG_FLOOR = 1e-4;

const SAFE_HEIGHT = FRAME_HEIGHT - SAFE_PADDING_TOP_PX - SAFE_PADDING_BOTTOM_PX;
const INSET_X = 72;
const CONTENT_WIDTH = FRAME_WIDTH - INSET_X * 2;
const BADGE_HEIGHT = 88;
const BANNER_HEIGHT = 52;
const STACK_GAP = 20;
const FFT_MIN = 16;
const FFT_MAX = 1024;
const BIN_MAX = FFT_MAX / 2 + 1;
const MAX_SCENE_START_MS = 7_200_000;
const MAX_FRAME = 216_000;

const PAINT = {
  wall: "#101418",
  window: "#1E2A33",
  desk: "#2C2822",
  ink: "#F4EFE6",
  wave: "#D7B56D",
  dramatization: "#3F2A12",
  archival: "#1C333C",
  banner: "#24303A",
} as const;

const REACT_ELEMENT = Symbol.for("react.element");

export class AudioEvidenceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AudioEvidenceError";
  }
}

export type CardStyle = Readonly<Record<string, string | number>>;

export type CardChild = CardElement | string;

export type CardElement = {
  readonly $$typeof: symbol;
  readonly type: "div";
  readonly key: string | null;
  readonly ref: null;
  readonly props: {
    readonly style: CardStyle;
    readonly children?: CardChild | readonly CardChild[];
  } & Readonly<Record<string, unknown>>;
};

export type LCutLead = {
  readonly requestedMs: number;
  readonly leadFrames: number;
  readonly fps: typeof FPS;
};

export type SpectrumPhase = "visual-lead" | "live";

export type AudioEvidenceCardProps = {
  readonly showDramatizationBadge: boolean;
  /** Global millisecond at which this card's picture starts. */
  readonly sceneStartMs: number;
  /** Law 6 visual lead before the 911 audio is heard. Integer milliseconds. */
  readonly lCutMs: number;
  /** Local frame on the 30 fps clock. The lead holds the meter until `leadFrames`. */
  readonly frame: number;
  readonly pcmSamples?: readonly number[];
  /** Linear FFT magnitudes. The card applies the log scale. */
  readonly fftMagnitudes?: readonly number[];
};

export type AudioEvidenceCardNode = CardElement & {
  readonly badge: string;
  readonly badgeKind: "dramatization" | "archival";
  readonly spectrum: readonly number[];
  readonly linearMagnitudes: readonly number[];
  readonly lCut: LCutLead;
  readonly phase: SpectrumPhase;
  readonly audioOnMs: number;
};

export function evidenceBadge(showDramatizationBadge: boolean): string {
  if (showDramatizationBadge === true) return DRAMATIZATION_BADGE;
  if (showDramatizationBadge === false) return ARCHIVAL_BADGE;
  throw new AudioEvidenceError("showDramatizationBadge must be true or false");
}

/**
 * Picture leads the 911 audio by 0.6–1.0s inside this card.
 * Local frame 0 is already on screen; the meter stays held until the lead ends.
 * A card that starts at timeline 0 still keeps that full lead, because the
 * audio simply begins later — it is not pulled before timestamp 0.
 */
export function resolveLCutLeadIn(lCutMs: number): LCutLead {
  if (!Number.isInteger(lCutMs) || lCutMs < L_CUT_MIN_MS || lCutMs > L_CUT_MAX_MS) {
    throw new AudioEvidenceError(
      `Law 6 L-cut must be an integer from ${L_CUT_MIN_MS} to ${L_CUT_MAX_MS} ms`,
    );
  }
  return {
    requestedMs: lCutMs,
    leadFrames: Math.round((lCutMs * FPS) / 1000),
    fps: FPS,
  };
}

export function lCutBanner(lead: LCutLead): string {
  return `LAW 6 L-CUT ${lead.requestedMs} ms`;
}

/**
 * Log-scaled meter levels in 0..1.
 * Peak-normalized m uses `(20*log10(max(m, 1e-4)) + 80) / 80`.
 * m=1 → 1, m=0.1 → 0.75, m=0.01 → 0.5, m<=1e-4 → 0.
 */
export function logScaledSpectrum(linearMagnitudes: readonly number[]): readonly number[] {
  if (linearMagnitudes.length < 1 || linearMagnitudes.length > BIN_MAX) {
    throw new AudioEvidenceError(`spectrum must contain 1 to ${BIN_MAX} bins`);
  }
  let peak = 0;
  for (const value of linearMagnitudes) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
      throw new AudioEvidenceError("FFT magnitude must be a finite number >= 0");
    }
    if (value > peak) peak = value;
  }
  const levels = linearMagnitudes.map((value) => {
    if (peak === 0) return 0;
    const normalized = value / peak;
    if (!(normalized > LOG_FLOOR)) return 0;
    if (normalized >= 1) return 1;
    const db = 20 * Math.log10(normalized);
    return (db - 20 * Math.log10(LOG_FLOOR)) / (0 - 20 * Math.log10(LOG_FLOOR));
  });
  return Object.freeze(levels);
}

/** One-sided linear magnitudes, including DC and Nyquist. Rectangular window. */
export function fftMagnitudes(samples: readonly number[]): number[] {
  const n = samples.length;
  if (!Number.isInteger(n) || n < FFT_MIN || n > FFT_MAX || (n & (n - 1)) !== 0) {
    throw new AudioEvidenceError(`pcmSamples length must be a power of two from ${FFT_MIN} to ${FFT_MAX}`);
  }
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  for (let index = 0; index < n; index += 1) {
    const sample = samples[index];
    if (typeof sample !== "number" || !Number.isFinite(sample)) {
      throw new AudioEvidenceError("pcmSamples must be finite numbers");
    }
    re[index] = sample;
  }
  transform(re, im);
  const bins = n / 2 + 1;
  const magnitudes = new Array<number>(bins);
  for (let bin = 0; bin < bins; bin += 1) {
    magnitudes[bin] = Math.hypot(re[bin] ?? 0, im[bin] ?? 0);
  }
  return magnitudes;
}

export function AudioEvidenceCard(props: AudioEvidenceCardProps): AudioEvidenceCardNode {
  const badge = evidenceBadge(props.showDramatizationBadge);
  const badgeKind = props.showDramatizationBadge ? "dramatization" : "archival";
  const lCut = resolveLCutLeadIn(props.lCutMs);
  const sceneStartMs = requireSceneStart(props.sceneStartMs);
  const frame = requireFrame(props.frame);
  const linearMagnitudes = Object.freeze(resolveLinear(props));
  const spectrum = logScaledSpectrum(linearMagnitudes);
  const phase: SpectrumPhase = frame < lCut.leadFrames ? "visual-lead" : "live";
  const audioOnMs = sceneStartMs + lCut.requestedMs;
  const drawn = phase === "live" ? spectrum : spectrum.map(() => 0);

  const wall = element("wall", { layer: "noir-room", "safe-zone-exempt": "background" }, {
    position: "absolute",
    left: 0,
    top: 0,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT,
    backgroundColor: PAINT.wall,
    backgroundImage: "none",
    filter: "none",
  });

  const windowPane = element("window", { layer: "window" }, {
    position: "absolute",
    left: 1500,
    top: 36,
    width: 280,
    height: 160,
    backgroundColor: PAINT.window,
    backgroundImage: "none",
    filter: "none",
  });

  const desk = element("desk", { slot: "desk", layer: "desk" }, {
    position: "absolute",
    left: 0,
    top: SAFE_HEIGHT - 120,
    width: FRAME_WIDTH,
    height: 120,
    backgroundColor: PAINT.desk,
    backgroundImage: "none",
    filter: "none",
  });

  const badgeBox = element(
    "badge",
    { slot: "badge", "badge-kind": badgeKind, prominent: "true" },
    {
      position: "absolute",
      left: INSET_X,
      top: 0,
      width: CONTENT_WIDTH,
      height: BADGE_HEIGHT,
      boxSizing: "border-box",
      overflow: "hidden",
      display: "flex",
      alignItems: "center",
      paddingLeft: 28,
      backgroundColor: badgeKind === "dramatization" ? PAINT.dramatization : PAINT.archival,
      color: PAINT.ink,
      fontSize: 40,
      fontWeight: 700,
      letterSpacing: "0.04em",
      lineHeight: 1.15,
      whiteSpace: "nowrap",
      backgroundImage: "none",
      filter: "none",
    },
    [badge],
  );

  const banner = element(
    "banner",
    { slot: "banner", "l-cut-ms": String(lCut.requestedMs) },
    {
      position: "absolute",
      left: INSET_X,
      top: BADGE_HEIGHT + STACK_GAP,
      width: CONTENT_WIDTH,
      height: BANNER_HEIGHT,
      boxSizing: "border-box",
      overflow: "hidden",
      display: "flex",
      alignItems: "center",
      paddingLeft: 28,
      backgroundColor: PAINT.banner,
      color: PAINT.ink,
      fontSize: 28,
      fontWeight: 700,
      lineHeight: 1.15,
      whiteSpace: "nowrap",
      backgroundImage: "none",
      filter: "none",
    },
    [lCutBanner(lCut)],
  );

  const waveTop = BADGE_HEIGHT + STACK_GAP + BANNER_HEIGHT + STACK_GAP;
  const bars = drawn.map((level, index) =>
    element(
      `bin-${index}`,
      { bin: String(index), level: level.toFixed(8) },
      {
        height: `${level * 100}%`,
        width: `${100 / drawn.length}%`,
        backgroundColor: PAINT.wave,
        backgroundImage: "none",
        filter: "none",
      },
    ),
  );

  const waveform = element(
    "waveform",
    { slot: "waveform", waveform: phase === "live" ? "live" : "held" },
    {
      position: "absolute",
      left: INSET_X,
      top: waveTop,
      width: CONTENT_WIDTH,
      height: SAFE_HEIGHT - waveTop,
      display: "flex",
      alignItems: "flex-end",
      overflow: "hidden",
      backgroundColor: PAINT.wall,
      backgroundImage: "none",
      filter: "none",
    },
    bars,
  );

  const safe = element(
    "safe",
    { slot: "safe" },
    {
      position: "absolute",
      left: 0,
      top: SAFE_PADDING_TOP_PX,
      width: FRAME_WIDTH,
      height: SAFE_HEIGHT,
      overflow: "hidden",
      backgroundImage: "none",
      filter: "none",
    },
    [windowPane, desk, badgeBox, banner, waveform],
  );

  const root = element(
    "audio-evidence-card",
    {
      motif: MOTIF_COMPONENT,
      "visual-engine": VISUAL_ENGINE,
      badge,
      "badge-kind": badgeKind,
      "show-dramatization-badge": props.showDramatizationBadge ? "true" : "false",
      "l-cut-ms": String(lCut.requestedMs),
      "lead-frames": String(lCut.leadFrames),
      phase,
      "scene-start-ms": String(sceneStartMs),
      "audio-on-ms": String(audioOnMs),
      fps: String(FPS),
      "paper-grain": "0",
      vignette: "0",
      room: "noir-911-booth",
    },
    {
      position: "relative",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      overflow: "hidden",
      backgroundColor: PAINT.wall,
      backgroundImage: "none",
      filter: "none",
      boxSizing: "border-box",
    },
    [wall, safe],
  );

  return {
    ...root,
    badge,
    badgeKind,
    spectrum,
    linearMagnitudes,
    lCut,
    phase,
    audioOnMs,
  };
}

function requireSceneStart(sceneStartMs: number): number {
  if (!Number.isInteger(sceneStartMs) || sceneStartMs < 0 || sceneStartMs > MAX_SCENE_START_MS) {
    throw new AudioEvidenceError("sceneStartMs must be an integer from 0 to 7200000");
  }
  return sceneStartMs;
}

function requireFrame(frame: number): number {
  if (!Number.isInteger(frame) || frame < 0 || frame > MAX_FRAME) {
    throw new AudioEvidenceError("frame must be an integer from 0 to 216000");
  }
  return frame;
}

function resolveLinear(props: AudioEvidenceCardProps): number[] {
  const pcm = props.pcmSamples;
  const bins = props.fftMagnitudes;
  const hasPcm = pcm !== undefined;
  const hasBins = bins !== undefined;
  if (hasPcm === hasBins) {
    throw new AudioEvidenceError("pass pcmSamples or fftMagnitudes");
  }
  if (pcm) return fftMagnitudes(pcm);
  return Array.from(bins ?? []);
}

function element(
  key: string,
  dataset: Readonly<Record<string, string>>,
  style: CardStyle,
  children?: readonly CardChild[],
): CardElement {
  const props: Record<string, unknown> = { style };
  for (const [name, value] of Object.entries(dataset)) {
    props[`data-${name}`] = value;
  }
  if (children && children.length === 1) {
    const only = children[0];
    if (only !== undefined) props.children = only;
  } else if (children && children.length > 1) {
    props.children = children;
  }
  return {
    $$typeof: REACT_ELEMENT,
    type: "div",
    key,
    ref: null,
    props: props as CardElement["props"],
  };
}

function transform(re: Float64Array, im: Float64Array): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i += 1) {
    let bit = n >> 1;
    for (; (j & bit) !== 0; bit >>= 1) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      const swapRe = re[i] ?? 0;
      re[i] = re[j] ?? 0;
      re[j] = swapRe;
      const swapIm = im[i] ?? 0;
      im[i] = im[j] ?? 0;
      im[j] = swapIm;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const half = len >> 1;
    const theta = (-2 * Math.PI) / len;
    const wRe = Math.cos(theta);
    const wIm = Math.sin(theta);
    for (let start = 0; start < n; start += len) {
      let curRe = 1;
      let curIm = 0;
      for (let k = 0; k < half; k += 1) {
        const even = start + k;
        const odd = even + half;
        const oddRe = (re[odd] ?? 0) * curRe - (im[odd] ?? 0) * curIm;
        const oddIm = (re[odd] ?? 0) * curIm + (im[odd] ?? 0) * curRe;
        const evenRe = re[even] ?? 0;
        const evenIm = im[even] ?? 0;
        re[even] = evenRe + oddRe;
        im[even] = evenIm + oddIm;
        re[odd] = evenRe - oddRe;
        im[odd] = evenIm - oddIm;
        const nextRe = curRe * wRe - curIm * wIm;
        curIm = curRe * wIm + curIm * wRe;
        curRe = nextRe;
      }
    }
  }
}
