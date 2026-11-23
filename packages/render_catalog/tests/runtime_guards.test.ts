import { expect, test, vi } from "vitest";

vi.mock("../src/theme/CaseBibleContext.tsx", () => ({
  useCaseBible: () => ({ paperBgHex: "#E9E2D2" }),
}));

import {
  ADVERSARIAL_LABEL,
  ADVERSARIAL_LABEL_WORDS,
  AUDITED_MOTIFS,
  BOTTOM_BAND_PX,
  BOTTOM_BAND_RATIO,
  EXCLUSION_HEIGHT_RATIO,
  EXCLUSION_WIDTH_RATIO,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  TOP_BAND_PX,
  TOP_BAND_RATIO,
  WRAP_CLAMP_Y,
  auditSafeZoneInChromium,
  buildAuditHtml,
  safeZoneBands,
} from "../src/guards/RuntimeGuards.ts";

test("safe-zone bands match SafeZoneLayout", () => {
  const bands = safeZoneBands();
  expect(FRAME_WIDTH).toBe(1920);
  expect(FRAME_HEIGHT).toBe(1080);
  expect(TOP_BAND_PX).toBe(108);
  expect(TOP_BAND_PX / FRAME_HEIGHT).toBe(TOP_BAND_RATIO);
  expect(BOTTOM_BAND_PX).toBe(194);
  expect(Math.abs(BOTTOM_BAND_PX / FRAME_HEIGHT - BOTTOM_BAND_RATIO)).toBeLessThan(0.001);
  expect(EXCLUSION_WIDTH_RATIO).toBe(0.22);
  expect(EXCLUSION_HEIGHT_RATIO).toBe(0.14);
  expect(bands.top).toEqual({ x: 0, y: 0, width: 1920, height: 108 });
  expect(bands.bottom.y).toBe(1080 - 194);
  expect(bands.exclusion.width).toBeCloseTo(1920 * 0.22, 5);
  expect(bands.exclusion.height).toBeCloseTo(1080 * 0.14, 5);
  expect(bands.exclusion.x).toBeCloseTo(1920 * 0.78, 5);
  expect(bands.exclusion.y).toBeCloseTo(1080 * 0.86, 5);
  expect(WRAP_CLAMP_Y).toBe(885);
  expect(ADVERSARIAL_LABEL_WORDS).toHaveLength(12);
  expect(ADVERSARIAL_LABEL.split(/\s+/)).toEqual([...ADVERSARIAL_LABEL_WORDS]);
});

test("chromium getBoundingClientRect finds no safe-zone leaks", async () => {
  const html = buildAuditHtml();
  for (const motif of AUDITED_MOTIFS) {
    expect(html).toContain(`data-audit-stage="${motif}"`);
  }
  expect(html).toContain(ADVERSARIAL_LABEL);
  expect(html).toContain("data-audit-probe=\"clamped\"");
  expect(html).toContain("-webkit-line-clamp:3");

  const audit = await auditSafeZoneInChromium();
  expect(audit.motifs).toEqual([...AUDITED_MOTIFS]);
  expect(audit.measuredText).toBeGreaterThan(12);
  expect(audit.probe.unclampedBottom).toBeGreaterThan(WRAP_CLAMP_Y);
  expect(audit.probe.clampedBottom).toBeLessThanOrEqual(WRAP_CLAMP_Y + 0.5);
  expect(audit.probe.clampedHeight).toBeLessThanOrEqual(audit.probe.maxHeight + 0.75);
  expect(audit.probe.clampedBottom).toBeLessThan(audit.probe.unclampedBottom);
  expect(audit.leaks, JSON.stringify(audit.leaks, null, 2)).toEqual([]);
}, 60_000);
