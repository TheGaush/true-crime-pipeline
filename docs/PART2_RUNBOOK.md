# Part 2 runbook

Part 2 renders the picture, mixes the sound, and packs an upload folder. It does not call Part 1.

## Install

Python 3.12 and FFmpeg are required. From the repo root:

```bash
pnpm install
python3 -m pytest packages/python_motion packages/crime_scene_2k packages/agent6_mastering
```

Node 22 runs the catalog package. The desk UI, when present, is a Vite app under `apps/batch_desk_ui/web`.

## Provider file

`providers.yaml` is the only place rates and model ids live. The default video adapter is the interactions adapter. Two other adapters are listed beside it: the enterprise adapter and the human batch desk. They are not aliases of each other. Packages read the file. Do not copy ids into source.

Offline tests must not open a provider socket. A live check is a separate opt-in.

## Picture and sound

Synthetic scenes take one grain pass. FOIA clips are copied. A safe-zone hit is re-rendered for that scene only, and the heal stops after two passes. The target is under five seconds for one scene.

The master targets -14.0 LUFS and a true peak at or under -1.0 dBTP. If the meter is far from -14, re-run the linear loudness pass on the pre-mixed stems rather than adding a second limiter on the picture.

## What this tree does not use

There is no second database writer. The desk API, when it is running, is the only process that writes `pipeline.db`. Docs in this folder do not describe a retired video-editor pool.
