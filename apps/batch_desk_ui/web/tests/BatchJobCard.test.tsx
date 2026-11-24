import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BatchJobCard } from "../src/components/BatchJobCard";

describe("job card", () => {
  it("copies at most fifteen words and rejects a non-mp4 drop", async () => {
    const copied: string[] = [];
    const files: string[] = [];
    const prompt = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen leftover words";
    render(
      React.createElement(BatchJobCard, {
        prompt,
        mode: "TEXT_TO_VIDEO",
        onCopied: (text: string) => copied.push(text),
        onFile: (name: string) => files.push(name),
      }),
    );
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("blocked"));
    document.execCommand = () => true;
    fireEvent.click(screen.getByRole("button", { name: "Copy Motion Prompt" }));
    await Promise.resolve();
    expect(copied[0].split(/\s+/)).toHaveLength(15);
    expect(copied[0].includes("leftover")).toBe(false);
    fireEvent.drop(screen.getByLabelText("dropzone"), {
      dataTransfer: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] },
    });
    fireEvent.change(screen.getByLabelText("mp4 file"), {
      target: { files: [new File(["x"], "clip.mp4", { type: "video/mp4" })] },
    });
    expect(files).toEqual(["rejected", "clip.mp4"]);
    expect(screen.getByRole("link", { name: "Open Flow in Browser" })).toBeTruthy();
    expect(screen.getByAltText("start bookend")).toBeTruthy();
  });
});
