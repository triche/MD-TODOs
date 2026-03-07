#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# MD-TODOs — Clean Teardown Script
# ─────────────────────────────────────────────────────────────
# Usage:
#   ./scripts/uninstall.sh [--all]
#
# Steps:
#   1. Unload launchd agents
#   2. Remove plist files from ~/Library/LaunchAgents/
#   3. (--all) Optionally remove ~/.md-todos/ data directory
#   4. (--all) Optionally remove Keychain entry
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Constants ────────────────────────────────────────────────
DATA_DIR="${HOME}/.md-todos"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_IDS=("com.md-todos.extractor" "com.md-todos.manager")

# ── Parse arguments ──────────────────────────────────────────
REMOVE_ALL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            REMOVE_ALL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--all]"
            echo ""
            echo "Options:"
            echo "  --all    Also remove data directory and Keychain entry"
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

confirm() {
    local prompt="$1"
    printf "%s [y/N]: " "$prompt"
    read -r answer
    case "$answer" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# ── Main ─────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MD-TODOs — Uninstall"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# ── 1. Unload launchd agents ────────────────────────────────
info "Unloading launchd agents…"

for plist_id in "${PLIST_IDS[@]}"; do
    plist_file="${LAUNCH_AGENTS_DIR}/${plist_id}.plist"

    if [[ -f "$plist_file" ]]; then
        launchctl unload "$plist_file" 2>/dev/null || true
        ok "Unloaded ${plist_id}"
    else
        echo "  — ${plist_id} not installed"
    fi
done
echo

# ── 2. Remove plist files ───────────────────────────────────
info "Removing plist files…"

for plist_id in "${PLIST_IDS[@]}"; do
    plist_file="${LAUNCH_AGENTS_DIR}/${plist_id}.plist"

    if [[ -f "$plist_file" ]]; then
        rm "$plist_file"
        ok "Removed ${plist_file}"
    fi
done
echo

if [[ "$REMOVE_ALL" != true ]]; then
    echo "Done. Data directory and Keychain entry kept."
    echo "Re-run with --all to remove everything."
    exit 0
fi

# ── 3. Remove data directory ────────────────────────────────
if [[ -d "$DATA_DIR" ]]; then
    if confirm "Delete data directory ${DATA_DIR}?"; then
        rm -rf "$DATA_DIR"
        ok "Removed ${DATA_DIR}"
    else
        echo "  — Kept ${DATA_DIR}"
    fi
else
    echo "  — Data directory not found: ${DATA_DIR}"
fi
echo

# ── 4. Remove Keychain entry ────────────────────────────────
if security find-generic-password -s "md-todos" -a "openai-api-key" &>/dev/null; then
    if confirm "Remove OpenAI API key from Keychain?"; then
        security delete-generic-password -s "md-todos" -a "openai-api-key" &>/dev/null || true
        ok "Removed API key from Keychain"
    else
        echo "  — Kept Keychain entry"
    fi
else
    echo "  — No API key found in Keychain"
fi
echo

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  MD-TODOs — Uninstall Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo
