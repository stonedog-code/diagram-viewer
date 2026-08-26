"""E2E: the scratchpad really draws, and really saves.

This is the only tier that can answer either question. Rendering happens in the
browser, so `TestClient` sees a textarea and a `<div>` and never learns whether
Mermaid drew anything — the integration tier's job is the POST, not the picture.

The distinction this file keeps making: **an `<svg>` appearing is not a
successful render.** Mermaid draws its own error graphic as an `<svg>` too, so
every positive assertion here goes through `aria-roledescription`, the same
discriminator `test_mermaid_render.py` uses on the gallery.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from support import GOOD_ROLE

GOOD = "graph TD\n    A[Client] --> B(API)\n    B --> C[(Database)]\n"
BROKEN = "graph TD\n    A[Client --> ]]]]] B(\n"

_MEASURE = """() => {
  const svg = document.querySelector('#preview svg');
  if (!svg) return {svg: false};
  return {
    svg: true,
    role: svg.getAttribute('aria-roledescription'),
    nodes: svg.querySelectorAll('g.node').length,
    edges: svg.querySelectorAll('path.flowchart-link').length,
  };
}"""


def _type_and_render(page: Page, source: str) -> None:
    page.fill("#code", source)
    page.click("#render")


def _wait_for_a_drawn_diagram(page: Page) -> dict:
    """Wait for Mermaid to finish, then report what it produced.

    Waits on `aria-roledescription` rather than on `svg`, for the reason
    `support.render` documents: Mermaid measures text in a throwaway `<svg>`
    before it draws, so a bare `svg` selector matches about a second too early
    and every count reads zero — indistinguishable from a broken diagram.
    """
    page.wait_for_selector("#preview svg[aria-roledescription]", state="attached", timeout=30_000)
    return page.evaluate(_MEASURE)


# --- rendering (read-only: the gallery server is fine for this) -------------


def test_the_scratchpad_starts_empty_and_says_so(page: Page) -> None:
    page.goto("/scratchpad")
    expect(page.locator("#preview-placeholder")).to_be_visible()
    expect(page.locator("#render-error")).to_be_hidden()
    assert page.input_value("#code") == ""


def test_render_draws_the_diagram_that_was_typed(page: Page) -> None:
    """The feature, in one test: type Mermaid, press Render, get a picture."""
    page.goto("/scratchpad")
    _type_and_render(page, GOOD)

    measured = _wait_for_a_drawn_diagram(page)

    assert measured["svg"], "Render produced no <svg> at all"
    assert measured["role"] == GOOD_ROLE, (
        f"Mermaid drew its ERROR graphic, not the diagram "
        f"(aria-roledescription={measured['role']!r})"
    )
    # The counts are what separate "an svg appeared" from "the diagram drew
    # whole": three nodes and two edges is what this source says.
    assert measured["nodes"] == 3, measured
    assert measured["edges"] == 2, measured
    expect(page.locator("#render-error")).to_be_hidden()
    expect(page.locator("#preview-placeholder")).to_be_hidden()


def test_a_second_render_replaces_the_first(page: Page) -> None:
    """Press Render twice on different source and get the second diagram.

    Proved non-vacuous by planting an early return when the preview already
    holds an `<svg>`: the first render still passes and this goes red. Note
    what that plant replaced — an earlier one (a reused Mermaid render id) was
    NOT caught, which is how the claim that Mermaid caches by id was found to
    be wrong. A guard is only proved by a failure it actually catches.
    """
    page.goto("/scratchpad")
    _type_and_render(page, GOOD)
    first = _wait_for_a_drawn_diagram(page)
    assert first["nodes"] == 3

    _type_and_render(page, "graph TD\n    X --> Y\n")
    page.wait_for_function(
        "() => { const s = document.querySelector('#preview svg');"
        " return s && s.querySelectorAll('g.node').length === 2; }",
        timeout=30_000,
    )
    second = page.evaluate(_MEASURE)
    assert second["role"] == GOOD_ROLE
    assert second["edges"] == 1, second


def test_a_render_after_a_failed_one_still_draws(page: Page) -> None:
    """Type something wrong, fix it, press Render again — the ordinary flow.

    Worth its own test because a failed `mermaid.render` leaves a temporary
    element behind in the document, so the recovery path is not the same code
    as the first-render path.
    """
    page.goto("/scratchpad")
    _type_and_render(page, BROKEN)
    expect(page.locator("#render-error")).to_be_visible(timeout=30_000)

    _type_and_render(page, GOOD)
    measured = _wait_for_a_drawn_diagram(page)
    assert measured["role"] == GOOD_ROLE, measured
    assert measured["nodes"] == 3, measured
    expect(page.locator("#render-error")).to_be_hidden()


def test_source_that_will_not_parse_says_so_instead_of_going_quiet(page: Page) -> None:
    """The failure that makes a Render button untrustworthy.

    A syntax error must produce a message. Silence is the same thing a working
    render looks like before it finishes, and Mermaid's own error graphic is an
    `<svg>` — so this asserts BOTH that the message appeared and that no
    successful diagram is claimed.
    """
    page.goto("/scratchpad")
    _type_and_render(page, BROKEN)

    error = page.locator("#render-error")
    expect(error).to_be_visible(timeout=30_000)
    assert error.inner_text().strip(), "the error box is visible but empty"

    measured = page.evaluate(_MEASURE)
    assert measured.get("role") != GOOD_ROLE, (
        "a diagram that does not parse was reported as a successful render"
    )


def test_rendering_nothing_is_refused_rather_than_ignored(page: Page) -> None:
    page.goto("/scratchpad")
    page.fill("#code", "   ")
    page.click("#render")
    expect(page.locator("#render-error")).to_be_visible()
    expect(page.locator("#preview-placeholder")).to_be_visible()


# --- saving (needs the writable server) ------------------------------------


def test_saving_creates_a_diagram_that_then_renders_on_its_own_page(
    page: Page, scratch_server: str
) -> None:
    """The whole round trip: type it, draw it, save it, open it.

    Against `scratch_server`, whose diagram directory is a throwaway one — see
    the fixture. Saving into the repository's own `diagrams/` would leave a file
    behind for every future run.
    """
    slug = "e2e-scratchpad-round-trip"

    page.goto(f"{scratch_server}/scratchpad")
    _type_and_render(page, GOOD)
    assert _wait_for_a_drawn_diagram(page)["role"] == GOOD_ROLE

    page.fill("#title", "E2E Scratchpad Round Trip")
    page.fill("#description", "Saved by the E2E tier")
    page.fill("#slug", slug)
    page.click("#save")

    page.wait_for_url(re.compile(rf".*/diagram/{slug}$"), timeout=30_000)
    assert "E2E Scratchpad Round Trip" in page.inner_text("h1")

    # It is a real diagram now: its own page renders it with the zoom pane.
    page.wait_for_selector(
        "#zoom-pane svg[aria-roledescription]", state="attached", timeout=30_000
    )
    role = page.evaluate(
        "() => document.querySelector('#zoom-pane svg').getAttribute('aria-roledescription')"
    )
    assert role == GOOD_ROLE

    # ...and the gallery lists it.
    page.goto(f"{scratch_server}/")
    expect(page.locator(f'a[href="/diagram/{slug}"]')).to_be_visible()


def test_a_refused_save_keeps_the_source_on_screen(
    page: Page, scratch_server: str
) -> None:
    """Measured in the browser, because this is the failure a person actually
    experiences: they press Save, something is wrong, and the diagram they just
    wrote is gone from the box."""
    typed = "graph TD\n    KEEP_ME[Do not lose this] --> B\n"

    page.goto(f"{scratch_server}/scratchpad")
    page.fill("#code", typed)
    page.fill("#slug", "Not A Valid Slug")
    page.click("#save")

    expect(page.locator("#save-error")).to_be_visible(timeout=30_000)
    assert page.input_value("#code") == typed, "the source was lost on a refused save"
    assert page.input_value("#slug") == "Not A Valid Slug"

    # And it is re-drawn, not just retained: coming back to a blank preview is a
    # second thing gone wrong on a page that is already reporting a problem.
    assert _wait_for_a_drawn_diagram(page)["role"] == GOOD_ROLE
