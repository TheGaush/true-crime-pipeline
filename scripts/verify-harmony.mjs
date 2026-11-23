#!/usr/bin/env node
/**
 * Day-1 harmony gate (Task 001).
 *
 *   node scripts/verify-harmony.mjs --task 001
 *   node scripts/verify-harmony.mjs --wave W1-A
 *   node scripts/verify-harmony.mjs --self-test
 *
 * Checks disjoint Part 1 / Part 2 ownership, wave order, v4 contract drift,
 * secrets, unconfigured model literals, schema tests, and diagram merge.
 * Child commands run with provider API keys removed.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");

const PROVIDER_ENV_KEYS = [
  "GEMINI_API_KEY",
  "DEEPSEEK_API_KEY",
  "ELEVENLABS_API_KEY",
  "GOOGLE_API_KEY",
  "GOOGLE_GENAI_API_KEY",
  "VERTEX_API_KEY",
  "VERTEXAI_API_KEY",
  "OPENAI_API_KEY",
];

const PART1_ROOTS = [
  "packages/db/",
  "packages/agent1_scout/",
  "packages/agent2_evidence/",
  "packages/agent3_gatekeeper/",
  "packages/voice_sync/",
  "packages/agent4_director/",
  "packages/orchestrator/",
];

const PART2_ROOTS = [
  "packages/render_catalog/",
  "packages/python_motion/",
  "packages/crime_scene_2k/",
  "packages/flow_adapter/",
  "packages/agent6_mastering/",
  "packages/analytics_feedback/",
  "apps/batch_desk_ui/",
];

const JOINT_M0 = [
  "schema/",
  "providers.yaml",
  "craft_rubric.yaml",
  "packages/shared_contracts/",
  "packages/shared-contracts-ts/",
  "scripts/agent-worktree.mjs",
  "scripts/verify-harmony.mjs",
];

// Task 001's pytest guard and the pnpm lockfile sit beside the named root files.
const TASK001_EXTRA = new Set(["conftest.py", "pnpm-lock.yaml"]);

const RETIRED = [
  "FRAMES" + "_MOTION_ONLY",
  "VEO" + "_3_1_LITE",
  "Veo 3.1" + " Lite",
  "veo-3.1" + "-lite",
  "CrimeScene" + "PanZoom",
];

const MODEL_RE =
  /\b(?:gemini-[A-Za-z0-9][A-Za-z0-9._-]*|DeepSeek-[A-Za-z0-9][A-Za-z0-9._-]*|whisperx-[A-Za-z0-9-]+|flash-lite-tts|veo-[A-Za-z0-9.-]+|gpt-[A-Za-z0-9.-]+|claude-[A-Za-z0-9.-]+)\b/g;

const SKIP_DIRS = new Set([
  ".git",
  "node_modules",
  ".venv",
  "venv",
  "artifacts",
  "ready_to_upload",
  "__pycache__",
  ".pytest_cache",
  "dist",
  "coverage",
]);

function range(start, end) {
  const out = [];
  for (let n = start; n <= end; n += 1) out.push(n);
  return out;
}

export const WAVES = [
  {
    id: "W1-A",
    track: "part1",
    branch: "integration/part1",
    tag: "p1-w1",
    prevTag: null,
    tasks: range(5, 14),
    commands: [
      ["uv", "run", "pytest", "packages/db"],
      ["node", "schema/schema-test.js"],
    ],
  },
  {
    id: "W2-A",
    track: "part1",
    branch: "integration/part1",
    tag: "p1-w2",
    prevTag: "p1-w1",
    tasks: range(15, 32),
    commands: [["uv", "run", "pytest", "packages/agent1_scout"]],
  },
  {
    id: "W3-A",
    track: "part1",
    branch: "integration/part1",
    tag: "p1-w3",
    prevTag: "p1-w2",
    tasks: range(33, 44),
    commands: [["uv", "run", "pytest", "packages/agent2_evidence"]],
  },
  {
    id: "W4-A",
    track: "part1",
    branch: "integration/part1",
    tag: "p1-w4",
    prevTag: "p1-w3",
    tasks: range(45, 72),
    commands: [["uv", "run", "pytest", "packages/agent3_gatekeeper", "packages/voice_sync"]],
  },
  {
    id: "W5-A",
    track: "part1",
    branch: "integration/part1",
    tag: "p1-cert",
    prevTag: "p1-w4",
    tasks: range(73, 100),
    commands: [["uv", "run", "pytest", "packages/agent4_director", "packages/orchestrator"]],
  },
  {
    id: "W1-B",
    track: "part2",
    branch: "integration/part2",
    tag: "p2-w1",
    prevTag: null,
    tasks: [...range(101, 115), 117, 118, 122, ...range(130, 142)],
    commands: [["pnpm", "--filter", "@tc/render_catalog", "test", "--", "--mvp-4-motifs"]],
  },
  {
    id: "W2-B",
    track: "part2",
    branch: "integration/part2",
    tag: "p2-w2",
    prevTag: "p2-w1",
    tasks: [116, ...range(119, 121), ...range(123, 129), ...range(143, 152)],
    commands: [["pnpm", "--filter", "@tc/render_catalog", "test"]],
  },
  {
    id: "W3-B",
    track: "part2",
    branch: "integration/part2",
    tag: "p2-w3",
    prevTag: "p2-w2",
    tasks: range(153, 176),
    commands: [["uv", "run", "pytest", "packages/flow_adapter", "packages/agent6_mastering"]],
  },
  {
    id: "W4-B",
    track: "part2",
    branch: "integration/part2",
    tag: "p2-cert",
    prevTag: "p2-w3",
    tasks: range(177, 192),
    commands: [["pnpm", "--filter", "@tc/batch_desk_web", "test"]],
  },
];

export function repoRoot() {
  return ROOT;
}

export function scrubEnv(base = process.env) {
  const next = { ...base };
  for (const key of Object.keys(next)) {
    if (
      PROVIDER_ENV_KEYS.includes(key) ||
      key.endsWith("_API_KEY") ||
      key.endsWith("_SECRET")
    ) {
      delete next[key];
    }
  }
  return next;
}

function gitRaw(args, cwd = ROOT) {
  return spawnSync("git", args, { cwd, encoding: "utf8" });
}

export function git(args, cwd = ROOT) {
  const res = gitRaw(args, cwd);
  if (res.status !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${(res.stderr || res.stdout || "").trim()}`);
  }
  return (res.stdout || "").trim();
}

function refExists(ref, cwd = ROOT) {
  return gitRaw(["rev-parse", "--verify", "--quiet", ref], cwd).status === 0;
}

export function trackForTask(taskId) {
  if (taskId >= 1 && taskId <= 4) return "foundation";
  if (taskId >= 5 && taskId <= 100) return "part1";
  if (taskId >= 101 && taskId <= 192) return "part2";
  if (taskId >= 193 && taskId <= 200) return "joint";
  return "unknown";
}

export function parseTaskScopes(markdown) {
  const scopes = new Map();
  const lines = markdown.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const heading = lines[i].match(/^### Task (\d{3}):/);
    if (!heading) continue;
    const taskId = Number(heading[1]);
    let block = "";
    for (let j = i + 1; j < lines.length; j += 1) {
      if (lines[j].startsWith("### ")) break;
      if (/^- \*\*(?:Owned Write Scope|Owned Files|Files|File):\*\*/.test(lines[j])) {
        block = lines[j];
        let k = j + 1;
        while (k < lines.length && /^\s+\S/.test(lines[k]) && !lines[k].startsWith("### ")) {
          block += `\n${lines[k]}`;
          k += 1;
        }
        break;
      }
    }
    const entries = new Set();
    for (const match of block.matchAll(/`([^`]+)`/g)) {
      const value = match[1].trim();
      if (value) entries.add(value);
    }
    const pathRe =
      /(?:^|[\s`(])((?:packages|apps|schema|fixtures|scripts|tools|tests|benchmarks|artifacts|\.agent-handoffs)\/[A-Za-z0-9_./@*-]+)/g;
    for (const match of block.matchAll(pathRe)) {
      entries.add(match[1].replace(/[),.;:]+$/, ""));
    }
    scopes.set(taskId, [...entries]);
  }
  return scopes;
}

function normalize(rel) {
  return rel.replace(/\\/g, "/").replace(/^\.\//, "").replace(/^\/+/, "");
}

export function pathAllowed(entries, relPath) {
  const rel = normalize(relPath);
  for (const entry of entries) {
    const raw = normalize(entry).replace(/\/+$/, "");
    if (!raw || raw.includes(" ")) continue;
    if (raw.endsWith("/**") || raw.endsWith("/*")) {
      const prefix = raw.replace(/\/\*{1,2}$/, "");
      if (rel === prefix || rel.startsWith(`${prefix}/`)) return true;
      continue;
    }
    if (raw.includes("*")) {
      const body = raw
        .split("**")
        .join("\u0000")
        .split("*")
        .join("[^/]*")
        .split("\u0000")
        .join(".*");
      if (new RegExp(`^${body}$`).test(rel)) return true;
      continue;
    }
    if (rel === raw) return true;
  }
  return false;
}

function under(rel, prefix) {
  return rel === prefix.replace(/\/$/, "") || rel.startsWith(prefix);
}

export function disjointReason(taskId, relPath) {
  const rel = normalize(relPath);
  const track = trackForTask(taskId);
  if (track !== "part1" && track !== "part2") return null;
  const other = track === "part1" ? PART2_ROOTS : PART1_ROOTS;
  for (const prefix of other) {
    if (under(rel, prefix)) {
      return `${track} cannot write ${prefix}`;
    }
  }
  for (const prefix of JOINT_M0) {
    if (under(rel, prefix.endsWith("/") ? prefix : `${prefix}`)) {
      if (prefix.endsWith("/") && under(rel, prefix)) {
        return `${track} cannot edit jointly owned ${prefix}`;
      }
      if (!prefix.endsWith("/") && rel === prefix) {
        return `${track} cannot edit jointly owned ${prefix}`;
      }
    }
  }
  return null;
}

export function diffBase(taskId, cwd = ROOT) {
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
  if (taskId === 1 && (branch === "integration/main" || branch === "main")) {
    if (refExists("origin/main", cwd)) return "origin/main";
    if (refExists("main", cwd)) return "main";
  }
  const marker = `refs/tc-base/${branch}`;
  if (refExists(marker, cwd)) return marker;
  if (refExists("origin/main", cwd)) return git(["merge-base", "HEAD", "origin/main"], cwd);
  return "HEAD";
}

export function changedFiles(taskId, cwd = ROOT) {
  const base = diffBase(taskId, cwd);
  const names = new Set();
  const collect = (text) => {
    for (const line of text.split(/\r?\n/)) {
      const rel = line.trim();
      if (rel) names.add(normalize(rel));
    }
  };
  collect(git(["diff", "--name-only", `${base}...HEAD`], cwd));
  collect(git(["diff", "--name-only"], cwd));
  collect(git(["diff", "--name-only", "--cached"], cwd));
  collect(git(["ls-files", "--others", "--exclude-standard"], cwd));
  return [...names].sort();
}

function secretRules() {
  const names = PROVIDER_ENV_KEYS.join("|");
  return [
    {
      name: "google-api-key",
      re: new RegExp("AI" + "za[0-9A-Za-z\\-_]{20,}"),
    },
    {
      name: "aws-access-key",
      re: /AKIA[0-9A-Z]{16}/,
    },
    {
      name: "private-key",
      re: /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
    },
    {
      name: "github-token",
      re: /ghp_[A-Za-z0-9]{20,}/,
    },
    {
      name: "slack-token",
      re: /xox[baprs]-[0-9A-Za-z-]{10,}/,
    },
    {
      name: "assigned-secret",
      re: new RegExp(
        `(?:${names}|API_KEY|SECRET|PASSWORD)\\s*[:=]\\s*['"]?[A-Za-z0-9_\\-]{12,}`,
        "i",
      ),
    },
  ];
}

function lineIgnored(line) {
  return /placeholder|redacted|example\.com|your-key|changeme|stripped/i.test(line);
}

export function findingsInText(rel, text) {
  const findings = [];
  const rules = secretRules();
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (lineIgnored(line)) continue;
    for (const rule of rules) {
      if (rule.re.test(line)) {
        findings.push({
          kind: "secret",
          file: rel,
          line: i + 1,
          detail: rule.name,
        });
        rule.re.lastIndex = 0;
      }
    }
  }
  return findings;
}

function walkFiles(dir, acc = []) {
  if (!fs.existsSync(dir)) return acc;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(full, acc);
      continue;
    }
    if (!entry.isFile()) continue;
    acc.push(full);
  }
  return acc;
}

export function secretFindings(cwd = ROOT) {
  const findings = [];
  for (const full of walkFiles(cwd)) {
    const rel = normalize(path.relative(cwd, full));
    let stat;
    try {
      stat = fs.statSync(full);
    } catch {
      continue;
    }
    if (stat.size > 1_000_000) continue;
    const sample = fs.readFileSync(full);
    if (sample.includes(0)) continue;
    findings.push(...findingsInText(rel, sample.toString("utf8")));
  }
  return findings;
}

function lineCount(text) {
  const lines = text.split(/\r?\n/);
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines.length;
}

export function driftFindings(cwd = ROOT) {
  const findings = [];
  const targets = [];
  const addFile = (rel) => {
    const full = path.join(cwd, rel);
    if (fs.existsSync(full) && fs.statSync(full).isFile()) targets.push(rel);
  };
  addFile("providers.yaml");
  addFile("craft_rubric.yaml");
  addFile("conftest.py");
  for (const rel of walkFiles(path.join(cwd, "schema")).concat(
    walkFiles(path.join(cwd, "packages")),
    walkFiles(path.join(cwd, "apps")),
    walkFiles(path.join(cwd, "scripts")),
  )) {
    targets.push(normalize(path.relative(cwd, rel)));
  }
  const seen = new Set();
  for (const rel of targets) {
    if (seen.has(rel)) continue;
    seen.add(rel);
    const full = path.join(cwd, rel);
    if (!fs.existsSync(full) || !fs.statSync(full).isFile()) continue;
    const buf = fs.readFileSync(full);
    if (buf.includes(0) || buf.length > 1_000_000) continue;
    const text = buf.toString("utf8");
    for (const token of RETIRED) {
      if (text.includes(token)) {
        findings.push({
          kind: "drift",
          file: rel,
          detail: `retired identifier ${token}`,
        });
      }
    }
  }
  const pipeline = path.join(cwd, "schema", "pipeline.sql");
  if (fs.existsSync(pipeline)) {
    const sql = fs.readFileSync(pipeline, "utf8");
    if (!sql.includes("('schema_version', '4')")) {
      findings.push({
        kind: "drift",
        file: "schema/pipeline.sql",
        detail: "schema_version is not 4",
      });
    }
  } else {
    findings.push({ kind: "drift", file: "schema/pipeline.sql", detail: "missing schema" });
  }
  const providersPath = path.join(cwd, "providers.yaml");
  if (!fs.existsSync(providersPath)) {
    findings.push({ kind: "drift", file: "providers.yaml", detail: "missing registry" });
  } else {
    const yaml = fs.readFileSync(providersPath, "utf8");
    for (const needle of [
      "gemini-omni-1.2-flash",
      "max_hero_clips: 10",
      "max_hero_duration_sec: 80",
      "whisperx-local",
      "DeepSeek-V4.1-Flash-1017",
      "DeepSeek-V4-Pro-0813",
      "gemini-3.8-flash-tts",
      "0.10",
      "10.40",
      "135",
    ]) {
      if (!yaml.includes(needle)) {
        findings.push({
          kind: "drift",
          file: "providers.yaml",
          detail: `missing ${needle}`,
        });
      }
    }
  }
  const rubricPath = path.join(cwd, "craft_rubric.yaml");
  if (!fs.existsSync(rubricPath)) {
    findings.push({ kind: "drift", file: "craft_rubric.yaml", detail: "missing rubric" });
  } else {
    const rubric = fs.readFileSync(rubricPath, "utf8");
    const count = lineCount(rubric);
    if (count > 150) {
      findings.push({
        kind: "drift",
        file: "craft_rubric.yaml",
        detail: `${count} lines exceeds 150`,
      });
    }
    if (!/interactive/i.test(rubric) || !/curiosity/i.test(rubric)) {
      findings.push({
        kind: "drift",
        file: "craft_rubric.yaml",
        detail: "interactive must mean visual curiosity hooks and pacing",
      });
    }
  }
  return findings;
}

function modelAllowlist(yaml) {
  const ids = new Set();
  MODEL_RE.lastIndex = 0;
  for (const match of yaml.matchAll(MODEL_RE)) ids.add(match[0]);
  return ids;
}

export function modelFindings(cwd = ROOT) {
  const providersPath = path.join(cwd, "providers.yaml");
  if (!fs.existsSync(providersPath)) return [];
  const allow = modelAllowlist(fs.readFileSync(providersPath, "utf8"));
  const findings = [];
  const files = walkFiles(path.join(cwd, "packages")).concat(walkFiles(path.join(cwd, "apps")));
  for (const full of files) {
    if (!/\.(py|ts|tsx|js|mjs|cjs|jsx|yml|yaml|json)$/.test(full)) continue;
    const buf = fs.readFileSync(full);
    if (buf.includes(0) || buf.length > 1_000_000) continue;
    const text = buf.toString("utf8");
    const lines = text.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      MODEL_RE.lastIndex = 0;
      for (const match of lines[i].matchAll(MODEL_RE)) {
        if (!allow.has(match[0])) {
          findings.push({
            kind: "model",
            file: normalize(path.relative(cwd, full)),
            line: i + 1,
            detail: `unconfigured model literal ${match[0]}`,
          });
        }
      }
    }
  }
  return findings;
}

function runCommand(args, cwd) {
  const res = spawnSync(args[0], args.slice(1), {
    cwd,
    encoding: "utf8",
    env: scrubEnv(),
  });
  return res;
}

export function commandFindings(cwd = ROOT) {
  const findings = [];
  const schema = runCommand([process.execPath, "schema/schema-test.js"], cwd);
  if (schema.status !== 0) {
    findings.push({
      kind: "command",
      detail: `schema/schema-test.js exited ${schema.status}\n${(schema.stdout || "").slice(-800)}\n${(schema.stderr || "").slice(-800)}`,
    });
  }
  const diagramPath = path.join(cwd, "pipeline-complete.mmd");
  const before = fs.existsSync(diagramPath) ? fs.readFileSync(diagramPath) : null;
  const merged = runCommand([process.execPath, "tools/merge-diagrams.js"], cwd);
  if (merged.status !== 0) {
    findings.push({
      kind: "command",
      detail: `tools/merge-diagrams.js exited ${merged.status}\n${merged.stderr || merged.stdout || ""}`,
    });
  }
  if (before && fs.existsSync(diagramPath) && !before.equals(fs.readFileSync(diagramPath))) {
    fs.writeFileSync(diagramPath, before);
    findings.push({
      kind: "drift",
      file: "pipeline-complete.mmd",
      detail: "merge-diagrams.js would change the committed atlas",
    });
  }
  const probe = runCommand(
    [process.execPath, "-e", "process.exit(process.env.GEMINI_API_KEY ? 2 : 0)"],
    cwd,
  );
  if (probe.status !== 0) {
    findings.push({
      kind: "secret",
      detail: "provider API key survived into a child command",
    });
  }
  return findings;
}

export function scopeFindings(taskId, files, scopes) {
  const findings = [];
  const entries = scopes.get(taskId) ?? [];
  const known = scopes.has(taskId);
  for (const rel of files) {
    const extra = taskId === 1 && TASK001_EXTRA.has(rel);
    const allowed = extra || (known && pathAllowed(entries, rel));
    if (!allowed) {
      findings.push({
        kind: "scope",
        file: rel,
        detail: known
          ? `outside owned write scope for task ${String(taskId).padStart(3, "0")}`
          : `task ${String(taskId).padStart(3, "0")} has no owned write scope`,
      });
    }
    const reason = disjointReason(taskId, rel);
    if (reason) {
      findings.push({ kind: "disjoint", file: rel, detail: reason });
    }
  }
  return findings;
}

export function waveById(id) {
  const wave = WAVES.find((item) => item.id === id);
  if (!wave) {
    throw new Error(`Unknown wave ${id}. Expected one of ${WAVES.map((item) => item.id).join(", ")}`);
  }
  return wave;
}

export function listTags(cwd = ROOT) {
  const text = git(["tag", "--list"], cwd);
  return new Set(text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
}

export function waveOrderErrors(wave, tags) {
  const errors = [];
  if (!tags.has("integration/m0-frozen")) {
    errors.push(
      "integration/m0-frozen is not tagged yet (Task 004). Part 1 and Part 2 waves branch from that tag.",
    );
  }
  if (wave.prevTag && !tags.has(wave.prevTag)) {
    errors.push(`previous wave tag ${wave.prevTag} is missing. Merge the previous wave first.`);
  }
  return errors;
}

export function waveCommandFindings(wave, cwd = ROOT) {
  const findings = [];
  for (const command of wave.commands) {
    const res = runCommand(command, cwd);
    if (res.status !== 0) {
      findings.push({
        kind: "command",
        detail: `${command.join(" ")} exited ${res.status}\n${(res.stdout || "").slice(-600)}\n${(res.stderr || "").slice(-600)}`,
      });
    }
  }
  return findings;
}

export function formatFindings(findings) {
  if (!findings.length) return "harmony: ok";
  return findings
    .map((item) => {
      const where = item.file ? `${item.file}${item.line ? `:${item.line}` : ""}` : "harmony";
      return `${item.kind}: ${where}: ${item.detail}`;
    })
    .join("\n");
}

function parseArgs(argv) {
  const out = { task: null, wave: null, selfTest: false, help: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") out.help = true;
    else if (arg === "--self-test") out.selfTest = true;
    else if (arg === "--task") out.task = Number(argv[++i]);
    else if (arg.startsWith("--task=")) out.task = Number(arg.slice(7));
    else if (arg === "--wave") out.wave = argv[++i];
    else if (arg.startsWith("--wave=")) out.wave = arg.slice(7);
    else throw new Error(`Unknown argument ${arg}`);
  }
  return out;
}

function assertOk(condition, message) {
  if (!condition) throw new Error(message);
}

export function selfTest() {
  const markdown = fs.readFileSync(path.join(ROOT, "IMPLEMENTATION_TASKS.md"), "utf8");
  const scopes = parseTaskScopes(markdown);
  assertOk(scopes.size === 200, `expected 200 task scopes, parsed ${scopes.size}`);
  const empty = [];
  for (let id = 1; id <= 200; id += 1) {
    if (!scopes.get(id) || scopes.get(id).length === 0) empty.push(id);
  }
  assertOk(empty.length === 0, `tasks missing write scope: ${empty.join(", ")}`);
  assertOk(pathAllowed(scopes.get(1), "providers.yaml"), "task 001 must own providers.yaml");
  assertOk(pathAllowed(scopes.get(1), "packages/db/pyproject.toml"), "task 001 must own package shells");
  assertOk(pathAllowed(scopes.get(1), "conftest.py") || TASK001_EXTRA.has("conftest.py"), "guard file");
  assertOk(!pathAllowed(scopes.get(1), "README.md"), "task 001 must not own README.md");
  assertOk(
    pathAllowed(scopes.get(5), "packages/db/src/connection.py"),
    "task 005 scope parse failed",
  );
  assertOk(
    !pathAllowed(scopes.get(5), "packages/db/src/migrations.py"),
    "task 005 must not own migrations.py",
  );
  assertOk(
    pathAllowed(scopes.get(151), "packages/crime_scene_2k/tests/test_aspect_stress.py"),
    "task 151 Files: line was not parsed",
  );
  const sample = "GEMINI_API_KEY=" + "AI" + "zaSyA0123456789abcdefghij";
  assertOk(findingsInText("mem.txt", sample).length >= 1, "secret sample was not detected");
  assertOk(findingsInText("mem.txt", "GEMINI_API_KEY = scrubbed").length === 0, "short placeholder flagged");
  const leaked = findingsInText("mem.txt", "note: use providers.yaml");
  assertOk(leaked.length === 0, "ordinary prose flagged as a secret");
  assertOk(disjointReason(5, "packages/render_catalog/src/x.ts"), "part1/part2 disjoint miss");
  assertOk(disjointReason(101, "packages/db/src/connection.py"), "part2/part1 disjoint miss");
  assertOk(disjointReason(5, "providers.yaml"), "joint file was allowed for part 1");
  assertOk(!disjointReason(1, "packages/render_catalog/src/index.ts"), "foundation shell blocked");
  const blocked = waveOrderErrors(waveById("W1-A"), new Set());
  assertOk(blocked.some((line) => line.includes("integration/m0-frozen")), "wave order did not require m0");
  const later = waveOrderErrors(waveById("W2-A"), new Set(["integration/m0-frozen"]));
  assertOk(later.some((line) => line.includes("p1-w1")), "W2-A did not require p1-w1");
  const child = scrubEnv({ GEMINI_API_KEY: "present", PATH: "/usr/bin" });
  assertOk(!("GEMINI_API_KEY" in child) && child.PATH === "/usr/bin", "scrubEnv failed");
  console.log("verify-harmony self-test: ok");
  return 0;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log("Usage: node scripts/verify-harmony.mjs [--task NNN] [--wave W1-A] [--self-test]");
    return 0;
  }
  if (args.selfTest) return selfTest();
  const findings = [];
  findings.push(...secretFindings(ROOT));
  findings.push(...driftFindings(ROOT));
  findings.push(...modelFindings(ROOT));
  findings.push(...commandFindings(ROOT));
  if (args.task != null && !Number.isNaN(args.task)) {
    const markdown = fs.readFileSync(path.join(ROOT, "IMPLEMENTATION_TASKS.md"), "utf8");
    const scopes = parseTaskScopes(markdown);
    const files = changedFiles(args.task, ROOT);
    findings.push(...scopeFindings(args.task, files, scopes));
  }
  if (args.wave) {
    const wave = waveById(args.wave);
    const order = waveOrderErrors(wave, listTags(ROOT));
    for (const detail of order) findings.push({ kind: "wave", detail });
    if (order.length === 0) findings.push(...waveCommandFindings(wave, ROOT));
  }
  console.log(formatFindings(findings));
  return findings.length ? 1 : 0;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  try {
    process.exit(main());
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
