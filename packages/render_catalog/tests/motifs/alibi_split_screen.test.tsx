import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import { CATALOG_MOTIFS, MOTIF_REGISTRY_V1 } from "../../../shared-contracts-ts/src/models.ts";
import {
  ALIBI_MOTIF_NUMBER,
  ALIBI_SPLIT_SCREEN_ID,
  ALIBI_SPLIT_SCREEN_OWNER,
  CHAR_PX,
  CLAIM_HEADER,
  CONFLICT_LABEL,
  CONFLICT_STAMP_CUE,
  CONFLICT_STAMP_DBTP,
  CONFLICT_STAMP_DURATION_SAMPLES,
  CONFLICT_STAMP_GAIN_UNITS,
  COOLDOWN_MS,
  EVIDENCE_CRIMSON,
  EVIDENCE_HEADER,
  FRAME_FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  GAIN_UNIT_SCALE,
  INK,
  MAX_SHAKE_PX,
  MAX_WORDS,
  MIX_SAMPLE_RATE_HZ,
  PAPER_BG,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  SAMPLES_PER_FRAME,
  SAMPLES_PER_MS,
  STAMP_HOLD_FRAMES,
  TRUE_PEAK_CEILING_UNITS,
  AlibiSplitScreen,
  AlibiSplitScreenError,
  frameForOffsetMs,
  layoutAlibiSplitScreen,
  linearGainUnits,
  microShake,
  mixSampleForOffsetMs,
  rectInside,
  rectsOverlap,
  translateRect,
  walkSplit,
  type AlibiSplitScreenProps,
  type SplitNode,
} from "../../src/motifs/AlibiSplitScreen.tsx";

const PACKS = ["ep_golden_01_20min", "ep_golden_02_2strike_fallback", "ep_golden_03_2k_grid_heavy"] as const;

const CLAIM_SUMMARY = "A news report said neighbors noticed the porch light.";
const EVIDENCE_SUMMARY = "The affidavit describes a porch light at the front steps.";
const CLAIM_CITATION = "Fixture Daily, 4 Apr 2019";
const EVIDENCE_CITATION = "Affidavit p. 4";
const STAMP_AT_MS = 2746;

type Fact = {
  fact_id: string;
  event_summary: string;
  source_type: string;
  citation_locator: string;
  hedging_required: number;
};

type Pack = {
  episode: { episode_id: string; turning_point_count: number };
  temporal_fact_ledger: Fact[];
  scene_plans: {
    scene_id: string;
    timing_start_ms: number;
    timing_end_ms: number;
    approved_narration_text: string;
    cited_fact_ids_json: string[];
  }[];
  voice_track_manifest: {
    segments: {
      seq_index: number;
      start_ms: number;
      end_ms: number;
      word_timestamps: { word: string; start_ms: number; end_ms: number }[];
    }[];
  };
};

function loadPack(name: string): Pack {
  return JSON.parse(
    readFileSync(new URL(`../../../../fixtures/golden_manifests/${name}/pack.json`, import.meta.url), "utf8"),
  ) as Pack;
}

function goldenProps(pack: Pack, frame: number, extra: Partial<AlibiSplitScreenProps> = {}): AlibiSplitScreenProps {
  const hit = pack.voice_track_manifest.segments.flatMap((segment) =>
    segment.word_timestamps.filter((word) => word.word === "claim").map((word) => ({ segment, word })),
  );
  if (hit.length !== 1) throw new Error(`${pack.episode.episode_id} should say claim once`);
  const spoken = hit[0];
  if (!spoken) throw new Error("missing claim word");
  const scene = pack.scene_plans.find(
    (item) => item.timing_start_ms <= spoken.word.start_ms && spoken.word.start_ms < item.timing_end_ms,
  );
  if (!scene) throw new Error("claim word is outside every scene");
  const claim = pack.temporal_fact_ledger.find((fact) => fact.fact_id === scene.cited_fact_ids_json[0]);
  const evidence = pack.temporal_fact_ledger.find(
    (fact) => fact.source_type === "police_affidavit" && fact.event_summary.includes("porch light"),
  );
  if (!claim || !evidence) throw new Error("missing golden panes");
  if (claim.source_type !== "news_report" || evidence.source_type !== "police_affidavit") {
    throw new Error("golden panes are not a hedged claim against a primary affidavit");
  }
  return {
    sceneId: scene.scene_id,
    frame,
    stampAtMs: spoken.word.start_ms - scene.timing_start_ms,
    claim: {
      fact_id: claim.fact_id,
      source_type: "news_report",
      text: claim.event_summary,
      citation: claim.citation_locator,
    },
    evidence: {
      fact_id: evidence.fact_id,
      source_type: "police_affidavit",
      text: evidence.event_summary,
      citation: evidence.citation_locator,
    },
    ...extra,
  };
}

function node(root: SplitNode, key: string, value: string): SplitNode {
  const found = walkSplit(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function bodyText(root: SplitNode, slot: string): string {
  const body = node(root, "slot", slot);
  if (typeof body.props.children !== "string") throw new Error(`${slot} has no text`);
  return body.props.children.replaceAll("\n", " ");
}

test("AlibiSplitScreen is motif 11 and does not amend the frozen registry", () => {
  expect(ALIBI_MOTIF_NUMBER).toBe(11);
  expect(ALIBI_SPLIT_SCREEN_ID).toBe("AlibiSplitScreen");
  expect(ALIBI_SPLIT_SCREEN_OWNER).toBe("render_catalog");
  expect(CATALOG_MOTIFS[10]).toBe("EvidenceGridMatrix");
  expect(CATALOG_MOTIFS[7]).toBe("SplitScreenComparison");
  expect(CATALOG_MOTIFS).not.toContain(ALIBI_SPLIT_SCREEN_ID);
  expect(MOTIF_REGISTRY_V1.map((entry) => entry.motif_component)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
  ]);

  const source = readFileSync(new URL("../../src/motifs/AlibiSplitScreen.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/function SafeZoneLayout/);
  expect(source).not.toMatch(/feTurbulence|feDisplacementMap/);
  expect(source).not.toMatch(/from ["'][^"']*sfx\/SfxRegistry/);
  expect(source).not.toMatch(/from ["'][^"']*safe_zone/);
  expect(source).not.toMatch(/from ["'][^"']*SfxRegistry/);

  const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");
  expect(sql).toContain("('EvidenceGridMatrix',     'render_catalog', 0)");
  expect(sql).toContain("('SplitScreenComparison',  'render_catalog', 0)");
  expect(sql).not.toContain("AlibiSplitScreen");
});

test("golden turning points stamp CONFLICT on the spoken claim millisecond", () => {
  expect(STAMP_AT_MS * SAMPLES_PER_MS).toBe(131_808);
  expect(frameForOffsetMs(STAMP_AT_MS)).toBe(82);
  expect(mixSampleForOffsetMs(STAMP_AT_MS)).toBe(STAMP_AT_MS * 48);
  expect(Math.floor((82 * 1_000) / FRAME_FPS)).toBe(2_733);
  expect(STAMP_AT_MS).toBe(2_746);

  for (const name of PACKS) {
    const pack = loadPack(name);
    expect(pack.episode.turning_point_count).toBe(4);
    const props = goldenProps(pack, 82);
    expect(props.stampAtMs).toBe(STAMP_AT_MS);
    expect(props.claim.text).toBe(CLAIM_SUMMARY);
    expect(props.claim.citation).toBe(CLAIM_CITATION);
    expect(props.evidence.text).toBe(EVIDENCE_SUMMARY);
    expect(props.evidence.citation).toBe(EVIDENCE_CITATION);
    expect(props.claim.text.trim().split(/\s+/)).toHaveLength(9);
    expect(props.evidence.text.trim().split(/\s+/)).toHaveLength(10);
    expect(props.claim.text.length).toBeLessThanOrEqual(59);
    expect(props.evidence.text.length).toBeLessThanOrEqual(Math.floor((814 - 40) / CHAR_PX));

    const before = layoutAlibiSplitScreen({ ...props, frame: 81 });
    expect(before.stamp).toBeNull();
    expect(before.shake).toEqual({ x: 0, y: 0 });
    expect(before.cuesStarted).toEqual([]);
    expect(before.cues).toHaveLength(1);

    const landed = layoutAlibiSplitScreen(props);
    expect(landed.sync).toEqual({ offset_ms: STAMP_AT_MS, start_sample: 131_808, start_frame: 82 });
    expect(landed.stamp?.label).toBe(CONFLICT_LABEL);
    expect(landed.shake).toEqual({ x: MAX_SHAKE_PX, y: 0 });
    expect(landed.shake.x * landed.shake.x + landed.shake.y * landed.shake.y).toBeLessThanOrEqual(MAX_SHAKE_PX ** 2);
    expect(landed.cuesStarted.map((cue) => cue.offset_ms)).toEqual([STAMP_AT_MS]);
    expect(landed.claim.display).toBe(CLAIM_SUMMARY);
    expect(landed.evidence.display).toBe(EVIDENCE_SUMMARY);
    expect(landed.claim.truncated).toBe(false);
    expect(landed.evidence.truncated).toBe(false);
    expect(landed.claim.wordCount).toBeLessThanOrEqual(MAX_WORDS);
    expect(landed.claim.lines).toEqual([CLAIM_SUMMARY]);
    expect(landed.evidence.lines).toEqual([EVIDENCE_SUMMARY]);
    expect(rectInside(landed.claim.bodyPage, landed.content)).toBe(true);
    expect(rectInside(landed.evidence.bodyPage, landed.content)).toBe(true);
    expect(rectInside(landed.stamp?.page ?? landed.graphic, translateRect(landed.graphic, landed.shake.x, landed.shake.y))).toBe(
      true,
    );
    expect(rectsOverlap(translateRect(landed.graphic, landed.shake.x, landed.shake.y), landed.captionBar)).toBe(false);
    expect(rectsOverlap(translateRect(landed.graphic, landed.shake.x, landed.shake.y), landed.exclusion)).toBe(false);

    const cue = landed.cues[0];
    if (!cue) throw new Error("missing cue");
    expect(cue.cue).toBe(CONFLICT_STAMP_CUE);
    expect(cue.scene_id).toBe(props.sceneId);
    expect(cue.cue_id).toBe(`${props.sceneId}:${CONFLICT_STAMP_CUE}:131808`);
    expect(cue.offset_ms).toBe(STAMP_AT_MS);
    expect(cue.start_sample).toBe(cue.offset_ms * SAMPLES_PER_MS);
    expect(cue.start_frame).toBe(82);
    expect(cue.sample_rate_hz).toBe(MIX_SAMPLE_RATE_HZ);
    expect(cue.duration_samples).toBe(CONFLICT_STAMP_DURATION_SAMPLES);
    expect(cue.duration_samples).toBe(19_200);
    expect(cue.cooldown_ms).toBe(COOLDOWN_MS);
    expect(cue.peak_dbtp).toBe(CONFLICT_STAMP_DBTP);
    expect(cue.gain_units).toBe(CONFLICT_STAMP_GAIN_UNITS);
    expect(cue.gain_units).toBe(linearGainUnits(-6));
    expect(cue.gain_units).toBe(501_187_233);
    expect(cue.gain_units).toBeLessThan(TRUE_PEAK_CEILING_UNITS);
    expect(cue.gain_unit_scale).toBe(GAIN_UNIT_SCALE);
    expect(cue.burst).toBe(false);
    expect(cue.tapered).toBe(false);
    expect(cue.start_frame * SAMPLES_PER_FRAME).not.toBe(cue.start_sample);
    expect(SAMPLES_PER_FRAME).toBe(1_600);
    expect(FRAME_FPS).toBe(30);

    const settled = layoutAlibiSplitScreen({ ...props, frame: 82 + STAMP_HOLD_FRAMES });
    expect(settled.stamp?.label).toBe(CONFLICT_LABEL);
    expect(settled.shake).toEqual({ x: 0, y: 0 });
    expect(settled.cues[0]?.offset_ms).toBe(STAMP_AT_MS);

    const tree = AlibiSplitScreen(props);
    expect(tree.dataset["safe-zone"]).toBe("css-contained");
    expect(tree.dataset.motif).toBe(ALIBI_SPLIT_SCREEN_ID);
    expect(tree.dataset["motif-number"]).toBe("11");
    expect(tree.dataset.owner).toBe(ALIBI_SPLIT_SCREEN_OWNER);
    expect(tree.dataset["end-screen"]).toBe("false");
    expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
    expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
    expect(tree.props.style.width).toBe(FRAME_WIDTH);
    expect(tree.props.style.height).toBe(FRAME_HEIGHT);
    expect(tree.props.style.overflow).toBe("hidden");
    expect(tree.props.style.background).toBe(PAPER_BG);
    expect(tree.props.style.transform).toBeUndefined();

    const graphic = node(tree, "slot", "graphic");
    expect(graphic.props.style.transform).toBe(`translate(${MAX_SHAKE_PX}px, 0px)`);
    expect(graphic.props.style.overflow).toBe("hidden");
    expect(graphic.dataset["shake-x"]).toBe(String(MAX_SHAKE_PX));
    expect(graphic.dataset["shake-y"]).toBe("0");
    const transformed = walkSplit(tree).filter((item) => item.props.style.transform !== undefined);
    expect(transformed.map((item) => item.dataset.slot)).toEqual(["graphic"]);

    const stamp = node(tree, "slot", "conflict-stamp");
    expect(stamp.props.children).toBe(CONFLICT_LABEL);
    expect(stamp.props.style.color).toBe(EVIDENCE_CRIMSON);
    expect(stamp.props.style.border).toBe(`4px solid ${EVIDENCE_CRIMSON}`);
    expect(stamp.dataset["offset-ms"]).toBe(String(STAMP_AT_MS));
    expect(stamp.dataset["start-sample"]).toBe("131808");
    expect(stamp.dataset.cue).toBe(CONFLICT_STAMP_CUE);
    expect(node(tree, "slot", "claim-header").props.children).toBe(CLAIM_HEADER);
    expect(node(tree, "slot", "evidence-header").props.children).toBe(EVIDENCE_HEADER);
    expect(bodyText(tree, "claim-body")).toBe(CLAIM_SUMMARY);
    expect(bodyText(tree, "evidence-body")).toBe(EVIDENCE_SUMMARY);
    expect(node(tree, "slot", "claim").dataset["source-type"]).toBe("news_report");
    expect(node(tree, "slot", "evidence").dataset["source-type"]).toBe("police_affidavit");
    expect(node(tree, "slot", "claim").dataset["fact-id"]).toBe(props.claim.fact_id);
    expect(node(tree, "slot", "evidence").dataset["fact-id"]).toBe(props.evidence.fact_id);
    expect(node(tree, "slot", "evidence-citation").props.children).toBe(EVIDENCE_CITATION);
    expect(node(tree, "slot", "claim-body").props.style.color).toBe(INK);
    expect(node(tree, "slot", "evidence-body").props.style.color).toBe(INK);
    expect(node(tree, "exclusion", "bottom-right").props.style).toMatchObject({ width: "22%", height: "14%" });
    expect(node(tree, "slot", "conflict-stamp-cue").dataset["offset-ms"]).toBe(String(STAMP_AT_MS));

    const crimsonNodes = walkSplit(tree).filter((item) => JSON.stringify(item.props.style).includes(EVIDENCE_CRIMSON));
    expect(crimsonNodes.map((item) => item.dataset.slot)).toEqual(["conflict-stamp"]);

    const hidden = AlibiSplitScreen({ ...props, frame: 81 });
    expect(walkSplit(hidden).some((item) => item.dataset.slot === "conflict-stamp")).toBe(false);
    expect(JSON.stringify(hidden)).not.toContain(EVIDENCE_CRIMSON);
    expect(node(hidden, "slot", "conflict-stamp-cue").dataset["offset-ms"]).toBe(String(STAMP_AT_MS));
    expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap/);
  }
});

test("a millisecond that is not a frame boundary stays on that millisecond", () => {
  const syncFrame = frameForOffsetMs(1);
  expect(syncFrame).toBe(0);
  expect(mixSampleForOffsetMs(1)).toBe(48);
  const layout = layoutAlibiSplitScreen({
    sceneId: "scene_ms_1",
    frame: 0,
    stampAtMs: 1,
    shakePx: 0,
    claim: {
      fact_id: "fact_claim",
      source_type: "suspect_statement",
      text: "I was at the diner.",
      citation: "Interview p. 3",
    },
    evidence: {
      fact_id: "fact_record",
      source_type: "court_ruling",
      text: "The ruling places the defendant at the house.",
      citation: "2021 MT 142 at paragraph 18",
    },
  });
  expect(layout.sync.offset_ms).toBe(1);
  expect(layout.sync.start_sample).toBe(48);
  expect(layout.sync.start_frame).toBe(0);
  expect(layout.cues[0]?.offset_ms).toBe(1);
  expect(layout.cues[0]?.start_sample).toBe(48);
  expect(layout.stamp?.label).toBe(CONFLICT_LABEL);
  expect(layout.shake).toEqual({ x: 0, y: 0 });
  const tree = AlibiSplitScreen({
    sceneId: "scene_ms_1",
    frame: 0,
    stampAtMs: 1,
    shakePx: 0,
    claim: {
      fact_id: "fact_claim",
      source_type: "suspect_statement",
      text: "I was at the diner.",
      citation: "Interview p. 3",
    },
    evidence: {
      fact_id: "fact_record",
      source_type: "court_ruling",
      text: "The ruling places the defendant at the house.",
      citation: "2021 MT 142 at paragraph 18",
    },
  });
  expect(node(tree, "slot", "graphic").props.style.transform).toBe("translate(0px, 0px)");
  expect(node(tree, "slot", "conflict-stamp").dataset["offset-ms"]).toBe("1");
  expect(node(tree, "slot", "conflict-stamp").dataset["start-sample"]).toBe("48");
});

test("micro-shake stays on the inner graphic and inside 6 px", () => {
  const pack = loadPack(PACKS[0]);
  const base = goldenProps(pack, 82, { shakePx: 80 });
  const layout = layoutAlibiSplitScreen(base);
  expect(layout.shakePx).toBe(MAX_SHAKE_PX);
  expect(layout.shake).toEqual(microShake(82, 82, 80));
  expect(layout.shake).toEqual(microShake(82, 82, 6));
  expect(Math.abs(layout.shake.x)).toBeLessThanOrEqual(MAX_SHAKE_PX);
  expect(Math.abs(layout.shake.y)).toBeLessThanOrEqual(MAX_SHAKE_PX);
  expect(layout.graphic.x).toBe(layout.content.x + MAX_SHAKE_PX);
  expect(layout.graphic.y).toBe(layout.content.y + MAX_SHAKE_PX);
  expect(layout.graphic.x + layout.graphic.width).toBe(layout.content.x + layout.content.width - MAX_SHAKE_PX);
  expect(layout.graphic.y + layout.graphic.height).toBe(layout.content.y + layout.content.height - MAX_SHAKE_PX);

  const tree = AlibiSplitScreen(base);
  expect(tree.props.style.transform).toBeUndefined();
  expect(node(tree, "slot", "graphic").props.style.transform).toBe(`translate(${layout.shake.x}px, ${layout.shake.y}px)`);
  const claimBody = node(tree, "slot", "claim-body");
  const graphic = node(tree, "slot", "graphic");
  expect(walkSplit(graphic).some((item) => item.dataset.slot === "claim-body")).toBe(true);
  expect(walkSplit(tree).filter((item) => item.props.style.transform !== undefined)).toHaveLength(1);
  expect(claimBody.props.style.transform).toBeUndefined();

  for (let frame = 0; frame <= 82 + STAMP_HOLD_FRAMES + 4; frame += 1) {
    const sample = layoutAlibiSplitScreen({ ...base, frame });
    const shaken = translateRect(sample.graphic, sample.shake.x, sample.shake.y);
    expect(sample.shake).toEqual(microShake(frame, 82, 80));
    expect(sample.shake.x * sample.shake.x + sample.shake.y * sample.shake.y).toBeLessThanOrEqual(MAX_SHAKE_PX ** 2);
    expect(rectInside(shaken, sample.content)).toBe(true);
    expect(rectInside(sample.claim.page, sample.content)).toBe(true);
    expect(rectInside(sample.evidence.page, sample.content)).toBe(true);
    expect(rectInside(sample.claim.bodyPage, sample.content)).toBe(true);
    expect(rectInside(sample.evidence.bodyPage, sample.content)).toBe(true);
    expect(rectInside(sample.claim.citationPage, sample.content)).toBe(true);
    expect(rectsOverlap(shaken, sample.captionBar)).toBe(false);
    expect(rectsOverlap(shaken, sample.exclusion)).toBe(false);
    if (sample.stamp) expect(rectInside(sample.stamp.page, shaken)).toBe(true);
    expect(frame >= 82).toBe(sample.stamp !== null);
  }

  const softer = layoutAlibiSplitScreen(goldenProps(pack, 82, { shakePx: 5.2 }));
  expect(softer.shakePx).toBe(5);
  expect(softer.shake).toEqual({ x: 5, y: 0 });
});

test("end-screen mask keeps the shaken graphic above the card", () => {
  const pack = loadPack(PACKS[0]);
  const layout = layoutAlibiSplitScreen(goldenProps(pack, 82, { isEndScreen: true, shakePx: 80 }));
  expect(layout.isEndScreen).toBe(true);
  expect(layout.endScreenMask).not.toBeNull();
  if (!layout.endScreenMask) throw new Error("missing end-screen mask");
  const shaken = translateRect(layout.graphic, layout.shake.x, layout.shake.y);
  expect(rectsOverlap(shaken, layout.endScreenMask)).toBe(false);
  expect(rectsOverlap(layout.claim.page, layout.endScreenMask)).toBe(false);
  expect(layout.stamp).not.toBeNull();
  expect(layout.sync.offset_ms).toBe(STAMP_AT_MS);
  const tree = AlibiSplitScreen(goldenProps(pack, 82, { isEndScreen: true }));
  expect(tree.dataset["end-screen"]).toBe("true");
  expect(node(tree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
  expect(node(tree, "slot", "graphic").props.style.transform).toBe(`translate(${MAX_SHAKE_PX}px, 0px)`);
});

test("a claim longer than 12 words is clamped inside the pane", () => {
  const words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen"];
  const layout = layoutAlibiSplitScreen({
    sceneId: "scene_long_claim",
    frame: 10,
    stampAtMs: 0,
    claim: {
      fact_id: "fact_long",
      source_type: "suspect_statement",
      text: words.join(" "),
      citation: "Statement p. 1",
    },
    evidence: {
      fact_id: "fact_short",
      source_type: "police_affidavit",
      text: EVIDENCE_SUMMARY,
      citation: EVIDENCE_CITATION,
    },
  });
  expect(layout.claim.truncated).toBe(true);
  expect(layout.claim.wordCount).toBe(MAX_WORDS);
  expect(layout.claim.display.split(/\s+/)).toHaveLength(MAX_WORDS);
  expect(layout.claim.display.endsWith("twelve")).toBe(true);
  expect(layout.claim.display).not.toContain("thirteen");
  expect(layout.claim.text).toContain("thirteen");
  expect(rectInside(layout.claim.bodyPage, layout.claim.page)).toBe(true);
  expect(rectInside(layout.claim.page, translateRect(layout.graphic, layout.shake.x, layout.shake.y))).toBe(true);
  const tree = AlibiSplitScreen({
    sceneId: "scene_long_claim",
    frame: 10,
    stampAtMs: 0,
    claim: {
      fact_id: "fact_long",
      source_type: "suspect_statement",
      text: words.join(" "),
      citation: "Statement p. 1",
    },
    evidence: {
      fact_id: "fact_short",
      source_type: "police_affidavit",
      text: EVIDENCE_SUMMARY,
      citation: EVIDENCE_CITATION,
    },
  });
  expect(node(tree, "slot", "claim").dataset.truncated).toBe("true");
  expect(node(tree, "slot", "claim").dataset.words).toBe("12");
  expect(bodyText(tree, "claim-body").split(/\s+/)).toHaveLength(MAX_WORDS);
  expect(bodyText(tree, "claim-body")).not.toContain("thirteen");
});

test("rejects a bad split, a fractional millisecond, and a negative shake", () => {
  const claim = {
    fact_id: "fact_claim",
    source_type: "suspect_statement" as const,
    text: "I was home.",
    citation: "Statement p. 1",
  };
  const evidence = {
    fact_id: "fact_record",
    source_type: "police_affidavit" as const,
    text: "The affidavit places the car downtown.",
    citation: "Affidavit p. 2",
  };
  const props = { sceneId: "scene_bad", frame: 0, stampAtMs: 10, claim, evidence };
  expect(() => layoutAlibiSplitScreen({ ...props, frame: -1 })).toThrow(/frame/);
  expect(() => layoutAlibiSplitScreen({ ...props, stampAtMs: 10.5 })).toThrow(/stampAtMs/);
  expect(() => layoutAlibiSplitScreen({ ...props, stampAtMs: -1 })).toThrow(/stampAtMs/);
  expect(() => layoutAlibiSplitScreen({ ...props, shakePx: -3 })).toThrow(/shakePx/);
  expect(() => layoutAlibiSplitScreen({ ...props, shakePx: Number.NaN })).toThrow(/shakePx/);
  expect(() => layoutAlibiSplitScreen({ ...props, sceneId: "bad id" })).toThrow(/sceneId/);
  expect(() => layoutAlibiSplitScreen({ ...props, claim: { ...claim, fact_id: evidence.fact_id } })).toThrow(
    /different facts/,
  );
  expect(() =>
    layoutAlibiSplitScreen({ ...props, claim: { ...claim, source_type: "police_affidavit" as "suspect_statement" } }),
  ).toThrow(/claim source/);
  expect(() =>
    layoutAlibiSplitScreen({ ...props, evidence: { ...evidence, source_type: "news_report" as "police_affidavit" } }),
  ).toThrow(/evidence source/);
  expect(() => layoutAlibiSplitScreen({ ...props, claim: { ...claim, text: "   " } })).toThrow(/claim text/);
  expect(() => layoutAlibiSplitScreen({ ...props, evidence: { ...evidence, citation: "bad\nline" } })).toThrow(
    /citation/,
  );
  expect(() => layoutAlibiSplitScreen({ ...props, isEndScreen: "yes" as unknown as boolean })).toThrow(/isEndScreen/);
  expect(() => layoutAlibiSplitScreen({ ...props, frame: 1.2 })).toThrow(AlibiSplitScreenError);
});
