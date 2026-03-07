# MD-TODOs

**AI-powered TODO extraction and GTD planning from your Markdown notes.**

MD-TODOs is a local macOS framework that watches your Markdown notes, automatically extracts TODOs and action items, and generates prioritized daily and weekly plans using the Getting Things Done (GTD) methodology — all powered by AI.

## Features

- **Automatic TODO Detection** — Finds explicit TODOs (`- [ ]`, `TODO:`, `FIXME:`, `ACTION:`) via regex and discovers implicit action items in prose via AI classification.
- **Live File Watching** — Monitors your notes directory in real time using macOS FSEvents. New, changed, and deleted files are processed instantly.
- **GTD-Based Planning** — Generates structured Markdown plans: morning priorities, afternoon quick-wins, Friday weekly reviews, and Sunday weekly plans.
- **Fully Local** — Runs entirely on your Mac. Your notes never leave your machine except for AI API calls to your configured provider.
- **Secure** — API keys stored in macOS Keychain. The repo is public; all personal data lives outside it.
- **Swappable AI** — Built on an AI provider abstraction. Ships with OpenAI support; swap providers by adding an implementation and updating config.
- **One-Command Install** — Bootstrap script handles venv, config, Keychain, launchd agents, and initial scan.

## How It Works

MD-TODOs runs two independent agents:

| Agent | Role | Runs As |
|---|---|---|
| **TODO Extractor** | Watches `notes/` for changes, extracts TODOs (regex + AI), persists to a JSON store | Long-running `launchd` daemon |
| **TODO Manager** | Reads open TODOs, applies GTD methodology via AI, writes prioritized Markdown plans | Scheduled `launchd` jobs |

```
Your Markdown Notes ──→ TODO Extractor ──→ TODO Store (JSON)
                                                │
                         GTD Skills File ──→ TODO Manager ──→ Markdown Plans
```

## Requirements

- macOS 13+ (Ventura or later)
- Python 3.12+
- An OpenAI API key (or compatible provider)
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/triche/MD-TODOs.git
cd MD-TODOs
```

### 2. Run the install script

```bash
./scripts/install.sh
```

This will:
- Check prerequisites (Python 3.12+, macOS)
- Create a Python virtual environment and install dependencies
- Set up the data directory (`~/.md-todos/`)
- Generate your `config.yaml` from the template
- Store your OpenAI API key in macOS Keychain
- Install and load `launchd` agents for both the extractor and manager
- Run an initial full scan of your notes

### 3. Verify

```bash
md-todos status
```

That's it. The extractor daemon is now watching your notes, and the manager will generate plans on schedule.

## CLI Commands

| Command | Description |
|---|---|
| `md-todos extract --full` | Force a full re-scan of all notes |
| `md-todos plan --type morning` | Generate a morning plan now |
| `md-todos plan --type afternoon` | Generate an afternoon plan now |
| `md-todos plan --type review` | Generate a weekly review now |
| `md-todos plan --type weekly` | Generate a weekly plan now |
| `md-todos install` | Interactive first-time setup |
| `md-todos uninstall` | Guided teardown of agents |
| `md-todos uninstall --all` | Full teardown including data directory |
| `md-todos status` | Show agent status, last run times, TODO count |

## Plan Schedule

| Plan | When | Purpose |
|---|---|---|
| Morning plan | 6:00 AM, Mon–Fri | Prioritize the day ahead |
| Afternoon plan | 12:00 PM, Mon–Fri | Re-triage; surface quick wins |
| Weekly review | 3:00 PM, Friday | Reflect on the week |
| Weekly plan | 6:00 PM, Sunday | Plan the coming week |

Plans are written to your configured `plans_dir` in `YYYY/MM/` subdirectories:

```
~/plans/
  2024/
    06/
      2024-06-10-morning-plan.md
      2024-06-10-afternoon-plan.md
      2024-06-14-weekly-review.md
      2024-06-16-weekly-plan.md
```

## Configuration

Runtime configuration lives at `~/.md-todos/config.yaml` (created during install from `templates/config.example.yaml`). Key settings:

```yaml
notes_dir: ~/notes                          # Your Markdown notes (read-only)
plans_dir: ~/plans                          # Where plans are written
data_dir: ~/.md-todos                       # Store, logs, config
store_path: ~/.md-todos/store/todos.json    # TODO store

ai:
  provider: openai
  models:
    extraction: gpt-5-mini       # Fast/cheap for TODO detection
    generation: gpt-5.2          # Capable for plan generation
  max_tokens: 4096
  temperature: 0.3

extractor:
  watch: true
  scan_glob: "**/*.md"
  implicit_detection: true       # AI-based implicit TODO detection

manager:
  schedules:
    morning: "06:00"
    afternoon: "12:00"
    weekly_review_day: friday
    weekly_review_time: "15:00"
    weekly_plan_day: sunday
    weekly_plan_time: "18:00"

logging:
  level: INFO
  file: ~/.md-todos/logs/md-todos.log
```

**Config resolution order:** CLI flags → environment variables → `config.yaml` → built-in defaults.

## Architecture

### Directory Separation

The repo contains only source code and templates. All personal data lives outside the repo:

```
MD-TODOs/                        ← repo (public on GitHub)
  src/                           ← agent code, AI provider, CLI
  skills/gtd.md                  ← GTD knowledge file
  templates/                     ← config + launchd plist templates
  scripts/                       ← install/uninstall scripts
  tests/
  docs/

~/.md-todos/                     ← user data (never committed)
  config.yaml
  store/todos.json
  logs/md-todos.log

~/notes/                         ← your Markdown notes (read-only)
~/plans/                         ← generated GTD plans
```

### TODO Detection

The extractor uses a layered approach:

1. **Regex** (fast, free) — catches `- [ ] …`, `TODO:`, `FIXME:`, `ACTION:` patterns.
2. **AI classification** (targeted) — only paragraphs not captured by regex are sent to the LLM for implicit action item detection.

This keeps API costs low while still catching buried action items in prose.

### AI Provider Abstraction

All AI calls go through a provider interface:

```
AIProvider
  ├── complete(system_prompt, user_prompt, options) → str
  └── classify(text, categories) → str
```

Ships with an OpenAI implementation. Swap providers by implementing the interface and updating `config.yaml`.

### GTD Skills File

GTD methodology is encoded in `skills/gtd.md`, not in code. This file is injected into the Manager agent's LLM system prompt. To refine GTD behavior, edit the skills file — no code changes required.

## Security

- **API keys** are stored in macOS Keychain only — never in config files, env vars, or source code.
- **The repo is public.** `.gitignore` excludes `config.yaml`, `store/`, `plans/`, `notes/`, `logs/`, rendered `.plist` files, and `.env`.
- **Notes are read-only.** The framework never modifies files in your notes directory.
- **Local processing.** Note content is only sent to the configured AI provider API; no other third-party services are involved.

## Uninstalling

Guided teardown:

```bash
md-todos uninstall
```

Or use the shell script:

```bash
./scripts/uninstall.sh
```

This will unload `launchd` agents, remove plist files, and optionally remove the `~/.md-todos/` data directory and Keychain entry.

## Project Documentation

- [Theory of Operation](docs/theory-of-operation.md) — Problem statement and requirements
- [Proposed Solution](docs/proposed-solution.md) — Detailed architecture and development plan
- [Project Page](docs/index.html) — HTML documentation

## Technology Stack

| Component | Choice |
|---|---|
| Language | Python 3.12+ |
| File watcher | `watchdog` (FSEvents on macOS) |
| Markdown parsing | `markdown-it-py` / regex |
| AI SDK | `openai` Python package |
| Config | `PyYAML` + `pydantic` |
| Store | JSON file (`todos.json`) |
| Scheduling | macOS `launchd` |
| Packaging | `uv` or `pip` + `venv` |
| Secrets | macOS Keychain |

## License

[MIT](LICENSE) © 2026 Taylor L. Riché
