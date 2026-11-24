import React from "react";

export type Pulse = {
  ctrPct: number | null;
  hookPct: number | null;
  yellowCount: number;
  watchHours: number;
};

export function AnalyticsPulseCard({ pulse }: { pulse: Pulse }) {
  const width = Math.max(0, Math.min(100, (pulse.watchHours / 8000) * 100));
  return React.createElement(
    "section",
    { "aria-label": "Analytics pulse" },
    React.createElement("p", null, `CTR ${pulse.ctrPct ?? "—"}`),
    React.createElement("p", null, `30s hook ${pulse.hookPct ?? "—"}`),
    React.createElement("p", null, `Yellow-icon count ${pulse.yellowCount}`),
    React.createElement(
      "div",
      { role: "meter", "aria-valuenow": pulse.watchHours, "aria-valuemax": 8000 },
      React.createElement("span", { style: { width: `${width}%` } }, `${pulse.watchHours} / 8,000`),
    ),
  );
}
