"""Statistical significance testing for model and run comparisons.

Replaces heuristic sample thresholds with:
  * Bootstrap confidence intervals (percentile method, vectorised with NumPy)
  * Paired sign-flip permutation tests (exact enumeration for n <= 15, Monte Carlo for n > 15)
  * Standardised effect sizes (Cohen's d_z for paired samples)
  * Normal-approximation sample size requirements for power = 0.8
  * Holm-Bonferroni correction for multiple pairwise model comparisons
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


def paired_differences(
    before: dict[str, float], after: dict[str, float]
) -> tuple[list[float], int]:
    """Extract paired differences between two sets of case scores.

    Only cases where the metric is available on BOTH sides enter the analysis.
    Returns (diffs, n_dropped) where diffs = after - before.
    """
    before_valid = {k: float(v) for k, v in before.items() if v is not None}
    after_valid = {k: float(v) for k, v in after.items() if v is not None}
    all_keys = set(before) | set(after)
    common_keys = sorted(set(before_valid) & set(after_valid))
    diffs = [after_valid[k] - before_valid[k] for k in common_keys]
    n_dropped = len(all_keys) - len(common_keys)
    return diffs, n_dropped


def bootstrap_ci(
    diffs: list[float] | np.ndarray,
    n_resamples: int = 10000,
    confidence: float = 0.95,
    seed: int = 1234,
) -> tuple[float, float]:
    """Compute a bootstrap confidence interval using the percentile method.

    Vectorised resampling with NumPy; handles n < 2 gracefully.
    """
    arr = np.asarray(diffs, dtype=np.float64)
    n = len(arr)
    if n < 2:
        val = round(float(arr[0]), 4) if n == 1 else 0.0
        return (val, val)

    rng = np.random.default_rng(seed)
    chunk_size = 2500
    means = np.empty(n_resamples, dtype=np.float64)
    for i in range(0, n_resamples, chunk_size):
        end = min(i + chunk_size, n_resamples)
        k = end - i
        idx = rng.integers(0, n, size=(k, n))
        means[i:end] = np.mean(arr[idx], axis=1)

    alpha = (1.0 - confidence) / 2.0
    low = float(np.percentile(means, 100.0 * alpha))
    high = float(np.percentile(means, 100.0 * (1.0 - alpha)))
    return (round(low, 4), round(high, 4))


def sign_flip_permutation_test(
    diffs: list[float] | np.ndarray,
    n_permutations: int = 10000,
    seed: int = 1234,
) -> float:
    """Two-sided paired sign-flip permutation test for H0: mean difference is 0.

    Uses exact enumeration (2^n sign patterns) when n <= 15,
    otherwise Monte Carlo with the standard +1 correction.
    """
    arr = np.asarray(diffs, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return 1.0

    t_obs = abs(float(np.mean(arr)))
    if t_obs < 1e-12:
        return 1.0

    if n <= 15:
        # Exact enumeration of all 2^n sign patterns
        signs = (((np.arange(1 << n, dtype=np.int32)[:, None] >> np.arange(n)) & 1) * 2 - 1).astype(
            np.float64
        )
        t_perm = np.abs(np.mean(signs * arr, axis=1))
        p = float(np.mean(t_perm >= t_obs - 1e-12))
        return round(p, 4)

    # Monte Carlo for n > 15
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=(n_permutations, n))
    t_perm = np.abs(np.mean(signs * arr, axis=1))
    p = (float(np.sum(t_perm >= t_obs - 1e-12)) + 1.0) / (n_permutations + 1.0)
    return round(p, 4)


def cohens_dz(diffs: list[float] | np.ndarray) -> float | None:
    """Standardised effect size for paired samples: mean / sample_std.

    Returns None if sample std is 0 or n < 2.
    """
    arr = np.asarray(diffs, dtype=np.float64)
    n = len(arr)
    if n < 2:
        return None
    std = float(np.std(arr, ddof=1))
    if std < 1e-12 or math.isnan(std):
        return None
    mean = float(np.mean(arr))
    return round(mean / std, 4)


def _norm_ppf(p: float) -> float:
    """Rational approximation of normal quantile function (Acklam's algorithm)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0, 1)")

    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)

    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def required_sample_size(
    effect_dz: float | None, alpha: float = 0.05, power: float = 0.8
) -> int | None:
    """Approximate sample size required for a paired test using normal approximation.

    n = ceil(((z_{1-alpha/2} + z_{power}) / |dz|)^2).
    Returns None if dz is None or 0.
    """
    if effect_dz is None or abs(effect_dz) < 1e-9:
        return None
    z_alpha = _norm_ppf(1.0 - alpha / 2.0)
    z_power = _norm_ppf(power)
    n = ((z_alpha + z_power) / abs(effect_dz)) ** 2
    return math.ceil(n)


def significance_verdict(
    n: int,
    mean_diff: float,
    ci: tuple[float, float],
    p_value: float,
    alpha: float = 0.05,
    min_n: int = 8,
    effect_dz: float | None = None,
    required_n: int | None = None,
) -> tuple[str, str]:
    """Determine statistical significance verdict and one-sentence explanation.

    Verdict is one of 'significant', 'not_significant', 'underpowered'.
    Rules:
      * n < min_n -> underpowered
      * CI excludes 0 and p < alpha -> significant
      * otherwise not_significant, but if required_n > n * 1.5 -> underpowered
    """
    if n < min_n:
        return (
            "underpowered",
            f"Sample size (n={n}) is too small to detect an effect (minimum {min_n} cases required).",
        )

    ci_excludes_zero = (ci[0] > 0 and ci[1] > 0) or (ci[0] < 0 and ci[1] < 0)
    if ci_excludes_zero and p_value < alpha:
        return (
            "significant",
            f"Statistically significant change (p={p_value:.4f}, 95% CI [{ci[0]:.4f}, {ci[1]:.4f}] excludes 0).",
        )

    if required_n is None and effect_dz is not None:
        required_n = required_sample_size(effect_dz, alpha=alpha)

    if required_n is not None and required_n > n * 1.5:
        return (
            "underpowered",
            f"Sample size (n={n}) is underpowered to detect this effect size (estimated ~{required_n} cases needed).",
        )

    return (
        "not_significant",
        f"No statistically significant difference detected (p={p_value:.4f}, 95% CI [{ci[0]:.4f}, {ci[1]:.4f}] spans 0).",
    )


def holm_correction(p_values: Sequence[float]) -> list[float]:
    """Holm-Bonferroni step-down correction for multiple pairwise comparisons."""
    m = len(p_values)
    if m <= 1:
        return [round(float(p), 4) for p in p_values]

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, (orig_idx, p_val) in enumerate(indexed):
        adj = (m - rank) * p_val
        running_max = max(running_max, adj)
        adjusted[orig_idx] = round(min(1.0, max(0.0, running_max)), 4)
    return adjusted


def analyse_metric(
    before: dict[str, float],
    after: dict[str, float],
    *,
    alpha: float = 0.05,
    min_n: int = 8,
    seed: int = 1234,
    n_resamples: int = 10000,
    n_permutations: int = 10000,
) -> dict[str, Any]:
    """Run full statistical analysis on paired before/after scores.

    Returns dict with n_pairs, n_dropped, mean_before, mean_after, mean_diff,
    ci_low, ci_high, p_value, effect_size_dz, required_n, significance,
    significance_reason.
    """
    diffs, n_dropped = paired_differences(before, after)
    before_valid = {k: float(v) for k, v in before.items() if v is not None}
    after_valid = {k: float(v) for k, v in after.items() if v is not None}
    common_keys = sorted(set(before_valid) & set(after_valid))

    if not diffs:
        return {
            "n_pairs": 0,
            "n_dropped": n_dropped,
            "mean_before": (
                round(float(np.mean(list(before_valid.values()))), 4) if before_valid else None
            ),
            "mean_after": (
                round(float(np.mean(list(after_valid.values()))), 4) if after_valid else None
            ),
            "mean_diff": None,
            "ci_low": None,
            "ci_high": None,
            "p_value": None,
            "effect_size_dz": None,
            "required_n": None,
            "significance": "not_comparable",
            "significance_reason": "No paired cases available with valid scores on both sides.",
        }

    mean_before = round(float(np.mean([before_valid[k] for k in common_keys])), 4)
    mean_after = round(float(np.mean([after_valid[k] for k in common_keys])), 4)
    mean_diff = round(float(np.mean(diffs)), 4)
    ci_low, ci_high = bootstrap_ci(diffs, n_resamples=n_resamples, confidence=1.0 - alpha, seed=seed)
    p_value = sign_flip_permutation_test(diffs, n_permutations=n_permutations, seed=seed)
    effect_dz = cohens_dz(diffs)
    req_n = required_sample_size(effect_dz, alpha=alpha, power=0.8)
    verdict, reason = significance_verdict(
        len(diffs),
        mean_diff,
        (ci_low, ci_high),
        p_value,
        alpha=alpha,
        min_n=min_n,
        effect_dz=effect_dz,
        required_n=req_n,
    )

    return {
        "n_pairs": len(diffs),
        "n_dropped": n_dropped,
        "mean_before": mean_before,
        "mean_after": mean_after,
        "mean_diff": mean_diff,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": p_value,
        "effect_size_dz": effect_dz,
        "required_n": req_n,
        "significance": verdict,
        "significance_reason": reason,
    }
