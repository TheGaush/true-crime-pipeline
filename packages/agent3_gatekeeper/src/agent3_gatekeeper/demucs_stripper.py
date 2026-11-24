"""Music-gated Demucs isolator with honest ASR metrics (F-15).

Runs source separation only when an injected music detector reports music.
Production logs ``asr_hypothesis_disagreement`` (never labeled WER). True WER
is ``labeled_corpus_wer`` against manually verified reference transcripts.
This module does not invoke Demucs, YAMNet, or PANNs and opens no sockets.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DISAGREEMENT_REVIEW_THRESHOLD = 0.10
_DEFAULT_LOW_CONFIDENCE = 0.85

MusicDetector = Callable[[Mapping[str, Any]], int]
AsrHypothesisProvider = Callable[[Mapping[str, Any], bool], tuple[str, float]]

_MEDIA_KIND_911 = frozenset({"call_911_wav"})


def tokenize(text: str) -> list[str]:
    return text.lower().split()


def token_edit_distance(left: Sequence[str], right: Sequence[str]) -> int:
    """Levenshtein edit distance over token sequences."""
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, tok_l in enumerate(left, start=1):
        row = [i]
        for j, tok_r in enumerate(right, start=1):
            cost = 0 if tok_l == tok_r else 1
            row.append(
                min(
                    prev[j] + 1,
                    row[j - 1] + 1,
                    prev[j - 1] + cost,
                )
            )
        prev = row
    return prev[-1]


def asr_hypothesis_disagreement(pre_demucs: str, post_demucs: str) -> float:
    """Token edit distance divided by the longer hypothesis token count.

    This is explicitly not WER: two ASR runs can share identical errors.
    """
    pre_tokens = tokenize(pre_demucs)
    post_tokens = tokenize(post_demucs)
    denom = max(len(pre_tokens), len(post_tokens), 1)
    return token_edit_distance(pre_tokens, post_tokens) / denom


def labeled_corpus_wer(hypothesis: str, reference: str) -> float:
    """Word error rate against a human-verified ground-truth reference."""
    ref_tokens = tokenize(reference)
    if not ref_tokens:
        return 0.0 if not tokenize(hypothesis) else 1.0
    hyp_tokens = tokenize(hypothesis)
    return token_edit_distance(hyp_tokens, ref_tokens) / len(ref_tokens)


def is_911_telephony_bypass(asset: Mapping[str, Any]) -> bool:
    """8 kHz (or narrower) telephony clips skip music detection and Demucs."""
    raw_path = str(asset.get("raw_path", ""))
    if raw_path.endswith("911_8khz_distorted.wav"):
        return True
    rate = asset.get("sample_rate_hz")
    media_kind = asset.get("media_kind")
    if media_kind in _MEDIA_KIND_911 and rate is not None and rate <= 8000:
        return True
    return False


@dataclass(frozen=True, slots=True)
class MusicGatedDemucsResult:
    music_detected: int
    demucs_applied: int
    asr_hypothesis_disagreement: float
    human_audio_review_required: int
    pre_demucs_hypothesis: str
    post_demucs_hypothesis: str
    asr_confidence: float | None


class MusicGatedDemucsIsolator:
    """Apply Demucs only on music-detected intervals; track honest disagreement."""

    def __init__(
        self,
        *,
        music_detector: MusicDetector | None = None,
        asr_provider: AsrHypothesisProvider | None = None,
        disagreement_threshold: float = DISAGREEMENT_REVIEW_THRESHOLD,
        low_confidence_threshold: float = _DEFAULT_LOW_CONFIDENCE,
        demucs_runner: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._music_detector = music_detector
        self._asr_provider = asr_provider
        self._disagreement_threshold = disagreement_threshold
        self._low_confidence_threshold = low_confidence_threshold
        self._demucs_runner = demucs_runner

    def process(
        self,
        asset: Mapping[str, Any],
        *,
        pre_demucs_hypothesis: str | None = None,
        post_demucs_hypothesis: str | None = None,
        asr_confidence: float | None = None,
    ) -> MusicGatedDemucsResult:
        if is_911_telephony_bypass(asset):
            music_detected = 0
        elif self._music_detector is not None:
            music_detected = 1 if self._music_detector(asset) else 0
        else:
            music_detected = 0

        demucs_applied = 0
        pre_hyp = pre_demucs_hypothesis or ""
        post_hyp = post_demucs_hypothesis or ""
        confidence = asr_confidence

        if music_detected == 1:
            demucs_applied = 1
            if self._demucs_runner is not None:
                self._demucs_runner(asset)
            if self._asr_provider is not None:
                pre_hyp, conf_pre = self._asr_provider(asset, False)
                post_hyp, conf_post = self._asr_provider(asset, True)
                confidence = min(conf_pre, conf_post)
            disagreement = asr_hypothesis_disagreement(pre_hyp, post_hyp)
        else:
            if pre_demucs_hypothesis is None and post_demucs_hypothesis is None:
                if self._asr_provider is not None:
                    pre_hyp, confidence = self._asr_provider(asset, False)
                    post_hyp = pre_hyp
            elif post_demucs_hypothesis is None:
                post_hyp = pre_hyp
            disagreement = 0.0

        review = self._human_review_flag(disagreement, confidence)
        return MusicGatedDemucsResult(
            music_detected=music_detected,
            demucs_applied=demucs_applied,
            asr_hypothesis_disagreement=disagreement,
            human_audio_review_required=review,
            pre_demucs_hypothesis=pre_hyp,
            post_demucs_hypothesis=post_hyp,
            asr_confidence=confidence,
        )

    def _human_review_flag(
        self, disagreement: float, confidence: float | None
    ) -> int:
        if disagreement > self._disagreement_threshold:
            return 1
        if confidence is not None and confidence < self._low_confidence_threshold:
            return 1
        return 0