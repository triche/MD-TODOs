#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MD-TODOs — One-Command Bootstrap Script
# ─────────────────────────────────────────────────────────────
# Usage:
#   ./scripts/install.sh [--non-interactive --notes-dir DIR --plans-dir DIR]
#
# Steps:
#   1. Check prerequisites (macOS, Python 3.12+, uv or pip)
#   2. Create Python virtual environment & install dependencies
#   3. Create data directory (~/.md-todos/) with store/ and logs/
#   4. Generate config.yaml from template (prompt for paths)
#   5. Store OpenAI API key in macOS Keychain
#   6. Render launchd plist templates & copy to ~/Library/LaunchAgents/
#   7. Load launchd agents
#   8. Run initial full scan
#   9. Print summary
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Constants ────────────────────────────────────────────────
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${HOME}/.md-todos"
CONFIG_PATH="${DATA_DIR}/config.yaml"
VENV_DIR="${REPO_DIR}/.venv"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_IDS=("com.md-todos.extractor" "com.md-todos.manager")

# Defaults for non-interactive mode
DEFAULT_NOTES_DIR="${HOME}/notes"
DEFAULT_PLANS_DIR="${HOME}/plans"

# ── Parse arguments ──────────────────────────────────────────
NON_INTERACTIVE=false
NOTES_DIR=""
PLANS_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --non-interactive)
            NON_INTERACTIVE=true
            shift
            ;;
        --notes-dir)
            NOTES_DIR="$2"
            shift 2
            ;;
        --plans-dir)
            PLANS_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--non-interactive] [--notes-dir DIR] [--plans-dir DIR]"
            echo ""
            echo "Options:"
            echo "  --non-interactive   Skip all prompts (use defaults or provided values)"
            echo "  --notes-dir DIR     Path to Markdown notes directory"
            echo "  --plans-dir DIR     Path for generated plans"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ── Helper functions ─────────────────────────────────────────

info()  { echo "→ $*"; }
ok()    { echo "✓ $*"; }
warn()  { echo "⚠ $*"; }
fail()  { echo "✗ $*" >&2; exit 1; }

prompt_value() {
    local prompt="$1"
    local default="$2"
    local varname="$3"
    if [[ "$NON_INTERACTIVE" == true ]]; then
        eval "$varname=\"$default\""
    else
        printf "%s [%s]: " "$prompt" "$default"
        read -r input
        eval "$varname=\"${input:-$default}\""
    fi
}

prompt_secret() {
    local prompt="$1"
    local varname="$2"
    if [[ "$NON_INTERACTIVE" == true ]]; then
        eval "$varname=\"\""
    else
        printf "%s: " "$prompt"
        read -rs input
        echo
        eval "$varname=\"$input\""
    fi
}

# ── 1. Check prerequisites ──────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MD-TODOs — Install"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

info "Checking prerequisites…"

# macOS check
if [[ "$(uname -s)" != "Darwin" ]]; then
    fail "MD-TODOs requires macOS. Detected: $(uname -s)"
fi
ok "macOS detected"

# Python 3.12+ check
PYTHON_CMD=""
for cmd in python3.12 python3.13 python3.14 python3; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 12 ]]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    fail "Python 3.12+ is required. Install it from https://www.python.org or via Homebrew."
fi
ok "Python $($PYTHON_CMD --version | cut -d' ' -f2) found at $(command -v "$PYTHON_CMD")"

# Package manager check
PKG_MANAGER=""
if command -v uv &>/dev/null; then
    PKG_MANAGER="uv"
    ok "uv found"
elif command -v pip &>/dev/null; then
    PKG_MANAGER="pip"
    ok "pip found"
else
    fail "Either uv or pip is required. Install uv: https://docs.astral.sh/uv/"
fi

echo

# ── 2. Create virtual environment & install dependencies ─────
info "Setting up Python virtual environment…"

if [[ -d "$VENV_DIR" ]]; then
    ok "Virtual environment already exists: ${VENV_DIR}"
else
    "$PYTHON_CMD" -m venv "$VENV_DIR"
    ok "Created virtual environment: ${VENV_DIR}"
fi

# Determine venv Python path
PYTHON_PATH="${VENV_DIR}/bin/python"

info "Installing dependencies…"
if [[ "$PKG_MANAGER" == "uv" ]]; then
    (cd "$REPO_DIR" && uv pip install --python "$PYTHON_PATH" -e ".[dev]")
else
    "$PYTHON_PATH" -m pip install --quiet -e ".[dev]"
fi
ok "Dependencies installed"
echo

# ── 3. Create data directory ────────────────────────────────
info "Setting up data directory…"

if [[ -d "$DATA_DIR" ]]; then
    ok "Data directory already exists: ${DATA_DIR}"
else
    mkdir -p "${DATA_DIR}/store" "${DATA_DIR}/logs"
    ok "Created data directory: ${DATA_DIR}"
fi
# Ensure subdirectories exist even if data dir already existed
mkdir -p "${DATA_DIR}/store" "${DATA_DIR}/logs"
echo

# ── 4. Generate config.yaml ─────────────────────────────────
info "Configuring…"

if [[ -f "$CONFIG_PATH" ]]; then
    ok "Config file already exists: ${CONFIG_PATH}"
else
    # Prompt for paths
    if [[ -z "$NOTES_DIR" ]]; then
        prompt_value "Markdown notes directory" "$DEFAULT_NOTES_DIR" NOTES_DIR
    fi
    if [[ -z "$PLANS_DIR" ]]; then
        prompt_value "Plans output directory" "$DEFAULT_PLANS_DIR" PLANS_DIR
    fi

    # Expand ~ in user-provided paths
    NOTES_DIR="${NOTES_DIR/#\~/$HOME}"
    PLANS_DIR="${PLANS_DIR/#\~/$HOME}"

    # Create notes and plans directories if they don't exist
    mkdir -p "$NOTES_DIR" "$PLANS_DIR"

    # Copy template and substitute user values
    TEMPLATE="${REPO_DIR}/templates/config.example.yaml"
    if [[ ! -f "$TEMPLATE" ]]; then
        fail "Config template not found: ${TEMPLATE}"
    fi

    cp "$TEMPLATE" "$CONFIG_PATH"

    # Patch the config with user-specific values
    SKILLS_PATH="${REPO_DIR}/skills/gtd.md"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        # macOS sed requires '' after -i
        sed -i '' "s|^notes_dir:.*|notes_dir: ${NOTES_DIR}|" "$CONFIG_PATH"
        sed -i '' "s|^plans_dir:.*|plans_dir: ${PLANS_DIR}|" "$CONFIG_PATH"
        sed -i '' "s|^skills_path:.*|skills_path: ${SKILLS_PATH}|" "$CONFIG_PATH"
    else
        sed -i "s|^notes_dir:.*|notes_dir: ${NOTES_DIR}|" "$CONFIG_PATH"
        sed -i "s|^plans_dir:.*|plans_dir: ${PLANS_DIR}|" "$CONFIG_PATH"
        sed -i "s|^skills_path:.*|skills_path: ${SKILLS_PATH}|" "$CONFIG_PATH"
    fi

    ok "Config written to ${CONFIG_PATH}"
fi
echo

# ── 5. Store API key in Keychain ────────────────────────────
info "API key setup…"

# Check if key already exists
if security find-generic-password -s "md-todos" -a "openai-api-key" -w &>/dev/null; then
    ok "OpenAI API key already in Keychain"
else
    API_KEY=""
    prompt_secret "Enter your OpenAI API key (or press Enter to skip)" API_KEY

    if [[ -n "$API_KEY" ]]; then
        security add-generic-password \
            -s "md-todos" \
            -a "openai-api-key" \
            -w "$API_KEY" \
            -U
        ok "API key stored in macOS Keychain"
    else
        warn "Skipped API key — AI features will be unavailable until you add one."
        warn "Run: md-todos install  (or use macOS Keychain Access to add manually)"
    fi
fi
echo

# ── 6. Render launchd plists ────────────────────────────────
info "Installing launchd agents…"

mkdir -p "$LAUNCH_AGENTS_DIR"

LOG_DIR="${DATA_DIR}/logs"

render_plist() {
    local template="$1"
    local output="$2"

    sed \
        -e "s|{{PYTHON_PATH}}|${PYTHON_PATH}|g" \
        -e "s|{{REPO_DIR}}|${REPO_DIR}|g" \
        -e "s|{{CONFIG_PATH}}|${CONFIG_PATH}|g" \
        -e "s|{{LOG_DIR}}|${LOG_DIR}|g" \
        "$template" > "$output"
}

for plist_id in "${PLIST_IDS[@]}"; do
    template="${REPO_DIR}/templates/${plist_id}.plist"
    output="${LAUNCH_AGENTS_DIR}/${plist_id}.plist"

    if [[ ! -f "$template" ]]; then
        warn "Template not found: ${template} — skipping"
        continue
    fi

    render_plist "$template" "$output"
    ok "Rendered ${output}"
done
echo

# ── 7. Load launchd agents ──────────────────────────────────
info "Loading launchd agents…"

for plist_id in "${PLIST_IDS[@]}"; do
    plist_file="${LAUNCH_AGENTS_DIR}/${plist_id}.plist"

    if [[ ! -f "$plist_file" ]]; then
        warn "Plist not found: ${plist_file} — skipping"
        continue
    fi

    # Unload first if already loaded (idempotent)
    launchctl unload "$plist_file" 2>/dev/null || true
    launchctl load "$plist_file"
    ok "Loaded ${plist_id}"
done
echo

# ── 8. Run initial full scan ────────────────────────────────
info "Running initial full scan…"

"$PYTHON_PATH" -m src.cli.main --config "$CONFIG_PATH" extract --full || {
    warn "Initial scan encountered an error (this is OK if notes_dir is empty)"
}
echo

# ── 9. Summary ──────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MD-TODOs — Installation Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
echo "  Data directory: ${DATA_DIR}"
echo "  Config file:    ${CONFIG_PATH}"
echo "  Virtual env:    ${VENV_DIR}"
echo "  Notes dir:      ${NOTES_DIR:-$(grep '^notes_dir:' "$CONFIG_PATH" 2>/dev/null | awk '{print $2}' || echo '~/notes')}"
echo "  Plans dir:      ${PLANS_DIR:-$(grep '^plans_dir:' "$CONFIG_PATH" 2>/dev/null | awk '{print $2}' || echo '~/plans')}"
echo
echo "  Agents:"
for plist_id in "${PLIST_IDS[@]}"; do
    if launchctl list "$plist_id" &>/dev/null; then
        echo "    ${plist_id}: loaded"
    else
        echo "    ${plist_id}: not loaded"
    fi
done
echo
echo "  Verify with:  md-todos status"
echo "  View logs:    tail -f ${LOG_DIR}/md-todos.log"
echo
