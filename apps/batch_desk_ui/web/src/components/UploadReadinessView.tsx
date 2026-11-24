import React from "react";

const GATES = [
  "FACTUAL_ACCURACY",
  "PRIVACY_PII",
  "SOURCE_RIGHTS",
  "SYNTHETIC_DISCLOSURE",
  "ILLUSTRATIVE_LABELING",
];

export function UploadReadinessView({
  approvals,
  pendingSpotCheck,
  legalHold,
  lufs,
}: {
  approvals: string[];
  pendingSpotCheck: boolean;
  legalHold: boolean;
  lufs: number;
}) {
  const ready = GATES.every((gate) => approvals.includes(gate)) && !pendingSpotCheck && !legalHold;
  return React.createElement(
    "section",
    null,
    legalHold ? React.createElement("p", null, "legal hold") : null,
    React.createElement("p", null, `integrated loudness ${lufs} LUFS`),
    React.createElement("p", null, "synthetic disclosure required"),
    React.createElement(
      "button",
      { type: "button", disabled: !ready },
      ready ? "Promote" : "Promote locked",
    ),
  );
}
