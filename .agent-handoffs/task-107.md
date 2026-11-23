# Task 107 handoff

- Task: 107
- Branch: `task/107-stick-figure-10-emotions`
- Worktree: `../tc-wt/task-107-stick-figure-10-emotions`
- Track: Part 2
- Status: implemented, not merged
- Owned paths touched: `packages/render_catalog/src/rig/StickEmotions.tsx`, `packages/render_catalog/tests/stick_emotions.test.tsx`, `.agent-handoffs/task-107.md`
- Dependencies added: none
- Verification: Node test runner, 18 passed / 0 failed. `tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. `node scripts/verify-harmony.mjs --task 107` accepted these three paths. The model-id lint still fails on Task 002 contract files this task must not edit. `pnpm --filter @tc/render_catalog test -- stick_emotions` does not run this suite (see Incomplete).
- Incomplete: `packages/render_catalog/package.json` has no `test` script. That file is outside this task's write scope. pnpm treats a missing script on a filtered run as success and prints nothing, so the acceptance command exits 0 without executing `stick_emotions.test.tsx`.
- Notes for the next agent: import from `packages/render_catalog/src/rig/StickEmotions.tsx`. Do not expect a barrel export; `src/index.ts` belongs to Task 101. `StickEmotions()` returns a rig object, not a React element, because this package has no JSX flag and no React dependency.

## Emotion contract

v4 shared contracts do not define a stick-figure emotion enum. This task locks these ten names, in order, `neutral` through `guilty`:

1. `neutral`
2. `attentive`
3. `skeptical`
4. `concerned`
5. `surprised`
6. `fearful`
7. `angry`
8. `grieving`
9. `ashamed`
10. `guilty`

`stickEmotionChannels(emotion)` is the base face and posture, each channel in `[-1, 1]`. Eye open, mouth open, mouth tight, shoulder raise, and spine curl stay in `[0, 1]`. Guilty has the lowest gaze and the deepest head pitch and spine curl. Angry has the lowest brows and the strongest forward lean. Fearful has the highest shrug and the strongest backward lean. Surprised has the most open mouth.

## Blink and distance

Blinks are a 4-frame closure every 105 frames (`3.5s` at `30 fps`). Phases 0 and 3 are half shut (`0.5`); phases 1 and 2 are shut (`1`). Fractional frames floor. `blinkOffsetFrames` shifts the phase and keeps the same period. Posture channels do not move during a blink, and the svg holds on the frames between blinks.

Scale uses magnitude. At `>= 0.45` the face keeps both brows and, for `surprised` and `fearful`, an inner mouth. Below `0.45` those strokes drop, mouth open and tight become `0`, and mouth curve is halved. Gaze and posture channels stay. Drawing scale floors at `0.05` so a zero scale does not pile every emotion on one point. A negative scale uses the same paths as its magnitude and records the signed value on `data-scale`.

Preview spine, shoulders, neck, and head are overlay geometry only. Task 104 owns the locked bone lengths. Strokes use ink `#1B1B1D`. The rig does not emit SVG filter primitives.

## How to run the suite

Node 22 cannot import `.tsx` directly, and this package has no test script. From a temp directory, strip types and run the file. No network and no new dependencies:

```bash
DIR=$(mktemp -d)
cat > "$DIR/loader.mjs" << 'EOF'
import { stripTypeScriptTypes } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
export async function load(url, context, nextLoad) {
  if (url.startsWith("file:") && url.endsWith(".tsx")) {
    const source = stripTypeScriptTypes(readFileSync(fileURLToPath(url), "utf8"), { mode: "strip" });
    return { format: "module", source, shortCircuit: true };
  }
  return nextLoad(url, context);
}
EOF
cat > "$DIR/register.mjs" << EOF
import { register } from "node:module";
import { pathToFileURL } from "node:url";
register(pathToFileURL("$DIR/loader.mjs").href, { parentURL: import.meta.url });
EOF
node --import "$DIR/register.mjs" --test packages/render_catalog/tests/stick_emotions.test.tsx
```

Result: `tests 18`, `pass 18`, `fail 0`.

Commit only on this branch. Do not merge.

```
TC-Task-ID: 107
TC-Track: part2
TC-Never-Merge: true
```
