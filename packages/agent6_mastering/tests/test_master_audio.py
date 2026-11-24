import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "master_audio.py"
_SPEC = importlib.util.spec_from_file_location("tc166_master", _PATH)
assert _SPEC and _SPEC.loader
audio = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = audio
_SPEC.loader.exec_module(audio)


def test_script_file_and_integrated_loudness(tmp_path: Path):
    script = audio.build_script(500, 1.0)
    assert script.count("adelay=") == 500
    assert script.count("normalize=0[submix_") == 16
    assert "-filter_complex" not in script
    made = audio.master(str(tmp_path / "master.wav"), cue_count=8, duration_sec=2.0)
    assert Path(made["script"]).name == "audio_graph.ffscript"
    assert abs(made["integrated_lufs"] - (-14.0)) <= 1.0
