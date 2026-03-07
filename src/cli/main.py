"""CLI entry point for md-todos.

Commands:
    extract  — Run TODO extraction (full scan or watch mode).
    plan     — Generate a GTD plan.
    status   — Show agent status and open TODO count.
    install  — Interactive first-time setup.
    uninstall — Remove launchd agents and optionally all data.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from src.common.config import DEFAULT_CONFIG_PATH, load_config
from src.common.config_models import AppConfig
from src.common.logging import get_logger, setup_logging
from src.manager.prompt_builder import ALL_PLAN_TYPES, PlanType

logger = get_logger(__name__)

# Repo root — used to locate templates/ and skills/
_REPO_DIR = Path(__file__).resolve().parent.parent.parent

# launchd plist identifiers
_PLIST_IDS = (
    "com.md-todos.extractor",
    "com.md-todos.manager",
)


# ── Group ────────────────────────────────────────────────────


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False),
    default=None,
    envvar="MD_TODOS_CONFIG",
    help="Path to config.yaml (default: ~/.md-todos/config.yaml).",
)
@click.version_option(version="0.1.0", prog_name="md-todos")
@click.pass_context
def cli(ctx: click.Context, config_path: str | None) -> None:
    """MD-TODOs — AI-powered TODO extraction and GTD planning."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = Path(config_path) if config_path else None


# ── extract ──────────────────────────────────────────────────


@cli.command()
@click.option("--full", is_flag=True, help="Run a one-shot full scan instead of watch mode.")
@click.pass_context
def extract(ctx: click.Context, *, full: bool) -> None:
    """Extract TODOs from Markdown notes.

    By default, starts in watch mode (initial scan + live monitoring).
    Use --full for a single scan that exits when complete.
    """
    config = _load_config(ctx)
    setup_logging(config.logging.level, config.logging.file)

    from src.ai.provider import AIProviderAuthError
    from src.extractor.agent import ExtractorAgent

    provider = None
    if config.extractor.implicit_detection:
        try:
            from src.ai.factory import create_provider

            provider = create_provider(config.ai)
        except (AIProviderAuthError, ValueError) as exc:
            click.echo(f"Warning: AI provider unavailable ({exc}). Using regex-only detection.")

    agent = ExtractorAgent(config, provider=provider)

    if full:
        open_count = agent.run_full_scan()
        click.echo(f"Full scan complete. {open_count} open TODOs in store.")
    else:
        click.echo("Starting extractor in watch mode (Ctrl+C to stop)…")
        try:
            agent.run()
        except KeyboardInterrupt:
            click.echo("\nExtractor stopped.")


# ── plan ─────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--type",
    "plan_type",
    required=True,
    type=click.Choice(ALL_PLAN_TYPES),
    help="Type of GTD plan to generate.",
)
@click.pass_context
def plan(ctx: click.Context, plan_type: PlanType) -> None:
    """Generate a GTD plan from open TODOs."""
    config = _load_config(ctx)
    setup_logging(config.logging.level, config.logging.file)

    from src.ai.factory import create_provider
    from src.ai.provider import AIProviderAuthError
    from src.manager.agent import ManagerAgent, PlanGenerationError

    try:
        provider = create_provider(config.ai)
    except (AIProviderAuthError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    agent = ManagerAgent(config, provider=provider)

    try:
        output_path = agent.generate_plan_sync(plan_type)
    except PlanGenerationError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Plan written to {output_path}")


# ── status ───────────────────────────────────────────────────


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show agent status, store info, and launchd state."""
    config = _load_config(ctx)

    from src.common.store import StoreError, TodoStore

    # Store info
    store = TodoStore(config.store_path)
    try:
        store.load()
        click.echo(f"Store:       {store.path}")
        click.echo(f"  Open:      {store.open_count}")
        done_count = len(store.get_done())
        click.echo(f"  Done:      {done_count}")
        click.echo(f"  Total:     {store.count}")
    except (OSError, StoreError):  # store file missing, corrupt, or unreadable
        click.echo(f"Store:       {config.store_path.expanduser()} (not found or unreadable)")

    # Paths
    notes = config.notes_dir.expanduser()
    click.echo(f"Notes dir:   {notes} ({'exists' if notes.is_dir() else 'missing'})")
    plans = config.plans_dir.expanduser()
    click.echo(f"Plans dir:   {plans} ({'exists' if plans.is_dir() else 'missing'})")
    click.echo(f"Config:      {(ctx.obj.get('config_path') or DEFAULT_CONFIG_PATH).expanduser()}")

    # launchd agents
    click.echo("Agents:")
    for plist_id in _PLIST_IDS:
        state = _launchd_status(plist_id)
        click.echo(f"  {plist_id}: {state}")


# ── install ──────────────────────────────────────────────────


@cli.command()
@click.pass_context
def install(ctx: click.Context) -> None:
    """Interactive first-time setup.

    Creates the data directory, copies the config template, and stores
    the OpenAI API key in the macOS Keychain.
    """
    config_path = (ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH).expanduser()
    data_dir = config_path.parent

    click.echo("MD-TODOs — Interactive Setup\n")

    # 1. Data directory
    if data_dir.is_dir():
        click.echo(f"✓ Data directory exists: {data_dir}")
    else:
        click.echo(f"Creating data directory: {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "store").mkdir(exist_ok=True)
        (data_dir / "logs").mkdir(exist_ok=True)
        click.echo(f"✓ Created {data_dir}")

    # 2. Config file
    if config_path.is_file():
        click.echo(f"✓ Config file exists: {config_path}")
    else:
        template = _REPO_DIR / "templates" / "config.example.yaml"
        if template.is_file():
            shutil.copy2(template, config_path)
            click.echo(f"✓ Copied config template to {config_path}")
            click.echo(f"  Edit {config_path} to customise paths and settings.")
        else:
            click.echo(f"⚠ Config template not found at {template}. Skipping.")

    # 3. API key
    click.echo()
    _setup_api_key()

    # 4. Summary
    click.echo("\nSetup complete. Next steps:")
    click.echo(f"  1. Edit {config_path} (set notes_dir and plans_dir)")
    click.echo("  2. Run `md-todos extract --full` to do an initial scan")
    click.echo("  3. Run `md-todos plan --type morning` to generate a plan")
    click.echo("  4. (Phase 8) Run install.sh to configure launchd agents")


# ── uninstall ────────────────────────────────────────────────


@cli.command()
@click.option(
    "--all", "remove_all", is_flag=True, help="Also remove data directory and Keychain entry."
)
@click.pass_context
def uninstall(ctx: click.Context, *, remove_all: bool) -> None:
    """Remove launchd agents and optionally all data.

    Without --all, only unloads launchd agents and removes plist files.
    With --all, also removes the data directory and Keychain API key.
    """
    click.echo("MD-TODOs — Uninstall\n")

    # 1. Unload launchd agents
    launch_agents_dir = Path("~/Library/LaunchAgents").expanduser()
    for plist_id in _PLIST_IDS:
        plist_file = launch_agents_dir / f"{plist_id}.plist"
        if plist_file.is_file():
            click.echo(f"Unloading {plist_id}…")
            subprocess.run(
                ["launchctl", "unload", str(plist_file)],
                capture_output=True,
                check=False,
            )
            plist_file.unlink()
            click.echo(f"  ✓ Removed {plist_file}")
        else:
            click.echo(f"  — {plist_id} not installed")

    if not remove_all:
        click.echo("\nDone. Data directory and Keychain entry kept.")
        click.echo("Re-run with --all to remove everything.")
        return

    # 2. Remove data directory
    config_path = (ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH).expanduser()
    data_dir = config_path.parent

    if data_dir.is_dir():
        if click.confirm(f"Delete data directory {data_dir}?", default=False):
            shutil.rmtree(data_dir)
            click.echo(f"  ✓ Removed {data_dir}")
    else:
        click.echo(f"  — Data directory not found: {data_dir}")

    # 3. Remove Keychain entry
    from src.ai.keychain import KeychainError, delete_api_key

    try:
        deleted = delete_api_key()
        if deleted:
            click.echo("  ✓ Removed API key from Keychain")
        else:
            click.echo("  — No API key in Keychain")
    except KeychainError as exc:
        click.echo(f"  ⚠ Could not remove Keychain entry: {exc}")

    click.echo("\nUninstall complete.")


# ── Helpers ──────────────────────────────────────────────────


def _load_config(ctx: click.Context) -> AppConfig:
    """Load config from the path stored in the Click context."""
    config_path = ctx.obj.get("config_path")
    try:
        return load_config(config_path)
    except Exception as exc:
        raise click.ClickException(f"Failed to load config: {exc}") from exc


def _launchd_status(plist_id: str) -> str:
    """Check whether a launchd agent is loaded."""
    try:
        result = subprocess.run(
            ["launchctl", "list", plist_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return "loaded"
        return "not loaded"
    except FileNotFoundError:
        return "launchctl not available"


def _setup_api_key() -> None:
    """Prompt for an OpenAI API key and store it in the Keychain."""
    from src.ai.keychain import (
        KeychainError,
        KeychainItemNotFoundError,
        get_api_key,
        set_api_key,
    )

    # Check if key already exists
    existing = False
    try:
        get_api_key()
        existing = True
    except KeychainItemNotFoundError:
        pass
    except KeychainError as exc:
        click.echo(f"⚠ Keychain check failed: {exc}")
        return

    if existing:
        click.echo("✓ OpenAI API key already in Keychain")
        if not click.confirm("  Replace it?", default=False):
            return

    api_key = click.prompt("Enter your OpenAI API key", hide_input=True)
    if not api_key.strip():
        click.echo("  ⚠ Empty key — skipping.")
        return

    try:
        set_api_key(api_key.strip())
        click.echo("✓ API key stored in Keychain")
    except KeychainError as exc:
        click.echo(f"⚠ Failed to store API key: {exc}")


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
