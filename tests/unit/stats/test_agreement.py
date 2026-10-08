\"\"\"Tests for judge agreement metrics (card S2).

Card S2 implements confusion matrix, sensitivity, specificity, and Cohen's kappa.
PASS is the positive class; see architecture §13.1 for the naming convention.
\"\"\"

import numpy as np
import pytest

from evalhawk.stats.agreement import (
    Confusion,
    cohen_kappa,
    confusion,
    sensitivity,
    specificity,
)


# ================================================== golden values: hand example
class TestHandExample:
    \"\"\"Known correct values from the specification.\"\"\"

    def test_hand_example_confusion(self) -> None:
        \"\"\"Hand example: human [1,1,1,1,1,1,0,0,0,0], judge [1,1,1,1,1,0,1,0,0,0].\"\"\"
        human = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]
        c = confusion(human, judge)
        assert c.tp == 5
        assert c.fn == 1
        assert c.fp == 1
        assert c.tn == 3

    def test_hand_example_sensitivity(self) -> None:
        \"\"\"Sensitivity = 5/6 = 0.8333.\"\"\"
        c = Confusion(tp=5, fn=1, fp=1, tn=3)
        est = sensitivity(c)
        assert est.point == pytest.approx(5 / 6, abs=1e-4)

    def test_hand_example_specificity(self) -> None:
        \"\"\"Specificity = 3/4 = 0.75.\"\"\"
        c = Confusion(tp=5, fn=1, fp=1, tn=3)
        est = specificity(c)
        assert est.point == pytest.approx(0.75, abs=1e-4)

    def test_hand_example_kappa_point(self) -> None:
        \"\"\"Kappa point = 0.5833.\"\"\"
        human = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng)
        # p_o = (5+3)/10 = 0.8
        # p_e = (6/10)*(6/10) + (4/10)*(4/10) = 0.36 + 0.16 = 0.52
        # κ = (0.8 - 0.52) / (1 - 0.52) = 0.28 / 0.48 = 0.5833
        assert est.point == pytest.approx(0.5833, abs=1e-4)




# ================================================== confusion matrix
class TestConfusionValidation:
    \"\"\"Validation of Confusion dataclass.\"\"\"

    def test_confusion_valid(self) -> None:
        \"\"\"Valid confusion matrix.\"\"\"
        c = Confusion(tp=5, fn=1, fp=1, tn=3)
        assert c.n == 10

    def test_confusion_tp_negative_raises(self) -> None:
        \"\"\"Negative tp raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"tp must be >= 0\"):
            Confusion(tp=-1, fn=1, fp=1, tn=3)

    def test_confusion_fn_negative_raises(self) -> None:
        \"\"\"Negative fn raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"fn must be >= 0\"):
            Confusion(tp=1, fn=-1, fp=1, tn=3)

    def test_confusion_fp_negative_raises(self) -> None:
        \"\"\"Negative fp raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"fp must be >= 0\"):
            Confusion(tp=1, fn=1, fp=-1, tn=3)

    def test_confusion_tn_negative_raises(self) -> None:
        \"\"\"Negative tn raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"tn must be >= 0\"):
            Confusion(tp=1, fn=1, fp=1, tn=-1)

    def test_confusion_all_zero_raises(self) -> None:
        \"\"\"All zeros raises ValueError (total < 1).\"\"\"
        with pytest.raises(ValueError, match=\"total must be >= 1\"):
            Confusion(tp=0, fn=0, fp=0, tn=0)


# ================================================== confusion() function
class TestConfusionFunction:
    \"\"\"Test confusion() function.\"\"\"

    def test_confusion_array_inputs(self) -> None:
        \"\"\"confusion() accepts array-like inputs.\"\"\"
        human = np.array([1, 1, 0, 0])
        judge = np.array([1, 0, 0, 0])
        c = confusion(human, judge)
        assert c.tp == 1
        assert c.fn == 1
        assert c.fp == 0
        assert c.tn == 2

    def test_confusion_list_inputs(self) -> None:
        \"\"\"confusion() accepts list inputs.\"\"\"
        c = confusion([1, 1, 0, 0], [1, 0, 0, 0])
        assert c.tp == 1
        assert c.fn == 1
        assert c.fp == 0
        assert c.tn == 2

    def test_confusion_bool_inputs(self) -> None:
        \"\"\"confusion() accepts bool arrays.\"\"\"
        human = np.array([True, True, False, False])
        judge = np.array([True, False, False, False])
        c = confusion(human, judge)
        assert c.tp == 1
        assert c.fn == 1
        assert c.fp == 0
        assert c.tn == 2

    def test_confusion_length_mismatch_raises(self) -> None:
        \"\"\"Length mismatch raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"must have the same length\"):
            confusion([1, 1, 0], [1, 0, 0, 0])

    def test_confusion_2d_array_raises(self) -> None:
        \"\"\"2-D array raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"must be 1-D\"):
            confusion([[1, 0]], [1, 0])

    def test_confusion_empty_raises(self) -> None:
        \"\"\"Empty array raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"non-empty\"):
            confusion([], [])

    def test_confusion_invalid_value_raises(self) -> None:
        \"\"\"Invalid value (not 0/1) raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"must contain only 0, 1\"):
            confusion([1, 1, 2], [1, 0, 0])


# ================================================== sensitivity
class TestSensitivity:
    \"\"\"Test sensitivity() function.\"\"\"

    def test_sensitivity_basic(self) -> None:
        \"\"\"Sensitivity computed correctly.\"\"\"
        c = Confusion(tp=8, fn=2, fp=1, tn=9)
        est = sensitivity(c)
        assert est.point == pytest.approx(0.8, abs=1e-6)
        assert est.n == 10

    def test_sensitivity_all_tp(self) -> None:
        \"\"\"All true positives: sensitivity = 1.0.\"\"\"
        c = Confusion(tp=5, fn=0, fp=1, tn=4)
        est = sensitivity(c)
        assert est.point == 1.0
        assert est.low >= 0.0
        assert est.high <= 1.0

    def test_sensitivity_no_pass_raises(self) -> None:
        \"\"\"No human PASS items raises ValueError.\"\"\"
        c = Confusion(tp=0, fn=0, fp=1, tn=9)
        with pytest.raises(ValueError, match=\"no PASS items\"):
            sensitivity(c)

    def test_sensitivity_confidence(self) -> None:
        \"\"\"confidence parameter passed through.\"\"\"
        c = Confusion(tp=5, fn=1, fp=1, tn=3)
        est = sensitivity(c, confidence=0.90)
        assert est.confidence == 0.90


# ================================================== specificity
class TestSpecificity:
    \"\"\"Test specificity() function.\"\"\"

    def test_specificity_basic(self) -> None:
        \"\"\"Specificity computed correctly.\"\"\"
        c = Confusion(tp=2, fn=3, fp=1, tn=4)
        est = specificity(c)
        assert est.point == pytest.approx(0.8, abs=1e-6)
        assert est.n == 10

    def test_specificity_all_tn(self) -> None:
        \"\"\"All true negatives: specificity = 1.0.\"\"\"
        c = Confusion(tp=1, fn=4, fp=0, tn=5)
        est = specificity(c)
        assert est.point == 1.0
        assert est.low >= 0.0
        assert est.high <= 1.0



# ================================================== cohen_kappa
class TestCohenKappa:
    \"\"\"Test cohen_kappa() function.\"\"\"

    def test_kappa_perfect_judge(self) -> None:
        \"\"\"Perfect agreement: kappa = 1.0.\"\"\"
        human = [1, 1, 0, 0]
        judge = [1, 1, 0, 0]
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng)
        assert est.point == pytest.approx(1.0, abs=1e-6)

    def test_kappa_random_chance(self) -> None:
        \"\"\"High disagreement: kappa close to 0.\"\"\"
        human = [1, 1, 0, 0]
        judge = [1, 0, 1, 0]
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng)
        assert -1.0 <= est.point <= 1.0

    def test_kappa_reproducible_seed(self) -> None:
        \"\"\"Same seed produces identical results.\"\"\"
        human = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]

        rng1 = np.random.default_rng(123)
        est1 = cohen_kappa(human, judge, rng=rng1)

        rng2 = np.random.default_rng(123)
        est2 = cohen_kappa(human, judge, rng=rng2)

        assert est1.point == est2.point
        assert est1.low == est2.low
        assert est1.high == est2.high

    def test_kappa_n_boot_too_small_raises(self) -> None:
        \"\"\"n_boot < 100 raises ValueError.\"\"\"
        human = [1, 1, 0, 0]
        judge = [1, 0, 0, 0]
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match=\"n_boot must be >= 100\"):
            cohen_kappa(human, judge, rng=rng, n_boot=50)

    def test_kappa_interval_properties(self) -> None:
        \"\"\"Kappa interval: low <= high, within [-1, 1].\"\"\"
        human = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0]
        judge = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng)
        assert est.low <= est.high
        assert -1.0 <= est.low
        assert est.high <= 1.0

    def test_kappa_both_constant_identical_raises(self) -> None:
        \"\"\"Both raters constant and identical: p_e == 1, raises ValueError.\"\"\"
        human = [1, 1, 1, 1]
        judge = [1, 1, 1, 1]
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match=\"identical.*kappa is undefined\"):
            cohen_kappa(human, judge, rng=rng)

    def test_kappa_invalid_inputs_raise(self) -> None:
        \"\"\"Invalid arrays raise ValueError.\"\"\"
        rng = np.random.default_rng(42)

        # Length mismatch
        with pytest.raises(ValueError, match=\"must have the same length\"):
            cohen_kappa([1, 1, 0], [1, 0, 0, 0], rng=rng)

        # 2-D array
        with pytest.raises(ValueError, match=\"must be 1-D\"):
            cohen_kappa([[1, 0]], [1, 0], rng=rng)

        # Empty
        with pytest.raises(ValueError, match=\"non-empty\"):
            cohen_kappa([], [], rng=rng)

        # Invalid value
        with pytest.raises(ValueError, match=\"must contain only 0, 1\"):
            cohen_kappa([1, 2], [1, 0], rng=rng)

    def test_kappa_method_string(self) -> None:
        \"\"\"method field is 'cohen_kappa+bootstrap'.\"\"\"
        human = [1, 1, 0, 0]
        judge = [1, 0, 0, 0]
        rng = np.random.default_rng(42)
        est = cohen_kappa(human, judge, rng=rng)
        assert est.method == \"cohen_kappa+bootstrap\"


# ================================================== as_binary edge cases
class TestAsBinaryErrors:
    \"\"\"Test as_binary() helper with error cases.\"\"\"

    def test_as_binary_2d_raises(self) -> None:
        \"\"\"2-D array raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"must be 1-D\"):
            confusion([[1, 0], [1, 0]], [1, 0, 1, 0])

    def test_as_binary_empty_raises(self) -> None:
        \"\"\"Empty array raises ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"non-empty\"):
            confusion([], [])

    def test_as_binary_invalid_value_raises(self) -> None:
        \"\"\"Values other than 0/1 raise ValueError.\"\"\"
        with pytest.raises(ValueError, match=\"must contain only 0, 1\"):
            confusion([1, 2], [1, 0])


    def test_specificity_no_fail_raises(self) -> None:
        \"\"\"No human FAIL items raises ValueError.\"\"\"
        c = Confusion(tp=5, fn=5, fp=0, tn=0)
        with pytest.raises(ValueError, match=\"no FAIL items\"):
            specificity(c)

    def test_specificity_always_pass_judge(self) -> None:
        \"\"\"Always-PASS judge: specificity point is 0.0.\"\"\"
        human = [1, 1, 1, 0, 0, 0]
        judge = [1, 1, 1, 1, 1, 1]
        c = confusion(human, judge)
        est = specificity(c)
        assert est.point == 0.0
