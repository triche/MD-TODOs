"""CLI entry point for md-todos.

Stub for Phase 1 — full implementation in Phase 7.
"""

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="md-todos")
def cli() -> None:
    """MD-TODOs — AI-powered TODO extraction and GTD planning."""


if __name__ == "__main__":
    cli()
