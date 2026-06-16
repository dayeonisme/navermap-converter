#!/usr/bin/env bash
# Install repository-local Git hooks.

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
HOOK_DIR="$ROOT/.git/hooks"

mkdir -p "$HOOK_DIR"
ln -sf ../../scripts/pre-commit "$HOOK_DIR/pre-commit"
chmod +x "$ROOT/scripts/pre-commit"

printf 'Installed pre-commit hook: %s\n' "$HOOK_DIR/pre-commit"
