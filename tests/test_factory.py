"""Unit tests for the AI provider factory."""

from unittest.mock import MagicMock, patch

import pytest

from src.ai.factory import create_provider
from src.ai.keychain import KeychainItemNotFoundError
from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import AIProviderAuthError
from src.ai.retry import RetryConfig
from src.common.config_models import AIConfig


class TestCreateProvider:
    """Tests for the create_provider factory function."""

    def test_creates_openai_provider_with_explicit_key(self) -> None:
        config = AIConfig(provider="openai")
        provider = create_provider(config, api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)

    def test_creates_openai_provider_case_insensitive(self) -> None:
        config = AIConfig(provider="OpenAI")
        provider = create_provider(config, api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)

    def test_uses_extraction_model_as_default(self) -> None:
        config = AIConfig(provider="openai")
        config.models.extraction = "custom-model"
        provider = create_provider(config, api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)
        assert provider.default_model == "custom-model"

    def test_passes_retry_config(self) -> None:
        config = AIConfig(provider="openai")
        retry = RetryConfig(max_retries=5)
        provider = create_provider(config, api_key="sk-test", retry_config=retry)
        assert isinstance(provider, OpenAIProvider)
        assert provider.retry_config.max_retries == 5

    def test_unknown_provider_raises(self) -> None:
        config = AIConfig(provider="anthropic")
        with pytest.raises(ValueError, match="Unknown AI provider"):
            create_provider(config, api_key="sk-test")

    @patch("src.ai.factory.get_api_key", return_value="sk-from-keychain")
    def test_gets_key_from_keychain(self, mock_get: MagicMock) -> None:
        config = AIConfig(provider="openai")
        provider = create_provider(config)
        assert isinstance(provider, OpenAIProvider)
        mock_get.assert_called_once()

    @patch("src.ai.factory.get_api_key", side_effect=KeychainItemNotFoundError("not found"))
    def test_raises_auth_error_when_keychain_empty(self, _mock_get: MagicMock) -> None:
        config = AIConfig(provider="openai")
        with pytest.raises(AIProviderAuthError, match="No API key found"):
            create_provider(config)

    def test_explicit_key_skips_keychain(self) -> None:
        """When api_key is given, Keychain should not be consulted."""
        config = AIConfig(provider="openai")
        with patch("src.ai.factory.get_api_key") as mock_get:
            provider = create_provider(config, api_key="sk-explicit")
            mock_get.assert_not_called()
        assert isinstance(provider, OpenAIProvider)
