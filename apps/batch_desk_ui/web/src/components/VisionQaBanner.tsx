import React from "react";

export type QaState = "uploading" | "passed" | "strike1" | "strike2";

export function VisionQaBanner({
  state,
  rewrite,
}: {
  state: QaState;
  rewrite?: string;
}) {
  if (state === "uploading") return React.createElement("p", null, "Uploading");
  if (state === "passed") return React.createElement("p", null, "qa_passed");
  if (state === "strike1") {
    const short = (rewrite ?? "neutral documentary motion").split(/\s+/).slice(0, 10).join(" ");
    return React.createElement(
      "p",
      null,
      "Strike 1 ",
      short,
      React.createElement("button", { type: "button" }, "Copy Simplified Prompt"),
    );
  }
  return React.createElement(
    "p",
    null,
    "Fallback Engaged (STILL_2K_PANZOOM) — 0 extra credits spent",
  );
}
