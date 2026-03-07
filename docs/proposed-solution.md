# Proposed Solution for MD-TODOs Framework

## 1. High-Level Architecture

The system is composed of two independent agents, a shared TODO store, a GTD skills file, and a thin AI-provider abstraction layer. Everything runs locally on macOS.

**The code repository and the user's personal data are kept strictly separate.** The repo is public on GitHub and contains only source code, skills files, configuration templates, and install tooling. All personal data — notes, plans, the TODO store, logs, and runtime configuration — lives in a user-chosen data directory outside the repo (defaulting to `~/.md-todos/`).

### 1.1 Repository Layout (cloned from GitHub)

```
MD-TODOs/                        ← cloned repo root
  src/
    extractor/                   ← TODO Extractor agent
    manager/                     ← TODO Manager agent
    ai/                          ← AI provider abstraction
    common/                      ← shared utilities (file I/O, config, logging)
    cli/                         ← CLI entry points & install/deploy commands
  skills/
    gtd.md                       ← GTD methodology knowledge file
  templates/
    config.example.yaml          ← annotated config template (committed)
    com.md-todos.extractor.plist ← launchd plist template
    com.md-todos.manager.plist   ← launchd plist template
  scripts/
    install.sh                   ← one-command bootstrap script
    uninstall.sh                 ← clean teardown script
  tests/
  docs/
  pyproject.toml
  README.md
```

### 1.2 User Data Directory (outside the repo, never committed)

```
~/.md-todos/                     ← default data root (configurable)
  config.yaml                    ← runtime configuration (from template)
  store/
    todos.json                   ← extracted TODO items (internal state)
  logs/
    md-todos.log                 ← application log

~/notes/                         ← user's Markdown notes (read-only input)
  2024/06/…

~/plans/                         ← generated GTD plans (output)
  2024/06/…
```

The paths to `notes/`, `plans/`, and the data root are all configurable in `config.yaml`. The install process creates the data directory, copies the config template, and prompts for paths — so a user can point `notes_dir` at any existing folder of Markdown files.

---

## 2. TODO Extractor Agent

### 2.1 Responsibility

Continuously watch the `notes/` directory tree, parse every Markdown file, identify TODOs and action items, and persist them to the shared store.

### 2.2 Detection Strategies

The extractor will use a layered approach:

| Layer | What it catches | Method |
|---|---|---|
| **Regex / syntax** | `- [ ] …`, `TODO:`, `FIXME:`, `ACTION:` | Pattern matching |
| **AI classification** | Implicit action items buried in prose | LLM call with a focused prompt |

Regex runs first (cheap, fast). Only paragraphs that are *not* already captured by regex are sent to the LLM for implicit-TODO detection, keeping API costs low.

### 2.3 Extracted TODO Schema

Each TODO item stored in `store/todos.json` will carry:

```jsonc
{
  "id": "uuid-v4",
  "text": "Schedule dentist appointment",
  "source_file": "2024/06/2024-06-10-meeting.md",   // relative to notes_dir
  "source_line": 42,
  "surrounding_context": "…two lines above and below…",
  "detection_method": "checkbox" | "keyword" | "ai_implicit",
  "status": "open" | "done",
  "created_at": "2024-06-10T09:15:00Z",
  "updated_at": "2024-06-10T09:15:00Z",
  "done_at": null,
  "tags": ["personal", "health"],    // AI-assigned
  "raw_checkbox_state": false         // tracks original Markdown checkbox
}
```

### 2.4 File Watching

Use macOS **FSEvents** (via a lightweight wrapper — e.g., Python's `watchdog` library or Node's `chokidar`) to receive near-instant notifications when files under `notes/` are created, modified, or deleted.

On each change:

1. Re-parse the changed file.
2. Diff the new TODO list against the store entries for that file.
3. Add new TODOs, mark removed TODOs as done, update changed TODOs.

### 2.5 Initial Full Scan

On first launch (or when the store is empty), perform a one-time recursive scan of all `notes/**/*.md` files to bootstrap the store.

---

## 3. TODO Manager Agent (GTD)

### 3.1 Responsibility

Read the current set of open TODOs from the store, apply GTD methodology (informed by the skills file), and produce prioritized plan documents in Markdown.

### 3.2 GTD Skills File (`skills/gtd.md`)

A standalone Markdown document that encodes:

- The five GTD phases: **Capture → Clarify → Organize → Reflect → Engage**
- The two-minute rule
- Context tagging (`@work`, `@home`, `@errands`, `@computer`, `@phone`, …)
- The Eisenhower matrix (urgent/important quadrants)
- Weekly review checklist
- Horizons of Focus (runway → 50,000 ft)

This file is injected into the LLM system prompt so the Manager agent "knows" GTD without hard-coding the logic. Updating GTD understanding is as simple as editing this Markdown file — no code changes required.

### 3.3 Plan Types & Schedules

| Plan | Cron Expression (launchd) | Output File Pattern | Purpose |
|---|---|---|---|
| Morning plan | `0 6 * * 1-5` (6 AM, Mon–Fri) | `YYYY-MM-DD-morning-plan.md` | Prioritize the day |
| Afternoon plan | `0 12 * * 1-5` (noon, Mon–Fri) | `YYYY-MM-DD-afternoon-plan.md` | Re-triage; quick wins |
| Weekly review | `0 15 * * 5` (3 PM, Friday) | `YYYY-MM-DD-weekly-review.md` | Reflect on the week |
| Weekly plan | `0 18 * * 0` (6 PM, Sunday) | `YYYY-MM-DD-weekly-plan.md` | Plan the coming week |

All plans are stored under:

```
plans/<YYYY>/<MM>/<filename>.md
```

Example: `plans/2024/06/2024-06-10-morning-plan.md`

### 3.4 Plan Generation Flow

```
1. Load open TODOs from store/todos.json
2. Load skills/gtd.md
3. Build prompt:
     system  = GTD skills + plan-type-specific instructions
     user    = JSON array of open TODOs
4. Call AI provider → receive structured Markdown plan
5. Write plan to plans/<year>/<month>/<plan-name>.md
```

### 3.5 Plan Content Outline

Each generated plan will contain:

- **Summary** — headline view of what's on the plate
- **Top 3 priorities** — the most important items for the time period
- **Categorized action lists** — grouped by GTD context (`@work`, `@home`, etc.)
- **Quick wins** (≤ 2 minutes) — called out separately per GTD's two-minute rule
- **Deferred / Someday-Maybe** — items to acknowledge but not act on today
- **Source links** — for each TODO, a reference back to its source file and line so the user can navigate there directly

---

## 4. AI Provider Abstraction

### 4.1 Interface

Define a simple provider interface:

```
AIProvider
  ├── complete(system_prompt, user_prompt, options) → string
  └── classify(text, categories) → category
```

### 4.2 Implementation

- **Initial provider**: OpenAI (`gpt-5-mini` for TODO extraction/classification, `gpt-5.2` for plan generation).
- Provider selection and model names live in `config.yaml`.
- Swapping providers means adding a new class that implements the interface and updating the config — zero changes to agent code.

### 4.3 API Key Management

- Store the OpenAI API key in macOS **Keychain** (accessed via `security` CLI or a keyring library).
- Never store keys in config files or environment variables that could be committed.

---

## 5. Scheduling & Automation (macOS)

### 5.1 Extractor (Long-Running Daemon)

Register a **launchd** user agent (`~/Library/LaunchAgents/com.md-todos.extractor.plist`) that:

- Starts at login.
- Restarts on failure (`KeepAlive = true`).
- Runs the file-watcher process.

### 5.2 Manager (Scheduled Jobs)

Register a separate **launchd** user agent (`~/Library/LaunchAgents/com.md-todos.manager.plist`) with a calendar-based schedule matching the cron expressions in Section 3.3. The plist will use `StartCalendarInterval` entries for each plan type.

Alternatively, a single plist can launch a dispatcher script that determines which plan type to generate based on the current day and time.

### 5.3 Install & Deploy Tooling

Provide automated scripts and CLI commands to bootstrap, install, and tear down the entire system. The goal is a single-command setup experience after cloning the repo.

#### Bootstrap Script (`scripts/install.sh`)

A shell script that performs first-time setup:

1. **Check prerequisites** — verify Python 3.12+, `uv` (or `pip`), and macOS version.
2. **Create Python virtual environment** — install all dependencies from `pyproject.toml`.
3. **Create data directory** — `~/.md-todos/` with `store/` and `logs/` subdirectories.
4. **Generate `config.yaml`** — copy `templates/config.example.yaml` to `~/.md-todos/config.yaml`; prompt the user for `notes_dir` and `plans_dir` paths (with sensible defaults).
5. **Store API key** — prompt for the OpenAI API key and write it to macOS Keychain via `security add-generic-password`.
6. **Render launchd plists** — substitute the actual Python path, repo path, and config path into the plist templates; copy them to `~/Library/LaunchAgents/`.
7. **Load launchd agents** — `launchctl load` both plist files.
8. **Run initial full scan** — invoke `md-todos extract --full` to bootstrap the TODO store.
9. **Print summary** — confirm what was installed and how to verify.

#### Uninstall Script (`scripts/uninstall.sh`)

1. `launchctl unload` both agents.
2. Remove plist files from `~/Library/LaunchAgents/`.
3. Optionally remove `~/.md-todos/` data directory (prompt for confirmation).
4. Optionally remove the Keychain entry.

#### CLI Install / Uninstall Commands

The same operations are also available through the CLI for users who prefer it:

```bash
md-todos install              # interactive first-time setup
md-todos install --non-interactive --notes-dir ~/notes --plans-dir ~/plans
md-todos uninstall            # guided teardown
md-todos uninstall --all      # remove everything including data
```

### 5.4 Manual Trigger

Provide a CLI entry point so any plan can be generated on demand:

```bash
md-todos plan --type morning    # generate a morning plan right now
md-todos plan --type review     # generate a weekly review right now
md-todos extract --full         # force a full re-scan
md-todos status                 # show agent status, last run times, TODO count
```

---

## 6. Technology Choices

| Component | Recommended Choice | Rationale |
|---|---|---|
| Language | **Python 3.12+** | Rich ecosystem for file watching, AI SDKs, Markdown parsing; lightweight |
| File watcher | `watchdog` | Mature, uses FSEvents on macOS natively |
| Markdown parsing | `markdown-it-py` or regex | Fast, handles checkboxes and frontmatter |
| AI SDK | `openai` Python package | Official, well-maintained |
| Config | `PyYAML` + `pydantic` | Typed config with validation |
| Store | JSON file (initially) | Zero-dependency; upgrade path to SQLite if needed |
| Scheduling | macOS `launchd` | Native, reliable, no extra dependencies |
| Packaging | `uv` or `pip` + `venv` | Isolated environment, reproducible installs |

---

## 7. Configuration

### 7.1 Template (`templates/config.example.yaml` — committed to repo)

An annotated template that ships with the repo. The install process copies this to the data directory and fills in user-specific values.

### 7.2 Runtime Config (`~/.md-todos/config.yaml` — never committed)

```yaml
# Paths — all resolve relative to the user's home directory.
# These are OUTSIDE the repo and contain personal data.
notes_dir: ~/notes
plans_dir: ~/plans

# Internal data — managed by md-todos, also outside the repo.
data_dir: ~/.md-todos              # root for store, logs, and this config
store_path: ~/.md-todos/store/todos.json

# The skills file ships with the repo; reference it by absolute or
# repo-relative path so updates via git pull take effect immediately.
skills_path: /Users/you/git/MD-TODOs/skills/gtd.md   # set by installer

ai:
  provider: openai
  models:
    extraction: gpt-5-mini
    generation: gpt-5.2
  max_tokens: 4096
  temperature: 0.3

extractor:
  watch: true
  scan_glob: "**/*.md"
  implicit_detection: true   # use AI for implicit TODOs

manager:
  schedules:
    morning:   "06:00"
    afternoon: "12:00"
    weekly_review_day: friday
    weekly_review_time: "15:00"
    weekly_plan_day: sunday
    weekly_plan_time: "18:00"

logging:
  level: INFO
  file: ~/.md-todos/logs/md-todos.log
```

### 7.3 Config Resolution Order

1. CLI flags (highest priority)
2. Environment variables (`MD_TODOS_NOTES_DIR`, etc.) — useful for CI/testing
3. `~/.md-todos/config.yaml`
4. Built-in defaults

---

## 8. Directory & File Naming Conventions

All paths below are **outside the repo**, configured via `notes_dir` and `plans_dir` in `config.yaml`.

### Notes (input — user-managed, e.g. `~/notes/`)

```
~/notes/
  2024/
    06/
      2024-06-10-meeting.md
      random-thoughts.md
    07/
      …
```

### Plans (output — system-generated, e.g. `~/plans/`)

```
~/plans/
  2024/
    06/
      2024-06-10-morning-plan.md
      2024-06-10-afternoon-plan.md
      2024-06-14-weekly-review.md
      2024-06-16-weekly-plan.md
```

---

## 9. Security & Privacy

- **The GitHub repo is public** — it contains only code, skills files, templates, and documentation. No personal notes, plans, TODO data, API keys, or runtime config are ever committed.
- `.gitignore` explicitly excludes `config.yaml`, `store/`, `plans/`, `notes/`, `logs/`, and any `*.plist` rendered with user-specific paths.
- All processing happens locally; Markdown content is only sent to the configured AI provider API.
- API keys stored in macOS Keychain, never in plaintext files.
- The `notes/` directory is read-only from the framework's perspective — it never modifies user files.
- `store/` and `plans/` can live under a location excluded from cloud sync if desired.

---

## 10. Future Enhancements (Out of Scope for v1, But Not Blocked)

| Enhancement | How the architecture supports it |
|---|---|
| **Email plans as PDF** | Add a `renderers/` module: Markdown → PDF (via `weasyprint` or `pandoc`), then send via SMTP or macOS Mail.app automation. Plan generation is decoupled from delivery. |
| **Cross-platform support** | Replace `launchd` with `cron` or `systemd` timers; `watchdog` already supports Linux/Windows. |
| **Swap AI provider** | Implement a new class behind the `AIProvider` interface; update `config.yaml`. |
| **Web dashboard** | Serve `store/todos.json` and `plans/` via a lightweight local HTTP server (FastAPI / Flask). |
| **Mobile notifications** | Push plan summaries via Pushover, Ntfy, or Shortcuts automation. |
| **SQLite store** | Drop-in replacement for the JSON store when the TODO count grows large. |

---

## 11. Implementation Phases

> **These phases are optimized for AI-agent construction (Claude Opus 4.6).**
> Each phase is scoped to fit within a single conversation session. Every phase
> produces runnable, testable code and ends with a commit checkpoint. Phases are
> ordered so each session can read finished artifacts from prior phases — no
> large refactors, no forward references. Interfaces and data models are created
> first so implementations can be built additively.

### Phase 1 — Project Skeleton & Data Models (1 session)

Goal: Establish every directory, every `__init__.py`, and every Pydantic model so all later phases just fill in implementations.

- [ ] Create full directory tree: `src/{extractor,manager,ai,common,cli}/`, `skills/`, `templates/`, `scripts/`, `tests/`
- [ ] Create `pyproject.toml` with all dependencies and `[project.scripts]` entry point
- [ ] Define Pydantic models: `AppConfig`, `AIConfig`, `ExtractorConfig`, `ManagerConfig`, `LoggingConfig`
- [ ] Define Pydantic model: `TodoItem` (the schema from Section 2.3)
- [ ] Implement config loader: read `config.yaml`, merge env vars, apply defaults
- [ ] Create `templates/config.example.yaml` with annotated defaults
- [ ] Implement structured logging setup (`src/common/logging.py`)
- [ ] Write unit tests for config loading (valid, missing file, env override)
- [ ] Verify: `uv sync && python -m pytest tests/` passes

### Phase 2 — AI Provider & Keychain (1 session)

Goal: The AI abstraction is complete and callable with real or mock credentials.

- [ ] Define `AIProvider` abstract base class: `complete()`, `classify()`
- [ ] Implement `OpenAIProvider` using the `openai` SDK
- [ ] Add retry logic with exponential backoff
- [ ] Implement Keychain helper: `get_api_key()`, `set_api_key()` via `security` CLI
- [ ] Wire provider instantiation into config (provider factory from `config.ai.provider`)
- [ ] Write unit tests with mocked OpenAI responses
- [ ] Write a thin integration smoke test (skipped without API key)
- [ ] Verify: all tests pass, provider is importable from `src.ai`

### Phase 3 — GTD Skills File (1 short session)

Goal: The skills file is complete, reviewed, and ready for prompt injection.

- [ ] Write `skills/gtd.md` — full GTD methodology reference (five phases, two-minute rule, context tags, Eisenhower matrix, weekly review checklist, Horizons of Focus)
- [ ] Add a utility in `src/common/` to load the skills file and validate it exists
- [ ] Verify: file loads cleanly, content is well-structured Markdown

### Phase 4 — TODO Store & Regex Detection (1 session)

Goal: TODOs can be detected in Markdown text and persisted to the JSON store with proper locking.

- [ ] Implement `TodoStore` class: `load()`, `save()`, `add()`, `update()`, `mark_done()`, `get_by_file()`, `get_open()`
- [ ] Implement file locking with `fcntl.flock`
- [ ] Implement regex detector: checkboxes (`- [ ]`, `- [x]`), keywords (`TODO:`, `FIXME:`, `ACTION:`)
- [ ] Regex detector returns list of `TodoItem` with `detection_method`, `source_line`, `surrounding_context`
- [ ] Store `source_file` as path relative to `notes_dir`
- [ ] Write thorough unit tests: detection edge cases, store CRUD, locking behavior, done-marking
- [ ] Verify: `pytest tests/` — all store and regex tests green

### Phase 5 — AI Detection & Extractor Agent (1 session)

Goal: The extractor agent is fully functional — watches files, detects TODOs (regex + AI), and maintains the store.

- [ ] Implement AI-based implicit TODO detector using `AIProvider.classify()`
- [ ] Implement file parser: reads a Markdown file, runs regex first, sends remaining paragraphs to AI
- [ ] Implement diff logic: compare new parse results against stored entries for a file; add/update/mark-done
- [ ] Implement file watcher using `watchdog` (FSEvents on macOS)
- [ ] Implement full initial scan (`notes/**/*.md`)
- [ ] Wire it all together in `src/extractor/agent.py` with a `run()` entry point
- [ ] Write unit tests for AI detection (mocked provider), diff logic, and file parser
- [ ] Write integration test: create/modify/delete temp Markdown files → verify store state
- [ ] Verify: extractor can be started, watches a test directory, and populates the store

### Phase 6 — Manager Agent & Plan Generation (1 session)

Goal: The manager agent reads open TODOs, builds GTD prompts, calls AI, and writes plan files.

- [ ] Implement prompt builder: load skills file + plan-type instructions + open TODOs as JSON
- [ ] Define plan-type-specific instruction templates (morning, afternoon, review, weekly)
- [ ] Implement plan file writer: resolve `plans_dir/YYYY/MM/filename.md`, create directories
- [ ] Implement plan filename logic: `YYYY-MM-DD-{type}.md`
- [ ] Wire it together in `src/manager/agent.py` with a `generate_plan(plan_type)` entry point
- [ ] Write integration tests with mock AI responses for all four plan types
- [ ] Verify: given a populated store, each plan type produces a correctly named file with expected structure

### Phase 7 — CLI (1 session)

Goal: All user-facing commands work and are wired to agent code.

- [ ] Set up CLI framework (`click`) with `md-todos` as the entry group
- [ ] Implement `md-todos extract [--full]` — runs extractor (full scan or watch mode)
- [ ] Implement `md-todos plan --type <type>` — runs manager for specified plan type
- [ ] Implement `md-todos status` — shows agent status, last run times, open TODO count
- [ ] Implement `md-todos install` — interactive setup (data dir, config, Keychain, launchd)
- [ ] Implement `md-todos uninstall [--all]` — guided teardown
- [ ] Add `--config` global option to override config path
- [ ] Write tests for CLI commands (using `click.testing.CliRunner`)
- [ ] Verify: `uv run md-todos --help` shows all commands; each subcommand executes

### Phase 8 — Install/Deploy Scripts & launchd (1 session)

Goal: One-command install and clean uninstall, with launchd agents running.

- [ ] Create `templates/com.md-todos.extractor.plist` with `{{PYTHON_PATH}}`, `{{REPO_DIR}}`, `{{CONFIG_PATH}}` placeholders
- [ ] Create `templates/com.md-todos.manager.plist` with `StartCalendarInterval` entries
- [ ] Write `scripts/install.sh`: prereq checks, venv, data dir, config from template, Keychain prompt, plist rendering, `launchctl load`, initial scan
- [ ] Write `scripts/uninstall.sh`: `launchctl unload`, remove plists, optional data/Keychain cleanup
- [ ] Test: run install on a clean machine → verify agents loaded → run uninstall → verify clean
- [ ] Final end-to-end test: install → extract → plan → status → uninstall

### Session Workflow Guidance

**At the start of each session:**
1. Read `docs/proposed-solution.md` Section 11 to identify the current phase.
2. Read existing source files that the phase depends on.
3. Use the todo list tool to track tasks within the phase.

**At the end of each session:**
1. All tests pass (`uv run pytest`).
2. All new files are created, no placeholder `pass` bodies remain in the current phase.
3. Commit with a message like `Phase N — <phase title>`.
4. Note which phase is complete so the next session knows where to start.

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinating TODOs that don't exist | Always ground AI output against actual file content; regex layer is source of truth for explicit TODOs |
| Large note corpus → slow AI calls | Batch TODOs; use cheaper model (gpt-5-mini) for extraction; cache unchanged files |
| API rate limits or outages | Retry with exponential backoff; degrade gracefully (skip AI classification, still capture regex TODOs) |
| Store corruption from concurrent access | Use file locking (`fcntl.flock`); extractor is the sole writer |
| launchd jobs not firing (laptop asleep) | launchd handles wake-up scheduling; alternatively, check last-run timestamp on wake and run if overdue |
