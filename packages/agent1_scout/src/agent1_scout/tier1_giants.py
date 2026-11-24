"""Tier-1 true-crime giant channel registry for mutually exclusive SI bucketing.

``Tier1GiantMatcher`` identifies uploads from configured network / giant
channels. It does not compute SI itself (see Task 020 ``SaturationCalculator``).

For a Tier-1 match:

* Upload age <= 14 days -> ``N_14d_excl``, ``instant_kill = True``.
  The video must not also be tagged ``N_mega_decayed`` (14-day bucket wins).
* Older Tier-1 upload -> ``N_mega_decayed``, ``instant_kill = False``.
* Non-match -> bucket ``NONE``.

Channels match on canonical ``channel_id`` or on normalized title (casefold,
strip punctuation, collapse whitespace). Extra giants load from an optional
YAML path at construction time. No network calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - tests install PyYAML in the local venv
    yaml = None  # type: ignore[assignment]

MS_PER_DAY = 24 * 60 * 60 * 1000
DAYS_14 = 14

BUCKET_14D = "N_14d_excl"
BUCKET_MEGA = "N_mega_decayed"
BUCKET_NONE = "NONE"

_DEFAULT_YAML = Path(__file__).with_name("tier1_giants.yaml")

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class GiantVideo:
    """Minimal YouTube upload fields for giant matching."""

    channel_id: str
    channel_title: str
    published_at_ms: int


@dataclass(frozen=True, slots=True)
class GiantEntry:
    key: str
    titles: tuple[str, ...]
    channel_ids: tuple[str, ...]
    normalized_titles: frozenset[str]


@dataclass(frozen=True, slots=True)
class Tier1GiantClassification:
    """Single-bucket outcome for one upload."""

    is_tier1_giant: bool
    bucket: str
    instant_kill: bool
    matched_giant_key: str | None = None
    age_days: float | None = None


def normalize_title(title: str) -> str:
    """Casefold, strip punctuation, collapse whitespace."""

    folded = title.casefold().strip()
    without_punct = _PUNCT_RE.sub("", folded)
    return " ".join(without_punct.split())


def _coerce_str_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} entries must be strings")
        text = item.strip()
        if text:
            out.append(text)
    return out


def _entry_from_mapping(raw: Any) -> GiantEntry:
    if not isinstance(raw, dict):
        raise ValueError("each giant must be a mapping")
    key = raw.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("giant.key must be a non-empty string")
    titles = _coerce_str_list(raw.get("titles"), "titles")
    channel_ids = _coerce_str_list(raw.get("channel_ids"), "channel_ids")
    if not titles and not channel_ids:
        raise ValueError(f"giant {key!r} needs titles and/or channel_ids")
    normalized = frozenset(normalize_title(t) for t in titles)
    return GiantEntry(
        key=key.strip(),
        titles=tuple(titles),
        channel_ids=tuple(channel_ids),
        normalized_titles=normalized,
    )


def _parse_giants_yaml(text: str) -> list[GiantEntry]:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load giant YAML files; pip install PyYAML",
        )
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("root YAML document must be a mapping")
    giants = data.get("giants")
    if not isinstance(giants, list):
        raise ValueError("YAML must contain a giants list")
    return [_entry_from_mapping(item) for item in giants]


def _load_yaml_file(path: Path) -> list[GiantEntry]:
    return _parse_giants_yaml(path.read_text(encoding="utf-8"))


def _merge_entries(*groups: list[GiantEntry]) -> tuple[GiantEntry, ...]:
    by_key: dict[str, GiantEntry] = {}
    for group in groups:
        for entry in group:
            if entry.key in by_key:
                prev = by_key[entry.key]
                titles = tuple(dict.fromkeys(prev.titles + entry.titles))
                channel_ids = tuple(dict.fromkeys(prev.channel_ids + entry.channel_ids))
                normalized = frozenset(
                    normalize_title(t) for t in titles
                )
                entry = GiantEntry(
                    key=entry.key,
                    titles=titles,
                    channel_ids=channel_ids,
                    normalized_titles=normalized,
                )
            by_key[entry.key] = entry
    return tuple(by_key[k] for k in sorted(by_key))


class Tier1GiantMatcher:
    """Classify uploads from Tier-1 giant channels into one SI bucket."""

    def __init__(
        self,
        *,
        extra_yaml_path: str | Path | None = None,
        default_yaml_path: str | Path | None = None,
    ) -> None:
        default_path = (
            Path(default_yaml_path) if default_yaml_path is not None else _DEFAULT_YAML
        )
        default_entries = _load_yaml_file(default_path)
        extra_entries: list[GiantEntry] = []
        if extra_yaml_path is not None:
            extra_entries = _load_yaml_file(Path(extra_yaml_path))
        self._entries = _merge_entries(default_entries, extra_entries)
        self._id_index: dict[str, str] = {}
        self._title_index: dict[str, str] = {}
        for entry in self._entries:
            for channel_id in entry.channel_ids:
                self._id_index[channel_id] = entry.key
            for norm in entry.normalized_titles:
                self._title_index[norm] = entry.key

    @property
    def giant_keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self._entries)

    def is_giant_channel(self, video: GiantVideo) -> bool:
        return self._resolve_key(video) is not None

    def classify(self, video: GiantVideo, now_ms: int) -> Tier1GiantClassification:
        matched_key = self._resolve_key(video)
        if matched_key is None:
            return Tier1GiantClassification(
                is_tier1_giant=False,
                bucket=BUCKET_NONE,
                instant_kill=False,
            )

        age_days = (now_ms - video.published_at_ms) / MS_PER_DAY
        if age_days <= DAYS_14:
            return Tier1GiantClassification(
                is_tier1_giant=True,
                bucket=BUCKET_14D,
                instant_kill=True,
                matched_giant_key=matched_key,
                age_days=age_days,
            )

        return Tier1GiantClassification(
            is_tier1_giant=True,
            bucket=BUCKET_MEGA,
            instant_kill=False,
            matched_giant_key=matched_key,
            age_days=age_days,
        )

    def _resolve_key(self, video: GiantVideo) -> str | None:
        channel_id = video.channel_id.strip()
        if channel_id and channel_id in self._id_index:
            return self._id_index[channel_id]
        norm_title = normalize_title(video.channel_title)
        if norm_title in self._title_index:
            return self._title_index[norm_title]
        return None