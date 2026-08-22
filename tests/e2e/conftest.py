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

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from support import EXAMINED, REPO_ROOT, _diagram_slugs


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def app_server() -> str:
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
