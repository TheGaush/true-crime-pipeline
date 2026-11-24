$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:TC_ROOT = $Root
$script = @'
import importlib.util, os, sys, time
from pathlib import Path
ROOT = Path(os.environ["TC_ROOT"])

def load(package, stem):
    path = ROOT / "packages" / package / "src" / package / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"m1_{package}_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

started = time.perf_counter()
call = load("crime_scene_2k", "callout_projector")
for name, args in (("A1", (128, 72, 0, 0, 800, 450)), ("J10", (2432, 1368, 1760, 990, 800, 450))):
    point = call.project(*args)
    found = call.ring_centroid(call.render_ring(point))
    error = ((found[0] - point.x) ** 2 + (found[1] - point.y) ** 2) ** 0.5
    if error > 1.0:
        raise SystemExit(f"{name} drift {error}")
tour = load("crime_scene_2k", "tour_sequencer")
anchors = [tour.Anchor(200 + index * 400, 180 + index * 200, 2.4) for index in range(4)]
plan = tour.plan_tour(50, anchors)
if plan.nb_frames != 1500 or plan.peak_zoom > 3.8:
    raise SystemExit(f"tour {plan.nb_frames} {plan.peak_zoom}")
sfx = load("python_motion", "sfx_synth")
engine = sfx.SfxSynthesizer()
names = ("typewriter_key", "stamp_thud", "paper_slide", "bass_drop_hit", "tension_drone_pulse", "camera_shutter", "redaction_swipe", "map_pin_pop", "police_beep_clean", "subtle_whoosh")
cues = [engine.synthesize(sfx.SfxRequest(name, duration_ms=20, seed=index)) for index, name in enumerate(names)]
if any(cue.sample_rate_hz != 48000 for cue in cues):
    raise SystemExit("sfx rate")
book = load("python_motion", "bookend_generator")
pair = book.BookendGenerator().generate(book.BookendRequest("gate", "TEXT_TO_VIDEO", 4, "/tmp/m1-book"))
if not pair.safety_passed or pair.start_frame is not None:
    raise SystemExit("bookend")
hits = [str(path) for path in (ROOT / "packages/render_catalog/src").rglob("*.tsx") if "<feTurbulence" in path.read_text(encoding="utf8") or "<feDisplacementMap" in path.read_text(encoding="utf8")]
if hits:
    raise SystemExit("turbulence")
print(f"PASS drift<=1 tour=1500 sfx=10 bookend=safe turbulence=0 seconds={time.perf_counter() - started:.2f}")
'@
$script | python3 -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
