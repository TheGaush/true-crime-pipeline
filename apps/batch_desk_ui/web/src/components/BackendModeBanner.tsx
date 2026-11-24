import React from "react";

const LABELS: Record<string, string> = {
  INTERACTIONS: "Interactions API",
  HUMAN_BATCH_DESK: "Human Batch Desk",
};

export function BackendModeBanner({ mode }: { mode: string }) {
  return React.createElement("p", { role: "status" }, LABELS[mode] ?? "Human Batch Desk");
}
