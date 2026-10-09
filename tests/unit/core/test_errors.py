"""Tests for the EvalHawk exception hierarchy (card J1).

All application exceptions inherit from EvalhawkError, with specialized subclasses
for different failure modes: DataError (user data), ConfigError (config), StoreError
(storage).
"""

import pytest

from evalhawk.core.errors import (
    ConfigError,
    DataError,
    EvalhawkError,
    JudgeTooWeakError,
    StoreError,
)


# ---------------------------------------------------------------- hierarchy
def test_evalhawk_error_is_an_exception() -> None:
    """EvalhawkError is the base class for all EvalHawk errors."""
    assert issubclass(EvalhawkError, Exception)


@pytest.mark.parametrize(
    "error_class",
    [DataError, ConfigError, StoreError, JudgeTooWeakError],
    ids=["DataError", "ConfigError", "StoreError", "JudgeTooWeakError"],
)
def test_every_error_is_an_evalhawk_error(error_class: type[EvalhawkError]) -> None:
    """All specific error types inherit from EvalhawkError."""
    assert issubclass(error_class, EvalhawkError)


def test_catching_the_base_class_catches_subclasses() -> None:
    """Catching EvalhawkError catches all its subclasses."""
    errors_caught = []
    for error_class in [DataError, ConfigError, StoreError, JudgeTooWeakError]:
        try:
            raise error_class("test")
        except EvalhawkError as e:
            errors_caught.append(type(e))

    assert errors_caught == [DataError, ConfigError, StoreError, JudgeTooWeakError]
