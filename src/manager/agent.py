"""Manager agent — generates GTD plans from open TODO items.

The agent ties together the TODO store, GTD skills file, AI provider,
prompt builder, and plan file writer into a single entry point.

Usage::

    from src.manager.agent import ManagerAgent

    agent = ManagerAgent(config)
    await agent.generate_plan("morning")
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from src.ai.provider import AIProvider, AIProviderError, CompletionOptions
from src.common.config_models import AppConfig
from src.common.logging import get_logger
from src.common.skills import SkillsFileError, load_skills
from src.common.store import TodoStore
from src.manager.plan_writer import write_plan
from src.manager.prompt_builder import (
    PlanType,
    build_system_prompt,
    build_user_prompt,
)

logger = get_logger(__name__)


class PlanGenerationError(Exception):
    """Raised when plan generation fails."""


class ManagerAgent:
    """Reads open TODOs, builds GTD prompts, and generates Markdown plans.

    Args:
        config: Application configuration.
        provider: AI provider for plan generation.
        store: Optional pre-initialised store. If *None*, one is created
            from ``config.store_path``.
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        provider: AIProvider,
        store: TodoStore | None = None,
    ) -> None:
        self._config = config
        self._provider = provider
        self._plans_dir = config.plans_dir.expanduser().resolve()
        self._skills_path = config.skills_path

        # Store — read-only access for the manager
        self._store = store or TodoStore(config.store_path)
        self._store.load()

        # Cache skills content
        self._skills_content: str | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def store(self) -> TodoStore:
        """The TODO store (read-only from the manager's perspective)."""
        return self._store

    @property
    def plans_dir(self) -> Path:
        """Resolved plans directory path."""
        return self._plans_dir

    # ------------------------------------------------------------------
    # Skills loading
    # ------------------------------------------------------------------

    def _load_skills(self) -> str:
        """Load and cache the GTD skills file content."""
        if self._skills_content is None:
            self._skills_content = load_skills(self._skills_path)
        return self._skills_content

    # ------------------------------------------------------------------
    # Plan generation
    # ------------------------------------------------------------------

    async def generate_plan(
        self,
        plan_type: PlanType,
        plan_date: date | None = None,
    ) -> Path:
        """Generate a GTD plan and write it to disk.

        Args:
            plan_type: The type of plan to generate (morning, afternoon,
                weekly-review, weekly-plan).
            plan_date: Date for the plan.  Defaults to today.

        Returns:
            The absolute path to the generated plan file.

        Raises:
            PlanGenerationError: If skills loading, AI call, or file write fails.
        """
        logger.info("Generating %s plan", plan_type)

        # 1. Reload store to pick up any recent extractor changes
        self._store.load()

        # 2. Get open TODOs
        open_todos = self._store.get_open()
        logger.info("Found %d open TODOs for plan generation", len(open_todos))

        # 3. Load skills
        try:
            skills = self._load_skills()
        except SkillsFileError as exc:
            msg = f"Failed to load GTD skills file: {exc}"
            raise PlanGenerationError(msg) from exc

        # 4. Build prompts
        system_prompt = build_system_prompt(skills, plan_type)
        user_prompt = build_user_prompt(open_todos)

        # 5. Call AI provider
        options = CompletionOptions(
            model=self._config.ai.models.generation,
            max_tokens=self._config.ai.max_tokens,
            temperature=self._config.ai.temperature,
        )

        try:
            plan_content = await self._provider.complete(system_prompt, user_prompt, options)
        except AIProviderError as exc:
            msg = f"AI provider failed during {plan_type} plan generation: {exc}"
            raise PlanGenerationError(msg) from exc

        # 6. Write plan file
        output_path = write_plan(self._plans_dir, plan_type, plan_content, plan_date)

        logger.info("Successfully generated %s plan: %s", plan_type, output_path)
        return output_path

    def generate_plan_sync(
        self,
        plan_type: PlanType,
        plan_date: date | None = None,
    ) -> Path:
        """Synchronous wrapper around :meth:`generate_plan`.

        Convenience method for CLI and non-async callers.
        """
        return asyncio.run(self.generate_plan(plan_type, plan_date))
