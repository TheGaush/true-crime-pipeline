"""Run the offline episode, or an opt-in live episode when --live is set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from integration_bridge.live_episode import LiveError, run_live
from integration_bridge.mvp_slice import run_slice
from integration_bridge.pipeline_run import workflow_report


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m integration_bridge")
    parser.add_argument("--out", default="artifacts/offline-run", help="Directory for pipeline.db and master.mp4")
    parser.add_argument("--live", action="store_true", help="Write the script with DeepSeek, draw a moving illustrated scene for each line, and speak with Gemini.")
    parser.add_argument("--topic", default="", help="Subject of the live episode.")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.live:
        try:
            receipt = run_live(out, args.topic)
        except LiveError as exc:
            print(str(exc))
            return 1
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if Path(receipt["master"]).is_file() else 1
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
    if master["nb_frames"] != 2700 or abs(master["integrated_lufs"] - (-14.0)) > 1.0:
        return 1
    if not receipt["voice"]["lines"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
