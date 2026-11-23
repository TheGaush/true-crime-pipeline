import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import {
  ARCHIVAL_BADGE,
  AudioEvidenceCard,
  AudioEvidenceError,
  DRAMATIZATION_BADGE,
  FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  L_CUT_MAX_MS,
  L_CUT_MIN_MS,
  MOTIF_COMPONENT,
  SAFE_PADDING_BOTTOM_PX,
  SAFE_PADDING_TOP_PX,
  VISUAL_ENGINE,
  evidenceBadge,
  fftMagnitudes,
  logScaledSpectrum,
  resolveLCutLeadIn,
  type AudioEvidenceCardNode,
  type AudioEvidenceCardProps,
  type CardChild,
  type CardElement,
} from "../../src/motifs/AudioEvidenceCard.tsx";

const SOURCE = readFileSync(new URL("../../src/motifs/AudioEvidenceCard.tsx", import.meta.url), "utf8");

const PACK = JSON.parse(
  readFileSync(
    new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url),
    "utf8",
  ),
) as {
  scene_plans: Array<{
    scene_id: string;
    motif_component: string;
    visual_engine: string;
    timing_start_ms: number;
    acceptance_criteria_json: string[];
    visual_concept: string;
  }>;
  scenes: Array<{
    scene_id: string;
    motif_component: string;
    visual_engine: string;
    start_ms: number;
  }>;
};

/** 1 kHz tone at 8 kHz telephony rate. 32 cycles in 256 samples, so bin 32 is the peak. */
function telephonySine(): number[] {
  const samples: number[] = [];
  for (let index = 0; index < 256; index += 1) {
    samples.push(Math.sin((2 * Math.PI * 1000 * index) / 8000));
  }
  return samples;
}

function card(patch: Partial<AudioEvidenceCardProps> = {}): AudioEvidenceCardNode {
  if (patch.fftMagnitudes !== undefined) {
    return AudioEvidenceCard({
      showDramatizationBadge: true,
      sceneStartMs: 48_000,
      lCutMs: 800,
      frame: 24,
      ...patch,
    });
  }
  return AudioEvidenceCard({
    showDramatizationBadge: true,
    sceneStartMs: 48_000,
    lCutMs: 800,
    frame: 24,
    pcmSamples: telephonySine(),
    ...patch,
  });
}

function walk(node: CardChild, into: CardElement[] = []): CardElement[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walk(child, into);
  return into;
}

function texts(node: CardChild, into: string[] = []): string[] {
  if (typeof node === "string") {
    into.push(node);
    return into;
  }
  const children = node.props.children;
  if (typeof children === "string") into.push(children);
  else if (Array.isArray(children)) {
    for (const child of children) texts(child, into);
  }
  return into;
}

function slot(root: CardElement, name: string): CardElement {
  const found = walk(root).find((node) => node.props["data-slot"] === name);
  if (!found) throw new Error(`missing slot ${name}`);
  return found;
}

function box(node: CardElement): { left: number; top: number; width: number; height: number } {
  const style = node.props.style;
  return {
    left: style.left as number,
    top: style.top as number,
    width: style.width as number,
    height: style.height as number,
  };
}

function overlaps(
  a: { left: number; top: number; width: number; height: number },
  b: { left: number; top: number; width: number; height: number },
): boolean {
  return a.left < b.left + b.width && a.left + a.width > b.left && a.top < b.top + b.height && a.top + a.height > b.top;
}

test("provider keys stay unset under the offline setup", () => {
  expect(process.env.GEMINI_API_KEY).toBeUndefined();
  expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
  expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
});

test("badges toggle between archival FOIA audio and a TTS transcript dramatization", () => {
  expect(evidenceBadge(true)).toBe(DRAMATIZATION_BADGE);
  expect(evidenceBadge(false)).toBe(ARCHIVAL_BADGE);
  expect(DRAMATIZATION_BADGE).toBe("TRANSCRIPT DRAMATIZATION · TTS READING");
  expect(ARCHIVAL_BADGE).toBe("ARCHIVAL 911 AUDIO (FOIA)");
  expect(DRAMATIZATION_BADGE.startsWith("TRANSCRIPT DRAMATIZATION")).toBe(true);
  expect(DRAMATIZATION_BADGE.includes("ARCHIVAL")).toBe(false);
  expect(DRAMATIZATION_BADGE.includes("FOIA")).toBe(false);
  expect(ARCHIVAL_BADGE.includes("TRANSCRIPT DRAMATIZATION")).toBe(false);
  expect(ARCHIVAL_BADGE.includes("TTS")).toBe(false);

  const dramatized = card({ showDramatizationBadge: true, frame: 0 });
  const archival = card({ showDramatizationBadge: false, frame: 0 });

  expect(dramatized.badge).toBe("TRANSCRIPT DRAMATIZATION · TTS READING");
  expect(dramatized.badgeKind).toBe("dramatization");
  expect(dramatized.props["data-badge"]).toBe(DRAMATIZATION_BADGE);
  expect(dramatized.props["data-show-dramatization-badge"]).toBe("true");
  expect(texts(dramatized)).toContain(DRAMATIZATION_BADGE);
  expect(texts(dramatized).join("\n")).not.toContain("ARCHIVAL");
  expect(texts(dramatized).join("\n")).not.toContain("FOIA");

  expect(archival.badge).toBe("ARCHIVAL 911 AUDIO (FOIA)");
  expect(archival.badgeKind).toBe("archival");
  expect(archival.props["data-show-dramatization-badge"]).toBe("false");
  expect(texts(archival)).toContain(ARCHIVAL_BADGE);
  expect(texts(archival).join("\n")).not.toContain("TRANSCRIPT");
  expect(texts(archival).join("\n")).not.toContain("TTS");
  expect(texts(archival).join("\n")).not.toContain("DRAMATIZATION");

  expect(dramatized.spectrum).toEqual(archival.spectrum);
  expect(dramatized.linearMagnitudes).toEqual(archival.linearMagnitudes);
  expect(slot(dramatized, "badge").props["data-prominent"]).toBe("true");
  expect(slot(archival, "badge").props["data-prominent"]).toBe("true");
  expect(slot(dramatized, "badge").props.style.fontWeight).toBe(700);
  expect(slot(archival, "badge").props.style.fontWeight).toBe(700);
  expect(slot(dramatized, "badge").props.style.fontSize).toBe(40);
  expect(slot(archival, "badge").props.style.fontSize).toBe(40);
  expect(slot(dramatized, "badge").props.style.backgroundColor).not.toBe(
    slot(archival, "badge").props.style.backgroundColor,
  );

  expect(() => evidenceBadge("yes" as unknown as boolean)).toThrow(AudioEvidenceError);
  expect(() => card({ showDramatizationBadge: "true" as unknown as boolean })).toThrow(
    /showDramatizationBadge must be true or false/,
  );
});

test("Law 6 holds the meter for a 0.6–1.0s visual lead, then draws the log spectrum", () => {
  expect(FPS).toBe(30);
  expect(L_CUT_MIN_MS).toBe(600);
  expect(L_CUT_MAX_MS).toBe(1000);
  expect(resolveLCutLeadIn(600)).toEqual({ requestedMs: 600, leadFrames: 18, fps: 30 });
  expect(resolveLCutLeadIn(800)).toEqual({ requestedMs: 800, leadFrames: 24, fps: 30 });
  expect(resolveLCutLeadIn(1000)).toEqual({ requestedMs: 1000, leadFrames: 30, fps: 30 });
  expect(resolveLCutLeadIn(700).leadFrames).toBe(21);

  const held = card({ lCutMs: 800, frame: 23, sceneStartMs: 0 });
  const live = card({ lCutMs: 800, frame: 24, sceneStartMs: 0 });
  expect(held.phase).toBe("visual-lead");
  expect(held.props["data-phase"]).toBe("visual-lead");
  expect(slot(held, "waveform").props["data-waveform"]).toBe("held");
  expect(live.phase).toBe("live");
  expect(slot(live, "waveform").props["data-waveform"]).toBe("live");
  expect(held.lCut.leadFrames).toBe(24);
  expect(live.audioOnMs).toBe(800);
  expect(texts(held)).toContain("LAW 6 L-CUT 800 ms");
  expect(texts(live)).toContain("LAW 6 L-CUT 800 ms");
  expect(held.spectrum).toEqual(live.spectrum);
  expect(held.spectrum.some((level) => level > 0)).toBe(true);

  const heldBars = walk(slot(held, "waveform")).filter((node) => node.props["data-bin"] !== undefined);
  const liveBars = walk(slot(live, "waveform")).filter((node) => node.props["data-bin"] !== undefined);
  expect(heldBars.length).toBe(held.spectrum.length);
  heldBars.forEach((bar) => expect(bar.props["data-level"]).toBe("0.00000000"));
  liveBars.forEach((bar, index) => {
    expect(Number(bar.props["data-level"])).toBeCloseTo(live.spectrum[index] ?? -1, 6);
  });

  const early = card({ sceneStartMs: 0, lCutMs: 800, frame: 0 });
  const mid = card({ sceneStartMs: 48_000, lCutMs: 800, frame: 0 });
  expect(early.lCut).toEqual(mid.lCut);
  expect(early.phase).toBe("visual-lead");
  expect(mid.audioOnMs).toBe(48_800);
  expect(mid.props["data-audio-on-ms"]).toBe("48800");

  for (const illegal of [599, 1001, 0, -800, 800.4]) {
    expect(() => resolveLCutLeadIn(illegal)).toThrow(AudioEvidenceError);
    expect(() => card({ lCutMs: illegal })).toThrow(/600 to 1000/);
  }
});

test("log-scaled FFT fixture peaks on the telephony bin and is not a linear meter", () => {
  const impulse = fftMagnitudes([1, ...new Array<number>(15).fill(0)]);
  expect(impulse).toHaveLength(9);
  for (const magnitude of impulse) expect(magnitude).toBeCloseTo(1, 8);

  const dc = fftMagnitudes(new Array<number>(16).fill(1));
  expect(dc[0]).toBeCloseTo(16, 8);
  for (const magnitude of dc.slice(1)) expect(magnitude).toBeCloseTo(0, 8);

  const sine = fftMagnitudes(telephonySine());
  expect(sine).toHaveLength(129);
  let peakAt = 0;
  sine.forEach((magnitude, index) => {
    if (magnitude > (sine[peakAt] ?? -1)) peakAt = index;
  });
  expect(peakAt).toBe(32);
  expect(sine[32]).toBeCloseTo(128, 4);
  expect(sine[31] ?? 0).toBeLessThan(1);
  expect(sine[33] ?? 0).toBeLessThan(1);
  expect(fftMagnitudes(telephonySine())).toEqual(sine);

  const shaped = logScaledSpectrum([0, 0.01, 0.1, 1]);
  expect(shaped[0]).toBe(0);
  expect(shaped[1]).toBeCloseTo(0.5, 5);
  expect(shaped[2]).toBeCloseTo(0.75, 5);
  expect(shaped[3]).toBeCloseTo(1, 5);
  expect(shaped[1] ?? 0).toBeGreaterThan(0.2);

  const scaledPeak = logScaledSpectrum([0, 2, 0.2]);
  expect(scaledPeak[1]).toBeCloseTo(1, 5);
  expect(scaledPeak[2]).toBeCloseTo(0.75, 5);
  expect(logScaledSpectrum([0, 0, 0])).toEqual([0, 0, 0]);

  const rendered = card({ fftMagnitudes: [0, 0.01, 0.1, 1], frame: 24 });
  expect(rendered.spectrum[1]).toBeCloseTo(0.5, 5);
  expect(rendered.spectrum[2]).toBeCloseTo(0.75, 5);
  const bars = walk(slot(rendered, "waveform")).filter((node) => node.props["data-bin"] !== undefined);
  expect(bars).toHaveLength(4);
  expect(Number(bars[3]?.props["data-level"])).toBeCloseTo(1, 5);
  expect(bars[3]?.props.style.backgroundColor).toBe("#D7B56D");

  const fromPcm = card({ frame: 24 });
  expect(fromPcm.linearMagnitudes[32]).toBeCloseTo(128, 4);
  expect(fromPcm.spectrum[32]).toBeCloseTo(1, 5);

  expect(() => logScaledSpectrum([])).toThrow(/spectrum/);
  expect(() => logScaledSpectrum([-0.1])).toThrow(/magnitude/);
  expect(() => logScaledSpectrum([Number.NaN])).toThrow(/magnitude/);
  expect(() => fftMagnitudes([1, 2, 3])).toThrow(/power of two/);
  expect(() => fftMagnitudes(new Array<number>(2048).fill(0))).toThrow(/power of two/);
  expect(() => fftMagnitudes([Number.NaN, ...new Array<number>(15).fill(0)])).toThrow(/finite/);
  expect(() => card({ pcmSamples: telephonySine(), fftMagnitudes: [1, 0, 0, 1] })).toThrow(/pcmSamples or fftMagnitudes/);
  expect(() =>
    AudioEvidenceCard({
      showDramatizationBadge: false,
      sceneStartMs: 0,
      lCutMs: 600,
      frame: 18,
    }),
  ).toThrow(/pcmSamples or fftMagnitudes/);
});

test("the booth stays inside the caption safe zone and paints no grain or crimson", () => {
  expect(FRAME_WIDTH).toBe(1920);
  expect(FRAME_HEIGHT).toBe(1080);
  expect(SAFE_PADDING_TOP_PX).toBe(108);
  expect(SAFE_PADDING_BOTTOM_PX).toBe(194);
  expect(MOTIF_COMPONENT).toBe("AudioEvidenceCard");
  expect(VISUAL_ENGINE).toBe("AUDIO_EVIDENCE_CARD");

  const rendered = card({ frame: 24 });
  expect(rendered.$$typeof).toBe(Symbol.for("react.element"));
  expect(rendered.type).toBe("div");
  expect(rendered.props["data-motif"]).toBe("AudioEvidenceCard");
  expect(rendered.props["data-visual-engine"]).toBe("AUDIO_EVIDENCE_CARD");
  expect(rendered.props["data-room"]).toBe("noir-911-booth");
  expect(rendered.props["data-paper-grain"]).toBe("0");
  expect(rendered.props["data-vignette"]).toBe("0");
  expect(rendered.props["data-fps"]).toBe("30");
  expect(rendered.props.style.width).toBe(1920);
  expect(rendered.props.style.height).toBe(1080);
  expect(rendered.props.style.overflow).toBe("hidden");
  expect(rendered.props.style.filter).toBe("none");
  expect(rendered.props.style.backgroundImage).toBe("none");

  const safe = slot(rendered, "safe");
  expect(safe.props.style).toMatchObject({
    left: 0,
    top: 108,
    width: 1920,
    height: 778,
    overflow: "hidden",
  });

  const windowPane = walk(rendered).find((node) => node.props["data-layer"] === "window");
  if (!windowPane) throw new Error("missing noir window");
  const windowBox = box(windowPane);
  expect(windowBox.top).toBeGreaterThanOrEqual(0);
  expect(windowBox.left).toBeGreaterThanOrEqual(0);
  expect(windowBox.top + windowBox.height).toBeLessThanOrEqual(778);
  expect(windowBox.left + windowBox.width).toBeLessThanOrEqual(1920);

  for (const name of ["badge", "banner", "waveform", "desk"]) {
    const node = slot(rendered, name);
    const rect = box(node);
    expect(rect.top).toBeGreaterThanOrEqual(0);
    expect(rect.left).toBeGreaterThanOrEqual(0);
    expect(rect.top + rect.height).toBeLessThanOrEqual(778);
    expect(rect.left + rect.width).toBeLessThanOrEqual(1920);
    expect(node.props.style.filter).toBe("none");
  }

  const safeRect = { left: 0, top: 108, width: 1920, height: 778 };
  const caption = { left: 0, top: 886, width: 1920, height: 194 };
  const exclusion = { left: 1920 * 0.78, top: 1080 * 0.86, width: 1920 * 0.22, height: 1080 * 0.14 };
  expect(overlaps(safeRect, caption)).toBe(false);
  expect(overlaps(safeRect, exclusion)).toBe(false);
  expect(box(slot(rendered, "waveform")).top + box(slot(rendered, "waveform")).height).toBe(778);

  const again = card({ frame: 24 });
  expect(again.props).toEqual(rendered.props);
  expect(again.spectrum).toEqual(rendered.spectrum);

  expect(SOURCE.includes("#C92A2A")).toBe(false);
  expect(SOURCE.includes("feTurbulence")).toBe(false);
  expect(SOURCE.includes("feDisplacementMap")).toBe(false);
  expect(SOURCE.includes("Math.random")).toBe(false);
  expect(JSON.stringify(rendered.props).includes("#C92A2A")).toBe(false);
  expect(JSON.stringify(rendered.props).includes("feTurbulence")).toBe(false);

  expect(() => card({ sceneStartMs: -1 })).toThrow(/sceneStartMs/);
  expect(() => card({ sceneStartMs: 1.5 })).toThrow(/sceneStartMs/);
  expect(() => card({ frame: -1 })).toThrow(/frame/);
  expect(() => card({ frame: 1.2 })).toThrow(/frame/);
});

test("golden audio-evidence scenes carry the dramatization badge on their timeline", () => {
  const plans = PACK.scene_plans.filter((plan) => plan.motif_component === "AudioEvidenceCard");
  expect(plans).toHaveLength(3);
  for (const plan of plans) {
    const scene = PACK.scenes.find((item) => item.scene_id === plan.scene_id);
    expect(scene?.motif_component).toBe("AudioEvidenceCard");
    expect(scene?.visual_engine).toBe("AUDIO_EVIDENCE_CARD");
    expect(scene?.start_ms).toBe(plan.timing_start_ms);
    expect(plan.visual_engine).toBe("AUDIO_EVIDENCE_CARD");
    expect(plan.acceptance_criteria_json.join(" ")).toContain("TRANSCRIPT DRAMATIZATION");
    expect(plan.visual_concept).toContain("TRANSCRIPT DRAMATIZATION");
    const rendered = card({
      showDramatizationBadge: true,
      sceneStartMs: plan.timing_start_ms,
      lCutMs: 800,
      frame: 24,
    });
    expect(rendered.badge).toBe("TRANSCRIPT DRAMATIZATION · TTS READING");
    expect(rendered.props["data-scene-start-ms"]).toBe(String(plan.timing_start_ms));
    expect(rendered.audioOnMs).toBe(plan.timing_start_ms + 800);
    expect(texts(rendered).join("\n")).not.toContain(ARCHIVAL_BADGE);
  }
});
