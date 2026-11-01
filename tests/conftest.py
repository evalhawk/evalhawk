"""Shared test fixtures."""

from collections.abc import Iterator

import pytest

from evalhawk.testing.fake_llm import FakeLLMServer


@pytest.fixture
def llm_server() -> Iterator[FakeLLMServer]:
    """A local fake OpenAI-compatible chat API (no network)."""
    with FakeLLMServer() as server:
        yield server
