"""Config-driven cost logger for the non-authoritative telemetry database.

Integer micro-USD rates are loaded only from the YAML path passed to
``TelemetryCostLogger``. A new model key in that file prices with the same
unit fields; this module has no model ids and no price constants.

The logger writes the telemetry database only. It does not open the
admission-control database and does not import escrow code. Each
``log_usage`` call commits on the telemetry connection before returning.

``cached_input_tokens`` must be less than or equal to ``total_input_tokens``.
The logger rejects the opposite before inserting. The schema CHECK is the
second barrier.

``prune(now_ms)`` deletes telemetry rows whose ``created_at`` is strictly
older than 30 days before the injected ``now_ms``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

_ADMISSION_DB_NAME = "pipeline.db"
_TOKEN_TABLE = "api_token_usage"
_PRUNE_TABLES = (_TOKEN_TABLE, "render_timings", "batch_desk_events")

_MS_PER_SECOND = 1000
_SECONDS_PER_DAY = 24 * 60 * 60
_RETENTION_DAYS = 30
_RETENTION_MS = _RETENTION_DAYS * _SECONDS_PER_DAY * _MS_PER_SECOND

# Usage dimension -> rate field. Values are names, not prices.
_UNIT_RATE_KEYS = (
    ("uncached_input_tokens", "zero_cache_input_micro_usd_per_token"),
    ("cached_input_tokens", "cached_input_micro_usd_per_token"),
    ("output_tokens", "output_micro_usd_per_token"),
    ("audio_tokens", "audio_micro_usd_per_token"),
    ("vision_image_count", "vision_micro_usd_per_image"),
    ("video_seconds", "video_micro_usd_per_second"),
)
_RATE_FIELDS = frozenset(rate_key for _unit, rate_key in _UNIT_RATE_KEYS)

_INSERT_USAGE = """
INSERT INTO api_token_usage (
  episode_id,
  agent_name,
  model_id,
  is_off_peak,
  total_input_tokens,
  cached_input_tokens,
  output_tokens,
  vision_image_count,
  audio_tokens,
  cost_micro_usd,
  latency_ms,
  created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class TelemetryCostError(Exception):
    """Base error for telemetry cost logging."""


class CachedTokensExceedTotal(TelemetryCostError):
    """``cached_input_tokens`` is greater than ``total_input_tokens``."""

    def __init__(self, cached_input_tokens: int, total_input_tokens: int) -> None:
        self.cached_input_tokens = cached_input_tokens
        self.total_input_tokens = total_input_tokens
        super().__init__(
            "cached_input_tokens "
            f"({cached_input_tokens}) exceeds total_input_tokens "
            f"({total_input_tokens})"
        )


class UnknownModel(TelemetryCostError):
    """The rates file has no entry for this model id."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"no rates for model {model_id!r}")


class MissingRate(TelemetryCostError):
    """Usage is non-zero and the model entry does not price that unit."""

    def __init__(self, model_id: str, rate_field: str) -> None:
        self.model_id = model_id
        self.rate_field = rate_field
        super().__init__(f"{model_id} has no {rate_field}")


class InvalidRates(TelemetryCostError):
    """The rates file is missing, the wrong shape, or not integer micro-USD."""


class InvalidUsage(TelemetryCostError):
    """A usage argument is the wrong type or out of range."""


@dataclass(frozen=True, slots=True)
class LoggedUsage:
    """One committed telemetry row."""

    row_id: int
    cost_micro_usd: int


@dataclass(frozen=True, slots=True)
class EpisodeSpend:
    """Sum of committed telemetry cost and input tokens for one episode."""

    episode_id: str
    cost_micro_usd: int
    total_input_tokens: int
    cached_input_tokens: int

    @property
    def cache_hit_ratio(self) -> float:
        return _cache_hit_ratio(self.cached_input_tokens, self.total_input_tokens)


def _cache_hit_ratio(cached_input_tokens: int, total_input_tokens: int) -> float:
    if total_input_tokens == 0:
        return float(0)
    return cached_input_tokens / total_input_tokens


def _require_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidUsage(f"{name} must be an int")
    return value


def _require_non_negative_int(name: str, value: object) -> int:
    number = _require_int(name, value)
    if number < 0:
        raise InvalidUsage(f"{name} must be a non-negative int")
    return number


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or value == "":
        raise InvalidUsage(f"{name} must be a non-empty string")
    return value


def resolve_schema_path(schema_path: str | Path | None) -> Path:
    """Return ``schema_path`` or the repo ``schema/telemetry.sql`` above this file."""

    if schema_path is not None:
        path = Path(schema_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "schema" / "telemetry.sql"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("schema/telemetry.sql")


def load_model_rates(rates_path: str | Path) -> dict[str, dict[str, int]]:
    """Load ``models: {model_id: {unit_field: integer micro-USD}}`` from ``rates_path``."""

    path = Path(rates_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise InvalidRates(f"cannot parse rates file {path}") from exc
    if not isinstance(loaded, dict) or isinstance(loaded, list):
        raise InvalidRates("rates file must be a mapping with a models mapping")
    models = loaded.get("models")
    if not isinstance(models, dict) or isinstance(models, list):
        raise InvalidRates("rates file must contain a models mapping")
    parsed: dict[str, dict[str, int]] = {}
    for model_id, spec in models.items():
        if not isinstance(model_id, str) or model_id == "":
            raise InvalidRates("model ids must be non-empty strings")
        if not isinstance(spec, dict) or isinstance(spec, list):
            raise InvalidRates(f"{model_id} rates must be a mapping")
        fields: dict[str, int] = {}
        for field, raw in spec.items():
            if field not in _RATE_FIELDS:
                raise InvalidRates(f"{model_id} has unknown rate field {field}")
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise InvalidRates(
                    f"{model_id}.{field} must be a non-negative integer micro-USD rate"
                )
            fields[field] = raw
        parsed[model_id] = fields
    return parsed


def cost_micro_usd(model_id: str, rates: dict[str, int], quantities: dict[str, int]) -> int:
    """Multiply usage quantities by that model's integer micro-USD rates."""

    total = 0
    for unit, rate_field in _UNIT_RATE_KEYS:
        quantity = quantities[unit]
        if quantity == 0:
            continue
        if rate_field not in rates:
            raise MissingRate(model_id, rate_field)
        total += quantity * rates[rate_field]
    return total


class TelemetryCostLogger:
    """Log provider usage into ``telemetry.db`` and price it from a rates file."""

    def __init__(
        self,
        telemetry_db_path: str | Path,
        rates_path: str | Path,
        *,
        schema_path: str | Path | None = None,
    ) -> None:
        db_path = Path(telemetry_db_path)
        if db_path.name.lower() == _ADMISSION_DB_NAME:
            raise TelemetryCostError(
                "refusing to open pipeline.db; telemetry costs are not admission control"
            )
        self.rates_path = Path(rates_path)
        self._rates = load_model_rates(self.rates_path)
        self.schema_path = resolve_schema_path(schema_path)
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        if db_path.name != ":memory:" and str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._apply_schema(schema_sql)
        except Exception:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> TelemetryCostLogger:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def log_usage(
        self,
        *,
        agent_name: str,
        model_id: str,
        created_at: int,
        episode_id: str | None = None,
        total_input_tokens: int = 0,
        cached_input_tokens: int = 0,
        output_tokens: int = 0,
        vision_image_count: int = 0,
        audio_tokens: int = 0,
        video_seconds: int = 0,
        is_off_peak: int = 0,
        latency_ms: int = 0,
    ) -> LoggedUsage:
        """Price one usage event and commit it to ``api_token_usage``."""

        agent = _require_text("agent_name", agent_name)
        model = _require_text("model_id", model_id)
        stamped = _require_int("created_at", created_at)
        if episode_id is not None:
            episode_id = _require_text("episode_id", episode_id)
        total_input = _require_non_negative_int("total_input_tokens", total_input_tokens)
        cached_input = _require_non_negative_int(
            "cached_input_tokens", cached_input_tokens
        )
        output = _require_non_negative_int("output_tokens", output_tokens)
        images = _require_non_negative_int("vision_image_count", vision_image_count)
        audio = _require_non_negative_int("audio_tokens", audio_tokens)
        video = _require_non_negative_int("video_seconds", video_seconds)
        off_peak = _require_int("is_off_peak", is_off_peak)
        if off_peak not in (0, 1):
            raise InvalidUsage("is_off_peak must be 0 or 1")
        latency = _require_non_negative_int("latency_ms", latency_ms)
        if cached_input > total_input:
            raise CachedTokensExceedTotal(cached_input, total_input)
        model_rates = self._rates.get(model)
        if model_rates is None:
            raise UnknownModel(model)
        priced = cost_micro_usd(
            model,
            model_rates,
            {
                "uncached_input_tokens": total_input - cached_input,
                "cached_input_tokens": cached_input,
                "output_tokens": output,
                "audio_tokens": audio,
                "vision_image_count": images,
                "video_seconds": video,
            },
        )
        try:
            cursor = self._conn.execute(
                _INSERT_USAGE,
                (
                    episode_id,
                    agent,
                    model,
                    off_peak,
                    total_input,
                    cached_input,
                    output,
                    images,
                    audio,
                    priced,
                    latency,
                    stamped,
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        row_id = cursor.lastrowid
        if not isinstance(row_id, int):
            raise TelemetryCostError("telemetry insert did not return a row id")
        return LoggedUsage(row_id=row_id, cost_micro_usd=priced)

    def episode_rollups(self) -> tuple[EpisodeSpend, ...]:
        """Per-episode spend and input-token totals, ordered by episode id."""

        rows = self._conn.execute(
            """
            SELECT episode_id,
                   COALESCE(SUM(cost_micro_usd), 0),
                   COALESCE(SUM(total_input_tokens), 0),
                   COALESCE(SUM(cached_input_tokens), 0)
            FROM api_token_usage
            WHERE episode_id IS NOT NULL
            GROUP BY episode_id
            ORDER BY episode_id
            """
        ).fetchall()
        return tuple(
            EpisodeSpend(
                episode_id=str(episode_id),
                cost_micro_usd=int(cost),
                total_input_tokens=int(total_input),
                cached_input_tokens=int(cached_input),
            )
            for episode_id, cost, total_input, cached_input in rows
        )

    def episode_spend(self, episode_id: str) -> EpisodeSpend:
        """Roll up one episode. Missing episodes return zeros."""

        episode = _require_text("episode_id", episode_id)
        for rollup in self.episode_rollups():
            if rollup.episode_id == episode:
                return rollup
        return EpisodeSpend(
            episode_id=episode,
            cost_micro_usd=0,
            total_input_tokens=0,
            cached_input_tokens=0,
        )

    def cache_hit_ratio(self, episode_id: str | None = None) -> float:
        """``cached_input_tokens / total_input_tokens`` across matching rows.

        Omit ``episode_id`` to roll the ratio across every telemetry row,
        including rows with a null episode id. Zero total input tokens
        yields zero.
        """

        if episode_id is None:
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(cached_input_tokens), 0),
                       COALESCE(SUM(total_input_tokens), 0)
                FROM api_token_usage
                """
            ).fetchone()
        else:
            episode = _require_text("episode_id", episode_id)
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(cached_input_tokens), 0),
                       COALESCE(SUM(total_input_tokens), 0)
                FROM api_token_usage
                WHERE episode_id = ?
                """,
                (episode,),
            ).fetchone()
        if row is None:
            return float(0)
        return _cache_hit_ratio(int(row[0]), int(row[1]))

    def prune(self, now_ms: int) -> int:
        """Delete telemetry rows strictly older than 30 days before ``now_ms``."""

        now = _require_int("now_ms", now_ms)
        cutoff = now - _RETENTION_MS
        deleted = 0
        try:
            for table in _PRUNE_TABLES:
                cursor = self._conn.execute(
                    f"DELETE FROM {table} WHERE created_at < ?",
                    (cutoff,),
                )
                deleted += cursor.rowcount if cursor.rowcount > 0 else 0
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return deleted

    def _apply_schema(self, schema_sql: str) -> None:
        existing = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()
        if existing is not None and int(existing[0]) == 0:
            self._conn.executescript(schema_sql)
            self._conn.commit()
