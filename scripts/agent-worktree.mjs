#!/usr/bin/env node
/**
 * Worktree CLI (Task 001).
 *
 *   node scripts/agent-worktree.mjs create 000 smoke
 *   node scripts/agent-worktree.mjs check 000
 *   node scripts/agent-worktree.mjs commit -m "message"
 *   node scripts/agent-worktree.mjs wave-merge W1-A
 *   node scripts/agent-worktree.mjs wave-rollback W1-A
 *
 * Task branches live in the sibling directory ../tc-wt/ so Windows
 * MAX_PATH stays shorter. core.longpaths=true and core.autocrlf=false
 * are applied in the shared local git config.
 */

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import {
  changedFiles,
  git,
  listTags,
  repoRoot,
  trackForTask,
  waveById,
  waveOrderErrors,
} from "./verify-harmony.mjs";

function die(message) {
  console.error(message);
  process.exit(1);
}

function run(args, cwd) {
  const res = spawnSync(args[0], args.slice(1), { cwd, stdio: "inherit" });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

function ensureGitDefaults(cwd) {
  git(["config", "core.longpaths", "true"], cwd);
  git(["config", "core.autocrlf", "false"], cwd);
}

function padTask(value) {
  const text = String(value);
  if (!/^\d{1,3}$/.test(text)) die(`Task id must be 1-3 digits, got ${value}`);
  return text.padStart(3, "0");
}

function worktreePath(nnn, slug) {
  return path.resolve(repoRoot(), "..", "tc-wt", `task-${nnn}-${slug}`);
}

function currentBranch(cwd = repoRoot()) {
  return git(["rev-parse", "--abbrev-ref", "HEAD"], cwd);
}

function taskFromBranch(branch) {
  const match = branch.match(/^task\/(\d{3})-/);
  if (!match) die(`Cannot infer a task id from branch ${branch}. Pass the task number.`);
  return Number(match[1]);
}

function create(nnnRaw, slug) {
  if (!slug) die("Usage: node scripts/agent-worktree.mjs create NNN <slug>");
  const nnn = padTask(nnnRaw);
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
    die("slug must be lowercase words separated by hyphens");
  }
  const cwd = repoRoot();
  ensureGitDefaults(cwd);
  const branch = `task/${nnn}-${slug}`;
  const dest = worktreePath(nnn, slug);
  if (fs.existsSync(dest)) die(`Worktree path already exists: ${dest}`);
  const existing = git(["branch", "--list", branch], cwd);
  if (existing) die(`Branch already exists: ${branch}`);
  const base = git(["rev-parse", "HEAD"], cwd);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  git(["worktree", "add", "-b", branch, dest, "HEAD"], cwd);
  git(["update-ref", `refs/tc-base/${branch}`, base], cwd);
  console.log(`created ${branch}`);
  console.log(`worktree ${dest}`);
}

function check(taskArg) {
  const cwd = repoRoot();
  ensureGitDefaults(cwd);
  const task = taskArg == null ? taskFromBranch(currentBranch(cwd)) : Number(padTask(taskArg));
  run([process.execPath, "scripts/verify-harmony.mjs", "--task", String(task).padStart(3, "0")], cwd);
}

function commit(message) {
  if (!message) die("Usage: node scripts/agent-worktree.mjs commit -m \"message\"");
  const cwd = repoRoot();
  ensureGitDefaults(cwd);
  const branch = currentBranch(cwd);
  const task = taskFromBranch(branch);
  const track = trackForTask(task);
  if (track === "unknown") die(`Refusing commit on ${branch}: task track is unknown.`);
  run([process.execPath, "scripts/verify-harmony.mjs", "--task", String(task).padStart(3, "0")], cwd);
  const files = changedFiles(task, cwd);
  if (!files.length) die("Nothing to commit.");
  git(["add", "-A", "--", ...files], cwd);
  git(
    [
      "commit",
      "-m",
      message,
      "--trailer",
      `TC-Task-ID: ${String(task).padStart(3, "0")}`,
      "--trailer",
      `TC-Track: ${track}`,
      "--trailer",
      "TC-Never-Merge: true",
    ],
    cwd,
  );
  console.log(`committed on ${branch}`);
}

function taskBranches(taskId, cwd) {
  const prefix = `task/${String(taskId).padStart(3, "0")}-`;
  return git(["branch", "--list", `${prefix}*`], cwd)
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^\* /, ""))
    .filter((line) => line.startsWith(prefix));
}

function branchExists(name, cwd) {
  return git(["branch", "--list", name], cwd).trim() !== "";
}

function waveMerge(id) {
  const cwd = repoRoot();
  ensureGitDefaults(cwd);
  const wave = waveById(id);
  if (wave.branch === "main" || wave.branch === "master") {
    die("Refusing to merge a wave into main.");
  }
  const order = waveOrderErrors(wave, listTags(cwd));
  if (order.length) die(order.join("\n"));
  const dirty = git(["status", "--porcelain"], cwd);
  if (dirty) die("Working tree is dirty. Commit or stash before wave-merge.");
  const branches = [];
  const missing = [];
  for (const taskId of wave.tasks) {
    const found = taskBranches(taskId, cwd);
    if (found.length !== 1) missing.push(`${String(taskId).padStart(3, "0")}: found ${found.length} branches`);
    else branches.push(found[0]);
  }
  if (missing.length) die(`Missing task branches:\n${missing.join("\n")}`);
  const dest = path.resolve(cwd, "..", "tc-wt", `wave-${wave.id}`);
  if (fs.existsSync(dest)) die(`Wave worktree already exists: ${dest}`);
  if (branchExists(wave.branch, cwd)) git(["worktree", "add", dest, wave.branch], cwd);
  else git(["worktree", "add", "-b", wave.branch, dest, "integration/m0-frozen"], cwd);
  try {
    for (const branch of branches) {
      const message = [
        `Merge ${branch} into ${wave.branch}`,
        "",
        `TC-Wave: ${wave.id}`,
        `TC-Track: ${wave.track}`,
        "TC-Never-Merge: true",
      ].join("\n");
      const merged = spawnSync("git", ["merge", "--no-ff", "--no-edit", "-m", message, branch], {
        cwd: dest,
        stdio: "inherit",
      });
      if (merged.status !== 0) {
        spawnSync("git", ["merge", "--abort"], { cwd: dest });
        die(`Merge of ${branch} failed.`);
      }
    }
    const harmony = spawnSync(process.execPath, ["scripts/verify-harmony.mjs", "--wave", wave.id], {
      cwd: dest,
      stdio: "inherit",
    });
    if (harmony.status !== 0) die(`Wave ${wave.id} failed harmony. Tag ${wave.tag} was not created.`);
    const sha = git(["rev-parse", "HEAD"], dest);
    git(["tag", "-a", wave.tag, sha, "-m", `${wave.id} green`], cwd);
    console.log(`tagged ${wave.tag} at ${sha}`);
  } finally {
    spawnSync("git", ["worktree", "remove", "--force", dest], { cwd, stdio: "inherit" });
  }
}

function waveRollback(id) {
  const cwd = repoRoot();
  ensureGitDefaults(cwd);
  const wave = waveById(id);
  if (!listTags(cwd).has(wave.tag)) {
    die(`Refusing wave-rollback: tag ${wave.tag} does not exist, so ${wave.id} was not merged.`);
  }
  if (!branchExists(wave.branch, cwd)) die(`Track branch ${wave.branch} does not exist.`);
  const sha = git(["rev-parse", `${wave.tag}^{}`], cwd);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const dest = path.resolve(cwd, "..", "tc-wt", `rollback-${wave.id}-${stamp}`);
  git(["worktree", "add", dest, wave.branch], cwd);
  try {
    const reverted = spawnSync("git", ["revert", "-m", "1", "--no-edit", sha], {
      cwd: dest,
      stdio: "inherit",
    });
    if (reverted.status !== 0) die(`Revert of ${sha} failed.`);
    const newSha = git(["rev-parse", "HEAD"], dest);
    const tag = `rollback/${wave.id}-${stamp}`;
    git(["tag", "-a", tag, newSha, "-m", `Rollback ${wave.id}`], cwd);
    console.log(`tagged ${tag} at ${newSha}`);
  } finally {
    spawnSync("git", ["worktree", "remove", "--force", dest], { cwd, stdio: "inherit" });
  }
}

function parseCommitMessage(argv) {
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "-m" || argv[i] === "--message") return argv[i + 1];
  }
  return "";
}

function main() {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || command === "--help" || command === "-h") {
    console.log(
      "Usage: node scripts/agent-worktree.mjs <create|check|commit|wave-merge|wave-rollback> ...",
    );
    return;
  }
  if (command === "create") create(rest[0], rest[1]);
  else if (command === "check") check(rest[0]);
  else if (command === "commit") commit(parseCommitMessage(rest));
  else if (command === "wave-merge") {
    if (!rest[0]) die("Usage: node scripts/agent-worktree.mjs wave-merge <wave-id>");
    waveMerge(rest[0]);
  } else if (command === "wave-rollback") {
    if (!rest[0]) die("Usage: node scripts/agent-worktree.mjs wave-rollback <wave-id>");
    waveRollback(rest[0]);
  } else die(`Unknown command ${command}`);
}

main();
