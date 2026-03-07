"""Unit tests for the retry logic (exponential backoff)."""

from unittest.mock import AsyncMock

import pytest

from src.ai.retry import RetryConfig, _compute_delay, with_retry


class TestComputeDelay:
    """Tests for delay calculation."""

    def test_first_attempt(self) -> None:
        cfg = RetryConfig(base_delay=1.0, backoff_factor=2.0, max_delay=30.0)
        assert _compute_delay(0, cfg) == 1.0

    def test_second_attempt(self) -> None:
        cfg = RetryConfig(base_delay=1.0, backoff_factor=2.0, max_delay=30.0)
        assert _compute_delay(1, cfg) == 2.0

    def test_third_attempt(self) -> None:
        cfg = RetryConfig(base_delay=1.0, backoff_factor=2.0, max_delay=30.0)
        assert _compute_delay(2, cfg) == 4.0

    def test_capped_at_max_delay(self) -> None:
        cfg = RetryConfig(base_delay=10.0, backoff_factor=3.0, max_delay=30.0)
        # 10 * 3^2 = 90, capped to 30
        assert _compute_delay(2, cfg) == 30.0

    def test_custom_config(self) -> None:
        cfg = RetryConfig(base_delay=0.5, backoff_factor=1.5, max_delay=10.0)
        assert _compute_delay(0, cfg) == 0.5
        assert _compute_delay(1, cfg) == 0.75


class TestRetryConfig:
    """Tests for RetryConfig defaults."""

    def test_defaults(self) -> None:
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 30.0
        assert cfg.backoff_factor == 2.0

    def test_custom(self) -> None:
        cfg = RetryConfig(max_retries=5, base_delay=0.1, max_delay=5.0, backoff_factor=3.0)
        assert cfg.max_retries == 5
        assert cfg.base_delay == 0.1


class TestWithRetry:
    """Tests for the with_retry decorator."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self) -> None:
        mock_fn = AsyncMock(return_value="ok")

        @with_retry(
            config=RetryConfig(max_retries=3, base_delay=0.01),
            retryable=(ValueError,),
        )
        async def fn() -> str:
            return await mock_fn()

        result = await fn()
        assert result == "ok"
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self) -> None:
        mock_fn = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])

        @with_retry(
            config=RetryConfig(max_retries=3, base_delay=0.01),
            retryable=(ValueError,),
        )
        async def fn() -> str:
            return await mock_fn()

        result = await fn()
        assert result == "ok"
        assert mock_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_all_retries_exhausted(self) -> None:
        mock_fn = AsyncMock(side_effect=ValueError("persistent"))

        @with_retry(
            config=RetryConfig(max_retries=2, base_delay=0.01),
            retryable=(ValueError,),
        )
        async def fn() -> str:
            return await mock_fn()

        with pytest.raises(ValueError, match="persistent"):
            await fn()
        # 1 initial + 2 retries = 3 calls total
        assert mock_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self) -> None:
        mock_fn = AsyncMock(side_effect=TypeError("not retryable"))

        @with_retry(
            config=RetryConfig(max_retries=3, base_delay=0.01),
            retryable=(ValueError,),
        )
        async def fn() -> str:
            return await mock_fn()

        with pytest.raises(TypeError, match="not retryable"):
            await fn()
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retries_when_max_zero(self) -> None:
        mock_fn = AsyncMock(side_effect=ValueError("fail"))

        @with_retry(
            config=RetryConfig(max_retries=0, base_delay=0.01),
            retryable=(ValueError,),
        )
        async def fn() -> str:
            return await mock_fn()

        with pytest.raises(ValueError):
            await fn()
        assert mock_fn.call_count == 1

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self) -> None:
        @with_retry(retryable=(ValueError,))
        async def my_function() -> str:
            """My docstring."""
            return "result"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
