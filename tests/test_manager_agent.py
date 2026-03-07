"""Integration tests for the Manager agent with mock AI responses."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest

from src.ai.provider import AIProvider, CompletionOptions
from src.common.config_models import AppConfig
from src.common.store import TodoStore
from src.common.todo_models import TodoItem
from src.manager.agent import ManagerAgent, PlanGenerationError
from src.manager.prompt_builder import ALL_PLAN_TYPES, PlanType

# ---------------------------------------------------------------------------
# Mock AI provider
# ---------------------------------------------------------------------------


class MockAIProvider(AIProvider):
    """AI provider that returns canned responses for testing."""

    def __init__(self, response: str = "# Mock Plan\n\n- [ ] Do things") -> None:
        self._response = response
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None
        self.last_options: CompletionOptions | None = None
        self.call_count: int = 0

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        options: CompletionOptions | None = None,
    ) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        self.last_options = options
        self.call_count += 1
        return self._response

    async def classify(self, text: str, categories: list[str]) -> str:
        return categories[0]


# ---------------------------------------------------------------------------
# ManagerAgent tests
# ---------------------------------------------------------------------------


class TestManagerAgent:
    """Integration tests for ManagerAgent."""

    @pytest.fixture
    def skills_file(self, tmp_path: Path) -> Path:
        """Create a minimal GTD skills file."""
        skills = tmp_path / "skills" / "gtd.md"
        skills.parent.mkdir(parents=True)
        skills.write_text("# GTD Reference\n\nThis is a test GTD skills file.\n")
        return skills

    @pytest.fixture
    def store_path(self, tmp_path: Path) -> Path:
        """Return a path for the TODO store."""
        return tmp_path / "store" / "todos.json"

    @pytest.fixture
    def plans_dir(self, tmp_path: Path) -> Path:
        """Return a plans directory path."""
        d = tmp_path / "plans"
        d.mkdir()
        return d

    @pytest.fixture
    def app_config(
        self, tmp_path: Path, skills_file: Path, store_path: Path, plans_dir: Path
    ) -> AppConfig:
        """Create a minimal AppConfig for testing."""
        return AppConfig(
            notes_dir=tmp_path / "notes",
            plans_dir=plans_dir,
            data_dir=tmp_path,
            store_path=store_path,
            skills_path=skills_file,
        )

    @pytest.fixture
    def populated_store(self, store_path: Path) -> TodoStore:
        """Create a store with some open TODO items."""
        store = TodoStore(store_path)
        store.load()
        store.add(
            TodoItem(
                text="Buy groceries",
                source_file="personal/shopping.md",
                source_line=3,
                detection_method="checkbox",
                tags=["personal", "errands"],
            )
        )
        store.add(
            TodoItem(
                text="Review pull request #42",
                source_file="work/tasks.md",
                source_line=10,
                detection_method="keyword",
                tags=["work", "code-review"],
            )
        )
        store.add(
            TodoItem(
                text="Schedule dentist appointment",
                source_file="personal/health.md",
                source_line=5,
                detection_method="ai_implicit",
                tags=["personal", "health"],
            )
        )
        store.save()
        return store

    @pytest.fixture
    def mock_provider(self) -> MockAIProvider:
        """Create a mock AI provider."""
        return MockAIProvider()

    @pytest.mark.parametrize("plan_type", ALL_PLAN_TYPES)
    def test_generate_plan_all_types(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
        plan_type: PlanType,
    ) -> None:
        """Each plan type produces a correctly named file."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        d = date(2026, 3, 7)
        result = asyncio.run(agent.generate_plan(plan_type, d))

        assert result.exists()
        assert result.name.startswith("2026-03-07")
        assert result.name.endswith(".md")
        assert result.read_text(encoding="utf-8") == "# Mock Plan\n\n- [ ] Do things"

    def test_morning_plan_path_structure(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
        plans_dir: Path,
    ) -> None:
        """Morning plan is written to plans/<year>/<month>/<filename>.md."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        d = date(2026, 3, 7)
        result = asyncio.run(agent.generate_plan("morning", d))

        expected = plans_dir / "2026" / "03" / "2026-03-07-morning-plan.md"
        assert result == expected

    def test_afternoon_plan_filename(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        d = date(2026, 6, 15)
        result = asyncio.run(agent.generate_plan("afternoon", d))
        assert result.name == "2026-06-15-afternoon-plan.md"

    def test_weekly_review_filename(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        d = date(2026, 3, 6)
        result = asyncio.run(agent.generate_plan("weekly-review", d))
        assert result.name == "2026-03-06-weekly-review.md"

    def test_weekly_plan_filename(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        result = asyncio.run(agent.generate_plan("weekly-plan", date(2026, 3, 8)))
        assert result.name == "2026-03-08-weekly-plan.md"

    def test_system_prompt_includes_skills_and_instructions(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """System prompt should contain both GTD skills and plan-type instructions."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

        assert mock_provider.last_system_prompt is not None
        assert "GTD Reference" in mock_provider.last_system_prompt
        assert "Morning Plan" in mock_provider.last_system_prompt

    def test_user_prompt_includes_todos_as_json(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """User prompt should contain the open TODOs as JSON."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

        assert mock_provider.last_user_prompt is not None
        assert "Buy groceries" in mock_provider.last_user_prompt
        assert "Review pull request #42" in mock_provider.last_user_prompt
        assert "Schedule dentist appointment" in mock_provider.last_user_prompt
        assert "3 total" in mock_provider.last_user_prompt

    def test_completion_options_use_config(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """AI call should use the generation model from config."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

        assert mock_provider.last_options is not None
        assert mock_provider.last_options.model == app_config.ai.models.generation
        assert mock_provider.last_options.max_tokens == app_config.ai.max_tokens
        assert mock_provider.last_options.temperature == app_config.ai.temperature

    def test_generate_plan_sync(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """Synchronous wrapper should work correctly."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        result = agent.generate_plan_sync("morning", date(2026, 3, 7))
        assert result.exists()

    def test_empty_store_generates_plan(
        self,
        app_config: AppConfig,
        store_path: Path,
        mock_provider: MockAIProvider,
    ) -> None:
        """Plan generation works even with no open TODOs."""
        empty_store = TodoStore(store_path)
        empty_store.load()
        agent = ManagerAgent(app_config, provider=mock_provider, store=empty_store)
        result = asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

        assert result.exists()
        assert mock_provider.last_user_prompt is not None
        assert "no open todo items" in mock_provider.last_user_prompt.lower()

    def test_ai_failure_raises_plan_generation_error(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
    ) -> None:
        """If the AI provider fails, PlanGenerationError is raised."""
        from src.ai.provider import AIProviderError

        class FailingProvider(MockAIProvider):
            async def complete(
                self,
                system_prompt: str,
                user_prompt: str,
                options: CompletionOptions | None = None,
            ) -> str:
                msg = "API unreachable"
                raise AIProviderError(msg)

        agent = ManagerAgent(app_config, provider=FailingProvider(), store=populated_store)
        with pytest.raises(PlanGenerationError, match="AI provider failed"):
            asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

    def test_missing_skills_file_raises(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """Missing skills file should raise PlanGenerationError."""
        bad_config = app_config.model_copy(update={"skills_path": Path("/nonexistent/gtd.md")})
        agent = ManagerAgent(bad_config, provider=mock_provider, store=populated_store)
        with pytest.raises(PlanGenerationError, match="Failed to load GTD skills"):
            asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))

    def test_creates_plan_directories(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
        plans_dir: Path,
    ) -> None:
        """Year/month directories should be created automatically."""
        d = date(2026, 11, 25)
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        result = asyncio.run(agent.generate_plan("morning", d))
        assert (plans_dir / "2026" / "11").is_dir()
        assert result.exists()

    def test_provider_called_once_per_plan(
        self,
        app_config: AppConfig,
        populated_store: TodoStore,
        mock_provider: MockAIProvider,
    ) -> None:
        """Each generate_plan call should make exactly one AI call."""
        agent = ManagerAgent(app_config, provider=mock_provider, store=populated_store)
        asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))
        assert mock_provider.call_count == 1

        asyncio.run(agent.generate_plan("afternoon", date(2026, 3, 7)))
        assert mock_provider.call_count == 2

    def test_store_reloaded_before_generation(
        self,
        app_config: AppConfig,
        store_path: Path,
        mock_provider: MockAIProvider,
    ) -> None:
        """Store should be reloaded to pick up extractor changes."""
        store = TodoStore(store_path)
        store.load()
        store.add(
            TodoItem(
                text="Initial item",
                source_file="notes.md",
                source_line=1,
                detection_method="checkbox",
            )
        )
        store.save()

        agent = ManagerAgent(app_config, provider=mock_provider, store=store)

        # Add another item to the store file externally
        store2 = TodoStore(store_path)
        store2.load()
        store2.add(
            TodoItem(
                text="External item",
                source_file="other.md",
                source_line=5,
                detection_method="keyword",
            )
        )
        store2.save()

        asyncio.run(agent.generate_plan("morning", date(2026, 3, 7)))
        # The agent should have picked up both items
        assert mock_provider.last_user_prompt is not None
        assert "2 total" in mock_provider.last_user_prompt
