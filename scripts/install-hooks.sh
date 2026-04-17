#!/bin/bash
# Point git at .githooks/ so pre-commit auto-bumps version.json.
# Idempotent — safe to run on every daily.sh invocation.
set -e
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"
current=$(git config --get core.hooksPath 2>/dev/null || true)
if [ "$current" != ".githooks" ]; then
  git config core.hooksPath .githooks
  echo "[hooks] core.hooksPath -> .githooks"
fi
chmod +x .githooks/pre-commit
