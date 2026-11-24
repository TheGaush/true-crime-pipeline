"""Offline tests for the config-driven telemetry cost logger."""

from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import telemetry_repo  # noqa: E402
from telemetry_repo import (  # noqa: E402
    CachedTokensExceedTotal,
    InvalidRates,
    InvalidUsage,
    MissingRate,
    TelemetryCostError,
    TelemetryCostLogger,
    UnknownModel,
)

_REPO = Path(__file__).resolve().parents[3]
_SCHEMA = _REPO / "schema" / "telemetry.sql"
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "telemetry_rates.yaml"
_MODULE = _SRC / "telemetry_repo.py"
_THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000
_DEEPSEEK = "DeepSeek-V4.1-Flash-1017"
_TTS = "gemini-3.8-flash-tts"
_VIDEO = "gemini-omni-1.2-flash"
_IMAGE = "gemini-image"


def _rates() -> dict:
    loaded = yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))
    return loaded["models"]


def _logger(tmp_path: Path, rates_path: Path | None = None) -> TelemetryCostLogger:
    return TelemetryCostLogger(
        tmp_path / "telemetry.db",
        rates_path or _FIXTURE,
        schema_path=_SCHEMA,
    )


def _count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM api_token_usage").fetchone()
    assert row is not None
    return int(row[0])


def test_fixture_carries_required_rates() -> None:
    models = _rates()
    deepseek = models[_DEEPSEEK]
    assert deepseek["zero_cache_input_micro_usd_per_token"] > 0
    assert deepseek["cached_input_micro_usd_per_token"] > 0
    assert (
        deepseek["zero_cache_input_micro_usd_per_token"]
        != deepseek["cached_input_micro_usd_per_token"]
    )
    assert models[_TTS]["audio_micro_usd_per_token"] > 0
    assert models[_VIDEO]["video_micro_usd_per_second"] == 100_000
    assert "zero_cache_input_micro_usd_per_token" not in models[_VIDEO]


def test_schema_check_rejects_cached_tokens_above_total(tmp_path: Path) -> None:
    schema = _SCHEMA.read_text(encoding="utf-8")
    assert "cached_input_tokens <= total_input_tokens" in schema
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        logger.log_usage(
            agent_name="agent4",
            model_id=_DEEPSEEK,
            created_at=1_700_000_000_000,
            episode_id="ep-check",
            total_input_tokens=10,
            cached_input_tokens=4,
            output_tokens=1,
        )
    with sqlite3.connect(db_path) as conn:
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'api_token_usage'"
        ).fetchone()
        assert table_sql is not None
        assert "cached_input_tokens <= total_input_tokens" in str(table_sql[0])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO api_token_usage (
                  episode_id, agent_name, model_id, is_off_peak,
                  total_input_tokens, cached_input_tokens, output_tokens,
                  cost_micro_usd, created_at
                ) VALUES ('ep-check', 'agent4', ?, 0, 10, 11, 0, 0, 1)
                """,
                (_DEEPSEEK,),
            )


def test_logger_refuses_cached_tokens_above_total_before_write(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        with pytest.raises(CachedTokensExceedTotal) as raised:
            logger.log_usage(
                agent_name="agent4",
                model_id="not-a-priced-model",
                created_at=10,
                total_input_tokens=4,
                cached_input_tokens=5,
            )
    assert raised.value.cached_input_tokens == 5
    assert raised.value.total_input_tokens == 4
    assert _count(db_path) == 0


def test_full_cache_and_zero_cache_use_distinct_deepseek_rates(tmp_path: Path) -> None:
    deepseek = _rates()[_DEEPSEEK]
    zero = deepseek["zero_cache_input_micro_usd_per_token"]
    cached = deepseek["cached_input_micro_usd_per_token"]
    output = deepseek["output_micro_usd_per_token"]
    with _logger(tmp_path) as logger:
        zero_hit = logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=20,
            episode_id="ep-cache",
            total_input_tokens=1000,
            cached_input_tokens=0,
            output_tokens=20,
        )
        full_hit = logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=21,
            episode_id="ep-cache",
            total_input_tokens=500,
            cached_input_tokens=500,
            output_tokens=0,
        )
        partial = logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=22,
            episode_id="ep-cache",
            total_input_tokens=1000,
            cached_input_tokens=400,
            output_tokens=50,
        )
    assert zero_hit.cost_micro_usd == 1000 * zero + 20 * output
    assert zero_hit.cost_micro_usd != 1000 * cached + 20 * output
    assert full_hit.cost_micro_usd == 500 * cached
    assert full_hit.cost_micro_usd != 500 * zero
    assert partial.cost_micro_usd == 600 * zero + 400 * cached + 50 * output


def test_tts_image_and_video_rates_come_from_yaml(tmp_path: Path) -> None:
    models = _rates()
    audio_rate = models[_TTS]["audio_micro_usd_per_token"]
    image_rate = models[_IMAGE]["vision_micro_usd_per_image"]
    per_second = models[_VIDEO]["video_micro_usd_per_second"]
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        speech = logger.log_usage(
            agent_name="voice",
            model_id=_TTS,
            created_at=30,
            episode_id="ep-media",
            audio_tokens=40,
        )
        still = logger.log_usage(
            agent_name="plates",
            model_id=_IMAGE,
            created_at=31,
            episode_id="ep-media",
            vision_image_count=3,
        )
        clip = logger.log_usage(
            agent_name="hero",
            model_id=_VIDEO,
            created_at=32,
            episode_id="ep-media",
            video_seconds=8,
            is_off_peak=1,
        )
        same_price_on_peak = logger.log_usage(
            agent_name="hero",
            model_id=_VIDEO,
            created_at=33,
            episode_id="ep-media",
            video_seconds=8,
            is_off_peak=0,
        )
    assert speech.cost_micro_usd == 40 * audio_rate
    assert still.cost_micro_usd == 3 * image_rate
    assert clip.cost_micro_usd == 8 * per_second
    assert same_price_on_peak.cost_micro_usd == clip.cost_micro_usd
    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            """
            SELECT cost_micro_usd, typeof(cost_micro_usd), is_off_peak
            FROM api_token_usage
            WHERE id = ?
            """,
            (clip.row_id,),
        ).fetchone()
    assert stored == (8 * per_second, "integer", 1)


def test_new_model_key_prices_without_a_code_change(tmp_path: Path) -> None:
    source = _MODULE.read_text(encoding="utf-8")
    assert "DeepSeek-V4.2" not in source
    rates_path = tmp_path / "new-model.yaml"
    rates_path.write_text(
        """
models:
  DeepSeek-V4.2:
    zero_cache_input_micro_usd_per_token: 7
    cached_input_micro_usd_per_token: 1
    output_micro_usd_per_token: 9
""",
        encoding="utf-8",
    )
    with _logger(tmp_path, rates_path) as logger:
        logged = logger.log_usage(
            agent_name="ledger",
            model_id="DeepSeek-V4.2",
            created_at=40,
            episode_id="ep-new",
            total_input_tokens=10,
            cached_input_tokens=4,
            output_tokens=3,
        )
    assert logged.cost_micro_usd == 6 * 7 + 4 * 1 + 3 * 9


def test_same_model_id_follows_the_file_that_was_passed(tmp_path: Path) -> None:
    cheap = tmp_path / "cheap.yaml"
    dear = tmp_path / "dear.yaml"
    cheap.write_text(
        "models:\n  shared-model:\n    output_micro_usd_per_token: 3\n",
        encoding="utf-8",
    )
    dear.write_text(
        "models:\n  shared-model:\n    output_micro_usd_per_token: 19\n",
        encoding="utf-8",
    )
    with _logger(tmp_path / "cheap", cheap) as logger:
        logged = logger.log_usage(
            agent_name="script",
            model_id="shared-model",
            created_at=41,
            output_tokens=5,
        )
    assert logged.cost_micro_usd == 15
    with _logger(tmp_path / "dear", dear) as logger:
        logged = logger.log_usage(
            agent_name="script",
            model_id="shared-model",
            created_at=42,
            output_tokens=5,
        )
    assert logged.cost_micro_usd == 95


def test_unknown_model_and_missing_unit_do_not_insert(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        with pytest.raises(UnknownModel):
            logger.log_usage(
                agent_name="script",
                model_id="missing-model",
                created_at=50,
                output_tokens=1,
            )
        with pytest.raises(MissingRate):
            logger.log_usage(
                agent_name="hero",
                model_id=_VIDEO,
                created_at=51,
                output_tokens=2,
            )
    assert _count(db_path) == 0


def test_float_rate_is_rejected_and_does_not_create_the_database(tmp_path: Path) -> None:
    rates_path = tmp_path / "float.yaml"
    rates_path.write_text(
        """
models:
  gemini-omni-1.2-flash:
    video_micro_usd_per_second: 0.10
""",
        encoding="utf-8",
    )
    db_path = tmp_path / "telemetry.db"
    with pytest.raises(InvalidRates):
        TelemetryCostLogger(db_path, rates_path, schema_path=_SCHEMA)
    assert not db_path.exists()


def test_episode_spend_and_cross_episode_cache_hit_ratio(tmp_path: Path) -> None:
    deepseek = _rates()[_DEEPSEEK]
    zero = deepseek["zero_cache_input_micro_usd_per_token"]
    cached = deepseek["cached_input_micro_usd_per_token"]
    per_second = _rates()[_VIDEO]["video_micro_usd_per_second"]
    with _logger(tmp_path) as logger:
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=60,
            episode_id="ep-a",
            total_input_tokens=1000,
            cached_input_tokens=200,
            output_tokens=0,
        )
        logger.log_usage(
            agent_name="hero",
            model_id=_VIDEO,
            created_at=61,
            episode_id="ep-a",
            video_seconds=2,
        )
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=62,
            episode_id="ep-b",
            total_input_tokens=1000,
            cached_input_tokens=800,
            output_tokens=0,
        )
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=63,
            episode_id=None,
            total_input_tokens=100,
            cached_input_tokens=25,
            output_tokens=0,
        )
        rollups = {item.episode_id: item for item in logger.episode_rollups()}
        episode_a = logger.episode_spend("ep-a")
        assert logger.episode_spend("missing").cost_micro_usd == 0
        assert logger.episode_spend("missing").cache_hit_ratio == 0.0
        assert logger.cache_hit_ratio("ep-a") == episode_a.cache_hit_ratio
        assert logger.cache_hit_ratio() == (200 + 800 + 25) / (1000 + 1000 + 100)
    token_cost_a = 800 * zero + 200 * cached
    assert episode_a.cost_micro_usd == token_cost_a + 2 * per_second
    assert episode_a.total_input_tokens == 1000
    assert episode_a.cached_input_tokens == 200
    assert episode_a.cache_hit_ratio == 0.2
    assert rollups["ep-b"].cost_micro_usd == 200 * zero + 800 * cached
    assert rollups["ep-b"].cache_hit_ratio == 0.8
    assert set(rollups) == {"ep-a", "ep-b"}


def test_prune_uses_injected_now_and_keeps_the_thirty_day_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    now_ms = 1_800_000_000_000
    boundary = now_ms - _THIRTY_DAYS_MS
    with _logger(tmp_path) as logger:
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=boundary - 1,
            episode_id="old",
            output_tokens=1,
        )
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=boundary,
            episode_id="boundary",
            output_tokens=1,
        )
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=now_ms,
            episode_id="fresh",
            output_tokens=1,
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO render_timings (
                  episode_id, scene_id, visual_engine, duration_ms,
                  wall_time_ms, local_re_render, created_at
                ) VALUES ('old', 'scene', 'engine', 1, 1, 0, ?)
                """,
                (boundary - 1,),
            )
            conn.execute(
                """
                INSERT INTO render_timings (
                  episode_id, scene_id, visual_engine, duration_ms,
                  wall_time_ms, local_re_render, created_at
                ) VALUES ('fresh', 'scene', 'engine', 1, 1, 0, ?)
                """,
                (now_ms,),
            )
            conn.execute(
                """
                INSERT INTO batch_desk_events (
                  account_id, flow_job_id, event_type, created_at
                ) VALUES ('acct', 'job', 'shift_open', ?)
                """,
                (boundary - 1,),
            )
            conn.execute(
                """
                INSERT INTO batch_desk_events (
                  account_id, flow_job_id, event_type, created_at
                ) VALUES ('acct', 'job', 'shift_close', ?)
                """,
                (now_ms,),
            )
        assert logger.prune(now_ms) == 3
        assert logger.prune(boundary) == 0
        with sqlite3.connect(db_path) as conn:
            episodes = {
                row[0]
                for row in conn.execute("SELECT episode_id FROM api_token_usage")
            }
            render_episodes = {
                row[0]
                for row in conn.execute("SELECT episode_id FROM render_timings")
            }
            events = {
                row[0]
                for row in conn.execute("SELECT event_type FROM batch_desk_events")
            }
    assert episodes == {"boundary", "fresh"}
    assert render_episodes == {"fresh"}
    assert events == {"shift_close"}


def test_negative_usage_and_off_peak_flag_are_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        with pytest.raises(InvalidUsage):
            logger.log_usage(
                agent_name="script",
                model_id=_DEEPSEEK,
                created_at=70,
                output_tokens=-1,
            )
        with pytest.raises(InvalidUsage):
            logger.log_usage(
                agent_name="hero",
                model_id=_VIDEO,
                created_at=71,
                video_seconds=1,
                is_off_peak=2,
            )
        with pytest.raises(InvalidUsage):
            logger.log_usage(
                agent_name="hero",
                model_id=_VIDEO,
                created_at=72,
                video_seconds=1,
                is_off_peak=True,  # type: ignore[arg-type]
            )
    assert _count(db_path) == 0


def test_refuses_pipeline_db_and_does_not_create_it(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "pipeline.db"
    with pytest.raises(TelemetryCostError):
        TelemetryCostLogger(target, _FIXTURE, schema_path=_SCHEMA)
    assert not target.exists()
    assert not target.parent.exists()
    with _logger(tmp_path) as logger:
        assert logger.db_path.name == "telemetry.db"
    names = {path.name for path in tmp_path.iterdir()}
    assert "pipeline.db" not in names
    assert "telemetry.db" in names


def test_reopen_applies_schema_once(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    with _logger(tmp_path) as logger:
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=80,
            episode_id="ep-reopen",
            output_tokens=2,
        )
    with TelemetryCostLogger(db_path, _FIXTURE, schema_path=_SCHEMA) as logger:
        assert logger.episode_spend("ep-reopen").total_input_tokens == 0
        assert logger.episode_spend("ep-reopen").cost_micro_usd > 0


def test_default_schema_path_is_repo_telemetry_sql(tmp_path: Path) -> None:
    with TelemetryCostLogger(tmp_path / "telemetry.db", _FIXTURE) as logger:
        assert logger.schema_path.resolve() == _SCHEMA.resolve()
        logger.log_usage(
            agent_name="script",
            model_id=_DEEPSEEK,
            created_at=90,
            output_tokens=1,
        )


def test_module_has_no_price_literals_or_escrow_imports() -> None:
    source = _MODULE.read_text(encoding="utf-8")
    assert "100000" not in source
    assert "100_000" not in source
    assert "0.10" not in source
    assert "$" not in source
    assert "providers.yaml" not in source
    tree = ast.parse(source)
    numbers: list[int | float] = []
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            numbers.append(node.value)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.append(module)
            imported.extend(alias.name for alias in node.names)
    assert numbers
    assert all(isinstance(number, int) for number in numbers)
    assert set(numbers) <= {0, 1, 24, 30, 60, 1000}
    joined = " ".join(imported).lower()
    assert "escrow" not in joined
    assert "budget" not in joined
    assert "pipeline" not in joined
