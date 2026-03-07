# Copilot Instructions for MD-TODOs

## Project Overview

MD-TODOs is a local macOS framework with two AI-powered agents:

1. **TODO Extractor** — a long-running daemon that watches a user's Markdown notes directory, detects TODOs (via regex and LLM classification), and persists them to a JSON store.
2. **TODO Manager** — a scheduled agent that reads open TODOs, applies GTD methodology (from a skills file), and generates prioritized Markdown plans.

The repo is **public on GitHub**. All personal data (notes, plans, TODO store, logs, runtime config) lives **outside the repo** in a user-configurable data directory (default `~/.md-todos/`).

## Key Architecture Constraints

- **Repo vs. user data separation.** The repo contains only source code, skills files, configuration templates, install/deploy scripts, tests, and documentation. Never add code that reads from or writes to paths inside the repo for user data. All user-facing paths (`notes_dir`, `plans_dir`, `store_path`, `logs`) must resolve from `config.yaml`, which lives outside the repo.
- **AI provider abstraction.** All LLM calls go through the `AIProvider` interface (`src/ai/`). Never call the OpenAI SDK directly from agent code. If a new AI capability is needed, add it to the interface first.
- **GTD knowledge is in `skills/gtd.md`, not in code.** The Manager agent injects this file into the LLM system prompt. GTD logic should not be hard-coded. To change GTD behavior, update the skills file.
- **Config resolution order:** CLI flags → environment variables → `~/.md-todos/config.yaml` → built-in defaults. Respect this in all config-consuming code.
- **macOS-first, cross-platform later.** Use `launchd` for scheduling, macOS Keychain for secrets. Isolate platform-specific code so it can be swapped.
- **Notes directory is read-only.** The framework must never modify files in the user's notes directory.

## Repository Structure

```
MD-TODOs/
  src/
    extractor/          # TODO Extractor agent
    manager/            # TODO Manager agent
    ai/                 # AIProvider interface + OpenAI implementation
    common/             # Shared utilities: config, file I/O, logging, store
    cli/                # CLI entry points (extract, plan, install, uninstall, status)
  skills/
    gtd.md              # GTD methodology knowledge file
  templates/
    config.example.yaml # Annotated config template (committed)
    com.md-todos.extractor.plist  # launchd template
    com.md-todos.manager.plist    # launchd template
  scripts/
    install.sh          # One-command bootstrap
    uninstall.sh        # Clean teardown
  tests/
  docs/
    index.html          # Project documentation page (matches README.md)
    proposed-solution.md
    theory-of-operation.md
  pyproject.toml
  README.md
```

## Technology Stack

| Component | Choice |
|---|---|
| Language | Python 3.12+ |
| File watcher | `watchdog` (FSEvents on macOS) |
| Markdown parsing | `markdown-it-py` or regex |
| AI SDK | `openai` Python package |
| Config | `PyYAML` + `pydantic` |
| Store | JSON file (`store/todos.json`) |
| Scheduling | macOS `launchd` |
| Packaging | `uv` or `pip` + `venv` |
| API key storage | macOS Keychain (`security` CLI / `keyring`) |

## Coding Guidelines

### Python Style
- Target Python 3.12+. Use modern syntax: type hints, `match` statements where appropriate, f-strings.
- Use `pydantic` models for all structured data (config, TODO items, plan metadata).
- Use `pathlib.Path` for all file system operations.
- Follow PEP 8. Use `ruff` for linting and formatting.

### Code Quality Gate
- **Always keep working until all source code in `src/` and `tests/` is completely free of lint errors and warnings.** After any code change, run `ruff check src/ tests/`, `ruff format --check src/ tests/`, and `pyright src/` and resolve every issue before considering the task complete. Do not leave behind unused imports, protected-member access warnings, unused variables, formatting violations, or type errors.

### TODO Extractor
- Regex detection runs first (cheap). Only paragraphs not captured by regex go to the LLM.
- The extractor is the **sole writer** to `store/todos.json`. Use file locking (`fcntl.flock`).
- Store `source_file` paths **relative to `notes_dir`**, never absolute.
- On file change: re-parse, diff against stored entries for that file, add/update/mark-done.

### TODO Manager
- Build prompts by combining `skills/gtd.md` (system prompt) + plan-type-specific instructions + open TODOs as JSON (user prompt).
- Plans output to `plans_dir/<YYYY>/<MM>/<filename>.md`. Create directories as needed.
- Plan filenames: `YYYY-MM-DD-morning-plan.md`, `YYYY-MM-DD-afternoon-plan.md`, `YYYY-MM-DD-weekly-review.md`, `YYYY-MM-DD-weekly-plan.md`.

### AI Provider
- Interface: `complete(system_prompt, user_prompt, options) → str` and `classify(text, categories) → str`.
- OpenAI implementation uses `gpt-5-mini` for extraction/classification, `gpt-5.2` for plan generation (configurable).
- Handle API errors with retry + exponential backoff. Degrade gracefully (skip AI classification if unavailable; regex TODOs still work).

### CLI
- Entry points: `md-todos extract [--full]`, `md-todos plan --type <type>`, `md-todos install`, `md-todos uninstall [--all]`, `md-todos status`.
- Use `click` or `argparse` for CLI parsing.

### Install / Deploy
- `scripts/install.sh`: prereq checks, venv creation, data dir setup, config from template, Keychain API key, plist rendering, `launchctl load`, initial scan.
- `scripts/uninstall.sh`: `launchctl unload`, remove plists, optionally remove data dir and Keychain entry.
- Plist templates use placeholder tokens (e.g., `{{PYTHON_PATH}}`, `{{REPO_DIR}}`, `{{CONFIG_PATH}}`) substituted at install time.

### Testing
- Unit tests for regex detection, store operations, config loading.
- Integration tests with mock AI responses for plan generation.
- End-to-end test: install → extract → plan → uninstall.

### Security
- API keys in macOS Keychain only. Never in config files, env vars that could be committed, or source code.
- `.gitignore` must exclude: `config.yaml`, `store/`, `plans/`, `notes/`, `logs/`, rendered `.plist` files, `.env`.
- Never log TODO content at INFO level or above (could contain sensitive user notes). Use DEBUG.

## Documentation Requirements

**Any change of substance to the implementation must be reflected in both `README.md` and `docs/index.html`.** These two documents must stay in sync with each other and with the actual capabilities of the system. This includes:

- New or changed CLI commands
- New or changed configuration options
- Changes to the install/uninstall process
- New agent capabilities or detection methods
- Changes to the directory structure or file naming conventions
- New or removed dependencies
- Changes to security model or API key handling

When updating, edit `README.md` first, then update `docs/index.html` to match.

## Implementation Phases

Phases are optimized for AI-agent construction (Claude Opus 4.6). Each phase fits within a single conversation session, produces testable code, and ends with a commit. See `docs/proposed-solution.md` Section 11 for full details.

1. **Phase 1 — Project Skeleton & Data Models:** Directory tree, `pyproject.toml`, all Pydantic models, config loader, logging, config template.
2. **Phase 2 — AI Provider & Keychain:** `AIProvider` ABC, `OpenAIProvider`, retry logic, Keychain helper, provider factory.
3. **Phase 3 — GTD Skills File:** Write `skills/gtd.md`, add loader utility.
4. **Phase 4 — TODO Store & Regex Detection:** `TodoStore` class with locking, regex detector (checkboxes + keywords), unit tests.
5. **Phase 5 — AI Detection & Extractor Agent:** AI implicit detector, file parser, diff logic, `watchdog` watcher, full scan, agent entry point.
6. **Phase 6 — Manager Agent & Plan Generation:** Prompt builder, plan-type templates, plan file writer, agent entry point.
7. **Phase 7 — CLI:** All `click` commands (`extract`, `plan`, `status`, `install`, `uninstall`).
8. **Phase 8 — Install/Deploy Scripts & launchd:** Plist templates, `install.sh`, `uninstall.sh`, end-to-end testing.

### Session Workflow

**Start of session:** Read Section 11 to find the current phase → read source files from prior phases → set up todo list.

**End of session:** All tests pass → no placeholder bodies → commit as `Phase N — <title>`.

## Reference Documents

- [docs/theory-of-operation.md](../docs/theory-of-operation.md) — Original problem statement and requirements.
- [docs/proposed-solution.md](../docs/proposed-solution.md) — Detailed architecture and development plan.
- [skills/gtd.md](../skills/gtd.md) — GTD methodology knowledge (consumed by the Manager agent at runtime).
