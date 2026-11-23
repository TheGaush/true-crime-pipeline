import http from "node:http";
import { describe, expect, it } from "vitest";

import {
  FRAME_RATE_FPS,
  JOINT_IDS,
  MIN_POSE_SEPARATION_DEG,
  POSE_TRANSITION_MS,
  RUN_CYCLE_MS,
  RUN_SPEED_PX_PER_SEC,
  RUN_STRIDE_PX,
  STICK_POSES,
  STICK_POSE_COUNT,
  TRAVEL_AXES,
  WALK_CYCLE_MS,
  WALK_SPEED_PX_PER_SEC,
  WALK_STRIDE_PX,
  StickPoseError,
  advanceChoreography,
  blendAngles,
  cubicEaseInOut,
  findPoseCoverageViolation,
  initialChoreography,
  isStickPoseId,
  isTravelAxis,
  maxJointDelta,
  poseKeyframe,
  requestPose,
  rootDeltaPx,
  sampleChoreography,
  setTravelAxis,
  solvePose,
  transitionPairs,
  zeroAngles,
  type JointAngles,
  type StickPoseId,
  type TravelAxis,
} from "../src/rig/StickPoses.ts";

delete process.env.GEMINI_API_KEY;
delete process.env.DEEPSEEK_API_KEY;
delete process.env.ELEVENLABS_API_KEY;

function anglesClose(actual: JointAngles, expected: JointAngles): void {
  for (const id of JOINT_IDS) {
    expect(actual[id], id).toBeCloseTo(expected[id], 8);
  }
}

describe("stick pose coverage", () => {
  it("locks exactly 14 poses from idle through slumped", () => {
    expect(STICK_POSE_COUNT).toBe(14);
    expect(STICK_POSES).toHaveLength(14);
    expect(STICK_POSES[0]).toBe("idle");
    expect(STICK_POSES[13]).toBe("slumped");
    expect(STICK_POSES).toContain("walk_loop");
    expect(STICK_POSES).toContain("run_loop");
    expect(new Set(STICK_POSES).size).toBe(14);
    expect(findPoseCoverageViolation(STICK_POSES, Object.fromEntries(STICK_POSES.map((pose) => [pose, poseKeyframe(pose)])))).toBeNull();
  });

  it("keeps every keyframe finite, separated, and immutable to callers", () => {
    for (const pose of STICK_POSES) {
      const frame = poseKeyframe(pose);
      for (const id of JOINT_IDS) expect(Number.isFinite(frame[id])).toBe(true);
      frame.torsoLean = 999;
      expect(poseKeyframe(pose).torsoLean).not.toBe(999);
    }
    for (let i = 0; i < STICK_POSES.length; i += 1) {
      for (let j = i + 1; j < STICK_POSES.length; j += 1) {
        const left = STICK_POSES[i] as StickPoseId;
        const right = STICK_POSES[j] as StickPoseId;
        expect(maxJointDelta(poseKeyframe(left), poseKeyframe(right))).toBeGreaterThanOrEqual(MIN_POSE_SEPARATION_DEG);
      }
    }
  });

  it("rejects a catalog that drops a pose or collapses two silhouettes", () => {
    const frames = Object.fromEntries(STICK_POSES.map((pose) => [pose, poseKeyframe(pose)]));
    expect(findPoseCoverageViolation(STICK_POSES.slice(0, 13), frames)).toMatch(/expected 14/);
    expect(findPoseCoverageViolation([...STICK_POSES].reverse(), frames)).toMatch(/idle through slumped/);
    const collapsed = { ...frames, slumped: poseKeyframe("idle") };
    expect(findPoseCoverageViolation(STICK_POSES, collapsed)).toMatch(/closer than 8/);
  });

  it("rejects unknown pose ids and travel axes", () => {
    expect(isStickPoseId("idle")).toBe(true);
    expect(isStickPoseId("slumped")).toBe(true);
    expect(isStickPoseId("walking")).toBe(false);
    expect(isTravelAxis("L_TO_R")).toBe(true);
    expect(isTravelAxis("R_TO_L")).toBe(true);
    expect(isTravelAxis("STATIC")).toBe(true);
    expect(isTravelAxis("UP")).toBe(false);
    expect(() => solvePose({ pose: "dancing" as StickPoseId, elapsedMs: 0 })).toThrow(StickPoseError);
    expect(() => solvePose({ pose: "idle", elapsedMs: 0, travelAxis: "UP" as TravelAxis })).toThrow(StickPoseError);
    expect(() => solvePose({ pose: "idle", elapsedMs: -1 })).toThrow(StickPoseError);
    try {
      solvePose({ pose: "dancing" as StickPoseId, elapsedMs: 0 });
    } catch (error) {
      expect(error).toBeInstanceOf(StickPoseError);
      expect((error as StickPoseError).code).toBe("UNKNOWN_POSE");
    }
  });
});

describe("stride velocity synced to travel_axis", () => {
  it("holds non-locomotion poses at zero velocity on every axis", () => {
    for (const pose of STICK_POSES) {
      if (pose === "walk_loop" || pose === "run_loop") continue;
      for (const travelAxis of TRAVEL_AXES) {
        const sample = solvePose({ pose, elapsedMs: 1000, travelAxis });
        expect(sample.velocityPxPerSec, `${pose} ${travelAxis}`).toBe(0);
        expect(sample.phase).toBe(0);
        expect(sample.cycleMs).toBeNull();
        anglesClose(sample.angles, poseKeyframe(pose));
      }
    }
  });

  it("signs walk and run stride by L_TO_R, R_TO_L, and STATIC", () => {
    expect(WALK_SPEED_PX_PER_SEC * WALK_CYCLE_MS / 1000).toBe(WALK_STRIDE_PX);
    expect(RUN_SPEED_PX_PER_SEC * RUN_CYCLE_MS / 1000).toBe(RUN_STRIDE_PX);
    expect(RUN_SPEED_PX_PER_SEC).toBeGreaterThan(WALK_SPEED_PX_PER_SEC);
    expect(RUN_CYCLE_MS).toBeLessThan(WALK_CYCLE_MS);
    expect(POSE_TRANSITION_MS * FRAME_RATE_FPS / 1000).toBe(9);

    const walkRight = solvePose({ pose: "walk_loop", elapsedMs: 0, travelAxis: "L_TO_R" });
    const walkLeft = solvePose({ pose: "walk_loop", elapsedMs: 0, travelAxis: "R_TO_L" });
    const walkStill = solvePose({ pose: "walk_loop", elapsedMs: 0, travelAxis: "STATIC" });
    expect(walkRight.velocityPxPerSec).toBe(WALK_SPEED_PX_PER_SEC);
    expect(walkLeft.velocityPxPerSec).toBe(-WALK_SPEED_PX_PER_SEC);
    expect(walkStill.velocityPxPerSec).toBe(0);
    expect(walkRight.facing).toBe(1);
    expect(walkLeft.facing).toBe(-1);
    expect(walkStill.facing).toBe(1);
    expect(rootDeltaPx(walkRight.velocityPxPerSec, WALK_CYCLE_MS)).toBe(WALK_STRIDE_PX);
    expect(rootDeltaPx(walkLeft.velocityPxPerSec, WALK_CYCLE_MS)).toBe(-WALK_STRIDE_PX);
    expect(rootDeltaPx(walkStill.velocityPxPerSec, WALK_CYCLE_MS)).toBe(0);

    const runRight = solvePose({ pose: "run_loop", elapsedMs: 0, travelAxis: "L_TO_R" });
    const runLeft = solvePose({ pose: "run_loop", elapsedMs: 0, travelAxis: "R_TO_L" });
    const runStill = solvePose({ pose: "run_loop", elapsedMs: 4000, travelAxis: "STATIC" });
    expect(runRight.velocityPxPerSec).toBe(RUN_SPEED_PX_PER_SEC);
    expect(runLeft.velocityPxPerSec).toBe(-RUN_SPEED_PX_PER_SEC);
    expect(runStill.velocityPxPerSec).toBe(0);
    expect(rootDeltaPx(runRight.velocityPxPerSec, RUN_CYCLE_MS)).toBe(RUN_STRIDE_PX);
    anglesClose(runStill.angles, poseKeyframe("run_loop"));
  });

  it("advances the stride phase only while the figure is traveling", () => {
    const walkStart = solvePose({ pose: "walk_loop", elapsedMs: 0, travelAxis: "L_TO_R" });
    const walkQuarter = solvePose({ pose: "walk_loop", elapsedMs: WALK_CYCLE_MS / 4, travelAxis: "L_TO_R" });
    const walkHalf = solvePose({ pose: "walk_loop", elapsedMs: WALK_CYCLE_MS / 2, travelAxis: "L_TO_R" });
    const walkCycle = solvePose({ pose: "walk_loop", elapsedMs: WALK_CYCLE_MS, travelAxis: "L_TO_R" });
    const walkHeld = solvePose({ pose: "walk_loop", elapsedMs: WALK_CYCLE_MS / 2, travelAxis: "STATIC" });
    expect(walkStart.phase).toBe(0);
    expect(walkQuarter.phase).toBe(0.25);
    expect(walkHalf.phase).toBe(0.5);
    expect(walkCycle.phase).toBe(0);
    expect(walkHeld.phase).toBe(0);
    anglesClose(walkStart.angles, poseKeyframe("walk_loop"));
    anglesClose(walkCycle.angles, poseKeyframe("walk_loop"));
    anglesClose(walkHeld.angles, poseKeyframe("walk_loop"));
    expect(maxJointDelta(walkStart.angles, walkQuarter.angles)).toBeGreaterThan(MIN_POSE_SEPARATION_DEG);

    const runAt225 = solvePose({ pose: "run_loop", elapsedMs: 225, travelAxis: "L_TO_R" });
    const walkAt225 = solvePose({ pose: "walk_loop", elapsedMs: 225, travelAxis: "L_TO_R" });
    expect(runAt225.phase).toBeCloseTo(0.5);
    expect(walkAt225.phase).toBeCloseTo(225 / WALK_CYCLE_MS);
    expect(runAt225.phase).toBeGreaterThan(walkAt225.phase);

    const right = solvePose({ pose: "walk_loop", elapsedMs: 200, travelAxis: "L_TO_R" });
    const left = solvePose({ pose: "walk_loop", elapsedMs: 200, travelAxis: "R_TO_L" });
    expect(left.phase).toBe(right.phase);
    anglesClose(left.angles, right.angles);
    expect(left.velocityPxPerSec).toBe(-right.velocityPxPerSec);
    expect(left.facing).toBe(-1);
  });

  it("refuses a negative root-delta interval", () => {
    expect(() => rootDeltaPx(WALK_SPEED_PX_PER_SEC, -5)).toThrow(StickPoseError);
  });
});

describe("300ms cubic transitions", () => {
  it("eases with zero endpoint slope", () => {
    expect(cubicEaseInOut(0)).toBe(0);
    expect(cubicEaseInOut(0.5)).toBe(0.5);
    expect(cubicEaseInOut(1)).toBe(1);
    expect(cubicEaseInOut(-1)).toBe(0);
    expect(cubicEaseInOut(2)).toBe(1);
    expect(cubicEaseInOut(1 / POSE_TRANSITION_MS)).toBeLessThan(0.01);
    let previous = -1;
    for (let step = 0; step <= 20; step += 1) {
      const value = cubicEaseInOut(step / 20);
      expect(value).toBeGreaterThanOrEqual(previous);
      previous = value;
    }
  });

  it("covers every ordered pair exactly once", () => {
    const pairs = transitionPairs();
    expect(pairs).toHaveLength(STICK_POSE_COUNT * STICK_POSE_COUNT);
    expect(new Set(pairs.map(([from, to]) => `${from}->${to}`)).size).toBe(196);
  });

  it.each(transitionPairs())(
    "blends %s -> %s across 300ms without an angle pop",
    (from, to) => {
      const source = solvePose({ pose: from, elapsedMs: 0, travelAxis: "STATIC" });
      const destination = solvePose({ pose: to, elapsedMs: POSE_TRANSITION_MS, travelAxis: "STATIC" });
      const atStart = solvePose({
        pose: to,
        fromPose: from,
        elapsedMs: 0,
        travelAxis: "STATIC",
      });
      const at1 = solvePose({
        pose: to,
        fromPose: from,
        elapsedMs: 1,
        travelAxis: "STATIC",
      });
      const atMid = solvePose({
        pose: to,
        fromPose: from,
        elapsedMs: POSE_TRANSITION_MS / 2,
        travelAxis: "STATIC",
      });
      const at299 = solvePose({
        pose: to,
        fromPose: from,
        elapsedMs: POSE_TRANSITION_MS - 1,
        travelAxis: "STATIC",
      });
      const atEnd = solvePose({
        pose: to,
        fromPose: from,
        elapsedMs: POSE_TRANSITION_MS,
        travelAxis: "STATIC",
      });

      expect(atStart.transitioning).toBe(true);
      expect(atStart.transitionT).toBe(0);
      expect(atEnd.transitioning).toBe(false);
      expect(atEnd.transitionT).toBe(1);
      anglesClose(atStart.angles, source.angles);
      anglesClose(atEnd.angles, destination.angles);
      anglesClose(atMid.angles, blendAngles(source.angles, destination.angles, 0.5));
      expect(atMid.transitionT).toBe(0.5);
      expect(maxJointDelta(atStart.angles, at1.angles)).toBeLessThan(0.01);
      expect(maxJointDelta(at299.angles, atEnd.angles)).toBeLessThan(0.01);
      expect(atStart.velocityPxPerSec).toBe(0);
      expect(atEnd.velocityPxPerSec).toBe(0);
    },
  );

  it("ramps walk velocity down to idle on the same cubic", () => {
    const start = solvePose({
      pose: "idle",
      fromPose: "walk_loop",
      fromElapsedMs: 0,
      elapsedMs: 0,
      travelAxis: "L_TO_R",
    });
    const mid = solvePose({
      pose: "idle",
      fromPose: "walk_loop",
      fromElapsedMs: 0,
      elapsedMs: POSE_TRANSITION_MS / 2,
      travelAxis: "L_TO_R",
    });
    const end = solvePose({
      pose: "idle",
      fromPose: "walk_loop",
      fromElapsedMs: 0,
      elapsedMs: POSE_TRANSITION_MS,
      travelAxis: "L_TO_R",
    });
    expect(start.velocityPxPerSec).toBe(WALK_SPEED_PX_PER_SEC);
    expect(mid.velocityPxPerSec).toBe(WALK_SPEED_PX_PER_SEC / 2);
    expect(end.velocityPxPerSec).toBe(0);
    anglesClose(start.angles, poseKeyframe("walk_loop"));
    anglesClose(end.angles, poseKeyframe("idle"));
    expect(end.facing).toBe(1);
  });
});

describe("choreography state machine", () => {
  it("starts settled on idle and keeps a same-pose request on the same clock", () => {
    const state = advanceChoreography(initialChoreography(), 40);
    const again = requestPose(state, "idle");
    expect(again).toBe(state);
    expect(again.elapsedMs).toBe(40);
    const sample = sampleChoreography(state);
    expect(sample.pose).toBe("idle");
    expect(sample.transitioning).toBe(false);
    expect(sample.velocityPxPerSec).toBe(0);
    anglesClose(sample.angles, poseKeyframe("idle"));
  });

  it("retargets mid-blend without an angle pop, then settles on the new pose", () => {
    let state = requestPose(initialChoreography("idle", "STATIC"), "walk_loop");
    state = advanceChoreography(state, 100);
    const before = sampleChoreography(state);
    expect(before.transitioning).toBe(true);
    state = requestPose(state, "run_loop");
    const after = sampleChoreography(state);
    expect(after.transitioning).toBe(true);
    expect(after.transitionT).toBe(0);
    expect(after.pose).toBe("run_loop");
    anglesClose(after.angles, before.angles);
    expect(after.velocityPxPerSec).toBe(before.velocityPxPerSec);

    state = advanceChoreography(state, POSE_TRANSITION_MS);
    const settled = sampleChoreography(state);
    expect(settled.transitioning).toBe(false);
    expect(settled.pose).toBe("run_loop");
    anglesClose(settled.angles, poseKeyframe("run_loop"));
    expect(settled.velocityPxPerSec).toBe(0);
  });

  it("applies travel_axis to a settled walk without rewriting local angles", () => {
    let state = initialChoreography("walk_loop", "STATIC");
    state = advanceChoreography(state, WALK_CYCLE_MS);
    expect(sampleChoreography(state).velocityPxPerSec).toBe(0);
    expect(sampleChoreography(state).phase).toBe(0);

    state = setTravelAxis(state, "L_TO_R");
    const right = sampleChoreography(state);
    expect(right.velocityPxPerSec).toBe(WALK_SPEED_PX_PER_SEC);
    expect(right.facing).toBe(1);
    expect(right.phase).toBe(0);

    state = setTravelAxis(state, "R_TO_L");
    const left = sampleChoreography(state);
    expect(left.velocityPxPerSec).toBe(-WALK_SPEED_PX_PER_SEC);
    expect(left.facing).toBe(-1);
    anglesClose(left.angles, right.angles);

    expect(advanceChoreography(state, 0)).toBe(state);
    expect(setTravelAxis(state, "R_TO_L")).toBe(state);
  });

  it("rejects a negative advance", () => {
    expect(() => advanceChoreography(initialChoreography(), -1)).toThrow(StickPoseError);
  });
});

describe("zero-spend offline guard", () => {
  it("does not leave paid provider keys in the test process", () => {
    expect(process.env.GEMINI_API_KEY).toBeUndefined();
    expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
    expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
  });

  it("blocks outbound http", () => {
    expect(() => {
      http.get("http://example.com/stick-poses");
    }).toThrow(/ZERO_SPEND_GUARD/);
  });
});

describe("blend helper", () => {
  it("returns the source at u=0 and the destination at u=1", () => {
    const from = poseKeyframe("pointing");
    const to = poseKeyframe("slumped");
    expect(blendAngles(from, to, 0)).toEqual(from);
    expect(blendAngles(from, to, 1)).toEqual(to);
    expect(blendAngles(zeroAngles(), zeroAngles(), 0.5)).toEqual(zeroAngles());
  });
});
