import React from "react";

const COLUMNS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];

export function SpatialGridInspector({ showGrid }: { showGrid: boolean }) {
  if (!showGrid) return React.createElement("p", null, "grid hidden");
  const cells = [];
  for (const column of COLUMNS) {
    for (let row = 1; row <= 10; row += 1) cells.push(`${column}${row}`);
  }
  return React.createElement(
    "div",
    { "aria-label": "margin grid" },
    ...cells.map((cell) => React.createElement("span", { key: cell }, cell)),
  );
}
