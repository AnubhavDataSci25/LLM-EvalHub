"""Judge calibration metrics: Cohen's kappa, bootstrap intervals, and bias metrics.

Enforces reproducibility, honest wording for single annotators, and no SciPy dependency.
Landis & Koch (1977) agreement bands are used for qualitative interpretation.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

THRESHOLD_LOW = 0.34
THRESHOLD_HIGH = 0.67

LANDIS_KOCH_NOTE = (
    "Conventional Landis & Koch (1977) agreement bands; interpretation is conventional and context-dependent. "
    "With a single human annotator, kappa measures agreement with that individual rater, not universal ground truth."
)


def discretise(score: float | None) -> int:
    """Discretise a continuous 0-1 judge score into a 3-point ordinal scale (0, 1, 2).

    0: incorrect (< 0.34)
    1: partially correct (0.34 <= score < 0.67)
    2: fully correct (>= 0.67)
    """
    if score is None:
        return 0
    s = float(score)
    if s < THRESHOLD_LOW:
        return 0
    if s < THRESHOLD_HIGH:
        return 1
    return 2


def cohens_kappa(
    a: list[int] | np.ndarray,
    b: list[int] | np.ndarray,
    weights: str | None = None,
) -> dict[str, Any]:
    """Compute Cohen's kappa for two raters with 3 categories (0, 1, 2).

    Supports weights=None (unweighted), 'linear', and 'quadratic'.
    Returns None for kappa when expected agreement equals 1.0 (degenerate).
    """
    arr_a = np.asarray(a, dtype=int)
    arr_b = np.asarray(b, dtype=int)
    n = len(arr_a)
    if n == 0 or len(arr_b) != n:
        return {
            "kappa": None,
            "observed_agreement": 0.0,
            "expected_agreement": 0.0,
            "n": n,
            "confusion_matrix": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            "per_class_agreement": {0: None, 1: None, 2: None},
        }

    k_cats = 3
    conf_mat = np.zeros((k_cats, k_cats), dtype=int)
    for i in range(n):
        ca = int(arr_a[i])
        cb = int(arr_b[i])
        if 0 <= ca < k_cats and 0 <= cb < k_cats:
            conf_mat[ca, cb] += 1

    r = conf_mat.sum(axis=1)  # row marginals (rater a)
    c = conf_mat.sum(axis=0)  # col marginals (rater b)

    w = np.zeros((k_cats, k_cats), dtype=np.float64)
    if weights is None:
        for i in range(k_cats):
            w[i, i] = 1.0
    elif weights == "linear":
        for i in range(k_cats):
            for j in range(k_cats):
                w[i, j] = 1.0 - abs(i - j) / float(k_cats - 1)
    elif weights == "quadratic":
        for i in range(k_cats):
            for j in range(k_cats):
                w[i, j] = 1.0 - ((i - j) ** 2) / float((k_cats - 1) ** 2)
    else:
        raise ValueError(f"Unsupported weights: {weights}. Must be None, 'linear', or 'quadratic'.")

    p_o = float(np.sum(w * conf_mat)) / float(n)
    p_e = float(np.sum(w * np.outer(r, c))) / float(n**2)

    if p_e >= 1.0 - 1e-12:
        kappa = None
    else:
        kappa = float((p_o - p_e) / (1.0 - p_e))

    per_class: dict[int, float | None] = {}
    for cat in range(k_cats):
        total_cat = int(r[cat] + c[cat])
        if total_cat > 0:
            per_class[cat] = round(2.0 * float(conf_mat[cat, cat]) / float(total_cat), 4)
        else:
            per_class[cat] = None

    return {
        "kappa": round(kappa, 4) if kappa is not None else None,
        "observed_agreement": round(p_o, 4),
        "expected_agreement": round(p_e, 4),
        "n": n,
        "confusion_matrix": conf_mat.tolist(),
        "per_class_agreement": per_class,
    }


def kappa_interval(
    a: list[int] | np.ndarray,
    b: list[int] | np.ndarray,
    weights: str | None = None,
    n_resamples: int = 2000,
    seed: int = 1234,
) -> tuple[float, float] | None:
    """Bootstrap confidence interval for Cohen's kappa over paired indices.

    Returns None if n < 10 or if all resamples are degenerate.
    """
    arr_a = np.asarray(a, dtype=int)
    arr_b = np.asarray(b, dtype=int)
    n = len(arr_a)
    if n < 10 or len(arr_b) != n:
        return None

    rng = np.random.default_rng(seed)
    idx_matrix = rng.integers(0, n, size=(n_resamples, n))
    kappas: list[float] = []

    for i in range(n_resamples):
        sample_idx = idx_matrix[i]
        sample_a = arr_a[sample_idx]
        sample_b = arr_b[sample_idx]
        res = cohens_kappa(sample_a, sample_b, weights=weights)
        k = res["kappa"]
        if k is not None:
            kappas.append(k)

    if len(kappas) < 10:
        return None

    low = float(np.percentile(kappas, 2.5))
    high = float(np.percentile(kappas, 97.5))
    return (round(low, 4), round(high, 4))


def interpret_kappa(k: float | None) -> str:
    """Interpret kappa using standard Landis & Koch (1977) conventional bands.

    <0: poor
    0 - 0.20: slight
    0.21 - 0.40: fair
    0.41 - 0.60: moderate
    0.61 - 0.80: substantial
    0.81 - 1.00: almost perfect
    """
    if k is None:
        return "uncalibrated"
    val = float(k)
    if val < 0.0:
        return "poor"
    if val <= 0.20:
        return "slight"
    if val <= 0.40:
        return "fair"
    if val <= 0.60:
        return "moderate"
    if val <= 0.80:
        return "substantial"
    return "almost perfect"


def judge_bias_summary(human: list[int], judge: list[int]) -> dict[str, Any]:
    """Compute directional bias: mean signed error, over-scoring and under-scoring shares."""
    n = len(human)
    if n == 0 or len(judge) != n:
        return {
            "mean_signed_error": 0.0,
            "over_scoring_share": 0.0,
            "under_scoring_share": 0.0,
            "exact_agreement_share": 0.0,
        }
    diffs = [j - h for h, j in zip(human, judge, strict=False)]
    mean_err = float(np.mean(diffs))
    over = sum(1 for d in diffs if d > 0) / float(n)
    under = sum(1 for d in diffs if d < 0) / float(n)
    exact = sum(1 for d in diffs if d == 0) / float(n)
    return {
        "mean_signed_error": round(mean_err, 4),
        "over_scoring_share": round(over, 4),
        "under_scoring_share": round(under, 4),
        "exact_agreement_share": round(exact, 4),
    }


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Compute the Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    p_hat = float(successes) / float(n)
    denom = 1.0 + (z**2) / float(n)
    center = (p_hat + (z**2) / (2.0 * float(n))) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / float(n)) + (z**2) / (4.0 * (float(n) ** 2)))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return (round(low, 4), round(high, 4))


def flip_rate(original: list[int], probed: list[int]) -> dict[str, Any]:
    """Compute proportion of verdicts that changed, Wilson 95% interval, and mean absolute shift."""
    n = len(original)
    if n == 0 or len(probed) != n:
        return {
            "flip_rate": 0.0,
            "interval": (0.0, 0.0),
            "mean_shift": 0.0,
            "n": 0,
            "flips": 0,
        }
    flips = sum(1 for o, p in zip(original, probed, strict=False) if o != p)
    rate = float(flips) / float(n)
    interval = wilson_interval(flips, n, z=1.96)
    shifts = [abs(p - o) for o, p in zip(original, probed, strict=False)]
    mean_shift = float(np.mean(shifts))
    return {
        "flip_rate": round(rate, 4),
        "interval": interval,
        "mean_shift": round(mean_shift, 4),
        "n": n,
        "flips": flips,
    }
