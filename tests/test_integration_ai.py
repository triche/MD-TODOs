"""Integration smoke test — calls the real OpenAI API.

Skipped unless the ``MD_TODOS_TEST_API_KEY`` environment variable is set.
This test validates the full provider stack (Keychain bypass, retry,
real HTTP request) against the live API.
"""

import os

import pytest

from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import CompletionOptions
from src.ai.retry import RetryConfig

_API_KEY = os.environ.get("MD_TODOS_TEST_API_KEY")

pytestmark = pytest.mark.skipif(
    _API_KEY is None,
    reason="Set MD_TODOS_TEST_API_KEY to run integration tests",
)


class TestOpenAIIntegration:
    """Live API smoke tests."""

    @pytest.fixture
    def live_provider(self) -> OpenAIProvider:
        """Provider configured to hit the real OpenAI API."""
        assert _API_KEY is not None
        return OpenAIProvider(
            api_key=_API_KEY,
            default_model="gpt-4o-mini",
            retry_config=RetryConfig(max_retries=1, base_delay=1.0),
        )

    @pytest.mark.asyncio
    async def test_simple_completion(self, live_provider: OpenAIProvider) -> None:
        result = await live_provider.complete(
            system_prompt="You are a helpful assistant. Reply in one short sentence.",
            user_prompt="What is 2 + 2?",
            options=CompletionOptions(max_tokens=50, temperature=0.0),
        )
        assert len(result) > 0
        assert "4" in result

    @pytest.mark.asyncio
    async def test_classify(self, live_provider: OpenAIProvider) -> None:
        result = await live_provider.classify(
            text="I need to buy groceries tomorrow",
            categories=["todo", "not_todo"],
        )
        assert result in ("todo", "not_todo")
