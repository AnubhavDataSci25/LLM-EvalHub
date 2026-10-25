"""Unit tests for statistical significance module (pure functions)."""

from __future__ import annotations

import numpy as np

from app.evaluation.statistics import (
    analyse_metric,
    bootstrap_ci,
    cohens_dz,
    holm_correction,
    paired_differences,
    required_sample_size,
    sign_flip_permutation_test,
    significance_verdict,
)


def test_pairing_drops_unavailable_metrics_and_reports_n_dropped():
    before = {"c1": 0.8, "c2": 0.6, "c3": None, "c4": 0.9}
    after = {"c1": 0.9, "c2": None, "c3": 0.7, "c5": 0.85}
    diffs, n_dropped = paired_differences(before, after)
    # Only c1 is available and valid on both sides
    assert len(diffs) == 1
    assert round(diffs[0], 2) == 0.1
    # Total unique keys across both sides: c1, c2, c3, c4, c5 = 5
    # Paired: c1 (1). Dropped: 4.
    assert n_dropped == 4


def test_bootstrap_ci_contains_true_mean_and_is_reproducible():
    rng = np.random.default_rng(999)
    true_mean = 0.15
    # Generate 100 samples with mean ~ 0.15
    sample = rng.normal(true_mean, 0.05, size=100).tolist()

    ci_1 = bootstrap_ci(sample, n_resamples=5000, seed=1234)
    ci_2 = bootstrap_ci(sample, n_resamples=5000, seed=1234)

    # Determinism
    assert ci_1 == ci_2
    low, high = ci_1
    assert low < true_mean < high
    assert low > 0  # Clearly excludes 0


def test_permutation_test_symmetric_noise_vs_shift():
    rng = np.random.default_rng(42)
    # Symmetric noise centered at 0
    noise = rng.normal(0.0, 0.5, size=20).tolist()
    p_noise = sign_flip_permutation_test(noise, seed=1234)
    assert p_noise > 0.1, f"Expected large p for symmetric noise, got {p_noise}"

    # Clear positive shift
    shifted = [0.4, 0.5, 0.35, 0.45, 0.6, 0.55, 0.42, 0.38, 0.49, 0.52]
    p_shifted = sign_flip_permutation_test(shifted, seed=1234)
    assert p_shifted < 0.01, f"Expected small p for clear shift, got {p_shifted}"


def test_permutation_test_exact_vs_monte_carlo_near_n15():
    rng = np.random.default_rng(1234)
    n = 15
    diffs = rng.normal(0.15, 0.4, size=n)
    t_obs = abs(float(np.mean(diffs)))

    # Exact enumeration (n=15 -> 32768)
    signs_exact = (((np.arange(1 << n, dtype=np.int32)[:, None] >> np.arange(n)) & 1) * 2 - 1).astype(
        np.float64
    )
    t_perm_exact = np.abs(np.mean(signs_exact * diffs, axis=1))
    p_exact = float(np.mean(t_perm_exact >= t_obs - 1e-12))

    # Monte Carlo with 10000 resamples
    signs_mc = rng.choice([-1.0, 1.0], size=(10000, n))
    t_perm_mc = np.abs(np.mean(signs_mc * diffs, axis=1))
    p_mc = (float(np.sum(t_perm_mc >= t_obs - 1e-12)) + 1.0) / (10000.0 + 1.0)

    assert abs(p_exact - p_mc) < 0.02, f"Exact ({p_exact}) and MC ({p_mc}) differ by > 0.02"


def test_required_sample_size_hand_computed_dz_05():
    # Hand-computed: ((z_0.975 + z_0.8) / 0.5)^2 = ((1.95996 + 0.84162) / 0.5)^2 ~ 31.4 -> ceil = 32
    req_n = required_sample_size(0.5, alpha=0.05, power=0.8)
    assert req_n == 32
    assert required_sample_size(0.0) is None
    assert required_sample_size(None) is None


def test_cohens_dz():
    diffs = [0.1, 0.2, 0.3, 0.4, 0.5]
    dz = cohens_dz(diffs)
    assert dz is not None
    # mean = 0.3, sample std = 0.15811388... -> dz ~ 1.8974
    assert round(dz, 2) == 1.90
    assert cohens_dz([0.1]) is None
    assert cohens_dz([0.2, 0.2, 0.2]) is None  # std = 0


def test_verdict_rules():
    # 1. n < 8 is underpowered
    verdict, reason = significance_verdict(5, 0.2, (0.05, 0.35), 0.01, min_n=8)
    assert verdict == "underpowered"
    assert "too small" in reason

    # 2. Clear effect: CI excludes 0 and p < alpha
    verdict, reason = significance_verdict(20, 0.15, (0.05, 0.25), 0.005, alpha=0.05, min_n=8)
    assert verdict == "significant"
    assert "Statistically significant" in reason

    # 3. Tiny effect with large n: not significant (CI spans 0 or effect is 0)
    verdict, reason = significance_verdict(
        1000, 0.0001, (-0.01, 0.01), 0.85, alpha=0.05, min_n=8, effect_dz=0.0
    )
    assert verdict == "not_significant"
    assert "No statistically significant difference" in reason

    # 4. Underpowered due to required_sample_size > n * 1.5
    # e.g. n=10, dz=0.3 -> req_n ~ 88 > 10 * 1.5 = 15
    req_n = required_sample_size(0.3)
    verdict, reason = significance_verdict(
        10, 0.05, (-0.02, 0.12), 0.15, alpha=0.05, min_n=8, required_n=req_n
    )
    assert verdict == "underpowered"
    assert "underpowered to detect this effect size" in reason


def test_holm_correction():
    # Known vector
    p_vals = [0.01, 0.04, 0.03, 0.005]
    adj = holm_correction(p_vals)
    # Sorted: 0.005 (rank 0, mult 4 -> 0.02)
    #         0.010 (rank 1, mult 3 -> 0.03)
    #         0.030 (rank 2, mult 2 -> 0.06)
    #         0.040 (rank 3, mult 1 -> 0.04 -> max with 0.06 -> 0.06)
    assert adj == [0.03, 0.06, 0.06, 0.02]


def test_analyse_metric_two_identical_runs():
    cases = {f"c{i}": 0.85 for i in range(20)}
    result = analyse_metric(cases, cases)
    assert result["mean_diff"] == 0.0
    assert result["significance"] == "not_significant"
    assert result["ci_low"] == 0.0
    assert result["ci_high"] == 0.0
    assert result["p_value"] == 1.0
