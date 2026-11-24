"""Run the offline 90-second slice. Spend stays at $0."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from integration_bridge.mvp_slice import run_slice
from integration_bridge.pipeline_run import workflow_report


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m integration_bridge")
    parser.add_argument("--out", default="artifacts/offline-run", help="Directory for pipeline.db and master.mp4")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    receipt = run_slice(str(out / "pipeline.db"), str(out / "master.mp4"))
    receipt["workflow"] = workflow_report()
    print(json.dumps(receipt, indent=2, sort_keys=True))
    master = receipt["master"]
    if receipt["released_without_gates"]:
        return 1
    if receipt["state"] != "READY_TO_UPLOAD":
        return 1
    if receipt["transport"]["spend_usd"] != 0.0:
        return 1
    if master["nb_frames"] != 2700 or master["integrated_lufs"] != -14.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
