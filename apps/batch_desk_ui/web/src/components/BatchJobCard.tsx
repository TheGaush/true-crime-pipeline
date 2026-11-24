import React from "react";

export function BatchJobCard({
  prompt,
  mode,
  onCopied,
  onFile,
}: {
  prompt: string;
  mode: string;
  onCopied: (text: string) => void;
  onFile: (name: string) => void;
}) {
  const words = prompt.trim().split(/\s+/).filter(Boolean);
  const safe = words.slice(0, 15).join(" ");
  async function copy() {
    try {
      await navigator.clipboard.writeText(safe);
    } catch {
      const field = document.createElement("textarea");
      field.value = safe;
      document.body.appendChild(field);
      field.select();
      document.execCommand("copy");
      field.remove();
    }
    onCopied(safe);
  }
  function take(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".mp4")) {
      onFile("rejected");
      return;
    }
    onFile(file.name);
  }
  return React.createElement(
    "article",
    null,
    React.createElement("p", null, mode),
    React.createElement("p", null, "manual-desk-video 3s-10s"),
    React.createElement("img", { alt: "start bookend", src: "start.png" }),
    React.createElement("img", { alt: "end bookend", src: "end.png" }),
    React.createElement("button", { type: "button", onClick: () => void copy() }, "Copy Motion Prompt"),
    React.createElement(
      "a",
      { href: "https://flow.local/desk" },
      "Open Flow in Browser",
    ),
    React.createElement("input", {
      "aria-label": "mp4 file",
      type: "file",
      accept: "video/mp4",
      onChange: (event: React.ChangeEvent<HTMLInputElement>) => take(event.target.files?.[0]),
    }),
    React.createElement(
      "div",
      {
        "aria-label": "dropzone",
        onDrop: (event: React.DragEvent<HTMLDivElement>) => {
          event.preventDefault();
          take(event.dataTransfer.files[0]);
        },
      },
      "Drop MP4",
    ),
  );
}
