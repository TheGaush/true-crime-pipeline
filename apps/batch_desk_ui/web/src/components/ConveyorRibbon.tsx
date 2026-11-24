import React from "react";

export type DeskEpisode = {
  episodeId: string;
  title: string;
  status: string;
  createdMs: number;
};

export function saturationBadge(spentFraction: number, wave: number): string {
  if (wave > 3 && spentFraction < 0.5) return "ABORTED_BEFORE_50PCT";
  if (spentFraction > 0.5 && wave <= 5) return "SUNK_COST_FINISH_GUARD";
  return "SAFE";
}

export function oldestSlots(episodes: DeskEpisode[], limit = 3): DeskEpisode[] {
  return episodes
    .filter((episode) => episode.status === "AWAITING_FLOW_BATCH")
    .slice()
    .sort((left, right) => left.createdMs - right.createdMs)
    .slice(0, limit);
}

export function ConveyorRibbon({
  episodes,
  spentFraction,
  wave,
}: {
  episodes: DeskEpisode[];
  spentFraction: number;
  wave: number;
}) {
  const slots = oldestSlots(episodes);
  return React.createElement(
    "section",
    { "aria-label": "conveyor" },
    React.createElement("p", null, saturationBadge(spentFraction, wave)),
    ...slots.map((episode) =>
      React.createElement("article", { key: episode.episodeId }, episode.title),
    ),
  );
}
