"""Statistics core: pure functions over NumPy arrays.

No Pydantic models, no database, no network. Every function that uses
randomness takes an explicit ``numpy.random.Generator``.
See docs/architecture.md, section 7.
"""
