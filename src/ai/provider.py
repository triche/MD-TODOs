"""Abstract base class for AI providers.

All LLM calls in MD-TODOs go through this interface. Agent code never
calls vendor SDKs directly — swap providers by implementing this ABC
and updating ``config.yaml``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompletionOptions:
    """Options passed to :meth:`AIProvider.complete`.

    Sensible defaults are provided; callers override only what they need.
    """

    model: str | None = None  # None → use the provider's configured default
    max_tokens: int = 4096
    temperature: float | None = 0.3  # None → let the model use its default
    stop: list[str] = field(default_factory=list)


class AIProvider(ABC):
    """Vendor-agnostic interface for LLM operations.

    Subclasses must implement ``complete()`` and ``classify()``.
    """

    # ── Core interface ─────────────────────────────────────────

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        options: CompletionOptions | None = None,
    ) -> str:
        """Generate a text completion.

        Args:
            system_prompt: System-level instructions (e.g. GTD skills).
            user_prompt: User-level content (e.g. open TODOs as JSON).
            options: Optional generation parameters.

        Returns:
            The model's response text.

        Raises:
            AIProviderError: On unrecoverable API failure.
        """

    @abstractmethod
    async def classify(
        self,
        text: str,
        categories: list[str],
    ) -> str:
        """Classify *text* into one of the given *categories*.

        Args:
            text: The text to classify.
            categories: Allowed category labels.

        Returns:
            The chosen category label (must be one of *categories*).

        Raises:
            AIProviderError: On unrecoverable API failure.
        """


# ── Exceptions ─────────────────────────────────────────────────


class AIProviderError(Exception):
    """Base exception for AI provider failures."""


class AIProviderAuthError(AIProviderError):
    """Raised when authentication with the AI provider fails (bad/missing key)."""


class AIProviderRateLimitError(AIProviderError):
    """Raised when the API rate limit is exceeded (after retries)."""


class AIProviderUnavailableError(AIProviderError):
    """Raised when the AI service is unreachable (after retries)."""
