/**
 * Promote recurring CustomDiagramScene tags into new catalog motifs.
 *
 * A tag that appears on at least three distinct scenes is scaffolded as a Zod
 * schema plus a React motif template. Motifs #1–#12 from
 * `schema/pipeline.sql` `motif_registry` and `code-animation-catalog.md` are
 * refused before any file is written. Promoted numbers start at 13.
 *
 * Tasks 127 and 128 own CustomDiagramScene and BatchCompiler. This module does
 * not import those files. It does not call a provider or open a socket.
 */

declare const process: {
  getBuiltinModule(id: string): unknown;
};

type FsPromises = {
  mkdir(path: string, options: { recursive: boolean }): Promise<void>;
  writeFile(path: string, data: string, options?: { flag?: string }): Promise<void>;
  readFile(path: string, encoding: "utf8"): Promise<string>;
  unlink(path: string): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  stat(path: string): Promise<{ isDirectory(): boolean }>;
};

type FsModule = { promises: FsPromises };

type PathModule = {
  join(...parts: string[]): string;
  resolve(...parts: string[]): string;
  basename(file: string): string;
  relative(from: string, to: string): string;
  isAbsolute(file: string): boolean;
};

export const PROMOTION_MIN_OCCURRENCES = 3;
export const FIRST_PROMOTED_MOTIF_NUMBER = 13;
export const PROMOTED_MOTIF_REGISTRY_FILENAME = "promoted_motif_registry.json";
export const PROMOTED_REGISTRY_SCHEMA = "promoted_motif_registry.v1";

/**
 * Authoritative render_catalog motifs #1–#12. Order matches
 * `schema/pipeline.sql` `motif_registry` and `code-animation-catalog.md`.
 * `Illustrative2KPanZoom` and `HeroVideoBridge` are registry rows owned by
 * other packages, so they are not part of this twelve.
 */
export const CATALOG_MOTIFS_1_TO_12 = [
  "StickmanStage",
  "AudioEvidenceCard",
  "RedactedDocReveal",
  "FoiaFootageFrame",
  "TimelineScrubber",
  "AnimatedMapRoute",
  "CellTowerTriangulation",
  "SplitScreenComparison",
  "CaseBoardSpine",
  "QuotePullout",
  "EvidenceGridMatrix",
  "ChapterSlateTransition",
] as const;

export type CatalogMotif = (typeof CATALOG_MOTIFS_1_TO_12)[number];
export type ReservedReason = "catalog_12" | "registry" | "alias" | "escape_hatch";
export type OwnerPackage = "render_catalog" | "crime_scene_2k" | "flow_adapter";

export type ReservedMotif = {
  motif_component: string;
  motif_number: number | null;
  reason: ReservedReason;
  owner_package: OwnerPackage;
};

/**
 * Names that must not be scaffolded. Catalog #1–#12, the other frozen registry
 * rows, the Layer 4 escape hatch, and component names later tasks already use
 * for those motif numbers (`SmsPhoneThread`, `MapRouteTrace`,
 * `TimelineDateScrubber`, `AlibiSplitScreen`, `EvidenceMatchCard`).
 */
const ALIAS_MOTIFS = [
  "SmsPhoneThread",
  "MapRouteTrace",
  "TimelineDateScrubber",
  "AlibiSplitScreen",
  "EvidenceMatchCard",
] as const;

export const RESERVED_MOTIFS: readonly ReservedMotif[] = [
  ...CATALOG_MOTIFS_1_TO_12.map((motif_component, index) => ({
    motif_component,
    motif_number: index + 1,
    reason: "catalog_12" as const,
    owner_package: "render_catalog" as const,
  })),
  {
    motif_component: "Illustrative2KPanZoom",
    motif_number: null,
    reason: "registry" as const,
    owner_package: "crime_scene_2k" as const,
  },
  {
    motif_component: "HeroVideoBridge",
    motif_number: null,
    reason: "registry" as const,
    owner_package: "flow_adapter" as const,
  },
  {
    motif_component: "CustomDiagramScene",
    motif_number: null,
    reason: "escape_hatch" as const,
    owner_package: "render_catalog" as const,
  },
  ...ALIAS_MOTIFS.map((motif_component) => ({
    motif_component,
    motif_number: null,
    reason: "alias" as const,
    owner_package: "render_catalog" as const,
  })),
];

const RESERVED_BY_LOWER = new Map(RESERVED_MOTIFS.map((entry) => [entry.motif_component.toLowerCase(), entry]));
const RESERVED_BY_COMPRESSED = new Map(
  RESERVED_MOTIFS.map((entry) => [entry.motif_component.toLowerCase().replace(/[_-]/g, ""), entry]),
);

const BANNED_SOURCE = ["feTurbulence", "feDisplacementMap", "dangerouslySetInnerHTML", "eval(", "new Function", "<script"] as const;
const SCENE_ID = /^[A-Za-z0-9_-]{1,128}$/;
const COMPONENT_NAME = /^[A-Z][A-Za-z0-9]+$/;
const TAG_CHARS = /^[A-Za-z][A-Za-z0-9_-]*$/;

export class PromoteDiagramError extends Error {
  readonly code: string;
  readonly reserved_motif: string | null;
  readonly motif_number: number | null;

  constructor(
    code: string,
    message: string,
    details?: { reserved_motif: string | null; motif_number: number | null },
  ) {
    super(message);
    this.name = "PromoteDiagramError";
    this.code = code;
    this.reserved_motif = details?.reserved_motif ?? null;
    this.motif_number = details?.motif_number ?? null;
  }
}

export type DiagramOccurrence = {
  scene_id: string;
  diagram_tag: string;
  motif_component?: string;
};

export type TagCount = {
  diagram_tag: string;
  occurrence_count: number;
  scene_ids: string[];
};

export type PlannedMotif = TagCount & {
  motif_component: string;
  motif_number: number;
};

export type PromotionPlan = {
  promoted: PlannedMotif[];
  already_registered: PlannedMotif[];
  below_threshold: TagCount[];
};

export type TakenMotif = {
  motif_component: string;
  motif_number: number;
  diagram_tag: string;
};

export type RegistryMotif = {
  motif_component: string;
  motif_number: number;
  diagram_tag: string;
  occurrence_count: number;
  scene_ids: string[];
  owner_package: "render_catalog";
  is_mvp_4: false;
  catalog_12: false;
};

export type PromotedMotifRegistry = {
  schema: typeof PROMOTED_REGISTRY_SCHEMA;
  owner_package: "render_catalog";
  first_motif_number: typeof FIRST_PROMOTED_MOTIF_NUMBER;
  reserved_catalog_12: CatalogMotif[];
  motifs: RegistryMotif[];
};

export type PromoteDiagramsInput = {
  outDir: string;
  occurrences?: readonly DiagramOccurrence[];
  document?: unknown;
};

export type PromoteDiagramsResult = PromotionPlan & {
  files_written: string[];
};

type Group = {
  key: string;
  diagram_tag: string;
  motif_component: string;
  reserved: ReservedMotif | null;
  scene_ids: Set<string>;
};

function fail(
  code: string,
  message: string,
  details?: { reserved_motif: string | null; motif_number: number | null },
): never {
  throw new PromoteDiagramError(code, message, details);
}

function nodeBuiltin<T>(id: string): T {
  const loaded = process.getBuiltinModule(id);
  if (!loaded || typeof loaded !== "object") fail("BAD_OUTPUT", `BAD_OUTPUT: node builtin ${id} is unavailable`);
  return loaded as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function reservedMotifFor(tag: string): ReservedMotif | null {
  const lower = tag.trim().toLowerCase();
  const direct = RESERVED_BY_LOWER.get(lower);
  if (direct) return direct;
  return RESERVED_BY_COMPRESSED.get(lower.replace(/[_-]/g, "")) ?? null;
}

function wordsFromTag(tag: string): string[] {
  const words: string[] = [];
  for (const segment of tag.split(/[_-]+/)) {
    if (segment.length === 0) continue;
    const parts = segment
      .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
      .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
      .split(" ");
    for (const part of parts) {
      if (part.length > 0) words.push(part.toLowerCase());
    }
  }
  if (words.length === 0 || words.some((word) => !/^[a-z][a-z0-9]*$/.test(word))) {
    fail("BAD_TAG", `BAD_TAG: ${JSON.stringify(tag)} cannot become a motif component`);
  }
  return words;
}

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function identifyTag(tag: string): Group {
  const trimmed = tag.trim();
  if (!TAG_CHARS.test(trimmed) || trimmed.length > 64) {
    fail("BAD_TAG", `BAD_TAG: ${JSON.stringify(tag)} is not a diagram tag`);
  }
  const reserved = reservedMotifFor(trimmed);
  if (reserved) {
    return {
      key: `reserved:${reserved.motif_component}`,
      diagram_tag: reserved.motif_component,
      motif_component: reserved.motif_component,
      reserved,
      scene_ids: new Set(),
    };
  }
  const words = wordsFromTag(trimmed);
  const motif_component = words.map(capitalize).join("");
  if (!COMPONENT_NAME.test(motif_component) || motif_component.length > 64) {
    fail("BAD_TAG", `BAD_TAG: ${JSON.stringify(tag)} cannot become a motif component`);
  }
  const derivedReserved = reservedMotifFor(motif_component);
  if (derivedReserved) {
    return {
      key: `reserved:${derivedReserved.motif_component}`,
      diagram_tag: derivedReserved.motif_component,
      motif_component: derivedReserved.motif_component,
      reserved: derivedReserved,
      scene_ids: new Set(),
    };
  }
  const diagram_tag = words.join("_");
  return {
    key: `fresh:${diagram_tag}`,
    diagram_tag,
    motif_component,
    reserved: null,
    scene_ids: new Set(),
  };
}

function readSceneId(value: unknown): string {
  if (typeof value !== "string") fail("BAD_OCCURRENCE", "BAD_OCCURRENCE: scene_id is required");
  const sceneId = value.trim();
  if (!SCENE_ID.test(sceneId)) fail("BAD_OCCURRENCE", `BAD_OCCURRENCE: scene_id ${JSON.stringify(value)} is invalid`);
  return sceneId;
}

function groupOccurrences(occurrences: readonly DiagramOccurrence[]): Group[] {
  const groups = new Map<string, Group>();
  for (const occurrence of occurrences) {
    if (occurrence.motif_component !== undefined) {
      if (typeof occurrence.motif_component !== "string" || occurrence.motif_component.trim() === "") {
        fail("BAD_OCCURRENCE", "BAD_OCCURRENCE: motif_component is invalid");
      }
      if (occurrence.motif_component !== "CustomDiagramScene") continue;
    }
    if (typeof occurrence.diagram_tag !== "string") fail("BAD_OCCURRENCE", "BAD_OCCURRENCE: diagram_tag is required");
    const sceneId = readSceneId(occurrence.scene_id);
    const identified = identifyTag(occurrence.diagram_tag);
    const existing = groups.get(identified.key);
    if (existing) existing.scene_ids.add(sceneId);
    else {
      identified.scene_ids.add(sceneId);
      groups.set(identified.key, identified);
    }
  }
  return [...groups.values()];
}

function sortedScenes(sceneIds: Set<string>): string[] {
  return [...sceneIds].sort((left, right) => left.localeCompare(right));
}

function throwReserved(groups: readonly Group[]): never {
  const sorted = [...groups].sort((left, right) => {
    const leftNumber = left.reserved?.motif_number ?? 999;
    const rightNumber = right.reserved?.motif_number ?? 999;
    if (leftNumber !== rightNumber) return leftNumber - rightNumber;
    return (left.reserved?.motif_component ?? "").localeCompare(right.reserved?.motif_component ?? "");
  });
  const first = sorted[0]?.reserved;
  if (!first) fail("RESERVED_MOTIF", "RESERVED_MOTIF: reserved motif collision before any file was written");
  const names = [...new Set(sorted.map((group) => group.reserved?.motif_component ?? ""))].filter((name) => name.length > 0);
  const place = first.motif_number === null ? "a reserved motif name" : `motif #${first.motif_number}`;
  const owner = first.reason === "registry" ? ` (${first.owner_package})` : "";
  fail(
    "RESERVED_MOTIF",
    `RESERVED_MOTIF: ${names.join(", ")} collided with ${place} before any file was written${owner}`,
    { reserved_motif: first.motif_component, motif_number: first.motif_number },
  );
}

function assertTaken(taken: readonly TakenMotif[]): void {
  const names = new Set<string>();
  const numbers = new Set<number>();
  const tags = new Set<string>();
  for (const entry of taken) {
    if (!COMPONENT_NAME.test(entry.motif_component) || reservedMotifFor(entry.motif_component)) {
      fail("BAD_REGISTRY", `BAD_REGISTRY: ${entry.motif_component} collides with the reserved motif registry`);
    }
    if (!Number.isInteger(entry.motif_number) || entry.motif_number < FIRST_PROMOTED_MOTIF_NUMBER) {
      fail("BAD_REGISTRY", `BAD_REGISTRY: motif_number ${String(entry.motif_number)} is inside motifs #1-#12`);
    }
    if (names.has(entry.motif_component) || numbers.has(entry.motif_number) || tags.has(entry.diagram_tag)) {
      fail("BAD_REGISTRY", `BAD_REGISTRY: duplicate motif ${entry.motif_component}`);
    }
    names.add(entry.motif_component);
    numbers.add(entry.motif_number);
    tags.add(entry.diagram_tag);
  }
}

export function planDiagramPromotions(
  occurrences: readonly DiagramOccurrence[],
  taken: readonly TakenMotif[] = [],
): PromotionPlan {
  assertTaken(taken);
  const groups = groupOccurrences(occurrences);
  const ready = groups.filter((group) => group.scene_ids.size >= PROMOTION_MIN_OCCURRENCES);
  const reservedReady = ready.filter((group) => group.reserved);
  if (reservedReady.length > 0) throwReserved(reservedReady);

  const takenByComponent = new Map(taken.map((entry) => [entry.motif_component, entry]));
  const takenByTag = new Map(taken.map((entry) => [entry.diagram_tag, entry]));
  const promoted: Group[] = [];
  const already: PlannedMotif[] = [];

  for (const group of ready) {
    const byComponent = takenByComponent.get(group.motif_component);
    const byTag = takenByTag.get(group.diagram_tag);
    if (byComponent && byTag && byComponent === byTag) {
      const scene_ids = sortedScenes(group.scene_ids);
      already.push({
        diagram_tag: byComponent.diagram_tag,
        motif_component: byComponent.motif_component,
        motif_number: byComponent.motif_number,
        occurrence_count: scene_ids.length,
        scene_ids,
      });
      continue;
    }
    if (byComponent || byTag) {
      const owner = byComponent ?? byTag;
      fail(
        "DUPLICATE_COMPONENT",
        `DUPLICATE_COMPONENT: ${group.motif_component} is already registered to ${owner?.diagram_tag ?? group.diagram_tag}`,
      );
    }
    promoted.push(group);
  }

  const seen = new Set<string>();
  for (const group of promoted) {
    if (seen.has(group.motif_component)) {
      fail("DUPLICATE_COMPONENT", `DUPLICATE_COMPONENT: ${group.motif_component} was derived twice`);
    }
    seen.add(group.motif_component);
  }

  let nextNumber = FIRST_PROMOTED_MOTIF_NUMBER;
  for (const entry of taken) nextNumber = Math.max(nextNumber, entry.motif_number + 1);
  const fresh = [...promoted].sort((left, right) => left.diagram_tag.localeCompare(right.diagram_tag));
  const planned: PlannedMotif[] = fresh.map((group) => {
    const scene_ids = sortedScenes(group.scene_ids);
    const motif: PlannedMotif = {
      diagram_tag: group.diagram_tag,
      motif_component: group.motif_component,
      motif_number: nextNumber,
      occurrence_count: scene_ids.length,
      scene_ids,
    };
    nextNumber += 1;
    return motif;
  });

  const below_threshold = groups
    .filter((group) => group.scene_ids.size < PROMOTION_MIN_OCCURRENCES)
    .map((group) => {
      const scene_ids = sortedScenes(group.scene_ids);
      return { diagram_tag: group.diagram_tag, occurrence_count: scene_ids.length, scene_ids };
    })
    .sort((left, right) => left.diagram_tag.localeCompare(right.diagram_tag));

  return {
    promoted: planned,
    already_registered: already.sort((left, right) => left.motif_number - right.motif_number),
    below_threshold,
  };
}

function assertClean(source: string): void {
  for (const token of BANNED_SOURCE) {
    if (source.includes(token)) fail("BAD_OUTPUT", `BAD_OUTPUT: scaffold contains ${token}`);
  }
}

export function renderMotifSource(motif: PlannedMotif): string {
  if (!Number.isInteger(motif.motif_number) || motif.motif_number < FIRST_PROMOTED_MOTIF_NUMBER) {
    fail("RESERVED_MOTIF", `RESERVED_MOTIF: motif #${String(motif.motif_number)} is reserved`, {
      reserved_motif: motif.motif_component,
      motif_number: motif.motif_number,
    });
  }
  const reserved = reservedMotifFor(motif.motif_component);
  if (reserved) {
    const place = reserved.motif_number === null ? "a reserved motif name" : `motif #${reserved.motif_number}`;
    fail("RESERVED_MOTIF", `RESERVED_MOTIF: ${reserved.motif_component} collided with ${place} before any file was written`, {
      reserved_motif: reserved.motif_component,
      motif_number: reserved.motif_number,
    });
  }
  if (!COMPONENT_NAME.test(motif.motif_component)) {
    fail("BAD_TAG", `BAD_TAG: ${motif.motif_component} cannot become a motif component`);
  }
  const name = motif.motif_component;
  const tag = JSON.stringify(motif.diagram_tag);
  const scenes = motif.scene_ids.map((sceneId) => JSON.stringify(sceneId)).join(", ");
  const source = `/**
 * Promoted render_catalog motif #${motif.motif_number} (${name}).
 * Scaffolded from recurring CustomDiagramScene tag ${tag} (${motif.occurrence_count} distinct scenes).
 * Motifs #1-#12 stay reserved. This component is outside that catalog.
 * Labels render as React text children. SVG turbulence filters are not used.
 */
import type { ReactNode } from "react";
import { z } from "zod";

export const MOTIF_NUMBER = ${motif.motif_number} as const;
export const MOTIF_COMPONENT = ${JSON.stringify(name)} as const;
export const SOURCE_DIAGRAM_TAG = ${tag} as const;
export const SOURCE_SCENE_IDS = [${scenes}] as const;

export const MOTIF_REGISTRY_ENTRY = {
  motif_component: MOTIF_COMPONENT,
  motif_number: MOTIF_NUMBER,
  owner_package: "render_catalog",
  is_mvp_4: false,
  catalog_12: false,
  diagram_tag: SOURCE_DIAGRAM_TAG,
} as const;

export const ${name}Schema = z
  .object({
    motif_component: z.literal(MOTIF_COMPONENT),
    motif_number: z.literal(MOTIF_NUMBER),
    diagram_tag: z.literal(SOURCE_DIAGRAM_TAG),
    title: z.string().min(1).max(80),
    labels: z.array(z.string().min(1).max(80)).max(12),
  })
  .strict();

export type ${name}Props = z.infer<typeof ${name}Schema>;

function wordCount(label: string): number {
  return label.trim().split(/\\s+/).filter(Boolean).length;
}

function SafeZoneLayout(props: { children: ReactNode }) {
  return (
    <div
      data-safe-zone="true"
      style={{
        width: 1920,
        height: 1080,
        boxSizing: "border-box",
        paddingTop: 108,
        paddingBottom: 194,
        overflow: "hidden",
      }}
    >
      {props.children}
    </div>
  );
}

export function ${name}(raw: ${name}Props) {
  const props = ${name}Schema.parse(raw);
  for (const label of [props.title, ...props.labels]) {
    if (wordCount(label) > 12) throw new Error("RULE_07: label exceeds 12 words");
  }
  return (
    <SafeZoneLayout>
      <article
        data-motif-component={MOTIF_COMPONENT}
        data-motif-number={MOTIF_NUMBER}
        data-diagram-tag={SOURCE_DIAGRAM_TAG}
      >
        <h1>{props.title}</h1>
        <ul>
          {props.labels.map((label, index) => (
            <li key={index}>{label}</li>
          ))}
        </ul>
      </article>
    </SafeZoneLayout>
  );
}
`;
  assertClean(source);
  return source;
}

function readTag(value: Record<string, unknown>): string | null {
  if (typeof value.diagram_tag === "string" && value.diagram_tag.trim() !== "") return value.diagram_tag.trim();
  if (typeof value.tag === "string" && value.tag.trim() !== "") return value.tag.trim();
  if (isRecord(value.diagram) && typeof value.diagram.tag === "string" && value.diagram.tag.trim() !== "") {
    return value.diagram.tag.trim();
  }
  return null;
}

function walkDocument(value: unknown, sceneId: string | null, found: DiagramOccurrence[], seen: WeakSet<object>): void {
  if (!value || typeof value !== "object") return;
  if (seen.has(value)) return;
  seen.add(value);
  if (Array.isArray(value)) {
    for (const item of value) walkDocument(item, sceneId, found, seen);
    return;
  }
  if (!isRecord(value)) return;
  const nextScene = typeof value.scene_id === "string" ? value.scene_id : sceneId;
  if (value.motif_component === "CustomDiagramScene") {
    const tag = readTag(value);
    if (tag !== null) {
      if (nextScene === null || nextScene.trim() === "") {
        fail("BAD_OCCURRENCE", "BAD_OCCURRENCE: CustomDiagramScene tag is missing scene_id");
      }
      found.push({ scene_id: nextScene.trim(), diagram_tag: tag, motif_component: "CustomDiagramScene" });
    }
  }
  for (const child of Object.values(value)) walkDocument(child, nextScene, found, seen);
}

export function collectCustomDiagramOccurrences(root: unknown): DiagramOccurrence[] {
  const found: DiagramOccurrence[] = [];
  walkDocument(root, null, found, new WeakSet());
  return found;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) fail("BAD_REGISTRY", `BAD_REGISTRY: ${label} must be a string array`);
  const sceneIds: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") fail("BAD_REGISTRY", `BAD_REGISTRY: ${label} must be a string array`);
    const sceneId = item.trim();
    if (!SCENE_ID.test(sceneId)) fail("BAD_REGISTRY", `BAD_REGISTRY: ${label} has an invalid scene id`);
    sceneIds.push(sceneId);
  }
  if (new Set(sceneIds).size !== sceneIds.length) fail("BAD_REGISTRY", `BAD_REGISTRY: ${label} has duplicate scene ids`);
  return sceneIds;
}

export function parsePromotedRegistry(text: string): PromotedMotifRegistry {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    fail("BAD_REGISTRY", "BAD_REGISTRY: promoted registry is not JSON");
  }
  if (!isRecord(parsed)) fail("BAD_REGISTRY", "BAD_REGISTRY: promoted registry must be an object");
  if (parsed.schema !== PROMOTED_REGISTRY_SCHEMA) fail("BAD_REGISTRY", "BAD_REGISTRY: unexpected registry schema");
  if (parsed.owner_package !== "render_catalog") fail("BAD_REGISTRY", "BAD_REGISTRY: owner_package must be render_catalog");
  if (parsed.first_motif_number !== FIRST_PROMOTED_MOTIF_NUMBER) {
    fail("BAD_REGISTRY", "BAD_REGISTRY: first_motif_number must be 13");
  }
  if (!Array.isArray(parsed.motifs)) fail("BAD_REGISTRY", "BAD_REGISTRY: motifs must be an array");
  const motifs: RegistryMotif[] = [];
  for (const item of parsed.motifs) {
    if (!isRecord(item)) fail("BAD_REGISTRY", "BAD_REGISTRY: motif entry must be an object");
    if (typeof item.motif_component !== "string" || typeof item.diagram_tag !== "string") {
      fail("BAD_REGISTRY", "BAD_REGISTRY: motif_component and diagram_tag are required");
    }
    if (typeof item.motif_number !== "number" || typeof item.occurrence_count !== "number") {
      fail("BAD_REGISTRY", "BAD_REGISTRY: motif_number and occurrence_count are required");
    }
    if (item.owner_package !== "render_catalog" || item.is_mvp_4 !== false || item.catalog_12 !== false) {
      fail("BAD_REGISTRY", `BAD_REGISTRY: ${item.motif_component} is not a promoted render_catalog motif`);
    }
    const scene_ids = stringArray(item.scene_ids, item.motif_component);
    if (item.occurrence_count !== scene_ids.length || item.occurrence_count < PROMOTION_MIN_OCCURRENCES) {
      fail("BAD_REGISTRY", `BAD_REGISTRY: ${item.motif_component} occurrence_count does not match its scenes`);
    }
    motifs.push({
      motif_component: item.motif_component,
      motif_number: item.motif_number,
      diagram_tag: item.diagram_tag,
      occurrence_count: item.occurrence_count,
      scene_ids,
      owner_package: "render_catalog",
      is_mvp_4: false,
      catalog_12: false,
    });
  }
  assertTaken(motifs);
  return {
    schema: PROMOTED_REGISTRY_SCHEMA,
    owner_package: "render_catalog",
    first_motif_number: FIRST_PROMOTED_MOTIF_NUMBER,
    reserved_catalog_12: [...CATALOG_MOTIFS_1_TO_12],
    motifs,
  };
}

function mergeRegistry(existing: PromotedMotifRegistry | null, promoted: readonly PlannedMotif[]): PromotedMotifRegistry {
  const added: RegistryMotif[] = promoted.map((motif) => ({
    motif_component: motif.motif_component,
    motif_number: motif.motif_number,
    diagram_tag: motif.diagram_tag,
    occurrence_count: motif.occurrence_count,
    scene_ids: [...motif.scene_ids],
    owner_package: "render_catalog",
    is_mvp_4: false,
    catalog_12: false,
  }));
  return {
    schema: PROMOTED_REGISTRY_SCHEMA,
    owner_package: "render_catalog",
    first_motif_number: FIRST_PROMOTED_MOTIF_NUMBER,
    reserved_catalog_12: [...CATALOG_MOTIFS_1_TO_12],
    motifs: [...(existing?.motifs ?? []), ...added].sort((left, right) => left.motif_number - right.motif_number),
  };
}

function absoluteOutDir(outDir: string): string {
  if (typeof outDir !== "string" || outDir.trim() === "") fail("BAD_OUTPUT", "BAD_OUTPUT: outDir is required");
  return nodeBuiltin<PathModule>("node:path").resolve(outDir);
}

function safeJoin(path: PathModule, outDir: string, name: string): string {
  if (name !== path.basename(name) || name.includes("..") || name.includes("/") || name.includes("\\")) {
    fail("BAD_OUTPUT", "BAD_OUTPUT: refusing a path outside outDir");
  }
  const filePath = path.join(outDir, name);
  const relative = path.relative(outDir, filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    fail("BAD_OUTPUT", "BAD_OUTPUT: refusing a path outside outDir");
  }
  return filePath;
}

async function readIfExists(fs: FsPromises, file: string): Promise<string | null> {
  try {
    return await fs.readFile(file, "utf8");
  } catch {
    return null;
  }
}

async function directoryStatus(fs: FsPromises, dir: string): Promise<"missing" | "dir" | "file"> {
  try {
    const info = await fs.stat(dir);
    return info.isDirectory() ? "dir" : "file";
  } catch {
    return "missing";
  }
}

async function unlinkQuiet(fs: FsPromises, file: string): Promise<void> {
  try {
    await fs.unlink(file);
  } catch {
    /* The partial scaffold is already gone, or it was never created. */
  }
}

function gatherOccurrences(input: PromoteDiagramsInput): DiagramOccurrence[] {
  const listed = input.occurrences ?? [];
  const discovered = input.document === undefined ? [] : collectCustomDiagramOccurrences(input.document);
  return [...listed, ...discovered];
}

export async function promoteDiagrams(input: PromoteDiagramsInput): Promise<PromoteDiagramsResult> {
  const outDir = absoluteOutDir(input.outDir);
  const occurrences = gatherOccurrences(input);
  const fs = nodeBuiltin<FsModule>("node:fs").promises;
  const path = nodeBuiltin<PathModule>("node:path");
  const status = await directoryStatus(fs, outDir);
  if (status === "file") fail("BAD_OUTPUT", "BAD_OUTPUT: outDir is not a directory");

  const registryPath = safeJoin(path, outDir, PROMOTED_MOTIF_REGISTRY_FILENAME);
  let existing: PromotedMotifRegistry | null = null;
  if (status === "dir") {
    const raw = await readIfExists(fs, registryPath);
    if (raw !== null) existing = parsePromotedRegistry(raw);
  }
  const taken = existing?.motifs ?? [];
  const plan = planDiagramPromotions(occurrences, taken);
  if (plan.promoted.length === 0) {
    return { ...plan, files_written: [] };
  }

  const files = plan.promoted.map((motif) => ({
    motif,
    filePath: safeJoin(path, outDir, `${motif.motif_component}.tsx`),
    source: renderMotifSource(motif),
  }));
  for (const file of files) {
    if ((await readIfExists(fs, file.filePath)) !== null) {
      fail("EXISTS", `EXISTS: ${file.motif.motif_component}.tsx already exists`);
    }
  }

  if (status === "missing") await fs.mkdir(outDir, { recursive: true });
  const written: string[] = [];
  const tmpRegistry = safeJoin(path, outDir, `.${PROMOTED_MOTIF_REGISTRY_FILENAME}.tmp`);
  await unlinkQuiet(fs, tmpRegistry);
  try {
    for (const file of files) {
      await fs.writeFile(file.filePath, file.source, { flag: "wx" });
      written.push(file.filePath);
    }
    const body = `${JSON.stringify(mergeRegistry(existing, plan.promoted), null, 2)}\n`;
    await fs.writeFile(tmpRegistry, body, { flag: "wx" });
    await fs.rename(tmpRegistry, registryPath);
    return { ...plan, files_written: [...written, registryPath] };
  } catch (error) {
    for (const file of written) await unlinkQuiet(fs, file);
    await unlinkQuiet(fs, tmpRegistry);
    throw error;
  }
}
