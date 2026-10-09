"""EvalHawk exception hierarchy for all application errors.

Users can catch EvalhawkError to catch any error raised on purpose by EvalHawk code.
"""


class EvalhawkError(Exception):
    """Base class for all EvalHawk errors.

    Subclasses indicate the nature of the problem: bad user data, bad config, or
    storage/I/O failures.
    """


class DataError(EvalhawkError):
    """User data is malformed or invalid.

    Examples: missing field in an evaluation file, row count mismatch, invalid
    format.
    """


class ConfigError(EvalhawkError):
    """Configuration is invalid or inconsistent.

    Examples: missing required setting, conflicting options, invalid parameter value.
    """


class StoreError(EvalhawkError):
    """Storage operation failed or was refused.

    Examples: database locked, file system full, permission denied.
    """


class JudgeTooWeakError(EvalhawkError):
    """Judge's calibration is too weak to correct.

    The judge's sensitivity and specificity (Youden's J = s + c − 1) are barely
    better than random, so correction would amplify noise rather than reduce it.
    Improve the judge or its prompt to get better signals.
    """
