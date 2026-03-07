"""OpenAI implementation of the AIProvider interface.

Uses the ``openai`` Python SDK. Retries transient errors (rate-limits,
server errors) with exponential back-off. Authentication failures and
exhausted retries are surfaced as typed exceptions.
"""

import logging

import openai
from openai import AsyncOpenAI

from src.ai.provider import (
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderUnavailableError,
    CompletionOptions,
)
from src.ai.retry import RetryConfig, with_retry

logger = logging.getLogger("md_todos.ai.openai")

# Exceptions from the openai SDK that are safe to retry
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


class OpenAIProvider(AIProvider):
    """AI provider backed by the OpenAI API.

    Args:
        api_key: OpenAI API key.
        default_model: Fallback model when ``CompletionOptions.model`` is *None*.
        retry_config: Optional retry configuration. Uses sensible defaults
            if *None*.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = "gpt-5-mini",
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.default_model = default_model
        self.retry_config = retry_config or RetryConfig()

    # ── AIProvider.complete ────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        options: CompletionOptions | None = None,
    ) -> str:
        opts = options or CompletionOptions()
        model = opts.model or self.default_model

        @with_retry(config=self.retry_config, retryable=_RETRYABLE_EXCEPTIONS)
        async def _call() -> str:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=opts.max_tokens,
                temperature=opts.temperature,
                stop=opts.stop or None,
            )
            content = response.choices[0].message.content
            if content is None:
                msg = "OpenAI returned an empty response"
                raise AIProviderError(msg)
            return content

        try:
            return await _call()
        except openai.AuthenticationError as exc:
            msg = f"OpenAI authentication failed: {exc}"
            raise AIProviderAuthError(msg) from exc
        except openai.RateLimitError as exc:
            msg = f"OpenAI rate limit exceeded after retries: {exc}"
            raise AIProviderRateLimitError(msg) from exc
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            msg = f"OpenAI service unavailable after retries: {exc}"
            raise AIProviderUnavailableError(msg) from exc
        except openai.OpenAIError as exc:
            msg = f"OpenAI API error: {exc}"
            raise AIProviderError(msg) from exc

    # ── AIProvider.classify ────────────────────────────────────

    async def classify(
        self,
        text: str,
        categories: list[str],
    ) -> str:
        categories_str = ", ".join(categories)
        system_prompt = (
            "You are a text classifier. Classify the following text into "
            f"exactly one of these categories: {categories_str}.\n\n"
            "Reply with ONLY the category name, nothing else."
        )

        result = await self.complete(
            system_prompt=system_prompt,
            user_prompt=text,
            options=CompletionOptions(
                max_tokens=50,
                temperature=0.0,
            ),
        )
        # Normalise: strip whitespace and attempt case-insensitive match
        cleaned = result.strip()
        for cat in categories:
            if cleaned.lower() == cat.lower():
                return cat
        # Fallback: return the raw response (caller can decide how to handle)
        logger.warning(
            "Classification response %r did not match any category in %s",
            cleaned,
            categories,
        )
        return cleaned
