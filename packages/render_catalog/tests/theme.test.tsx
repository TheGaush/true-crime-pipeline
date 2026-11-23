import { readFileSync } from "node:fs";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  CASE_BIBLE_MIN_CONTRAST,
  CaseBibleCharacter,
  CaseBibleError,
  CaseBibleProvider,
  CaseBibleSafeZone,
  contrastRatio,
  lockCaseBible,
  useCaseBible,
  type LockedCaseBible,
} from "../src/theme/CaseBibleContext.tsx";

const endScreenFlags = vi.hoisted(() => [] as boolean[]);

vi.mock("../src/safe_zone.tsx", async () => {
  const { createElement: h } = await import("react");
  return {
    SafeZoneLayout: ({ isEndScreen = false, children }: { isEndScreen?: boolean; children?: ReactNode }) => {
      endScreenFlags.push(isEndScreen);
      return h("div", { "data-safe-zone": "task-101" }, children);
    },
  };
});

const SOURCE_URL = new URL("../src/theme/CaseBibleContext.tsx", import.meta.url);

function bible(patch?: {
  style?: Record<string, unknown>;
  characters?: Array<Record<string, unknown>>;
  extra?: Record<string, unknown>;
}) {
  return {
    contract_version: "v4",
    episode_id: "ep_golden_01_20min",
    locked_at: 500,
    style_dna_json: {
      evidence_crimson_hex: "#C92A2A",
      paper_bg_hex: "#E9E2D2",
      ink_hex: "#1B1B1D",
      slate_hex: "#3A4F66",
      flow_keyframe_safe_palette: ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"],
      ...patch?.style,
    },
    characters_json: patch?.characters ?? [
      { character_id: "detective_01", prop: "notepad", color_hex: "#3A4F66" },
      { character_id: "suspect_01", prop: "coat", color_hex: "#1B1B1D" },
    ],
    ...patch?.extra,
  };
}

function renderTheme(node: ReactNode, value: unknown = bible()) {
  return renderToStaticMarkup(createElement(CaseBibleProvider, { bible: value }, node));
}

describe("contrastRatio", () => {
  it("matches black on white and a flat color", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrastRatio("#E9E2D2", "#e9e2d2")).toBeCloseTo(1, 5);
    expect(contrastRatio("#1B1B1D", "#E9E2D2")).toBeGreaterThan(CASE_BIBLE_MIN_CONTRAST);
    expect(contrastRatio("#C4A574", "#E9E2D2")).toBeLessThan(CASE_BIBLE_MIN_CONTRAST);
  });
});

describe("lockCaseBible", () => {
  it("distributes the locked palette and character props without rewriting them", () => {
    const flow = ["#161616", "#F7F4EC", "#2C455C", "#8A7348"];
    const theme = lockCaseBible(
      bible({
        style: {
          evidence_crimson_hex: "#B42318",
          paper_bg_hex: "#F7F4EC",
          ink_hex: "#161616",
          slate_hex: "#2C455C",
          flow_keyframe_safe_palette: flow,
        },
        characters: [{ character_id: "detective_01", prop: "notepad", color_hex: "#2C455C" }],
      }),
    );

    expect(theme.contractVersion).toBe("v4");
    expect(theme.episodeId).toBe("ep_golden_01_20min");
    expect(theme.lockedAt).toBe(500);
    expect(theme.paperBgHex).toBe("#F7F4EC");
    expect(theme.inkHex).toBe("#161616");
    expect(theme.slateHex).toBe("#2C455C");
    expect(theme.evidenceCrimsonHex).toBe("#B42318");
    expect(theme.flowKeyframeSafePalette).toEqual(flow);
    expect(theme.character("detective_01")).toEqual({
      characterId: "detective_01",
      prop: "notepad",
      colorHex: "#2C455C",
    });

    flow.push("#FFFFFF");
    expect(theme.flowKeyframeSafePalette).toHaveLength(4);
  });

  it("keeps the caller's hex spelling", () => {
    const theme = lockCaseBible(
      bible({
        style: { paper_bg_hex: "#e9e2d2" },
      }),
    );
    expect(theme.paperBgHex).toBe("#e9e2d2");
  });

  it("rejects character color below 3.5:1 on paper", () => {
    expect(() =>
      lockCaseBible(
        bible({
          characters: [{ character_id: "suspect_01", prop: "coat", color_hex: "#C4A574" }],
        }),
      ),
    ).toThrow(CaseBibleError);
    expect(() =>
      lockCaseBible(
        bible({
          characters: [{ character_id: "suspect_01", prop: "coat", color_hex: "#C4A574" }],
        }),
      ),
    ).toThrow(/characterId suspect_01 \(#C4A574 on #E9E2D2\) is below 3.5:1/);
  });

  it("rejects ink, slate, and crimson that fail contrast on paper", () => {
    expect(() => lockCaseBible(bible({ style: { ink_hex: "#D9D0C0" } }))).toThrow(/ink_hex/);
    expect(() => lockCaseBible(bible({ style: { slate_hex: "#E0D8C8" } }))).toThrow(/slate_hex/);
    expect(() =>
      lockCaseBible(
        bible({
          style: {
            evidence_crimson_hex: "#E4D5C0",
            flow_keyframe_safe_palette: ["#1B1B1D", "#E9E2D2", "#3A4F66"],
          },
        }),
      ),
    ).toThrow(/evidence_crimson_hex/);
  });

  it("rejects evidence crimson inside the flow palette, including a lowercase ban", () => {
    expect(() =>
      lockCaseBible(bible({ style: { flow_keyframe_safe_palette: ["#C92A2A"] } })),
    ).toThrow(/flow_keyframe_safe_palette must exclude evidence crimson/);
    expect(() =>
      lockCaseBible(
        bible({
          style: {
            evidence_crimson_hex: "#B42318",
            flow_keyframe_safe_palette: ["#c92a2a", "#1B1B1D"],
          },
        }),
      ),
    ).toThrow(/exclude evidence crimson/);
  });

  it("rejects a missing palette field instead of filling one in", () => {
    const payload = bible();
    delete (payload.style_dna_json as { paper_bg_hex?: string }).paper_bg_hex;
    expect(() => lockCaseBible(payload)).toThrow(/paper_bg_hex must be a #RRGGBB color/);
  });

  it("rejects an unregistered characterId", () => {
    const theme = lockCaseBible(bible());
    expect(() => theme.character("witness_09")).toThrow(CaseBibleError);
    expect(() => theme.character("witness_09")).toThrow("unregistered characterId: witness_09");
  });

  it("rejects duplicate ids, empty casts, and unexpected fields", () => {
    expect(() =>
      lockCaseBible(
        bible({
          characters: [
            { character_id: "detective_01", prop: "notepad", color_hex: "#1B1B1D" },
            { character_id: "detective_01", prop: "badge", color_hex: "#3A4F66" },
          ],
        }),
      ),
    ).toThrow(/duplicate characterId: detective_01/);
    expect(() => lockCaseBible(bible({ characters: [] }))).toThrow(/at least one character/);
    expect(() => lockCaseBible(bible({ extra: { mood: "noir" } }))).toThrow(/unexpected field mood/);
    expect(() =>
      lockCaseBible(
        bible({
          characters: [{ character_id: "Detective_01", prop: "notepad", color_hex: "#1B1B1D" }],
        }),
      ),
    ).toThrow(/character_id is not a registered id pattern/);
  });
});

describe("useCaseBible render", () => {
  it("throws when the hook is used outside the provider", () => {
    function Probe() {
      useCaseBible();
      return null;
    }
    expect(() => renderToStaticMarkup(createElement(Probe))).toThrow(/useCaseBible\(\) requires CaseBibleProvider/);
  });

  it("rejects a low-contrast character while the provider is rendering", () => {
    const payload = bible({
      characters: [{ character_id: "suspect_01", prop: "coat", color_hex: "#C4A574" }],
    });
    expect(() => renderTheme(createElement(CaseBibleCharacter, { characterId: "suspect_01" }), payload)).toThrow(
      /below 3.5:1/,
    );
  });

  it("throws a render-time error when the character entry is missing", () => {
    expect(() => renderTheme(createElement(CaseBibleCharacter, { characterId: "witness_09" }))).toThrow(
      CaseBibleError,
    );
    expect(() => renderTheme(createElement(CaseBibleCharacter, { characterId: "witness_09" }))).toThrow(
      "unregistered characterId: witness_09",
    );
  });

  it("paints paper and ink from the bible inside SafeZoneLayout", () => {
    endScreenFlags.length = 0;
    const html = renderTheme(
      createElement(
        CaseBibleSafeZone,
        { isEndScreen: true },
        createElement(CaseBibleCharacter, { characterId: "detective_01" }),
        createElement(CaseBibleCharacter, { characterId: "suspect_01" }),
      ),
    );

    expect(endScreenFlags).toContain(true);
    expect(html).toContain('data-safe-zone="task-101"');
    expect(html).toContain('data-paper-bg="#E9E2D2"');
    expect(html).toContain('data-ink="#1B1B1D"');
    expect(html).toContain('data-slate="#3A4F66"');
    expect(html).toContain('data-evidence-crimson="#C92A2A"');
    expect(html).toContain("background-color:#E9E2D2");
    expect(html).toContain("color:#1B1B1D");
    expect(html).toContain('data-character-id="detective_01"');
    expect(html).toContain('data-prop="notepad"');
    expect(html).toContain('data-character-id="suspect_01"');
    expect(html).toContain('data-prop="coat"');
    expect(html).not.toContain("#C4A574");
  });

  it("passes isEndScreen false by default", () => {
    endScreenFlags.length = 0;
    renderTheme(createElement(CaseBibleSafeZone, null, createElement(CaseBibleCharacter, { characterId: "detective_01" })));
    expect(endScreenFlags).toContain(false);
  });

  it("exposes the same locked theme through the hook", () => {
    let seen: LockedCaseBible | undefined;
    function Probe() {
      seen = useCaseBible();
      return null;
    }
    renderTheme(createElement(Probe));
    expect(seen?.paperBgHex).toBe("#E9E2D2");
    expect(seen?.character("suspect_01").prop).toBe("coat");
  });
});

describe("palette drift", () => {
  it("imports SafeZoneLayout from Task 101 and hardcodes no palette hex except the flow crimson ban", () => {
    const source = readFileSync(SOURCE_URL, "utf8");
    expect(source).toMatch(
      /import\s*\{[^}]*\bSafeZoneLayout\b[^}]*\}\s*from\s*["']\.\.\/safe_zone\.tsx["']/,
    );
    const hexes = source.match(/#[0-9A-Fa-f]{6}/g) ?? [];
    expect(hexes.map((hex) => hex.toUpperCase())).toEqual(["#C92A2A"]);
  });
});
