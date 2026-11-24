"""Millisecond keyword cue mapping and ASR proper-noun pronunciation gate (Task 068)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

PRONUNCIATION_SIMILARITY_THRESHOLD = 0.72

# Canonical phonetic respellings for TTS re-synthesis overrides.
PHONETIC_RESPELLINGS: dict[str, str] = {
    "krzysztof": "KRIH-stohf",
    "nguyen": "WIN",
    "szczesny": "SHCHEH-snee",
    "worcestershire": "WUSS-ter-sheer",
}


@dataclass(frozen=True, slots=True)
class WordStamp:
    word: str
    start_ms: int
    end_ms: int
    segment_id: str = ""


@dataclass(frozen=True, slots=True)
class PronunciationFinding:
    expected: str
    asr_token: str
    similarity: float
    passed: bool
    phonetic_respelling: str | None
    needs_resynthesis: bool
    chunk_id: str


@dataclass(frozen=True, slots=True)
class PronunciationGateResult:
    findings: tuple[PronunciationFinding, ...]
    chunks_needing_resynthesis: frozenset[str]


def _normalize_token(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    asciiish = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", asciiish.lower())


def map_keyword_cue_timestamp(
    keyword: str,
    word_timestamps: Sequence[WordStamp],
    beat_start_ms: int,
    beat_end_ms: int,
) -> int | None:
    """Return the first keyword onset (ms) that falls inside [beat_start_ms, beat_end_ms]."""
    if beat_end_ms < beat_start_ms:
        raise ValueError("beat_end_ms must be >= beat_start_ms")
    target = _normalize_token(keyword)
    if not target:
        raise ValueError("keyword must contain at least one alphanumeric character")

    for stamp in sorted(word_timestamps, key=lambda w: w.start_ms):
        if stamp.start_ms < beat_start_ms or stamp.start_ms > beat_end_ms:
            continue
        if _normalize_token(stamp.word) == target:
            return stamp.start_ms
    return None


def jaro_winkler(left: str, right: str, *, prefix_scale: float = 0.1) -> float:
    """Jaro–Winkler similarity in [0, 1]."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    len_left = len(left)
    len_right = len(right)
    match_distance = max(len_left, len_right) // 2 - 1
    left_matches = [False] * len_left
    right_matches = [False] * len_right

    matches = 0
    for i in range(len_left):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_right)
        for j in range(start, end):
            if right_matches[j] or left[i] != right[j]:
                continue
            left_matches[i] = True
            right_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    transpositions = 0
    for i in range(len_left):
        if not left_matches[i]:
            continue
        while not right_matches[k]:
            k += 1
        if left[i] != right[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    jaro = (
        matches / len_left
        + matches / len_right
        + (matches - transpositions) / matches
    ) / 3.0

    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
        if prefix == 4:
            break
    return jaro + prefix * prefix_scale * (1.0 - jaro)


def _is_vowel(ch: str) -> bool:
    return ch in "aeiou"


def _dedupe(code: str) -> str:
    if not code:
        return ""
    out: list[str] = []
    prev = ""
    for ch in code:
        if ch and ch != prev:
            out.append(ch)
        prev = ch
    return "".join(out)


def double_metaphone(word: str) -> tuple[str, str]:
    """Compact Double Metaphone encoder (primary, alternate)."""
    primary: list[str] = []
    alternate: list[str] = []
    current = _normalize_token(word)
    if not current:
        return "", ""

    length = len(current)
    idx = 0
    first = current[0]
    if first in {"x", "k", "g", "p"} and length > 1 and current[1] == "n":
        primary.append("KN")
        alternate.append("KN")
        idx = 2

    while idx < length:
        ch = current[idx]
        nxt = current[idx + 1] if idx + 1 < length else ""
        prev = current[idx - 1] if idx > 0 else ""

        if ch in {"a", "e", "i", "o", "u", "y"}:
            if idx == 0:
                primary.append("A")
                alternate.append("A")
            idx += 1
            continue

        if ch == "b":
            primary.append("P")
            alternate.append("P")
            idx += 2 if nxt == "b" else 1
            continue

        if ch == "c":
            if nxt == "h":
                primary.append("X")
                alternate.append("X")
                idx += 2
            elif nxt in {"i", "e", "y"}:
                primary.append("S")
                alternate.append("S")
                idx += 2
            else:
                primary.append("K")
                alternate.append("K")
                idx += 2 if nxt == "c" else 1
            continue

        if ch == "d":
            if nxt == "g" and idx + 2 < length and current[idx + 2] in {"i", "e", "y"}:
                primary.append("J")
                alternate.append("J")
                idx += 3
            else:
                primary.append("T")
                alternate.append("T")
                idx += 2 if nxt == "d" else 1
            continue

        if ch in {"f", "j", "l", "m", "n", "r"}:
            primary.append(ch.upper())
            alternate.append(ch.upper())
            idx += 2 if nxt == ch else 1
            continue

        if ch == "g":
            if nxt == "n" and idx + 2 == length:
                idx += 2
                continue
            if nxt in {"i", "e", "y"}:
                primary.append("J")
                alternate.append("K")
            else:
                primary.append("K")
                alternate.append("K")
            idx += 2 if nxt == "g" else 1
            continue

        if ch == "h":
            vowel_neighbour = (
                (not prev or _is_vowel(prev)) and (_is_vowel(nxt) or not nxt)
            )
            if vowel_neighbour and (not prev or prev[-1:] not in {"c", "s", "p", "t", "g"}):
                primary.append("H")
                alternate.append("H")
            idx += 1
            continue

        if ch == "k":
            if nxt == "n":
                idx += 2
                continue
            primary.append("K")
            alternate.append("K")
            idx += 2 if nxt == "k" else 1
            continue

        if ch == "p":
            if nxt == "h":
                primary.append("F")
                alternate.append("F")
                idx += 2
            else:
                primary.append("P")
                alternate.append("P")
                idx += 2 if nxt == "p" else 1
            continue

        if ch == "q":
            primary.append("K")
            alternate.append("K")
            idx += 2 if nxt == "q" else 1
            continue

        if ch == "s":
            if nxt == "h":
                primary.append("X")
                alternate.append("X")
                idx += 2
            elif nxt in {"i", "y"} and prev not in {"s", "c", "t"}:
                primary.append("S")
                alternate.append("X")
                idx += 2
            else:
                primary.append("S")
                alternate.append("S")
                idx += 2 if nxt == "s" else 1
            continue

        if ch == "t":
            if nxt == "h":
                primary.append("0")  # TH fricative bucket
                alternate.append("T")
                idx += 2
            elif nxt == "i" and idx + 2 < length and current[idx + 2] in {"o", "a"}:
                primary.append("X")
                alternate.append("X")
                idx += 3
            else:
                primary.append("T")
                alternate.append("T")
                idx += 2 if nxt == "t" else 1
            continue

        if ch == "v":
            primary.append("F")
            alternate.append("F")
            idx += 2 if nxt == "v" else 1
            continue

        if ch in {"w", "y"}:
            if _is_vowel(nxt):
                primary.append(ch.upper())
                alternate.append(ch.upper())
            idx += 1
            continue

        if ch == "x":
            primary.append("KS")
            alternate.append("KS")
            idx += 2 if nxt in {"c", "x"} else 1
            continue

        if ch == "z":
            primary.append("S")
            alternate.append("S")
            idx += 2 if nxt == "z" else 1
            continue

        idx += 1

    p = _dedupe("".join(primary))
    a = _dedupe("".join(alternate)) or p
    return p[:6], a[:6]


def _metaphone_similarity(left: str, right: str) -> float:
    lp, la = double_metaphone(left)
    rp, ra = double_metaphone(right)
    scores = [jaro_winkler(lp, rp)]
    if la:
        scores.append(jaro_winkler(la, ra))
    if la != lp or ra != rp:
        scores.append(jaro_winkler(lp, ra))
        scores.append(jaro_winkler(la, rp))
    return max(scores)


def pronunciation_similarity(expected: str, asr_token: str) -> float:
    """Blend literal and metaphone Jaro–Winkler for proper-noun ASR comparison."""
    left = _normalize_token(expected)
    right = _normalize_token(asr_token)
    if not left or not right:
        return 0.0
    string_score = jaro_winkler(left, right)
    meta_score = _metaphone_similarity(expected, asr_token)
    similarity = string_score
    # Boost only near-miss spellings with strong metaphone agreement (not unrelated homophones).
    if meta_score >= 0.95 and string_score >= 0.60:
        similarity = max(similarity, 0.75 * string_score + 0.25 * meta_score)
    elif meta_score > string_score:
        similarity = max(similarity, string_score + 0.05 * (meta_score - string_score))
    return similarity


def phonetic_respelling_for(proper_noun: str) -> str:
    key = _normalize_token(proper_noun)
    if key in PHONETIC_RESPELLINGS:
        return PHONETIC_RESPELLINGS[key]
    meta, _alt = double_metaphone(proper_noun)
    if not meta:
        return proper_noun.upper()
    return meta


def verify_respelling_meets_threshold(
    respelling: str,
    expected_proper_noun: str,
    *,
    threshold: float = PRONUNCIATION_SIMILARITY_THRESHOLD,
) -> bool:
    return pronunciation_similarity(expected_proper_noun, respelling) >= threshold


def _best_asr_match(expected: str, asr_tokens: Sequence[str]) -> tuple[str, float]:
    best_token = ""
    best_score = 0.0
    for token in asr_tokens:
        score = pronunciation_similarity(expected, token)
        if score > best_score:
            best_score = score
            best_token = token
    return best_token, best_score


def check_proper_noun_pronunciation(
    expected: str,
    asr_tokens: Sequence[str],
    *,
    chunk_id: str,
    threshold: float = PRONUNCIATION_SIMILARITY_THRESHOLD,
) -> PronunciationFinding:
    asr_token, similarity = _best_asr_match(expected, asr_tokens)
    passed = similarity >= threshold
    respelling: str | None = None
    needs_resynthesis = False
    if not passed:
        respelling = phonetic_respelling_for(expected)
        needs_resynthesis = True
        if not verify_respelling_meets_threshold(respelling, expected, threshold=threshold):
            raise ValueError(
                f"generated respelling {respelling!r} for {expected!r} "
                f"does not reach similarity threshold {threshold}"
            )
    return PronunciationFinding(
        expected=expected,
        asr_token=asr_token,
        similarity=round(similarity, 4),
        passed=passed,
        phonetic_respelling=respelling,
        needs_resynthesis=needs_resynthesis,
        chunk_id=chunk_id,
    )


def run_pronunciation_gate(
    proper_nouns: Sequence[tuple[str, str]],
    asr_tokens_by_chunk: dict[str, Sequence[str]],
    *,
    threshold: float = PRONUNCIATION_SIMILARITY_THRESHOLD,
) -> PronunciationGateResult:
    findings: list[PronunciationFinding] = []
    resynth: set[str] = set()
    for expected, chunk_id in proper_nouns:
        tokens = asr_tokens_by_chunk.get(chunk_id, ())
        finding = check_proper_noun_pronunciation(
            expected,
            tokens,
            chunk_id=chunk_id,
            threshold=threshold,
        )
        findings.append(finding)
        if finding.needs_resynthesis:
            resynth.add(chunk_id)
    return PronunciationGateResult(
        findings=tuple(findings),
        chunks_needing_resynthesis=frozenset(resynth),
    )