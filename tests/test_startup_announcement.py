"""The one thing this app's silence used to hide.

`DIAGRAMS_DIR` is relative to `loader.py` and the diagrams are read per request,
so a wrong working directory, a container missing a mount, or a file saved as
`.mmd` instead of `.mer` all produce the SAME thing: a server that starts
cleanly, answers 200, and shows an empty gallery — indistinguishable from a
server whose diagrams have simply not been added yet.

The count is the only thing that separates those two, so these assert the count
is printed, and printed correctly, in both directions.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
import loader

pytestmark = pytest.mark.unit


def _ours(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Only THIS app's log records.

    Scoped by logger name because `TestClient` is httpx, and httpx logs a line
    per request. An assertion that the app logged nothing would otherwise be
    asserting something about httpx — and would have been "fixed" by loosening
    it, which is how a test stops testing anything.
    """
    return [
        r.getMessage() for r in caplog.records
        if r.name.startswith(app_module.__name__)
    ]


def _start(caplog: pytest.LogCaptureFixture) -> str:
    """Run the app's lifespan and return everything IT logged."""
    with caplog.at_level(logging.INFO):
        with TestClient(app_module.app):
            pass
    return "\n".join(_ours(caplog))


def test_startup_names_the_directory_and_the_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The positive control, and it must report the REAL number.

    A line that always said "0 diagrams" would satisfy the empty-directory test
    below perfectly.
    """
    expected = loader.load_diagrams()
    assert expected, "fixture check: no diagrams on disk to count"

    logged = _start(caplog)

    assert str(loader.DIAGRAMS_DIR) in logged
    assert f"{len(expected)} diagram(s)" in logged
    assert expected[0].slug in logged


def test_an_empty_directory_says_so_rather_than_starting_silently(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failure this file exists for.

    Without this line the server starts, answers 200, and shows nothing — with
    no way to tell a misconfiguration from an empty project.
    """
    empty = tmp_path / "no-diagrams-here"
    empty.mkdir()
    # One patch, not two: `app` reads `loader.DIAGRAMS_DIR` through the module
    # now, so there is only one binding of this fact to move.
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", empty)

    logged = _start(caplog)

    assert "0 diagram(s)" in logged
    assert str(empty) in logged, "it must say WHERE it looked"
    assert "will render empty" in logged


def test_a_missing_directory_is_reported_rather_than_crashing(
    caplog: pytest.LogCaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container missing its mount should say so, not fail to start —
    the app is still useful for whatever is there, which is nothing."""
    missing = tmp_path / "never-created"
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", missing)

    logged = _start(caplog)

    assert "0 diagram(s)" in logged
    assert str(missing) in logged


def test_a_request_for_an_unknown_diagram_says_what_was_asked_for(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bare 404 tells an operator nothing they can act on."""
    with caplog.at_level(logging.INFO):
        with TestClient(app_module.app) as client:
            caplog.clear()
            response = client.get("/diagram/no-such-diagram")

    assert response.status_code == 404
    logged = "\n".join(_ours(caplog))
    assert "no-such-diagram" in logged
    assert str(loader.DIAGRAMS_DIR) in logged


def test_a_request_for_a_real_diagram_logs_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The other direction. uvicorn already has an access log; duplicating it
    per request would be noise, and noise is what makes the lines above
    unreadable."""
    real = loader.load_diagrams()[0]

    with caplog.at_level(logging.INFO):
        with TestClient(app_module.app) as client:
            caplog.clear()
            assert client.get(f"/diagram/{real.slug}").status_code == 200

    assert _ours(caplog) == []
