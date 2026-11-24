"""Gemini YouTube URL x-ray (`youtube-xray@2`) with an age-gate fallback.

Playback that Gemini can actually watch returns factual lead keys in
`AGENTIC_VIDEO` mode. `PLAYBACK_RESTRICTED` and `AGE_GATED` fall back to
authorized `videos.list` fields (`title`, `description`, `tags`) plus public
`commentThreads.list` questions, labeled `LEAD_ONLY`. Comments and metadata
are lookup leads, not confirmed facts.

The model id is loaded from the gemini-family `youtube_xray` entry in
`providers.yaml`. This module does not download MP4s and does not call
`captions.download`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

CONTRACT_ID = "youtube-xray@2"
MAX_YOUTUBE_URLS = 5
SOURCE_AGENTIC_VIDEO = "AGENTIC_VIDEO"
SOURCE_LEAD_ONLY = "LEAD_ONLY"
LEAD_CLASSIFICATION_FACTUAL = "FACTUAL"
LEAD_CLASSIFICATION_LEAD_ONLY = "LEAD_ONLY"
PLAYBACK_RESTRICTED = "PLAYBACK_RESTRICTED"
AGE_GATED = "AGE_GATED"
BLOCKED_PLAYBACK = frozenset({PLAYBACK_RESTRICTED, AGE_GATED})
YOUTUBE_XRAY_ROLE = "youtube_xray"
VIDEO_FIELDS = "items(snippet(title,description,tags))"
AUTHORIZED_METADATA_FIELDS = ("title", "description", "tags")
LEAD_LIST_KEYS = (
    "suspect_names",
    "victim_names",
    "docket_ids",
    "unanswered_comment_questions",
)
LEAD_TEXT_KEYS = ("incident_date_or_year", "county_state")
SEED_LEAD_KEYS = (
    "suspect_names",
    "victim_names",
    "incident_date_or_year",
    "county_state",
    "docket_ids",
    "unanswered_comment_questions",
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_QUESTION = re.compile(r"[^.!?\n]*\?")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_MP4 = re.compile(r"(?i)(?:\.mp4(?:$|[?#])|(?:^|[/?&=])(?:mime|type)=video/mp4\b)")
_LABELED_FIELDS = (
    (
        "suspect_names",
        re.compile(r"(?i)\b(?:suspect_names|suspects|suspect)\s*[:=]\s*([^\n;]+)"),
    ),
    (
        "victim_names",
        re.compile(r"(?i)\b(?:victim_names|victims|victim)\s*[:=]\s*([^\n;]+)"),
    ),
    (
        "incident_date_or_year",
        re.compile(
            r"(?i)\b(?:incident_date_or_year|incident_date|year|date)\s*[:=]\s*([^\n;]+)"
        ),
    ),
    (
        "county_state",
        re.compile(r"(?i)\bcounty_state\s*[:=]\s*([^\n;]+)"),
    ),
    (
        "docket_ids",
        re.compile(r"(?i)\b(?:docket_ids|dockets|docket)\s*[:=]\s*([^\n;]+)"),
    ),
)
_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)


class UnsupportedCaptionsDownload(RuntimeError):
    """`captions.download` is not available on this client.

    The YouTube Data API captions.download method requires edit permission on
    the target video. Agent 1 does not scrape third-party captions.
    """


class TooManyYouTubeUrls(ValueError):
    """Gemini receives at most five YouTube URLs per inspection."""


class Mp4DownloadForbidden(ValueError):
    """X-ray accepts YouTube watch URLs and never downloads MP4 bytes."""


class YouTubeXRayModelError(LookupError):
    """`providers.yaml` has no gemini-family model for the x-ray role."""


@dataclass
class YouTubeXRayResult:
    """One URL after agentic playback or the authorized-metadata fallback."""

    url: str
    video_id: str
    model_id: str
    contract_id: str
    source_mode: str
    lead_classification: str
    lead_keys: dict[str, Any]
    facts_confirmed: bool
    comments_are_confirmed_facts: bool
    metadata_is_confirmed_facts: bool
    authorized_metadata: dict[str, Any] | None
    public_comment_questions: list[str]
    playback_block: str | None
    mp4_downloaded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "video_id": self.video_id,
            "model_id": self.model_id,
            "contract_id": self.contract_id,
            "source_mode": self.source_mode,
            "lead_classification": self.lead_classification,
            "lead_keys": dict(self.lead_keys),
            "facts_confirmed": self.facts_confirmed,
            "comments_are_confirmed_facts": self.comments_are_confirmed_facts,
            "metadata_is_confirmed_facts": self.metadata_is_confirmed_facts,
            "authorized_metadata": (
                None if self.authorized_metadata is None else dict(self.authorized_metadata)
            ),
            "public_comment_questions": list(self.public_comment_questions),
            "playback_block": self.playback_block,
            "mp4_downloaded": self.mp4_downloaded,
        }


class _UnsupportedCaptions:
    """Any captions request fails closed. There is no download implementation."""

    def download(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedCaptionsDownload(
            "captions.download is unsupported; it requires video edit rights"
        )

    def list(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedCaptionsDownload(
            "captions.download is unsupported; it requires video edit rights"
        )

    def __getattr__(self, name: str) -> Any:
        raise UnsupportedCaptionsDownload(
            "captions.download is unsupported; it requires video edit rights"
        )


def default_providers_yaml() -> Path:
    """Locate `providers.yaml` by walking parents of this module."""

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "providers.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("providers.yaml was not found above the x-ray package")


def load_youtube_xray_model_id(path: str | Path) -> str:
    """Return the first gemini-family model id whose roles include `youtube_xray`.

    The id is whatever `providers.yaml` contains. This loader is the only
    place that reads it.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"providers.yaml not found: {source}")
    ids = _gemini_role_model_ids(source.read_text(encoding="utf-8"), role=YOUTUBE_XRAY_ROLE)
    if not ids:
        raise YouTubeXRayModelError(
            "providers.yaml has no gemini-family model with role youtube_xray"
        )
    return ids[0]


def _scalar(value: str) -> str:
    text = value.strip()
    if " #" in text:
        text = text.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text.strip()


def _gemini_role_model_ids(text: str, *, role: str) -> list[str]:
    ids: list[str] = []
    in_providers = False
    in_gemini = False
    in_models = False
    collecting_roles = False
    current_id: str | None = None
    current_roles: list[str] = []

    def finish() -> None:
        nonlocal current_id, current_roles, collecting_roles
        if in_gemini and current_id and role in current_roles:
            ids.append(current_id)
        current_id = None
        current_roles = []
        collecting_roles = False

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        if indent == 0 and line == "providers:":
            finish()
            in_providers = True
            in_gemini = False
            in_models = False
            continue
        if indent == 0 and line.endswith(":") and line != "providers:":
            finish()
            in_providers = False
            in_gemini = False
            in_models = False
            continue
        if not in_providers:
            continue

        if indent == 2 and line.endswith(":") and not line.startswith("-"):
            finish()
            in_gemini = line[:-1].strip().startswith("gemini")
            in_models = False
            collecting_roles = False
            continue
        if not in_gemini:
            continue

        if indent <= 4 and line.endswith(":") and not line.startswith("-"):
            in_models = line == "models:"
            collecting_roles = False
            continue
        if not in_models:
            continue

        if line.startswith("- "):
            body = line[2:].strip()
            if body.startswith("id:"):
                finish()
                current_id = _scalar(body.split(":", 1)[1])
                continue
            if collecting_roles:
                current_roles.append(_scalar(body))
            continue

        if line.startswith("id:"):
            current_id = _scalar(line.split(":", 1)[1])
            collecting_roles = False
            continue
        if line.startswith("roles:") or line.startswith("role:"):
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("[") and "]" in rest:
                inner = rest[1 : rest.index("]")]
                current_roles = [_scalar(part) for part in inner.split(",") if part.strip()]
                collecting_roles = False
            elif rest:
                current_roles = [_scalar(rest)]
                collecting_roles = False
            else:
                current_roles = []
                collecting_roles = True
            continue

    finish()
    return ids


def _block_code(payload: Any) -> str | None:
    if isinstance(payload, str):
        token = payload.strip().upper()
        return token if token in BLOCKED_PLAYBACK else None
    if isinstance(payload, Mapping):
        for key in ("status", "code", "error", "playback", "reason"):
            if key not in payload:
                continue
            found = _block_code(payload[key])
            if found:
                return found
    return None


def _exception_block_code(exc: BaseException) -> str | None:
    for attr in ("code", "status", "reason"):
        found = _block_code(getattr(exc, attr, None))
        if found:
            return found
    return _block_code(str(exc))


def _clean_text(value: str) -> str:
    text = _EMAIL.sub("", value)
    text = " ".join(text.split()).strip(" \t\"'`")
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text[:200]


def _empty_lead_keys() -> dict[str, Any]:
    return {
        "suspect_names": [],
        "victim_names": [],
        "incident_date_or_year": "",
        "county_state": "",
        "docket_ids": [],
        "unanswered_comment_questions": [],
    }


def _normalize_lead_keys(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    source = raw or {}
    keys = _empty_lead_keys()
    for name in LEAD_LIST_KEYS:
        value = source.get(name) or []
        if isinstance(value, str):
            value = [value]
        cleaned: list[str] = []
        for item in value:
            text = _clean_text(str(item))
            if text and text not in cleaned:
                cleaned.append(text)
        keys[name] = cleaned[:8]
    for name in LEAD_TEXT_KEYS:
        value = source.get(name) or ""
        keys[name] = _clean_text(str(value)) if str(value).strip() else ""
    return keys


def _split_labeled(value: str) -> list[str]:
    parts = [_clean_text(part) for part in value.split("|")]
    return [part for part in parts if part]


def _absorb_labeled_text(keys: dict[str, Any], text: str) -> None:
    for name, pattern in _LABELED_FIELDS:
        for match in pattern.finditer(text):
            extracted = _split_labeled(match.group(1))
            if not extracted:
                continue
            if name in LEAD_TEXT_KEYS:
                if not keys[name]:
                    keys[name] = extracted[0]
            else:
                for item in extracted:
                    if item not in keys[name]:
                        keys[name].append(item)


def _absorb_mentions(keys: dict[str, Any], mentions: Mapping[str, Any] | None) -> None:
    if not isinstance(mentions, Mapping):
        return
    for name in LEAD_LIST_KEYS:
        if name == "unanswered_comment_questions":
            continue
        value = mentions.get(name) or []
        if isinstance(value, str):
            value = [value]
        for item in value:
            text = _clean_text(str(item))
            if text and text not in keys[name]:
                keys[name].append(text)
    for name in LEAD_TEXT_KEYS:
        value = mentions.get(name)
        if value and not keys[name]:
            keys[name] = _clean_text(str(value))


def _questions_from_text(text: str) -> list[str]:
    questions: list[str] = []
    for match in _QUESTION.finditer(_EMAIL.sub("", text)):
        question = " ".join(match.group(0).split())
        if question and question not in questions and len(question) <= 200:
            questions.append(question)
        if len(questions) >= 8:
            break
    return questions


def _comment_records(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        raw_items = response
    elif isinstance(response, Mapping):
        raw_items = response.get("items") or response.get("comments") or []
    else:
        raw_items = []
    records: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, str):
            records.append({"text": item, "entity_mentions": {}})
            continue
        if not isinstance(item, Mapping):
            continue
        snippet = item.get("snippet") if isinstance(item.get("snippet"), Mapping) else {}
        top = snippet.get("topLevelComment") if isinstance(snippet.get("topLevelComment"), Mapping) else {}
        top_snippet = top.get("snippet") if isinstance(top.get("snippet"), Mapping) else snippet
        text = (
            top_snippet.get("textOriginal")
            or top_snippet.get("textDisplay")
            or item.get("text")
            or item.get("question")
            or ""
        )
        mentions = top_snippet.get("entity_mentions") or item.get("entity_mentions") or {}
        records.append({"text": str(text), "entity_mentions": mentions})
    return records


def _whitelist_metadata(response: Any) -> dict[str, Any]:
    item: Mapping[str, Any] = {}
    if isinstance(response, Mapping):
        items = response.get("items")
        if isinstance(items, list) and items and isinstance(items[0], Mapping):
            item = items[0]
        elif isinstance(response.get("snippet"), Mapping) or "title" in response:
            item = response
    snippet = item.get("snippet") if isinstance(item.get("snippet"), Mapping) else item
    tags = snippet.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    description = snippet.get("description") or ""
    return {
        "title": str(snippet.get("title") or ""),
        "description": str(description).strip(),
        "tags": [str(tag) for tag in tags],
    }


def video_id_from_url(url: str) -> str:
    """Return the 11-character id from a YouTube watch URL.

    Direct MP4 links are refused before any client call.
    """

    if _MP4.search(url):
        raise Mp4DownloadForbidden(
            "refusing to download MP4 bytes; pass a YouTube watch URL"
        )
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":", 1)[0].removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
                video_id = parts[1]
    if _VIDEO_ID.fullmatch(video_id) is None:
        raise ValueError(f"not a YouTube watch URL: {url}")
    return video_id


class GeminiYouTubeXRayClient:
    """`youtube-xray@2` client. Gemini and YouTube transports are injected.

    `inspect` sends at most five YouTube URLs to `gemini_client.inspect_youtube_urls`.
    It never downloads MP4s. Asking for captions raises `UnsupportedCaptionsDownload`.
    """

    CONTRACT_ID = CONTRACT_ID
    MAX_YOUTUBE_URLS = MAX_YOUTUBE_URLS

    def __init__(
        self,
        gemini_client: Any,
        youtube_client: Any,
        providers_path: str | Path | None = None,
    ) -> None:
        if gemini_client is None or youtube_client is None:
            raise TypeError("gemini_client and youtube_client are required")
        self._gemini = gemini_client
        self._youtube = youtube_client
        self.captions = _UnsupportedCaptions()
        path = Path(providers_path) if providers_path is not None else default_providers_yaml()
        self.model_id = load_youtube_xray_model_id(path)

    def download_captions(self, *args: Any, **kwargs: Any) -> None:
        raise UnsupportedCaptionsDownload(
            "captions.download is unsupported; it requires video edit rights"
        )

    def inspect(
        self,
        urls: Sequence[str],
        *,
        search_snippets: Sequence[Any] | None = None,
        captions: bool = False,
    ) -> list[YouTubeXRayResult]:
        if captions:
            raise UnsupportedCaptionsDownload(
                "captions.download is unsupported; it requires video edit rights"
            )
        url_list = [str(url) for url in urls]
        if len(url_list) > MAX_YOUTUBE_URLS:
            raise TooManyYouTubeUrls(
                f"at most {MAX_YOUTUBE_URLS} YouTube URLs can be sent"
            )
        if not url_list:
            raise ValueError("at least one YouTube URL is required")
        video_ids = [video_id_from_url(url) for url in url_list]
        outcomes = self._split_outcomes(url_list, self._call_gemini(url_list))
        snippets = list(search_snippets or [])
        results: list[YouTubeXRayResult] = []
        for url, video_id, outcome in zip(url_list, video_ids, outcomes, strict=True):
            code = _block_code(outcome)
            if code is None:
                results.append(self._agentic(url, video_id, outcome))
            else:
                results.append(self._fallback(url, video_id, snippets, code))
        return results

    def _call_gemini(self, urls: list[str]) -> Any:
        method = getattr(self._gemini, "inspect_youtube_urls", None)
        if method is None:
            raise TypeError("gemini client must provide inspect_youtube_urls")
        if len(urls) > MAX_YOUTUBE_URLS:
            raise TooManyYouTubeUrls(
                f"at most {MAX_YOUTUBE_URLS} YouTube URLs can be sent"
            )
        try:
            return method(model=self.model_id, urls=list(urls))
        except Exception as exc:
            code = _exception_block_code(exc)
            if code is None:
                raise
            return code

    def _split_outcomes(self, urls: list[str], raw: Any) -> list[Any]:
        if isinstance(raw, list):
            if len(raw) != len(urls):
                raise ValueError("gemini client returned a mismatched result list")
            return list(raw)
        if _block_code(raw) is not None:
            return [raw for _ in urls]
        if isinstance(raw, Mapping):
            nested = raw.get("results")
            if isinstance(nested, list):
                return self._split_outcomes(urls, nested)
            if len(urls) == 1:
                return [raw]
            if all(isinstance(raw.get(url), (Mapping, str)) for url in urls):
                return [raw[url] for url in urls]
        raise TypeError("unrecognized gemini youtube x-ray response")

    def _agentic(self, url: str, video_id: str, outcome: Any) -> YouTubeXRayResult:
        payload = outcome if isinstance(outcome, Mapping) else {}
        raw_keys = payload.get("lead_keys")
        if raw_keys is None:
            raw_keys = payload.get("factual_lead_keys")
        if not isinstance(raw_keys, Mapping):
            raw_keys = {}
        return YouTubeXRayResult(
            url=url,
            video_id=video_id,
            model_id=self.model_id,
            contract_id=CONTRACT_ID,
            source_mode=SOURCE_AGENTIC_VIDEO,
            lead_classification=LEAD_CLASSIFICATION_FACTUAL,
            lead_keys=_normalize_lead_keys(raw_keys),
            facts_confirmed=True,
            comments_are_confirmed_facts=False,
            metadata_is_confirmed_facts=False,
            authorized_metadata=None,
            public_comment_questions=[],
            playback_block=None,
            mp4_downloaded=False,
        )

    def _fallback(
        self,
        url: str,
        video_id: str,
        snippets: Sequence[Any],
        code: str,
    ) -> YouTubeXRayResult:
        metadata = self._videos_list(video_id)
        comments = _comment_records(self._comment_threads(video_id))
        questions: list[str] = []
        for comment in comments:
            for question in _questions_from_text(comment["text"]):
                if question not in questions:
                    questions.append(question)
                if len(questions) >= 8:
                    break
        keys = _empty_lead_keys()
        if metadata["description"]:
            _absorb_labeled_text(
                keys,
                "\n".join(
                    [
                        metadata["title"],
                        metadata["description"],
                        " ".join(metadata["tags"]),
                    ]
                ),
            )
        else:
            for comment in comments:
                _absorb_mentions(keys, comment.get("entity_mentions"))
                _absorb_labeled_text(keys, comment["text"])
            for snippet in snippets:
                if isinstance(snippet, str):
                    _absorb_labeled_text(keys, snippet)
                elif isinstance(snippet, Mapping):
                    _absorb_mentions(keys, snippet.get("entity_mentions"))
                    if snippet.get("text"):
                        _absorb_labeled_text(keys, str(snippet["text"]))
        keys["unanswered_comment_questions"] = questions
        return YouTubeXRayResult(
            url=url,
            video_id=video_id,
            model_id=self.model_id,
            contract_id=CONTRACT_ID,
            source_mode=SOURCE_LEAD_ONLY,
            lead_classification=LEAD_CLASSIFICATION_LEAD_ONLY,
            lead_keys=_normalize_lead_keys(keys),
            facts_confirmed=False,
            comments_are_confirmed_facts=False,
            metadata_is_confirmed_facts=False,
            authorized_metadata={field: metadata[field] for field in AUTHORIZED_METADATA_FIELDS},
            public_comment_questions=list(questions),
            playback_block=code,
            mp4_downloaded=False,
        )

    def _videos_list(self, video_id: str) -> dict[str, Any]:
        kwargs = {
            "part": "snippet",
            "id": video_id,
            "fields": VIDEO_FIELDS,
        }
        videos = getattr(self._youtube, "videos", None)
        if videos is not None and hasattr(videos, "list"):
            response = videos.list(**kwargs)
        elif hasattr(self._youtube, "videos_list"):
            response = self._youtube.videos_list(**kwargs)
        else:
            raise TypeError("youtube client must provide videos.list")
        metadata = _whitelist_metadata(response)
        return {field: metadata[field] for field in AUTHORIZED_METADATA_FIELDS}

    def _comment_threads(self, video_id: str) -> Any:
        kwargs = {
            "part": "snippet",
            "videoId": video_id,
            "textFormat": "plainText",
            "maxResults": 20,
        }
        threads = getattr(self._youtube, "commentThreads", None)
        if threads is None:
            threads = getattr(self._youtube, "comment_threads", None)
        if threads is not None and hasattr(threads, "list"):
            return threads.list(**kwargs)
        if hasattr(self._youtube, "comment_threads_list"):
            return self._youtube.comment_threads_list(**kwargs)
        raise TypeError("youtube client must provide commentThreads.list")
