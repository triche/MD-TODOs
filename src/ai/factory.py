"""Factory for creating AI provider instances from configuration.

Reads ``config.ai.provider`` to decide which concrete ``AIProvider``
to instantiate. API keys are fetched from the macOS Keychain.
"""

import logging

from src.ai.keychain import (
    KeychainError,
    KeychainItemNotFoundError,
    get_api_key,
)
from src.ai.openai_provider import OpenAIProvider
from src.ai.provider import AIProvider, AIProviderAuthError
from src.ai.retry import RetryConfig
from src.common.config_models import AIConfig

logger = logging.getLogger("md_todos.ai.factory")

# Registry of supported provider names → factory callables.
# Extend this dict when adding new providers.
_PROVIDER_REGISTRY: dict[str, type] = {
    "openai": OpenAIProvider,
}


def create_provider(
    config: AIConfig,
    *,
    api_key: str | None = None,
    retry_config: RetryConfig | None = None,
) -> AIProvider:
    """Create an AI provider instance from the application config.

    Args:
        config: The ``ai`` section of ``AppConfig``.
        api_key: Optional explicit API key. If *None*, the key is
            fetched from the macOS Keychain.
        retry_config: Optional retry configuration override.

    Returns:
        An initialised :class:`AIProvider` instance.

    Raises:
        AIProviderAuthError: If no API key could be obtained.
        ValueError: If the configured provider name is not recognised.
    """
    provider_name = config.provider.lower()

    if provider_name not in _PROVIDER_REGISTRY:
        supported = ", ".join(sorted(_PROVIDER_REGISTRY))
        msg = f"Unknown AI provider {config.provider!r}. Supported providers: {supported}"
        raise ValueError(msg)

    # Resolve API key
    key = api_key
    if key is None:
        try:
            key = get_api_key()
            logger.debug("Retrieved API key from Keychain for provider %r", provider_name)
        except KeychainItemNotFoundError as exc:
            msg = (
                "No API key found in macOS Keychain. "
                "Run `md-todos install` or store the key manually:\n"
                "  security add-generic-password -s md-todos -a openai-api-key -w <YOUR_KEY>"
            )
            raise AIProviderAuthError(msg) from exc
        except KeychainError as exc:
            msg = f"Failed to retrieve API key from Keychain: {exc}"
            raise AIProviderAuthError(msg) from exc

    # Instantiate the provider
    match provider_name:
        case "openai":
            return OpenAIProvider(
                api_key=key,
                default_model=config.models.extraction,
                retry_config=retry_config,
            )
        case _:
            # This branch should be unreachable given the registry check above,
            # but satisfies the type-checker.
            msg = f"Unsupported provider: {provider_name}"
            raise ValueError(msg)
