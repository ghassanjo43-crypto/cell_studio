"""Scientific confidence: turn evidence (sample size + effect strength) into a level.

Confidence is deterministic and evidence-based. It is driven primarily by the number
of supporting runs and secondarily by the effect strength (|r|), so a claim backed by
many consistent runs reads "high" and a thin/noisy one reads "low".
"""

from __future__ import annotations

from typing import Literal

Confidence = Literal["high", "medium", "low"]

#: Run-count thresholds for each level (a claim needs at least this many runs).
#: Calibrated to study scale: a full single-axis sweep (~5 points) with a strong,
#: consistent effect reaches "medium"; a pooled cross-experiment correlation (~10+
#: runs) with a strong effect reaches "high".
HIGH_N = 10
MEDIUM_N = 5


def level_for(n: int, strength: float = 1.0) -> Confidence:
    """Confidence level from supporting-run count ``n`` and effect strength |r|.

    A strong, consistent effect (|r| ≥ 0.7) can reach "high" with fewer runs; a weak
    effect is capped at "medium" no matter how many runs support it.
    """
    if n >= HIGH_N and strength >= 0.6:
        return "high"
    if n >= MEDIUM_N and strength >= 0.4:
        return "medium"
    if n >= HIGH_N:  # many runs but weak/noisy effect
        return "medium"
    return "low"


def describe(level: Confidence, n: int) -> str:
    """A short, human phrase for the confidence, citing the sample size."""
    if level == "high":
        return f"High — supported by {n} runs."
    if level == "medium":
        return f"Medium — supported by {n} runs."
    return f"Low — only {n} run(s); insufficient evidence."
