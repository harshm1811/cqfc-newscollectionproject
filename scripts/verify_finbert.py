"""Run strict, real ProsusAI/finbert inference and validate its outputs.

Run from the repository root with the documented SENTIMENT_* environment
variables. This script deliberately instantiates FinBERT directly and never
consults the lexicon fallback.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from models.sentiment import FinBERTSentimentModel, SentimentConfig


SAMPLE_TEXTS = [
    "The company reported record quarterly revenue and raised its full-year earnings guidance.",
    "The company warned of a sharp profit decline after a major product recall and rising costs.",
    "The company announced that its board will meet next week to review the quarterly results.",
]


def validate_result(result) -> None:
    probabilities = (
        result.positive_probability,
        result.neutral_probability,
        result.negative_probability,
    )
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError(f"Invalid sentiment probabilities: {probabilities!r}")
    if not math.isclose(sum(probabilities), 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"Sentiment probabilities do not sum to 1: {probabilities!r}")
    expected = result.positive_probability - result.negative_probability
    if not math.isfinite(result.sentiment_score) or not -1.0 <= result.sentiment_score <= 1.0:
        raise ValueError(f"Invalid sentiment score: {result.sentiment_score!r}")
    if not math.isclose(result.sentiment_score, expected, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("sentiment_score does not equal positive_probability - negative_probability")
    if result.model_name != "ProsusAI/finbert":
        raise ValueError(f"Unexpected model provenance: {result.model_name!r}")


def main() -> int:
    try:
        config = SentimentConfig.from_env()
        if config.model != "finbert":
            raise ValueError("SENTIMENT_MODEL must be 'finbert' for this strict verification")
        if config.fallback_enabled:
            raise ValueError("SENTIMENT_FALLBACK_ENABLED must be 'false'; this script never uses fallback")
        if config.model_name != "ProsusAI/finbert":
            raise ValueError("Strict verification requires SENTIMENT_MODEL_NAME=ProsusAI/finbert")
        if config.local_files_only:
            raise ValueError("SENTIMENT_LOCAL_FILES_ONLY must be 'false' so missing weights can download")

        model = FinBERTSentimentModel(
            model_name="ProsusAI/finbert",
            device=config.device,
            batch_size=config.batch_size,
            max_length=config.max_length,
            local_files_only=False,
        )
        model.ensure_loaded()
        results = model.analyze(SAMPLE_TEXTS)
        if len(results) != len(SAMPLE_TEXTS):
            raise ValueError(f"Expected {len(SAMPLE_TEXTS)} outputs, received {len(results)}")

        for text, result in zip(SAMPLE_TEXTS, results):
            validate_result(result)
            predicted = max(
                (
                    ("positive", result.positive_probability),
                    ("neutral", result.neutral_probability),
                    ("negative", result.negative_probability),
                ),
                key=lambda pair: pair[1],
            )[0]
            print(f"Input: {text}")
            print(f"Predicted sentiment: {predicted}")
            print(f"Positive probability: {result.positive_probability:.6f}")
            print(f"Negative probability: {result.negative_probability:.6f}")
            print(f"Neutral probability:  {result.neutral_probability:.6f}")
            print(f"Sentiment score:      {result.sentiment_score:.6f}")
            print(f"Model provenance:     {result.model_name}")
            print()
    except Exception as exc:
        print(f"FinBERT verification FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("REAL FinBERT inference and probability validation succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
