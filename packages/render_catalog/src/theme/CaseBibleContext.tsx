/**
 * Task 102. Distributes a locked v4 CaseBible through React.
 * Colors are copied from the bible passed in. This module does not invent a palette.
 * SafeZoneLayout is the Task 101 frame (1920x1080 @ 30 fps safe zone).
 */
import { createContext, createElement, useContext, useMemo, type ReactNode } from "react";
import { SafeZoneLayout } from "../safe_zone.tsx";

/** WCAG relative-luminance ratio required for ink, slate, crimson, and character props on paper. */
export const CASE_BIBLE_MIN_CONTRAST = 3.5;

/**
 * Contract ban from StyleDna: this crimson is never a Flow keyframe color,
 * even when evidence_crimson_hex is a different red.
 */
const FLOW_CRIMSON_BAN = "#C92A2A";

const CONTRACT_VERSION = "v4";
const BIBLE_FIELDS = ["contract_version", "episode_id", "style_dna_json", "characters_json", "locked_at"];
const STYLE_FIELDS = [
  "evidence_crimson_hex",
  "paper_bg_hex",
  "ink_hex",
  "slate_hex",
  "flow_keyframe_safe_palette",
];
const CHARACTER_FIELDS = ["character_id", "prop", "color_hex"];
const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
const CHARACTER_ID = /^[a-z][a-z0-9_]*$/;
const EPISODE_ID = /^[A-Za-z0-9_-]+$/;

export class CaseBibleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CaseBibleError";
  }
}

export type CharacterProp = {
  readonly characterId: string;
  readonly prop: string;
  readonly colorHex: string;
};

export type LockedCaseBible = {
  readonly contractVersion: typeof CONTRACT_VERSION;
  readonly episodeId: string;
  readonly lockedAt: number;
  readonly evidenceCrimsonHex: string;
  readonly paperBgHex: string;
  readonly inkHex: string;
  readonly slateHex: string;
  readonly flowKeyframeSafePalette: readonly string[];
  readonly characters: readonly CharacterProp[];
  character(characterId: string): CharacterProp;
};

const CaseBibleReactContext = createContext<LockedCaseBible | null>(null);

export function contrastRatio(foregroundHex: string, backgroundHex: string): number {
  const foreground = relativeLuminance(foregroundHex);
  const background = relativeLuminance(backgroundHex);
  const lighter = Math.max(foreground, background);
  const darker = Math.min(foreground, background);
  return (lighter + 0.05) / (darker + 0.05);
}

export function lockCaseBible(input: unknown): LockedCaseBible {
  const bible = asRecord(input, "CaseBible");
  rejectUnknown(bible, BIBLE_FIELDS, "CaseBible");
  if ("contract_version" in bible && bible.contract_version !== CONTRACT_VERSION) {
    throw new CaseBibleError("CaseBible contract_version must be v4");
  }

  const episodeId = requireEpisodeId(bible.episode_id);
  const lockedAt = requireLockedAt(bible.locked_at);
  const style = asRecord(bible.style_dna_json, "style_dna_json");
  rejectUnknown(style, STYLE_FIELDS, "style_dna_json");

  const evidenceCrimsonHex = requireHex(style.evidence_crimson_hex, "evidence_crimson_hex");
  const paperBgHex = requireHex(style.paper_bg_hex, "paper_bg_hex");
  const inkHex = requireHex(style.ink_hex, "ink_hex");
  const slateHex = requireHex(style.slate_hex, "slate_hex");
  const flowKeyframeSafePalette = requireFlowPalette(style.flow_keyframe_safe_palette, evidenceCrimsonHex);

  assertContrast(inkHex, paperBgHex, "ink_hex");
  assertContrast(slateHex, paperBgHex, "slate_hex");
  assertContrast(evidenceCrimsonHex, paperBgHex, "evidence_crimson_hex");

  const characters = requireCharacters(bible.characters_json, paperBgHex);
  const byId = new Map(characters.map((character) => [character.characterId, character]));

  return Object.freeze({
    contractVersion: CONTRACT_VERSION,
    episodeId,
    lockedAt,
    evidenceCrimsonHex,
    paperBgHex,
    inkHex,
    slateHex,
    flowKeyframeSafePalette,
    characters,
    character(characterId: string): CharacterProp {
      if (typeof characterId !== "string" || !byId.has(characterId)) {
        throw new CaseBibleError(`unregistered characterId: ${String(characterId)}`);
      }
      const found = byId.get(characterId);
      if (!found) throw new CaseBibleError(`unregistered characterId: ${characterId}`);
      return found;
    },
  });
}

export function useCaseBible(): LockedCaseBible {
  const theme = useContext(CaseBibleReactContext);
  if (!theme) throw new CaseBibleError("useCaseBible() requires CaseBibleProvider");
  return theme;
}

export function CaseBibleProvider({ bible, children }: { bible: unknown; children: ReactNode }) {
  const theme = useMemo(() => lockCaseBible(bible), [bible]);
  return createElement(CaseBibleReactContext.Provider, { value: theme }, children);
}

export function CaseBibleCharacter({ characterId }: { characterId: string }) {
  const theme = useCaseBible();
  const character = theme.character(characterId);
  return createElement("span", {
    "data-character-id": character.characterId,
    "data-prop": character.prop,
    "data-color": character.colorHex,
    style: { color: character.colorHex },
  });
}

/** Paints the locked paper and ink inside the Task 101 safe-zone frame. */
export function CaseBibleSafeZone({
  isEndScreen = false,
  children,
}: {
  isEndScreen?: boolean;
  children?: ReactNode;
}) {
  const theme = useCaseBible();
  return createElement(
    SafeZoneLayout,
    { isEndScreen },
    createElement(
      "div",
      {
        "data-tc-theme": "case-bible",
        "data-paper-bg": theme.paperBgHex,
        "data-ink": theme.inkHex,
        "data-slate": theme.slateHex,
        "data-evidence-crimson": theme.evidenceCrimsonHex,
        style: { backgroundColor: theme.paperBgHex, color: theme.inkHex },
      },
      children,
    ),
  );
}

function assertContrast(foreground: string, background: string, label: string): void {
  const ratio = contrastRatio(foreground, background);
  if (ratio < CASE_BIBLE_MIN_CONTRAST) {
    throw new CaseBibleError(
      `contrast ${ratio.toFixed(2)}:1 for ${label} (${foreground} on ${background}) is below ${CASE_BIBLE_MIN_CONTRAST}:1`,
    );
  }
}

function requireCharacters(value: unknown, paperBgHex: string): readonly CharacterProp[] {
  if (!Array.isArray(value) || value.length < 1) {
    throw new CaseBibleError("CaseBible requires at least one character");
  }
  const seen = new Set<string>();
  const characters = value.map((entry, index) => {
    const record = asRecord(entry, `characters_json[${index}]`);
    rejectUnknown(record, CHARACTER_FIELDS, `characters_json[${index}]`);
    const characterId = requireCharacterId(record.character_id, index);
    if (seen.has(characterId)) throw new CaseBibleError(`duplicate characterId: ${characterId}`);
    seen.add(characterId);
    const prop = requireProp(record.prop, index);
    const colorHex = requireHex(record.color_hex, `characters_json[${index}].color_hex`);
    assertContrast(colorHex, paperBgHex, `characterId ${characterId}`);
    return Object.freeze({ characterId, prop, colorHex });
  });
  return Object.freeze(characters);
}

/** Flow keyframe swatches are not Remotion text, so they are not contrast-checked against paper. */
function requireFlowPalette(value: unknown, evidenceCrimsonHex: string): readonly string[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > 8) {
    throw new CaseBibleError("flow_keyframe_safe_palette must contain 1 to 8 hex colors");
  }
  const banned = new Set([normalizeHex(evidenceCrimsonHex), normalizeHex(FLOW_CRIMSON_BAN)]);
  const colors = value.map((color, index) => {
    const hex = requireHex(color, `flow_keyframe_safe_palette[${index}]`);
    if (banned.has(normalizeHex(hex))) {
      throw new CaseBibleError("flow_keyframe_safe_palette must exclude evidence crimson");
    }
    return hex;
  });
  return Object.freeze(colors);
}

function requireEpisodeId(value: unknown): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 128 || !EPISODE_ID.test(value)) {
    throw new CaseBibleError("episode_id must be a 1-128 character id");
  }
  return value;
}

function requireLockedAt(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new CaseBibleError("locked_at must be an integer >= 0");
  }
  return value;
}

function requireCharacterId(value: unknown, index: number): string {
  if (typeof value !== "string" || value.length > 64 || !CHARACTER_ID.test(value)) {
    throw new CaseBibleError(`characters_json[${index}].character_id is not a registered id pattern`);
  }
  return value;
}

function requireProp(value: unknown, index: number): string {
  if (typeof value !== "string" || value.length < 1 || value.length > 80) {
    throw new CaseBibleError(`characters_json[${index}].prop must be 1-80 characters`);
  }
  return value;
}

function requireHex(value: unknown, label: string): string {
  if (typeof value !== "string" || !HEX_COLOR.test(value)) {
    throw new CaseBibleError(`${label} must be a #RRGGBB color from the CaseBible`);
  }
  return value;
}

function normalizeHex(hex: string): string {
  return hex.toUpperCase();
}

function relativeLuminance(hex: string): number {
  const [red, green, blue] = parseRgb(hex);
  return 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue);
}

function parseRgb(hex: string): [number, number, number] {
  const matched = requireHex(hex, "color");
  return [
    Number.parseInt(matched.slice(1, 3), 16),
    Number.parseInt(matched.slice(3, 5), 16),
    Number.parseInt(matched.slice(5, 7), 16),
  ];
}

function linearize(channel: number): number {
  const srgb = channel / 255;
  return srgb <= 0.04045 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
}

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CaseBibleError(`${label} must be an object`);
  }
  return value as Record<string, unknown>;
}

function rejectUnknown(record: Record<string, unknown>, allowed: readonly string[], label: string): void {
  for (const key of Object.keys(record)) {
    if (!allowed.includes(key)) throw new CaseBibleError(`${label} has an unexpected field ${key}`);
  }
}
