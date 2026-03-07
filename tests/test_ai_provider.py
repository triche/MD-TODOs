"""Unit tests for the AIProvider ABC and CompletionOptions."""

import pytest

from src.ai.provider import (
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderUnavailableError,
    CompletionOptions,
)


class TestCompletionOptions:
    """Tests for the CompletionOptions dataclass."""

    def test_defaults(self) -> None:
        opts = CompletionOptions()
        assert opts.model is None
        assert opts.max_tokens == 4096
        assert opts.temperature == 0.3
        assert opts.stop == []

    def test_custom_values(self) -> None:
        opts = CompletionOptions(model="gpt-5.2", max_tokens=2048, temperature=0.7, stop=["END"])
        assert opts.model == "gpt-5.2"
        assert opts.max_tokens == 2048
        assert opts.temperature == 0.7
        assert opts.stop == ["END"]

    def test_frozen(self) -> None:
        opts = CompletionOptions()
        with pytest.raises(AttributeError):
            opts.model = "changed"  # type: ignore[misc]


class TestAIProviderIsAbstract:
    """Verify that AIProvider cannot be instantiated directly."""

    def test_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            AIProvider()  # type: ignore[abstract]  # pylint: disable=abstract-class-instantiated


class TestExceptionHierarchy:
    """All provider exceptions inherit from AIProviderError."""

    def test_auth_error(self) -> None:
        assert issubclass(AIProviderAuthError, AIProviderError)

    def test_rate_limit_error(self) -> None:
        assert issubclass(AIProviderRateLimitError, AIProviderError)

    def test_unavailable_error(self) -> None:
        assert issubclass(AIProviderUnavailableError, AIProviderError)

    def test_catch_all_base(self) -> None:
        """All provider exceptions can be caught with AIProviderError."""
        for exc_cls in (AIProviderAuthError, AIProviderRateLimitError, AIProviderUnavailableError):
            exc = exc_cls("test")
            assert isinstance(exc, AIProviderError)
