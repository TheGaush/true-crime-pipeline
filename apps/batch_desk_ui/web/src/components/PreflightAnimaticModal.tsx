import React from "react";

export function PreflightAnimaticModal({
  chapters,
  onClose,
  onSeek,
}: {
  chapters: { id: string; label: string; seconds: number }[];
  onClose: () => void;
  onSeek: (seconds: number) => void;
}) {
  return React.createElement(
    "dialog",
    {
      open: true,
      "aria-label": "animatic",
      onKeyDown: (event: React.KeyboardEvent<HTMLDialogElement>) => {
        if (event.key === "Escape") onClose();
      },
    },
    React.createElement("video", { "aria-label": "animatic video" }),
    ...chapters.map((chapter) =>
      React.createElement(
        "button",
        { key: chapter.id, type: "button", onClick: () => onSeek(chapter.seconds) },
        chapter.label,
      ),
    ),
  );
}
