# agent6 mastering

Overnight assembly for a 1920x1080, 30 fps documentary. The package reads a scene plan and a voice manifest and writes a ready-to-upload pack.

## Commands

```bash
python -m agent6_mastering run --episode-dir workspace/ep_golden_01
```

Stages, in order: ingest, per-track loudness, one grain pass, mux, safe-zone and contact-sheet review, export. A restart reads `overnight_state.json` and continues at the interrupted stage.

## Loudness and picture

Narration is pre-normalized near -16 LUFS, evidence near -18 LUFS, and the music bed near -22 LUFS before the mix. The final master targets -14.0 LUFS and a true peak at or under -1.0 dBTP. FOIA pictures are copied through. Synthetic scenes take a single grain pass.

## Empty inputs

`sound_cues_json` may be an empty list. An episode with no FOIA scene is valid. Neither case is an error.

## Environment

No provider key is read here. Temp files live under the episode directory and are removed after the export checksum is written.
