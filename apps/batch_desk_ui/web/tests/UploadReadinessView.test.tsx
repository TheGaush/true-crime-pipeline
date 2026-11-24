import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UploadReadinessView } from "../src/components/UploadReadinessView";

const gates = [
  "FACTUAL_ACCURACY",
  "PRIVACY_PII",
  "SOURCE_RIGHTS",
  "SYNTHETIC_DISCLOSURE",
  "ILLUSTRATIVE_LABELING",
];

describe("upload readiness", () => {
  it("stays locked until every gate is approved and the hold is clear", () => {
    const { rerender } = render(
      React.createElement(UploadReadinessView, {
        approvals: gates.slice(0, 4),
        pendingSpotCheck: true,
        legalHold: true,
        lufs: -14,
      }),
    );
    expect(screen.getByRole("button", { name: "Promote locked" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("legal hold")).toBeTruthy();
    rerender(
      React.createElement(UploadReadinessView, {
        approvals: gates,
        pendingSpotCheck: false,
        legalHold: false,
        lufs: -14,
      }),
    );
    expect(screen.getByRole("button", { name: "Promote" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByText(/-14 LUFS/)).toBeTruthy();
  });
});
