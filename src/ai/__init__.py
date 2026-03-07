"""AI provider abstraction layer."""

from src.ai.factory import create_provider
from src.ai.keychain import (
    KeychainError,
    KeychainItemNotFoundError,
    KeychainUnavailableError,
    delete_api_key,
    get_api_key,
    set_api_key,
)
from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import (
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderUnavailableError,
    CompletionOptions,
)
from src.ai.retry import RetryConfig

__all__ = [
    "AIProvider",
    "AIProviderAuthError",
    "AIProviderError",
    "AIProviderRateLimitError",
    "AIProviderUnavailableError",
    "CompletionOptions",
    "KeychainError",
    "KeychainItemNotFoundError",
    "KeychainUnavailableError",
    "OpenAIProvider",
    "RetryConfig",
    "create_provider",
    "delete_api_key",
    "get_api_key",
    "set_api_key",
]
