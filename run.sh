#!/usr/bin/env bash
# run.sh — start diagram-viewer (or its tests) on Linux or macOS.
#
#     ./run.sh                    # serve on :8000 with --reload
#     ./run.sh serve --port 9000  # extra args go to uvicorn
#     ./run.sh test               # extra args go to pytest
#
# Why this exists rather than a bare `uv run uvicorn app:app`: it picks a
# per-platform uv environment and syncs it first, so one command works on both
# platforms with nothing exported by hand. That matters most when a single
# checkout is shared between two machines over a network mount — see
# scripts/uv-env.sh for the confusing error that prevents.
#
# Written for bash 3.2 — that is what macOS ships as /bin/bash.

set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=scripts/uv-env.sh
. ./scripts/uv-env.sh

cmd="${1:-serve}"
[ $# -gt 0 ] && shift

# Build the environment from uv.lock if it is missing or stale. This is what
# makes the script sufficient on its own on a fresh Mac checkout.
uv sync --quiet

case "$cmd" in
  serve)
    if [ $# -eq 0 ]; then
      set -- --reload --port 8000
      printf 'serving from %s — http://localhost:8000\n' "$UV_PROJECT_ENVIRONMENT"
    else
      # Don't guess a URL from caller-supplied args; uvicorn prints the real
      # one on startup anyway.
      printf 'serving from %s\n' "$UV_PROJECT_ENVIRONMENT"
    fi
    exec uv run uvicorn app:app "$@"
    ;;
  test)
    exec uv run pytest "$@"
    ;;
  *)
    printf 'usage: %s [serve|test] [args...]\n' "$0" >&2
    exit 2
    ;;
esac
