"""Offline comment-gap miner and safe-title CTR check.

``CommentQualityGapMiner`` pulls the top 100 public comments through an
injected ``commentThreads.list`` callable, strips commenter PII, and clusters
unanswered forensic questions. The clusterer id is ``comment-gap-miner@1``.

Nothing in this module opens a socket or calls YouTube. Comments are
``LEAD_ONLY`` lookup leads, never factual evidence.
"""

from __future__ import annotations

import html
import re
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CLUSTERER_ID = "comment-gap-miner@1"
LEAD_CLASSIFICATION = "LEAD_ONLY"
TOP_COMMENT_LIMIT = 100
SEED_QUESTION_LIMIT = 8
MAX_QUESTION_CHARS = 200

NO_HOOK_PREDICTED_CTR = 1.0
HOOK_BASE_PREDICTED_CTR = 6.0
CLUSTER_CTR_BONUS = 0.5
MAX_CLUSTER_BONUS = 2.0

REASON_TABLOID_WEAK_STORY = "TABLOID_GRAPHIC_TITLE_WEAK_STORY"
REASON_NO_CURIOSITY_HOOK = "SAFE_TITLE_LACKS_CURIOSITY_HOOK"
REASON_BELOW_MEDIAN_CTR = "PREDICTED_HOOK_BELOW_MEDIAN_CTR"

STATUS_CANDIDATE = "CANDIDATE"
STATUS_REJECTED = "REJECTED"
WEAK_STORY_TITLE = "Local Incident Overview"

FORENSIC_AXES = ("who", "where", "when", "weapon", "timeline", "alibi")

_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
_HANDLE = re.compile(r"(?<![A-Za-z0-9])@[A-Za-z0-9_.]{2,30}(?![A-Za-z0-9_.])")
_PHONE_PATTERNS = (
    re.compile(r"\+\d{1,3}(?:[\s.\-]*\d){7,14}"),
    re.compile(r"(?<!\d)\(?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{10,15}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}[\s.\-]\d{4}(?!\d)"),
)
_TAG = re.compile(r"<[^>\n]{0,200}>")
_CONTROL = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f]")
_SENTENCE = re.compile(r"[^.!?\n]*[.!?]+|[^.!?\n]+$")
_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions"
    r"|you\s+are\s+now\b"
    r"|system\s+prompt"
    r"|</?\s*data\b",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"(?i)^(?:who|where|when|what|which|why|how|did|does|do|is|are|was|were)\b"
)
_AXIS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("alibi", re.compile(r"\balibis?\b", re.IGNORECASE)),
    (
        "weapon",
        re.compile(
            r"\b(?:weapons?|guns?|knives|knife|firearm|firearms|pistol|rifle|"
            r"shotgun|revolver|murder weapon)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "timeline",
        re.compile(
            r"\b(?:timeline|chronology|sequence of events|order of events)\b"
            r"|\bwhat happened\s+(?:first|next|before|after)\b",
            re.IGNORECASE,
        ),
    ),
    ("who", re.compile(r"\bwho(?:'s|s|m|se)?\b", re.IGNORECASE)),
    ("where", re.compile(r"\bwhere\b", re.IGNORECASE)),
    ("when", re.compile(r"\bwhen\b", re.IGNORECASE)),
)
_ANSWER_CUES: dict[str, re.Pattern[str]] = {
    "who": re.compile(
        r"\b(?:identified as|named|signer was|suspect is|suspect was|"
        r"defendant is|defendant was|witness was|witness is|killer was|"
        r"killer is)\s+[A-Z][a-z]+"
    ),
    "where": re.compile(
        r"\b(?:found|located|recovered|dumped|buried|parked|seen|arrested)\s+"
        r"(?:at|in|near|inside|outside|from)\b",
        re.IGNORECASE,
    ),
    "when": re.compile(
        r"\b(?:on\s+)?(?:january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\s+\d{1,2}(?:,\s*|\s+)\d{4}\b"
        r"|\b\d{1,2}:\d{2}\s*(?:a\.m\.|p\.m\.|am|pm)\b"
        r"|\b(?:signed|occurred|happened|killed|died|arrested|filed)\s+"
        r"(?:on|at)\b",
        re.IGNORECASE,
    ),
    "weapon": re.compile(
        r"\bweapon\s+was\b"
        r"|\b(?:killed|stabbed|shot)\s+with\b"
        r"|\b(?:used|using)\s+(?:a|an|the)\s+(?:knife|gun|pistol|rifle|"
        r"shotgun|hammer|rope|poison|axe|blade|firearm|revolver)\b",
        re.IGNORECASE,
    ),
    "timeline": re.compile(
        r"\bfirst\b.{0,80}\bthen\b"
        r"|\btimeline\s+(?:shows|is|was|:)"
        r"|\bsequence of events\b",
        re.IGNORECASE,
    ),
    "alibi": re.compile(
        r"\balibi\s+(?:was|is|places|placed|puts|put)\b"
        r"|\bclaimed to be at\b",
        re.IGNORECASE,
    ),
}
_HOOK = re.compile(
    r"\b(?:missing|unanswered|unknown|unexplained|discrepancy|discrepancies|"
    r"contradiction|contradicts|contradicted|alibi|hidden|withheld|omitted|"
    r"omits|gap|timeline|who|where|when|why|unsigned|unresolved|"
    r"vanish(?:ed|es)?)\b",
    re.IGNORECASE,
)
_GRAPHIC = re.compile(
    r"\b(?:chopped(?:\s+up)?|mutilated|mutilation|dismembered|dismemberment|"
    r"gore|gory|bloodbath|guts|slaughter(?:ed)?|hacked(?:\s+up)?|butchered|"
    r"corpse|decapitated|beheaded|tortured|torture|mangled|"
    r"stabbed\s+to\s+death|cut\s+up)\b",
    re.IGNORECASE,
)
_CLICKBAIT = re.compile(
    r"you won['’]t believe|shocking|gone wrong|must watch|what happened next",
    re.IGNORECASE,
)
_SCREAM_RUN = re.compile(r"[!?]{2,}")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PROPER_NAME = re.compile(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b")
_TOKEN = re.compile(r"[a-z0-9']+")
_NAME_FIRST_SKIP = frozenset(
    {
        "the",
        "this",
        "that",
        "when",
        "where",
        "what",
        "who",
        "why",
        "missing",
        "local",
        "case",
        "file",
        "record",
        "king",
        "weekly",
        "court",
        "incident",
        "unanswered",
    }
)
_NAME_SECOND_SKIP = frozenset(
    {
        "county",
        "street",
        "road",
        "avenue",
        "city",
        "parish",
        "state",
        "record",
        "file",
        "case",
        "page",
        "warrant",
        "alibi",
        "timeline",
    }
)
_STOP = frozenset(
    {
        "who",
        "whom",
        "whose",
        "where's",
        "where",
        "when",
        "what",
        "which",
        "why",
        "how",
        "who's",
        "whats",
        "did",
        "does",
        "do",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "the",
        "and",
        "or",
        "of",
        "to",
        "for",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "into",
        "onto",
        "about",
        "that",
        "this",
        "those",
        "these",
        "his",
        "her",
        "their",
        "them",
        "they",
        "she",
        "him",
        "our",
        "anyone",
        "someone",
        "somebody",
        "everybody",
        "people",
        "know",
        "think",
        "thought",
        "used",
        "using",
        "use",
        "happen",
        "happened",
        "really",
        "just",
        "ever",
        "still",
        "any",
        "out",
        "not",
        "dont",
        "doesnt",
        "didn't",
        "don't",
        "doesn't",
        "can't",
        "cannot",
        "could",
        "would",
        "should",
        "can",
        "will",
        "have",
        "has",
        "had",
        "please",
        "tell",
        "say",
        "said",
        "there",
        "here",
        "its",
        "it's",
        "wasnt",
        "wasn't",
    }
)


@dataclass(frozen=True)
class ForensicQuestionCluster:
    """One forensic axis of unanswered viewer questions.

    Questions are ``LEAD_ONLY``. They are not facts for the ledger.
    """

    axis: str
    questions: tuple[str, ...]
    support_count: int
    clusterer: str = CLUSTERER_ID

    def __post_init__(self) -> None:
        if self.axis not in FORENSIC_AXES:
            raise ValueError(f"unknown forensic axis: {self.axis}")
        if self.clusterer != CLUSTERER_ID:
            raise ValueError("clusterer must be comment-gap-miner@1")
        if self.support_count < len(self.questions):
            raise ValueError("support_count cannot be below the unique questions")


@dataclass(frozen=True)
class CommentGapMiningResult:
    """Comment clusters plus the safe-title CTR decision for one candidate."""

    clusterer: str
    video_id: str
    lead_classification: str
    source_title: str
    comments_pulled: int
    clusters: tuple[ForensicQuestionCluster, ...]
    unanswered_comment_questions: tuple[str, ...]
    safe_title: str
    safe_title_ctr_ok: int
    predicted_hook_ctr: float
    median_historical_ctr: float | None
    has_curiosity_hook: bool
    tabloid_or_graphic_source: bool
    story_is_weak: bool
    rejected: bool
    candidate_status: str
    policy_kill_reason: str | None

    def __post_init__(self) -> None:
        if self.clusterer != CLUSTERER_ID:
            raise ValueError("clusterer must be comment-gap-miner@1")
        if self.lead_classification != LEAD_CLASSIFICATION:
            raise ValueError("comment gaps are LEAD_ONLY")
        if self.safe_title_ctr_ok not in (0, 1):
            raise ValueError("safe_title_ctr_ok must be 0 or 1")
        if self.rejected != (self.safe_title_ctr_ok == 0):
            raise ValueError("a failed safe-title check rejects the candidate")
        if self.safe_title_ctr_ok == 1 and self.policy_kill_reason is not None:
            raise ValueError("a passing safe title has no kill reason")
        if self.safe_title_ctr_ok == 0 and not self.policy_kill_reason:
            raise ValueError("a rejected safe title needs a kill reason")
        expected_status = STATUS_REJECTED if self.rejected else STATUS_CANDIDATE
        if self.candidate_status != expected_status:
            raise ValueError("candidate_status does not match the CTR decision")
        if len(self.unanswered_comment_questions) > SEED_QUESTION_LIMIT:
            raise ValueError("seed questions are capped at 8")


def strip_commenter_pii(text: str) -> str:
    """Remove emails, @handles, phone-like numbers, and HTML from a comment.

    Years and short docket numbers stay. Clustering must see this output,
    not the raw comment.
    """

    cleaned = html.unescape(text or "")
    cleaned = _TAG.sub(" ", cleaned)
    cleaned = _CONTROL.sub(" ", cleaned)
    cleaned = _EMAIL.sub(" ", cleaned)
    cleaned = _HANDLE.sub(" ", cleaned)
    for pattern in _PHONE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\s+([?.!,])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def predicted_hook_ctr(*, has_curiosity_hook: bool, cluster_count: int) -> float:
    """Map a safe title's curiosity hook onto the ``ctr_pct`` 0–100 scale.

    This is a bounded editorial prior used only for the median comparison.
    It is not a trained click model and it does not call a network.
    """

    if not has_curiosity_hook:
        return NO_HOOK_PREDICTED_CTR
    steps = int(MAX_CLUSTER_BONUS / CLUSTER_CTR_BONUS)
    bonus = min(max(cluster_count, 0), steps) * CLUSTER_CTR_BONUS
    return HOOK_BASE_PREDICTED_CTR + bonus


class CommentQualityGapMiner:
    """Mine unanswered forensic questions and score a safe documentary title.

    ``comment_threads_list`` is the injected ``commentThreads.list`` callable.
    It is invoked once per video with ``maxResults=100`` and ``order=relevance``.
    The callable's return value is the comment payload. This module does not
    build a YouTube client or follow a page token.
    """

    def __init__(self, comment_threads_list: Callable[..., Any]) -> None:
        if not callable(comment_threads_list):
            raise TypeError(
                "comment_threads_list must be an injected commentThreads.list callable"
            )
        self._comment_threads_list = comment_threads_list

    def mine(
        self,
        video_id: str,
        *,
        title: str,
        description: str = "",
        episode_analytics: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> CommentGapMiningResult:
        if not str(video_id).strip():
            raise ValueError("video_id is required")
        if not str(title).strip():
            raise ValueError("title is required")

        comments = self._pull_top_comments(video_id)
        clusters = _cluster_unanswered(comments, title, description)
        assessment = _assess_safe_title(
            title=title,
            description=description,
            clusters=clusters,
            episode_analytics=episode_analytics,
        )
        seed_questions: list[str] = []
        for cluster in clusters:
            for question in cluster.questions:
                if len(seed_questions) >= SEED_QUESTION_LIMIT:
                    break
                seed_questions.append(question)
            if len(seed_questions) >= SEED_QUESTION_LIMIT:
                break

        return CommentGapMiningResult(
            clusterer=CLUSTERER_ID,
            video_id=str(video_id),
            lead_classification=LEAD_CLASSIFICATION,
            source_title=str(title),
            comments_pulled=len(comments),
            clusters=clusters,
            unanswered_comment_questions=tuple(seed_questions),
            safe_title=assessment.safe_title,
            safe_title_ctr_ok=assessment.safe_title_ctr_ok,
            predicted_hook_ctr=assessment.predicted_hook_ctr,
            median_historical_ctr=assessment.median_historical_ctr,
            has_curiosity_hook=assessment.has_curiosity_hook,
            tabloid_or_graphic_source=assessment.tabloid_or_graphic_source,
            story_is_weak=assessment.story_is_weak,
            rejected=assessment.safe_title_ctr_ok == 0,
            candidate_status=(
                STATUS_REJECTED if assessment.safe_title_ctr_ok == 0 else STATUS_CANDIDATE
            ),
            policy_kill_reason=assessment.policy_kill_reason,
        )

    def _pull_top_comments(self, video_id: str) -> tuple[str, ...]:
        payload = self._comment_threads_list(
            part="snippet",
            videoId=str(video_id),
            maxResults=TOP_COMMENT_LIMIT,
            order="relevance",
            textFormat="plainText",
        )
        texts: list[str] = []
        for raw in _extract_comment_texts(payload):
            if len(texts) >= TOP_COMMENT_LIMIT:
                break
            if raw and raw.strip():
                texts.append(raw)
        return tuple(texts)


@dataclass(frozen=True)
class _SafeTitleAssessment:
    safe_title: str
    safe_title_ctr_ok: int
    predicted_hook_ctr: float
    median_historical_ctr: float | None
    has_curiosity_hook: bool
    tabloid_or_graphic_source: bool
    story_is_weak: bool
    policy_kill_reason: str | None


def _extract_comment_texts(payload: Any) -> list[str]:
    if payload is None:
        return []
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        texts: list[str] = []
        for item in payload:
            texts.extend(_extract_comment_texts(item))
        return texts
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            texts = []
            for item in items:
                texts.extend(_thread_texts(item))
            return texts
        return _thread_texts(payload)
    text = getattr(payload, "textOriginal", None) or getattr(payload, "text", None)
    if isinstance(text, str):
        return [text]
    return []


def _thread_texts(item: Any) -> list[str]:
    """Read the top-level comment only. Replies are not the relevance ranking."""

    if not isinstance(item, Mapping):
        if isinstance(item, str):
            return [item]
        return []
    direct = item.get("textOriginal") or item.get("textDisplay") or item.get("text")
    if isinstance(direct, str):
        return [direct]
    snippet = item.get("snippet")
    if not isinstance(snippet, Mapping):
        return []
    top = snippet.get("topLevelComment")
    if not isinstance(top, Mapping):
        return []
    top_snippet = top.get("snippet")
    if not isinstance(top_snippet, Mapping):
        return []
    text = (
        top_snippet.get("textOriginal")
        or top_snippet.get("textDisplay")
        or top_snippet.get("text")
        or ""
    )
    return [text] if isinstance(text, str) and text.strip() else []


def _cluster_unanswered(
    comments: Sequence[str],
    title: str,
    description: str,
) -> tuple[ForensicQuestionCluster, ...]:
    grouped: dict[str, list[str]] = {axis: [] for axis in FORENSIC_AXES}
    seen: dict[str, set[str]] = {axis: set() for axis in FORENSIC_AXES}
    support: dict[str, int] = {axis: 0 for axis in FORENSIC_AXES}

    for raw in comments:
        prepared = strip_commenter_pii(raw)
        for sentence in _sentences(prepared):
            if _INJECTION.search(sentence):
                continue
            axis = _classify_axis(sentence)
            if axis is None:
                continue
            display = _display_question(sentence)
            if not display or _INJECTION.search(display):
                continue
            if _is_answered(display, axis, title, description):
                continue
            support[axis] += 1
            key = _dedupe_key(display)
            if key in seen[axis]:
                continue
            seen[axis].add(key)
            grouped[axis].append(display)

    clusters: list[ForensicQuestionCluster] = []
    for axis in FORENSIC_AXES:
        questions = tuple(grouped[axis])
        if not questions:
            continue
        clusters.append(
            ForensicQuestionCluster(
                axis=axis,
                questions=questions,
                support_count=support[axis],
                clusterer=CLUSTERER_ID,
            )
        )
    return tuple(clusters)


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE.findall(text)]
    return [part for part in parts if part]


def _classify_axis(sentence: str) -> str | None:
    if "?" not in sentence and _QUESTION_START.match(sentence.strip()) is None:
        return None
    for axis, pattern in _AXIS_PATTERNS:
        if pattern.search(sentence):
            return axis
    return None


def _display_question(sentence: str) -> str:
    text = re.sub(r"[!?.]+$", "", sentence.strip(" \"'`")).strip()
    text = re.sub(r"\s+", " ", text)
    if not re.search(r"[A-Za-z]", text):
        return ""
    if len(text) > MAX_QUESTION_CHARS - 1:
        shortened = text[: MAX_QUESTION_CHARS - 1]
        text = shortened.rsplit(" ", 1)[0] if " " in shortened else shortened
    question = text[:1].upper() + text[1:]
    if not question.endswith("?"):
        question = f"{question}?"
    if len(question) > MAX_QUESTION_CHARS:
        question = question[: MAX_QUESTION_CHARS - 1].rstrip() + "?"
    terminators = re.findall(r"[.!?]+", question)
    if len(terminators) != 1:
        return ""
    return question


def _dedupe_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def _content_tokens(question: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for word in _TOKEN.findall(question.lower()):
        if len(word) < 3 or word in _STOP or word in tokens:
            continue
        tokens.append(word)
    return tuple(tokens)


def _is_answered(question: str, axis: str, title: str, description: str) -> bool:
    haystack = f"{title}\n{description}"
    if _ANSWER_CUES[axis].search(haystack) is None:
        return False
    tokens = _content_tokens(question)
    if not tokens:
        return True
    lowered = haystack.lower()
    return all(
        re.search(rf"\b{re.escape(token)}\b", lowered) is not None for token in tokens
    )


def _assess_safe_title(
    *,
    title: str,
    description: str,
    clusters: Sequence[ForensicQuestionCluster],
    episode_analytics: Sequence[Any] | Mapping[str, Any] | None,
) -> _SafeTitleAssessment:
    tabloid = _is_tabloid_title(title)
    weak = _story_is_weak(title, description, clusters)
    safe_title = _draft_safe_title(title, description, clusters)
    if _is_tabloid_title(safe_title):
        safe_title = WEAK_STORY_TITLE
    has_hook = _has_curiosity_hook(safe_title) and not _is_tabloid_title(safe_title)
    predicted = predicted_hook_ctr(
        has_curiosity_hook=has_hook,
        cluster_count=len(clusters),
    )
    median = _median_historical_ctr(episode_analytics)
    below_median = median is not None and predicted < median

    if tabloid and weak:
        reason: str | None = REASON_TABLOID_WEAK_STORY
        ok = 0
    elif not has_hook:
        reason = REASON_NO_CURIOSITY_HOOK
        ok = 0
    elif below_median:
        reason = REASON_BELOW_MEDIAN_CTR
        ok = 0
    else:
        reason = None
        ok = 1

    return _SafeTitleAssessment(
        safe_title=safe_title,
        safe_title_ctr_ok=ok,
        predicted_hook_ctr=predicted,
        median_historical_ctr=median,
        has_curiosity_hook=has_hook,
        tabloid_or_graphic_source=tabloid,
        story_is_weak=weak,
        policy_kill_reason=reason,
    )


def _draft_safe_title(
    title: str,
    description: str,
    clusters: Sequence[ForensicQuestionCluster],
) -> str:
    cleaned = _normalize_space(title)
    if not _is_tabloid_title(cleaned):
        return _clamp_title(_soften_shouting(cleaned))

    salvaged = _clamp_title(_soften_shouting(_strip_tabloid_language(cleaned)))
    if (
        _has_curiosity_hook(salvaged)
        and not _is_tabloid_title(salvaged)
        and len(salvaged.split()) >= 2
    ):
        return salvaged

    if clusters and clusters[0].questions:
        drafted = _editorial_from_question(clusters[0].questions[0], description)
        if _has_curiosity_hook(drafted) and not _is_tabloid_title(drafted):
            return _clamp_title(drafted)

    lifted = _lift_hook_sentence(description)
    if lifted:
        return lifted
    return WEAK_STORY_TITLE


def _editorial_from_question(question: str, description: str) -> str:
    core = question.rstrip("?").strip()
    surname = _subject_surname(description)
    if surname and surname.lower() not in core.lower():
        core = f"{core} in the {surname} Record"
    return _normalize_space(_strip_tabloid_language(core))


def _lift_hook_sentence(description: str) -> str | None:
    for sentence in _sentences(description):
        salvaged = _soften_shouting(_strip_tabloid_language(sentence))
        salvaged = salvaged.rstrip(".!?").strip()
        if (
            _has_curiosity_hook(salvaged)
            and not _is_tabloid_title(salvaged)
            and len(salvaged.split()) >= 3
        ):
            return _clamp_title(salvaged)
    return None


def _story_is_weak(
    title: str,
    description: str,
    clusters: Sequence[ForensicQuestionCluster],
) -> bool:
    if clusters:
        return False
    blob = f"{title} {description}"
    if _YEAR.search(blob) or _subject_surname(description):
        return False
    residue = _strip_tabloid_language(blob)
    if _has_curiosity_hook(residue):
        return False
    return True


def _subject_surname(text: str) -> str | None:
    for first, second in _PROPER_NAME.findall(text or ""):
        if first.lower() in _NAME_FIRST_SKIP or second.lower() in _NAME_SECOND_SKIP:
            continue
        return second
    return None


def _is_tabloid_title(title: str) -> bool:
    if _GRAPHIC.search(title) or _CLICKBAIT.search(title):
        return True
    return _is_screaming(title)


def _is_screaming(title: str) -> bool:
    letters = [char for char in title if char.isalpha()]
    if len(letters) < 8:
        return False
    upper_ratio = sum(char.isupper() for char in letters) / len(letters)
    if upper_ratio < 0.8:
        return False
    if _SCREAM_RUN.search(title):
        return True
    return title.rstrip().endswith("!")


def _has_curiosity_hook(title: str) -> bool:
    return _HOOK.search(title or "") is not None


def _strip_tabloid_language(text: str) -> str:
    cleaned = _CLICKBAIT.sub(" ", text or "")
    cleaned = _GRAPHIC.sub(" ", cleaned)
    cleaned = _SCREAM_RUN.sub(" ", cleaned)
    cleaned = cleaned.replace("!", " ")
    return _normalize_space(cleaned)


def _soften_shouting(title: str) -> str:
    letters = [char for char in title if char.isalpha()]
    normalized = _normalize_space(title)
    if len(letters) >= 8 and sum(char.isupper() for char in letters) / len(letters) >= 0.8:
        lowered = normalized.lower()
        return lowered[:1].upper() + lowered[1:] if lowered else lowered
    return normalized


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clamp_title(title: str) -> str:
    text = _normalize_space(title)
    if len(text) <= MAX_QUESTION_CHARS:
        return text
    shortened = text[:MAX_QUESTION_CHARS].rsplit(" ", 1)[0]
    return shortened or text[:MAX_QUESTION_CHARS]


def _median_historical_ctr(
    episode_analytics: Sequence[Any] | Mapping[str, Any] | None,
) -> float | None:
    values = _ctr_values(episode_analytics)
    if not values:
        return None
    return float(statistics.median(values))


def _ctr_values(
    episode_analytics: Sequence[Any] | Mapping[str, Any] | None,
) -> list[float]:
    if episode_analytics is None:
        return []
    rows: Sequence[Any]
    if isinstance(episode_analytics, Mapping):
        if "rows" in episode_analytics:
            nested = episode_analytics["rows"]
            rows = nested if isinstance(nested, Sequence) and not isinstance(nested, str) else []
        elif "ctr_history" in episode_analytics:
            nested = episode_analytics["ctr_history"]
            rows = nested if isinstance(nested, Sequence) and not isinstance(nested, str) else []
        else:
            rows = [episode_analytics]
    else:
        rows = episode_analytics

    values: list[float] = []
    for row in rows:
        raw = _ctr_from_row(row)
        if raw is None:
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN
            continue
        values.append(number)
    return values


def _ctr_from_row(row: Any) -> Any:
    if isinstance(row, bool) or row is None:
        return None
    if isinstance(row, (int, float, str)):
        return row
    if isinstance(row, Mapping):
        return row.get("ctr_pct")
    return getattr(row, "ctr_pct", None)
