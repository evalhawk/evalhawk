"""evalhawk: trustworthy LLM evaluation.

Calibrate LLM judges against human labels, then report bias-corrected
results with honest error bars.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("evalhawk")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
