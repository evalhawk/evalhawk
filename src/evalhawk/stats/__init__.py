"""Statistics core: pure functions over NumPy arrays.

No Pydantic models, no database, no network. Every function that uses
randomness takes an explicit ``numpy.random.Generator``.

**Pure statistic functions**: inputs are arrays (0/1 for counts); outputs are
frozen dataclasses (Estimate). No I/O, no printing, no global state.

**UNKNOWN handling**: stats/ only sees 0/1 arrays. Filtering UNKNOWN labels
and computing Estimate.unknown_rate belong to services/ (X1).

See docs/architecture.md, section 7.
"""
