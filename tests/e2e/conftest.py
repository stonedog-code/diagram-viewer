"""Fixtures for the E2E tier: a really-running server and a real browser.

Why this tier exists at all: rendering is client-side. `TestClient` returns the
HTML and never executes the Mermaid module, so a diagram with a syntax error
sails through every other test in this repo — the page is a valid 200 with a
valid `<pre>` in it, and only a browser can tell you the picture never drew.

Two things here are load-bearing and easy to undo by accident:

* **The server is a real subprocess and is always torn down.** An orphaned
  uvicorn outlives the run that started it and holds a port nobody can name.
* **The input-set size is reported.** "0 failures over 0 diagrams" and "0
  failures over 7" are the same terminal output and different facts, so the
  count of diagrams actually rendered is printed in the terminal summary. The
  guard that makes an empty set *fail* lives in `test_mermaid_render.py`.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from support import EXAMINED, REPO_ROOT, _diagram_slugs


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _serve(env: dict | None = None) -> str:
    """A real uvicorn on a real port, torn down however the session ends.

    `sys.executable -m uvicorn` rather than `uv run`, so the subprocess inherits
    the environment pytest is already running in and does not need `uv` on PATH
    or a second sync.
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--port", str(port),
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        env={**os.environ, **(env or {})},
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"uvicorn exited with {proc.returncode} before serving {base}"
                )
            try:
                with urllib.request.urlopen(base, timeout=1):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            raise RuntimeError(f"uvicorn never answered on {base} within 30s")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


@pytest.fixture(scope="session")
def app_server() -> str:
    """The gallery, serving this repository's own `diagrams/`. Read-only."""
    with _serve() as base:
        yield base


@pytest.fixture(scope="session")
def scratch_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A SECOND server whose diagram directory is a throwaway one.

    The scratchpad writes files, and the only honest way to test that is to let
    it. Pointed at `diagrams/` it would leave a diagram behind that the next run
    reports as undocumented — and a test that pollutes the tree it is testing
    passes the first time and fails for the next person.

    `DIAGRAM_VIEWER_DIAGRAMS_DIR` is the app's own configuration, not a test
    hook: this is the same knob a self-hosted instance uses to keep its diagrams
    outside the checkout.
    """
    directory = tmp_path_factory.mktemp("scratch-diagrams")
    with _serve({"DIAGRAM_VIEWER_DIAGRAMS_DIR": str(directory)}) as base:
        yield base


@pytest.fixture(scope="session")
def base_url(app_server: str) -> str:
    """Override pytest-base-url's fixture so `page.goto('/diagram/x')` works."""
    return app_server


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """A real desktop viewport.

    jsdom reports every box as zero-sized, which is why the zoom controls are
    invisible to the other tiers; a tier that exists to see layout has to name
    the viewport it saw it at.
    """
    return {**browser_context_args, "viewport": {"width": 1280, "height": 900}}


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Report the size of the input set, not just pass/fail."""
    on_disk = len(_diagram_slugs())
    if not EXAMINED and not on_disk:
        terminalreporter.write_line(
            "e2e: examined 0 diagram(s) — diagrams/ is empty", red=True
        )
        return
    if EXAMINED:
        terminalreporter.write_line(
            "e2e: rendered and asserted {n} of {total} diagram(s) in a real "
            "browser: {slugs}".format(
                n=len(EXAMINED), total=on_disk, slugs=", ".join(sorted(EXAMINED))
            )
        )
