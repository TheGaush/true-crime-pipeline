import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  EXCLUSION_RECT,
  FoiaFootageError,
  FoiaFootageFrame,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  SAFE_RECT,
  SCENE_GRADE_MANIFEST_FILENAME,
  ZOOM_MIN_FACTOR,
  gradeTargetAt,
  probeFoiaMp4,
  rectInside,
  rectsOverlap,
  walkFoia,
  type CalloutZoom,
  type FoiaFootageInput,
  type FoiaProvenance,
  type SceneGradeManifest,
  type StickPoseId,
} from "../../src/motifs/FoiaFootageFrame.tsx";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");

function u32(value: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32BE(value >>> 0, 0);
  return buf;
}

function box(type: string, payload: Buffer): Buffer {
  return Buffer.concat([u32(8 + payload.length), Buffer.from(type, "ascii"), payload]);
}

function zeros(length: number): Buffer {
  return Buffer.alloc(length);
}

function matrix(): Buffer {
  const bytes = Buffer.alloc(36);
  bytes.writeUInt32BE(0x00010000, 0);
  bytes.writeUInt32BE(0x00010000, 16);
  bytes.writeUInt32BE(0x40000000, 32);
  return bytes;
}

interface SampleEntry {
  readonly count: number;
  readonly delta: number;
}

function syntheticMp4(options: {
  readonly width: number;
  readonly height: number;
  readonly timescale: number;
  readonly entries: readonly SampleEntry[];
  readonly handler?: "vide" | "soun";
}): Uint8Array {
  const handler = options.handler ?? "vide";
  const sampleCount = options.entries.reduce((sum, entry) => sum + entry.count, 0);
  const duration = options.entries.reduce((sum, entry) => sum + entry.count * entry.delta, 0);
  const ftyp = box(
    "ftyp",
    Buffer.concat([Buffer.from("isom", "ascii"), u32(0), Buffer.from("isomiso2mp41", "ascii")]),
  );
  const mdat = box("mdat", Buffer.alloc(Math.max(sampleCount, 1)));
  const sttsBody = [u32(0), u32(options.entries.length)];
  for (const entry of options.entries) sttsBody.push(u32(entry.count), u32(entry.delta));
  const stbl = box(
    "stbl",
    Buffer.concat([
      box("stsd", Buffer.concat([u32(0), u32(1), box(handler === "vide" ? "mp4v" : "sowt", zeros(8))])),
      box("stts", Buffer.concat(sttsBody)),
      box("stsc", Buffer.concat([u32(0), u32(1), u32(1), u32(Math.max(sampleCount, 1)), u32(1)])),
      box("stsz", Buffer.concat([u32(0), u32(1), u32(Math.max(sampleCount, 1))])),
      box("stco", Buffer.concat([u32(0), u32(1), u32(ftyp.length + 8)])),
    ]),
  );
  const mediaHeader = handler === "vide"
    ? box("vmhd", Buffer.concat([u32(1), zeros(8)]))
    : box("smhd", Buffer.concat([u32(0), zeros(4)]));
  const minf = box(
    "minf",
    Buffer.concat([
      mediaHeader,
      box("dinf", box("dref", Buffer.concat([u32(0), u32(1), box("url ", u32(1))]))),
      stbl,
    ]),
  );
  const mdhd = box(
    "mdhd",
    Buffer.concat([
      u32(0),
      u32(0),
      u32(0),
      u32(options.timescale),
      u32(duration),
      Buffer.from([0x55, 0xc4, 0x00, 0x00]),
    ]),
  );
  const hdlr = box(
    "hdlr",
    Buffer.concat([
      u32(0),
      u32(0),
      Buffer.from(handler, "ascii"),
      zeros(12),
      Buffer.from("VideoHandler\0", "ascii"),
    ]),
  );
  const width = Buffer.alloc(4);
  const height = Buffer.alloc(4);
  width.writeUInt32BE((options.width * 65536) >>> 0, 0);
  height.writeUInt32BE((options.height * 65536) >>> 0, 0);
  const tkhd = box(
    "tkhd",
    Buffer.concat([
      u32(0x7),
      u32(0),
      u32(0),
      u32(1),
      u32(0),
      u32(duration),
      zeros(8),
      Buffer.from([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),
      matrix(),
      width,
      height,
    ]),
  );
  const mvhd = box(
    "mvhd",
    Buffer.concat([
      u32(0),
      u32(0),
      u32(0),
      u32(options.timescale),
      u32(duration),
      u32(0x00010000),
      Buffer.from([0x01, 0x00, 0x00, 0x00]),
      zeros(8),
      matrix(),
      zeros(24),
      u32(2),
    ]),
  );
  const trak = box("trak", Buffer.concat([tkhd, box("mdia", Buffer.concat([mdhd, hdlr, minf]))]));
  const moov = box("moov", Buffer.concat([mvhd, trak]));
  return new Uint8Array(Buffer.concat([ftyp, mdat, moov]));
}

function cfrClip(width: number, height: number, timescale = 30, delta = 1, frames = 30): Uint8Array {
  return syntheticMp4({
    width,
    height,
    timescale,
    entries: [{ count: frames, delta }],
  });
}

function provenance(overrides: Partial<FoiaProvenance> = {}): FoiaProvenance {
  return {
    asset_id: "case_golden_foia_bodycam",
    creator_entity: "Marlow County Sheriff",
    rights_holder: "Marlow County",
    license_basis: "STATE_PUBLIC_RECORD_PERMITTED",
    rights_review_status: "APPROVED",
    contains_third_party_attach: 0,
    media_kind: "bodycam_mp4",
    scrubbed_path: "fixtures/synthetic_media/bodycam_scrubbed_cfr30.mp4",
    normalized_cfr_30fps_48k: 1,
    visual_pii_blurred: 1,
    spoken_pii_bleeped: 1,
    raw_path: "RAW_SECRET_BODYCAM_PATH",
    source_domain: "records.marlow.example",
    ...overrides,
  };
}

function calloutFor(width: number, height: number, label = "Dispatcher clock at 2:14 a.m."): CalloutZoom {
  return {
    x: Math.round(width * 0.2),
    y: Math.round(height * 0.25),
    width: Math.round(width * 0.12),
    height: Math.round(height * 0.12),
    label,
    fact_id: "case_golden_fact_affidavit",
  };
}

function inputFor(bytes: Uint8Array, overrides: Partial<FoiaFootageInput> = {}): FoiaFootageInput {
  const probe = probeFoiaMp4(bytes);
  return {
    sceneId: "ep_golden_s001",
    episodeId: "ep_golden_01",
    bytes,
    provenance: provenance(),
    callout: calloutFor(probe.width, probe.height),
    frame: 15,
    ...overrides,
  };
}

function render(bytes: Uint8Array, overrides: Partial<FoiaFootageInput> = {}) {
  return FoiaFootageFrame(inputFor(bytes, overrides));
}

function textOf(node: ReturnType<typeof walkFoia>[number] | string): string {
  if (typeof node === "string") return node;
  return (node.props.children ?? []).map((child) => textOf(child as typeof node)).join(" ");
}

function role(model: ReturnType<typeof FoiaFootageFrame>, name: string) {
  return walkFoia(model.element).find((item) => item.dataset.role === name);
}

describe("FoiaFootageFrame", () => {
  it("plays a scrubbed 16:9 CFR clip full-bleed and keeps the footage ungraded", () => {
    const bytes = cfrClip(1920, 1080);
    const model = render(bytes);
    expect(model.motif).toBe("FoiaFootageFrame");
    expect(model.visualEngine).toBe("FOIA_REAL_FOOTAGE");
    expect(model.applyGrade).toBe(false);
    expect(model.fps).toBe(30);
    expect(model.cfr).toBe(true);
    expect(model.layout).toBe("full-bleed");
    expect(model.sidebarRect).toBeNull();
    expect(model.videoRect).toEqual({ x: 0, y: 0, width: FRAME_WIDTH, height: FRAME_HEIGHT });
    expect(model.videoRect.width / model.videoRect.height).toBeCloseTo(16 / 9, 8);
    expect(model.frame).toBe(15);
    expect(model.timestampMs).toBe(500);
    expect(model.zoomFactor).toBeGreaterThan(ZOOM_MIN_FACTOR);
    expect(rectInside(model.calloutOutlineRect, model.videoRect)).toBe(true);
    expect(rectInside(model.hudRect, SAFE_RECT)).toBe(true);
    expect(rectInside(model.zoomRect, SAFE_RECT)).toBe(true);
    expect(rectsOverlap(model.hudRect, EXCLUSION_RECT)).toBe(false);
    expect(rectsOverlap(model.zoomRect, EXCLUSION_RECT)).toBe(false);
    expect(role(model, "dossier-sidebar")).toBeUndefined();
    const footage = role(model, "foia-footage");
    expect(footage?.dataset["apply-grade"]).toBe("false");
    expect(footage?.dataset.src).toBe("fixtures/synthetic_media/bodycam_scrubbed_cfr30.mp4");
    expect(footage?.dataset.cfr).toBe("true");
    expect(footage?.dataset.fps).toBe("30");
    expect(footage?.props.style.filter).toBe("none");
    expect(footage?.props.style.backgroundImage).toBe("none");
    expect(footage?.props.style.objectFit).toBeUndefined();
    const hud = textOf(model.element);
    expect(hud).toContain("FOIA SCRUBBED CFR 30");
    expect(hud).toContain("Marlow County Sheriff");
    expect(hud).toContain("apply_grade false");
    expect(hud).toContain("case_golden_fact_affidavit");
    expect(JSON.stringify(model.element)).not.toContain("RAW_SECRET_BODYCAM_PATH");
    expect(JSON.stringify(model.element)).not.toContain("feTurbulence");
    expect(JSON.stringify(model.element)).not.toContain("feDisplacementMap");
    for (const node of walkFoia(model.element)) {
      expect(node.props.style.filter).toBe("none");
      expect(node.props.style.backgroundImage).toBe("none");
    }
    expect(model.grade.filename).toBe(SCENE_GRADE_MANIFEST_FILENAME);
    expect(model.grade.source).toBe("local");
    expect(model.grade.json.endsWith("\n")).toBe(true);
    const scene = model.grade.manifest.scenes[0];
    expect(scene?.apply_grade).toBe(false);
    expect(scene?.needs_grade).toBe(false);
    expect(scene?.is_foia).toBe(true);
    expect(scene?.exempt_from_grain).toBe(true);
    expect(scene?.paper_grain).toBe(0);
    expect(scene?.vignette).toBe(0);
    expect(scene?.remotion_grain_applied).toBe(false);
    expect(scene?.remotion_vignette_applied).toBe(false);
    expect(scene?.grain_phase).toBeNull();
    expect(scene?.grade_owner).toBe("none");
    expect(scene?.stylized_overlays).toEqual([]);
    expect(model.grade.manifest.paper_grain).toBe(0);
    expect(model.grade.manifest.vignette).toBe(0);
    expect(gradeTargetAt(scene!, model.videoRect.x + 10, model.videoRect.y + 10)).toBe("exempt");
    expect(JSON.stringify(model.grade.manifest)).not.toContain('"apply_grade": true');
  });

  it("pillarboxes a 9:16 phone clip into a dossier sidebar", () => {
    const bytes = cfrClip(1080, 1920);
    const model = render(bytes, { pip: { pose: "phone_call", facing: "left" } });
    expect(model.layout).toBe("dossier-sidebar");
    expect(model.element.dataset.pillarbox).toBe("true");
    expect(model.sidebarRect).not.toBeNull();
    expect(model.videoRect.width / model.videoRect.height).toBeCloseTo(1080 / 1920, 8);
    expect(model.videoRect.width).toBeCloseTo(437.625, 5);
    expect(model.videoRect.x + model.videoRect.width).toBeLessThan(FRAME_WIDTH / 2);
    expect(rectsOverlap(model.videoRect, model.sidebarRect!)).toBe(false);
    expect(rectInside(model.videoRect, SAFE_RECT)).toBe(true);
    expect(rectInside(model.sidebarRect!, SAFE_RECT)).toBe(true);
    expect(rectInside(model.hudRect, model.sidebarRect!)).toBe(true);
    expect(rectInside(model.zoomRect, model.sidebarRect!)).toBe(true);
    expect(rectInside(model.pipRect!, model.sidebarRect!)).toBe(true);
    expect(rectsOverlap(model.pipRect!, model.videoRect)).toBe(false);
    expect(rectsOverlap(model.hudRect, model.zoomRect)).toBe(false);
    expect(rectsOverlap(model.pipRect!, model.zoomRect)).toBe(false);
    expect(rectsOverlap(model.pipRect!, EXCLUSION_RECT)).toBe(false);
    expect(model.zoomFactor).toBeGreaterThan(ZOOM_MIN_FACTOR);
    expect(role(model, "dossier-sidebar")?.dataset.pillarbox).toBe("true");
    const pip = role(model, "pip-stick-figure");
    expect(pip?.dataset.component).toBe("StickFigure");
    expect(pip?.dataset.pose).toBe("phone_call");
    expect(pip?.dataset.facing).toBe("left");
    expect(pip?.dataset.mounted).toBe("slot");
    const scene = model.grade.manifest.scenes[0]!;
    expect(scene.apply_grade).toBe(false);
    expect(gradeTargetAt(scene, model.videoRect.x + model.videoRect.width / 2, model.videoRect.y + 20)).toBe("exempt");
    expect(gradeTargetAt(scene, model.pipRect!.x + 4, model.pipRect!.y + 4)).toBe("agent6");
    expect(scene.ungraded_masks[0]?.apply_grade).toBe(false);
    expect(scene.stylized_overlays[0]?.kind).toBe("narrator_pip_border");
    expect(scene.stylized_overlays[0]?.apply_grade).toBe(true);
    expect(rectsOverlap(scene.stylized_overlays[0]!, model.videoRect)).toBe(false);
  });

  it("accepts a 30 fps CFR timescale other than 30 and rejects drift", () => {
    const fast = cfrClip(1280, 720, 30000, 1000, 30);
    const probe = probeFoiaMp4(fast);
    expect(probe.fps).toBe(30);
    expect(probe.cfr).toBe(true);
    expect(probe.timescale).toBe(30000);
    expect(probe.sampleDelta).toBe(1000);
    expect(render(fast).layout).toBe("full-bleed");

    expect(() => probeFoiaMp4(syntheticMp4({
      width: 1920,
      height: 1080,
      timescale: 30,
      entries: [
        { count: 15, delta: 1 },
        { count: 15, delta: 2 },
      ],
    }))).toThrow(FoiaFootageError);
    try {
      probeFoiaMp4(syntheticMp4({
        width: 1920,
        height: 1080,
        timescale: 24,
        entries: [{ count: 24, delta: 1 }],
      }));
      throw new Error("24 fps should have failed");
    } catch (error) {
      expect(error).toBeInstanceOf(FoiaFootageError);
      expect((error as FoiaFootageError).code).toBe("NOT_CFR_30");
    }
    expect(() => probeFoiaMp4(syntheticMp4({
      width: 1440,
      height: 1080,
      timescale: 30,
      entries: [{ count: 30, delta: 1 }],
    }))).toThrow(expect.objectContaining({ code: "ASPECT" }));
  });

  it("rejects audio-only MP4s, including the golden bodycam sowt file", () => {
    expect(() => probeFoiaMp4(syntheticMp4({
      width: 0,
      height: 0,
      timescale: 8000,
      entries: [{ count: 8000, delta: 1 }],
      handler: "soun",
    }))).toThrow(expect.objectContaining({ code: "NO_VIDEO" }));
    const golden = readFileSync(resolve(repoRoot, "fixtures/synthetic_media/bodycam_440hz_music_042profanity.mp4"));
    expect(() => probeFoiaMp4(new Uint8Array(golden))).toThrow(expect.objectContaining({ code: "NO_VIDEO" }));
  });

  it("refuses footage that is not scrubbed, cleared, or free of third-party bytes", () => {
    const bytes = cfrClip(1920, 1080);
    const cases: Array<[Partial<FoiaProvenance>, string]> = [
      [{ rights_review_status: "IN_REVIEW" }, "RIGHTS"],
      [{ license_basis: "RESTRICTED_NO_REUSE" }, "RIGHTS"],
      [{ contains_third_party_attach: 1 }, "RIGHTS"],
      [{ media_kind: "call_911_wav" }, "RIGHTS"],
      [{ normalized_cfr_30fps_48k: 0 }, "SCRUB"],
      [{ scrubbed_path: "https://records.example/clip.mp4" }, "SCRUB"],
      [{ scrubbed_path: "" }, "SCRUB"],
      [{ visual_pii_blurred: 0 }, "PII"],
      [{ spoken_pii_bleeped: 0 }, "PII"],
    ];
    for (const [override, code] of cases) {
      expect(() => render(bytes, { provenance: provenance(override) })).toThrow(
        expect.objectContaining({ code }),
      );
    }
  });

  it("keeps the callout inside the clip, the word limit, and the safe zone", () => {
    const bytes = cfrClip(1920, 1080);
    const twelve = "one two three four five six seven eight nine ten eleven twelve";
    expect(render(bytes, { callout: calloutFor(1920, 1080, twelve) }).zoomFactor).toBeGreaterThan(1);
    expect(() => render(bytes, {
      callout: calloutFor(1920, 1080, `${twelve} thirteen`),
    })).toThrow(expect.objectContaining({ code: "CALLOUT" }));
    expect(() => render(bytes, {
      callout: { ...calloutFor(1920, 1080), y: 20 },
    })).toThrow(expect.objectContaining({ code: "CALLOUT" }));
    expect(() => render(bytes, {
      callout: { ...calloutFor(1920, 1080), x: 1800, width: 400 },
    })).toThrow(expect.objectContaining({ code: "CALLOUT" }));
    expect(() => render(bytes, { frame: 30 })).toThrow(expect.objectContaining({ code: "FRAME" }));
    expect(() => render(bytes, { frame: -1 })).toThrow(expect.objectContaining({ code: "FRAME" }));
    expect(render(bytes, { frame: 29 }).timestampMs).toBe(967);
  });

  it("mounts an optional StickFigure PiP without drawing it into the raw clip", () => {
    const bytes = cfrClip(1920, 1080);
    expect(role(render(bytes), "pip-stick-figure")).toBeUndefined();
    const figure = { marker: "external-stick-rig" };
    const model = render(bytes, { pip: { pose: "idle", figure } });
    const pip = role(model, "pip-stick-figure");
    expect(pip?.dataset.mounted).toBe("figure");
    expect(pip?.stickFigure).toBe(figure);
    expect(rectInside(model.pipRect!, SAFE_RECT)).toBe(true);
    expect(JSON.stringify(role(model, "foia-footage"))).not.toContain("external-stick-rig");
    const scene = model.grade.manifest.scenes[0]!;
    expect(gradeTargetAt(scene, model.pipRect!.x + 8, model.pipRect!.y + 8)).toBe("exempt");
    expect(scene.apply_grade).toBe(false);
    expect(() => render(bytes, { pip: { pose: "dancing" as StickPoseId } })).toThrow(
      expect.objectContaining({ code: "POSE" }),
    );
  });

  it("rejects a grade delegate that would grain the footage and keeps a raw delegate", () => {
    const bytes = cfrClip(1920, 1080);
    const local = render(bytes);
    const delegated = render(bytes, {
      gradeDelegate: () => local.grade.manifest,
    });
    expect(delegated.grade.source).toBe("delegate");
    expect(delegated.grade.manifest.scenes[0]?.apply_grade).toBe(false);
    const graded = {
      ...local.grade.manifest,
      scenes: [{ ...local.grade.manifest.scenes[0], apply_grade: true, needs_grade: true }],
    } as SceneGradeManifest;
    expect(() => render(bytes, { gradeDelegate: () => graded })).toThrow(
      expect.objectContaining({ code: "GRADE" }),
    );
    const grained = {
      ...local.grade.manifest,
      paper_grain: 1,
    } as unknown as SceneGradeManifest;
    expect(() => render(bytes, { gradeDelegate: () => grained })).toThrow(
      expect.objectContaining({ code: "GRADE" }),
    );
  });

  it("blocks outbound network while the motif is built from in-memory bytes", async () => {
    expect(process.env.GEMINI_API_KEY).toBeUndefined();
    await expect(fetch("https://example.com/foia.mp4")).rejects.toThrow(/ZERO_SPEND_GUARD/);
    expect(render(cfrClip(1920, 1080)).probe.sampleCount).toBe(30);
  });
});
