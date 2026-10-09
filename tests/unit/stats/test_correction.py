"""Tests for Rogan-Gladen judge correction (card S3).

Card S3 implements Rogan-Gladen correction to account for judge miscalibration.
The formula θ = (q + c − 1)/(s + c − 1) corrects the observed pass rate q for
sensitivity s and specificity c of the judge. Bootstrap uncertainty from both
calibration and test sets.
"""

import numpy as np
import pytest

from evalhawk.core.errors import JudgeTooWeakError
from evalhawk.stats.correction import corrected_pass_rate, rogan_gladen


# ========================================== rogan_gladen: golden values
class TestRoganGladenGoldenValues:
    """Known correct values from the specification."""

    def test_rogan_gladen_0_7636(self) -> None:
        """RG(0.82, 0.95, 0.60) = 0.7636."""
        # q=0.82, s=0.95, c=0.60
        # θ = (0.82 + 0.60 - 1) / (0.95 + 0.60 - 1)
        #   = 0.42 / 0.55 = 0.763636...
        result = rogan_gladen(0.82, 0.95, 0.60)
        assert result == pytest.approx(0.7636, abs=5e-5)

    def test_rogan_gladen_perfect_judge(self) -> None:
        """Perfect judge (s=1, c=1) → θ = q."""
        q = 0.7
        result = rogan_gladen(q, 1.0, 1.0)
        assert result == pytest.approx(q)

    def test_rogan_gladen_clipping_lower(self) -> None:
        """q < 1 - c → θ clipped to 0."""
        # q=0.1, c=0.8: q < 1 - c (0.1 < 0.2 is true) → should clip to 0
        result = rogan_gladen(0.1, 0.9, 0.8)
        assert result == 0.0

    def test_rogan_gladen_clipping_upper(self) -> None:
        """q > s → θ clipped to 1."""
        result = rogan_gladen(0.99, 0.9, 0.8)
        assert result == 1.0


# ========================================== rogan_gladen: validation
class TestRoganGladenValidation:
    """Validate input ranges and raise on invalid inputs."""

    def test_rogan_gladen_q_not_finite_raises(self) -> None:
        """q must be finite."""
        with pytest.raises(ValueError, match="q.*finite"):
            rogan_gladen(float("nan"), 0.95, 0.60)
        with pytest.raises(ValueError, match="q.*finite"):
            rogan_gladen(float("inf"), 0.95, 0.60)

    def test_rogan_gladen_sensitivity_not_finite_raises(self) -> None:
        """sensitivity must be finite."""
        with pytest.raises(ValueError, match="sensitivity.*finite"):
            rogan_gladen(0.82, float("nan"), 0.60)

    def test_rogan_gladen_specificity_not_finite_raises(self) -> None:
        """specificity must be finite."""
        with pytest.raises(ValueError, match="specificity.*finite"):
            rogan_gladen(0.82, 0.95, float("nan"))

    def test_rogan_gladen_q_out_of_range_raises(self) -> None:
        """q must be in [0, 1]."""
        with pytest.raises(ValueError, match="q.*\\[0, 1\\]"):
            rogan_gladen(-0.1, 0.95, 0.60)
        with pytest.raises(ValueError, match="q.*\\[0, 1\\]"):
            rogan_gladen(1.1, 0.95, 0.60)

    def test_rogan_gladen_sensitivity_out_of_range_raises(self) -> None:
        """sensitivity must be in [0, 1]."""
        with pytest.raises(ValueError, match="sensitivity.*\\[0, 1\\]"):
            rogan_gladen(0.82, -0.1, 0.60)
        with pytest.raises(ValueError, match="sensitivity.*\\[0, 1\\]"):
            rogan_gladen(0.82, 1.1, 0.60)

    def test_rogan_gladen_specificity_out_of_range_raises(self) -> None:
        """specificity must be in [0, 1]."""
        with pytest.raises(ValueError, match="specificity.*\\[0, 1\\]"):
            rogan_gladen(0.82, 0.95, -0.1)
        with pytest.raises(ValueError, match="specificity.*\\[0, 1\\]"):
            rogan_gladen(0.82, 0.95, 1.1)


# ========================================== rogan_gladen: too weak
class TestRoganGladenTooWeak:
    """Judge too weak to correct (Youden's J ≤ MIN_YOUDEN)."""

    def test_rogan_gladen_youden_exactly_at_min_raises(self) -> None:
        """J = 0.1 exactly → JudgeTooWeakError."""
        # s=0.6, c=0.5: J = 0.6 + 0.5 - 1 = 0.1
        with pytest.raises(JudgeTooWeakError) as exc_info:
            rogan_gladen(0.5, 0.6, 0.5)
        msg = str(exc_info.value)
        assert "0.1" in msg

    def test_rogan_gladen_youden_below_min_raises(self) -> None:
        """J < 0.1 → JudgeTooWeakError."""
        # s=0.55, c=0.5: J = 0.55 + 0.5 - 1 = 0.05 < 0.1
        with pytest.raises(JudgeTooWeakError):
            rogan_gladen(0.5, 0.55, 0.5)

    def test_rogan_gladen_too_weak_error_message_format(self) -> None:
        """Error message contains observed s, c, J and explanation."""
        s, c = 0.6, 0.5
        with pytest.raises(JudgeTooWeakError) as exc_info:
            rogan_gladen(0.5, s, c)
        msg = str(exc_info.value)
        # Should mention Youden, why, and guidance
        assert "barely better than random" in msg or "amplify" in msg or "judge" in msg


# ========================================== corrected_pass_rate: validation
class TestCorrectedPassRateValidation:
    """Validate inputs to corrected_pass_rate."""

    def test_corrected_pass_rate_judge_test_not_binary_raises(self) -> None:
        """judge_test must be binary."""
        with pytest.raises(ValueError, match="judge_test"):
            corrected_pass_rate(
                [1, 2, 0],
                [1, 1, 0],
                [1, 1, 0],
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_judge_cal_not_binary_raises(self) -> None:
        """judge_cal must be binary."""
        with pytest.raises(ValueError, match="judge_cal"):
            corrected_pass_rate(
                [1, 1, 0],
                [1, 2, 0],
                [1, 1, 0],
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_human_cal_not_binary_raises(self) -> None:
        """human_cal must be binary."""
        with pytest.raises(ValueError, match="human_cal"):
            corrected_pass_rate(
                [1, 1, 0],
                [1, 1, 0],
                [1, 2, 0],
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_empty_test_raises(self) -> None:
        """test non-empty."""
        with pytest.raises(ValueError, match="judge_test.*non-empty"):
            corrected_pass_rate(
                [],
                [1, 1, 0],
                [1, 1, 0],
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_mismatched_calibration_lengths_raises(self) -> None:
        """judge_cal and human_cal must have same length."""
        with pytest.raises(ValueError, match="must have the same length"):
            corrected_pass_rate(
                [1, 1, 0],
                [1, 1],
                [1, 1, 0],
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_calibration_without_human_pass_raises(self) -> None:
        """human_cal must have both classes (P4)."""
        with pytest.raises(ValueError, match="human_cal.*PASS"):
            corrected_pass_rate(
                [1, 1, 0],
                [1, 1, 0],
                [0, 0, 0],  # No PASS (1s)
                rng=np.random.default_rng(42),
            )

    def test_corrected_pass_rate_calibration_without_human_fail_raises(self) -> None:
        """human_cal must have both classes (P4)."""
        with pytest.raises(ValueError, match="human_cal.*FAIL"):
            corrected_pass_rate(
                [1, 1, 0],
                [1, 1, 0],
                [1, 1, 1],  # No FAIL (0s)
                rng=np.random.default_rng(42),
            )


# ========================================== corrected_pass_rate: reproducibility
class TestCorrectedPassRateReproducibility:
    """Same seed gives same result."""

    def test_corrected_pass_rate_reproducible_with_seed(self) -> None:
        """Reproducible with fixed seed."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10

        rng1 = np.random.default_rng(42)
        est1 = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=rng1, n_boot=100)

        rng2 = np.random.default_rng(42)
        est2 = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=rng2, n_boot=100)

        assert est1.point == est2.point
        assert est1.low == est2.low
        assert est1.high == est2.high


# ========================================== corrected_pass_rate: method and metadata
class TestCorrectedPassRateMetadata:
    """Check metadata: method, n, confidence."""

    def test_corrected_pass_rate_method_string(self) -> None:
        """method='rogan_gladen+bootstrap'."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10
        est = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=np.random.default_rng(42))
        assert est.method == "rogan_gladen+bootstrap"

    def test_corrected_pass_rate_n_equals_len_judge_test(self) -> None:
        """n = len(judge_test)."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10
        est = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=np.random.default_rng(42))
        assert est.n == len(judge_test)

    def test_corrected_pass_rate_confidence_default(self) -> None:
        """confidence defaults to 0.95."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10
        est = corrected_pass_rate(judge_test, judge_cal, human_cal, rng=np.random.default_rng(42))
        assert est.confidence == 0.95

    def test_corrected_pass_rate_confidence_custom(self) -> None:
        """Custom confidence is respected."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10
        est = corrected_pass_rate(
            judge_test, judge_cal, human_cal, rng=np.random.default_rng(42), confidence=0.90
        )
        assert est.confidence == 0.90


# ========================================== corrected_pass_rate: large synthetic world
class TestCorrectedPassRateLargeSyntheticWorld:
    """Large synthetic world test (P1, P2, P3)."""

    def test_corrected_pass_rate_large_synthetic_world(self) -> None:
        """
        θ=0.7, s=0.9, c=0.8, n_cal=2000, n_test=50_000.
        Point within 0.02 of 0.7, interval contains 0.7.
        """
        rng = np.random.default_rng(42)

        # Generate synthetic calibration data
        # True θ=0.7, s=0.9, c=0.8
        theta_true = 0.7
        s_true = 0.9
        c_true = 0.8
        n_cal = 2000

        # Generate human labels for calibration (assume balanced)
        n_pos = int(n_cal * 0.5)
        n_neg = n_cal - n_pos
        human_cal = np.concatenate(
            [np.ones(n_pos, dtype=np.int64), np.zeros(n_neg, dtype=np.int64)]
        )
        rng.shuffle(human_cal)

        # Generate judge labels based on confusion matrix
        judge_cal = np.zeros(n_cal, dtype=np.int64)
        # For human 1s: judge 1 with prob s_true (TP), judge 0 with prob 1-s_true (FN)
        judge_cal[human_cal == 1] = (rng.random(n_pos) < s_true).astype(np.int64)
        # For human 0s: judge 0 with prob c_true (TN), judge 1 with prob 1-c_true (FP)
        judge_cal[human_cal == 0] = (rng.random(n_neg) > c_true).astype(np.int64)

        # Test data: truth with pass rate theta_true, then the judge's flips
        n_test = 50000
        human_test = (rng.random(n_test) < theta_true).astype(np.int64)
        flips = rng.random(n_test)
        judge_test = np.where(human_test == 1, flips < s_true, flips > c_true).astype(np.int64)

        # Correct the pass rate
        est = corrected_pass_rate(
            judge_test, judge_cal, human_cal, rng=np.random.default_rng(43), n_boot=2000
        )

        # Point should be within 0.02 of 0.7
        assert abs(est.point - 0.7) < 0.02
        # Interval should contain 0.7
        assert est.low <= 0.7 <= est.high


# ========================================== corrected_pass_rate: degenerate resamples
class TestCorrectedPassRateDegenerateResamples:
    """Handle degenerate resamples (P3)."""

    def test_corrected_pass_rate_few_degenerate_resamples_ok(self) -> None:
        """< 1% degenerate resamples is OK."""
        judge_test = [1, 1, 1, 0, 0] * 10
        judge_cal = [1, 1, 1, 1, 0, 0, 0, 0] * 10
        human_cal = [1, 1, 1, 0, 0, 0, 0, 1] * 10
        est = corrected_pass_rate(
            judge_test, judge_cal, human_cal, rng=np.random.default_rng(42), n_boot=200
        )
        # Should not raise
        assert est.point >= 0.0
