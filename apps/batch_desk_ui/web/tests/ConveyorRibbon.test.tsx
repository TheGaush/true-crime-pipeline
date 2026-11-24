import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BackendModeBanner } from "../src/components/BackendModeBanner";
import { ConveyorRibbon, oldestSlots, saturationBadge } from "../src/components/ConveyorRibbon";

const episodes = [
  { episodeId: "c", title: "third", status: "AWAITING_FLOW_BATCH", createdMs: 30 },
  { episodeId: "a", title: "first", status: "AWAITING_FLOW_BATCH", createdMs: 10 },
  { episodeId: "d", title: "later", status: "AWAITING_FLOW_BATCH", createdMs: 40 },
  { episodeId: "b", title: "second", status: "AWAITING_FLOW_BATCH", createdMs: 20 },
  { episodeId: "x", title: "done", status: "MASTERED", createdMs: 1 },
];

describe("conveyor", () => {
  it("keeps the three oldest waiting episodes", () => {
    expect(oldestSlots(episodes).map((episode) => episode.episodeId)).toEqual(["a", "b", "c"]);
    render(React.createElement(ConveyorRibbon, { episodes, spentFraction: 0.2, wave: 1 }));
    expect(screen.getByText("first")).toBeTruthy();
    expect(screen.queryByText("later")).toBeNull();
    expect(screen.getByText("SAFE")).toBeTruthy();
  });

  it("badges an early abort and a sunk-cost finish", () => {
    expect(saturationBadge(0.35, 4)).toBe("ABORTED_BEFORE_50PCT");
    expect(saturationBadge(0.68, 4)).toBe("SUNK_COST_FINISH_GUARD");
  });

  it("names the desk mode without a provider id", () => {
    render(React.createElement(BackendModeBanner, { mode: "INTERACTIONS" }));
    expect(screen.getByRole("status").textContent).toBe("Interactions API");
  });
});
