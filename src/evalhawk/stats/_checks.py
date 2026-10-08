"""Private validation helpers for stats functions (P7)."""

import statistics

import numpy as np
import numpy.typing as npt


def check_confidence(confidence: float, name: str = "confidence") -> None:
    """Validate that confidence is a float strictly between 0 and 1.

    Args:
        confidence: The confidence level to validate.
        name: The parameter name to use in error messages.

    Raises:
        ValueError: If confidence is not in (0, 1).
    """
    if not (0 < confidence < 1):
        raise ValueError(
            f"{name} must be strictly between 0 and 1, got {confidence!r}"
        )


def z_value(confidence: float) -> float:
    """Compute the z-score for a given confidence level.

    Uses the normal distribution's inverse CDF to find the z-score such that
    the central confidence interval has the desired coverage.

    Args:
        confidence: Confidence level (e.g., 0.95 for 95%). Must be in (0, 1).

    Returns:
        The z-score for the given confidence level.

    Example:
        >>> z_value(0.95)
        1.959963984540054
    """
    return statistics.NormalDist().inv_cdf((1 + confidence) / 2)


def as_binary(
    name: str, values: npt.ArrayLike
) -> npt.NDArray[np.int64]:
    """Convert array-like to 1-D array of 0/1 values.

    Validates that the input is 1-D, non-empty, and contains only 0, 1, or bool
    values. Booleans are converted to 0/1. Returns a NumPy int64 array.

    Args:
        name: Parameter name for error messages.
        values: Array-like to convert. Must be 1-D and non-empty.

    Returns:
        A 1-D NumPy int64 array with values 0 or 1.

    Raises:
        ValueError: If the array is not 1-D, is empty, or contains values
            other than 0, 1, or bool.
    """
    arr = np.asarray(values)

    # Check 1-D
    if arr.ndim != 1:
        raise ValueError(
            f"{name} must be 1-D, got {arr.ndim}-D array of shape {arr.shape!r}"
        )

    # Check non-empty
    if arr.size == 0:
        raise ValueError(f"{name} must be non-empty, got shape {arr.shape!r}")

    # Convert bool to int
    if arr.dtype == bool:
        return arr.astype(np.int64)

    # Check values are 0 or 1
    if arr.dtype in (np.int64, np.int32, np.int16, np.int8, int):
        if np.all((arr == 0) | (arr == 1)):
            return np.asarray(arr, dtype=np.int64)
    if arr.dtype in (np.float64, np.float32, float):
        if np.all((arr == 0.0) | (arr == 1.0)):
            return np.asarray(arr, dtype=np.int64)

    raise ValueError(
        f"{name} must contain only 0, 1, or bool values, got {arr.dtype} "
        f"with values {np.unique(arr)!r}"
    )


def check_same_length(
    name1: str, arr1: npt.NDArray, name2: str, arr2: npt.NDArray
) -> None:
    """Validate that two arrays have the same length.

    Args:
        name1: Name of first array for error messages.
        arr1: First array.
        name2: Name of second array for error messages.
        arr2: Second array.

    Raises:
        ValueError: If arrays have different lengths.
    """
    if len(arr1) != len(arr2):
        raise ValueError(
            f"{name1} and {name2} must have the same length, "
            f"got {len(arr1)} and {len(arr2)}"
        )


def check_n_boot(n_boot: int, name: str = "n_boot") -> None:
    """Validate that n_boot is >= 100 (P8).

    Args:
        n_boot: Number of bootstrap resamples.
        name: Parameter name for error messages.

    Raises:
        ValueError: If n_boot < 100.
    """
    if n_boot < 100:
        raise ValueError(f"{name} must be >= 100, got {n_boot!r}")
