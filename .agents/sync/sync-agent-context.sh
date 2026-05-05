#!/bin/bash
# sync-agent-context.sh
# ─────────────────────────────────────────────────────
# Single source of truth: .agents/sync/AGENT_CONTEXT.md
# Generates: CLAUDE.md, GEMINI.md, AGENTS.md
#
# Each file gets a model-specific header (lines 1-3) + shared body.
# Edit ONLY .agents/sync/AGENT_CONTEXT.md, then run this script.
# The pre-commit hook runs this automatically.
# ─────────────────────────────────────────────────────

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CANONICAL="$REPO_ROOT/.agents/sync/AGENT_CONTEXT.md"

if [ ! -f "$CANONICAL" ]; then
    echo "[sync-agent-context] ERROR: $CANONICAL not found"
    exit 1
fi

generate() {
    local target="$1"
    local header_line="$2"

    cat > "$REPO_ROOT/$target" <<EOF
# Botero Trade — Agent Context

$header_line

$(cat "$CANONICAL")
EOF
    echo "[sync-agent-context] ✅ $target synced"
}

generate "CLAUDE.md"  "This file is auto-loaded by Claude Code at the start of every session. Read it fully before writing any code."
generate "GEMINI.md"  "This file is auto-loaded by Gemini CLI / Gemini Code Assist at the start of every session. Read it fully before writing any code."
generate "AGENTS.md"  "This file is auto-loaded by OpenAI Codex CLI at the start of every session. Read it fully before writing any code."

echo "[sync-agent-context] All 3 files synced from .agents/sync/AGENT_CONTEXT.md"
