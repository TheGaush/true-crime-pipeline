import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PreflightAnimaticModal } from "../src/components/PreflightAnimaticModal";
import { SpatialGridInspector } from "../src/components/SpatialGridInspector";

describe("inspectors", () => {
  it("closes the animatic on escape and seeks a chapter", () => {
    const onClose = vi.fn();
    const onSeek = vi.fn();
    render(
      React.createElement(PreflightAnimaticModal, {
        onClose,
        onSeek,
        chapters: [{ id: "s32", label: "[04:12] Scene S032", seconds: 252 }],
      }),
    );
    fireEvent.keyDown(screen.getByRole("dialog", { name: "animatic" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "[04:12] Scene S032" }));
    expect(onClose).toHaveBeenCalled();
    expect(onSeek).toHaveBeenCalledWith(252);
  });

  it("draws the A to J margin grid", () => {
    render(React.createElement(SpatialGridInspector, { showGrid: true }));
    expect(screen.getByText("A1")).toBeTruthy();
    expect(screen.getByText("J10")).toBeTruthy();
  });
});
