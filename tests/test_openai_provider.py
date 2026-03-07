"""Unit tests for the OpenAI provider (with mocked API responses)."""

from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import (
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderUnavailableError,
    CompletionOptions,
)
from src.ai.retry import RetryConfig


def _make_chat_response(content: str) -> MagicMock:
    """Build a fake ChatCompletion response object."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


class TestOpenAIProviderComplete:
    """Tests for OpenAIProvider.complete()."""

    @pytest.fixture
    def fast_retry(self) -> RetryConfig:
        """Retry config with near-zero delays for fast tests."""
        return RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05)

    @pytest.fixture
    def provider(self, fast_retry: RetryConfig) -> OpenAIProvider:
        """OpenAIProvider with a patched client."""
        return OpenAIProvider(api_key="test-key", default_model="gpt-test", retry_config=fast_retry)

    @pytest.mark.asyncio
    async def test_successful_completion(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("Hello world"))
        provider.client.chat.completions.create = mock_create

        result = await provider.complete("system msg", "user msg")
        assert result == "Hello world"

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-test"
        assert call_kwargs.kwargs["messages"][0]["content"] == "system msg"
        assert call_kwargs.kwargs["messages"][1]["content"] == "user msg"

    @pytest.mark.asyncio
    async def test_custom_model_override(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("result"))
        provider.client.chat.completions.create = mock_create

        opts = CompletionOptions(model="gpt-5.2", max_tokens=1024, temperature=0.9)
        await provider.complete("sys", "usr", options=opts)

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-5.2"
        assert call_kwargs.kwargs["max_tokens"] == 1024
        assert call_kwargs.kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_empty_response_raises(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response(None))
        # content=None scenario
        msg_mock = MagicMock()
        msg_mock.content = None
        choice = MagicMock()
        choice.message = msg_mock
        resp = MagicMock()
        resp.choices = [choice]
        mock_create.return_value = resp
        provider.client.chat.completions.create = mock_create

        with pytest.raises(AIProviderError, match="empty response"):
            await provider.complete("sys", "usr")

    @pytest.mark.asyncio
    async def test_auth_error(self, provider: OpenAIProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "bad key"}}
        error = openai.AuthenticationError(
            message="bad key",
            response=mock_response,
            body={"error": {"message": "bad key"}},
        )
        mock_create = AsyncMock(side_effect=error)
        provider.client.chat.completions.create = mock_create

        with pytest.raises(AIProviderAuthError, match="authentication failed"):
            await provider.complete("sys", "usr")

    @pytest.mark.asyncio
    async def test_rate_limit_retries_then_raises(self, provider: OpenAIProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "rate limited"}}
        error = openai.RateLimitError(
            message="rate limited",
            response=mock_response,
            body={"error": {"message": "rate limited"}},
        )
        mock_create = AsyncMock(side_effect=error)
        provider.client.chat.completions.create = mock_create

        with pytest.raises(AIProviderRateLimitError, match="rate limit"):
            await provider.complete("sys", "usr")
        # 1 initial + 2 retries = 3
        assert mock_create.call_count == 3

    @pytest.mark.asyncio
    async def test_timeout_retries_then_raises(self, provider: OpenAIProvider) -> None:
        error = openai.APITimeoutError(request=MagicMock())
        mock_create = AsyncMock(side_effect=error)
        provider.client.chat.completions.create = mock_create

        with pytest.raises(AIProviderUnavailableError, match="unavailable"):
            await provider.complete("sys", "usr")
        assert mock_create.call_count == 3

    @pytest.mark.asyncio
    async def test_transient_error_then_success(self, provider: OpenAIProvider) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_response.json.return_value = {"error": {"message": "server error"}}
        error = openai.InternalServerError(
            message="server error",
            response=mock_response,
            body={"error": {"message": "server error"}},
        )
        mock_create = AsyncMock(side_effect=[error, _make_chat_response("recovered")])
        provider.client.chat.completions.create = mock_create

        result = await provider.complete("sys", "usr")
        assert result == "recovered"
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_sequences_passed(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("stopped"))
        provider.client.chat.completions.create = mock_create

        opts = CompletionOptions(stop=["###", "END"])
        await provider.complete("sys", "usr", options=opts)

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["stop"] == ["###", "END"]


class TestOpenAIProviderClassify:
    """Tests for OpenAIProvider.classify()."""

    @pytest.fixture
    def fast_retry(self) -> RetryConfig:
        """Retry config with near-zero delays for fast tests."""
        return RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.05)

    @pytest.fixture
    def provider(self, fast_retry: RetryConfig) -> OpenAIProvider:
        """OpenAIProvider with a patched client."""
        return OpenAIProvider(api_key="test-key", default_model="gpt-test", retry_config=fast_retry)

    @pytest.mark.asyncio
    async def test_classify_returns_matching_category(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("  todo  "))
        provider.client.chat.completions.create = mock_create

        result = await provider.classify("Buy milk ASAP", ["todo", "not_todo"])
        assert result == "todo"

    @pytest.mark.asyncio
    async def test_classify_case_insensitive(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("TODO"))
        provider.client.chat.completions.create = mock_create

        result = await provider.classify("Buy milk", ["todo", "not_todo"])
        assert result == "todo"

    @pytest.mark.asyncio
    async def test_classify_unrecognised_returns_raw(self, provider: OpenAIProvider) -> None:
        mock_create = AsyncMock(return_value=_make_chat_response("maybe_todo"))
        provider.client.chat.completions.create = mock_create

        result = await provider.classify("Some text", ["todo", "not_todo"])
        assert result == "maybe_todo"
