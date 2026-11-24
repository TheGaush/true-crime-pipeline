import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VisionQaBanner } from "../src/components/VisionQaBanner";

describe("vision banner", () => {
  it("walks upload, pass, strike one, and a locked fallback", () => {
    const { rerender } = render(React.createElement(VisionQaBanner, { state: "uploading" }));
    expect(screen.getByText("Uploading")).toBeTruthy();
    rerender(React.createElement(VisionQaBanner, { state: "passed" }));
    expect(screen.getByText("qa_passed")).toBeTruthy();
    rerender(
      React.createElement(VisionQaBanner, {
        state: "strike1",
        rewrite: "one two three four five six seven eight nine ten eleven",
      }),
    );
    expect(screen.getByText(/Strike 1/).textContent?.split(/\s+/).filter((word) => word !== "Strike" && word !== "1").length).toBeLessThanOrEqual(12);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    rerender(React.createElement(VisionQaBanner, { state: "strike2" }));
    expect(screen.getByText(/0 extra credits spent/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
