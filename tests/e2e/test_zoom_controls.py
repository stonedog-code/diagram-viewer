"""E2E: the zoom controls, at a real viewport.

This is the only tier that can see them. jsdom reports every element as a
zero-sized box, so a jsdom test will agree that a 3000px diagram fits a 375px
screen and that a sizer which never grew is fine. Everything asserted here is
about measured geometry, which is why it is here and not in `test_routes.py`.

Every test states the viewport it ran at. A percentage is meaningless without
one — "fit" is a ratio between the diagram and the window.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from support import render

# A window narrow enough that the interesting diagrams genuinely overflow it,
# which is the state Fit exists for. Each test asserts that precondition rather
# than assuming it, so a future diagram set that happens to fit fails loudly
# instead of testing nothing.
NARROW = {"width": 700, "height": 800}
WIDE = {"width": 1400, "height": 900}

# The widest diagram in the set at the time of writing; the precondition check
# below is what keeps that from being a silent assumption.
WIDE_DIAGRAM = "test-traditional-rest"
SMALL_DIAGRAM = "spa-vs-htmx"

_GEOMETRY_JS = """() => {
  const vp = document.getElementById('zoom-viewport');
  const sizer = document.getElementById('zoom-sizer');
  return {
    level: parseInt(document.getElementById('zoom-level').textContent, 10),
    viewportWidth: vp.clientWidth,
    scrollWidth: vp.scrollWidth,
    scrollLeft: vp.scrollLeft,
    sizerWidth: sizer.getBoundingClientRect().width,
  };
}"""


def geometry(page: Page) -> dict:
    return page.evaluate(_GEOMETRY_JS)


def open_wide_diagram(page: Page, viewport: dict = NARROW) -> dict:
    """Load the overflowing diagram and confirm it really does overflow."""
    page.set_viewport_size(viewport)
    render(page, WIDE_DIAGRAM)
    page.keyboard.press("0")  # 100%, so the measurement is of the diagram
    geo = geometry(page)
    assert geo["sizerWidth"] > geo["viewportWidth"], (
        f"precondition failed: at 100% {WIDE_DIAGRAM} is "
        f"{geo['sizerWidth']:.0f}px wide inside a {geo['viewportWidth']}px "
        f"viewport, so it does not overflow and these tests would prove "
        f"nothing. Pick a wider diagram or a narrower viewport."
    )
    return geo


def test_a_page_opens_fitted_to_width_rather_than_at_100_percent(page: Page) -> None:
    # ARRANGE — a diagram wider than the window (700x800).
    page.set_viewport_size(NARROW)
    render(page, WIDE_DIAGRAM)

    # ACT — nothing. This is the state the reader is handed.
    opened = geometry(page)

    # ASSERT — shrunk to fit, and the whole width is reachable.
    assert 0 < opened["level"] < 100, (
        f"expected the page to open fitted below 100%, got {opened['level']}% "
        f"at viewport {NARROW['width']}px"
    )
    assert opened["scrollWidth"] <= opened["viewportWidth"] + 2, (
        f"fitted at {opened['level']}% but the content still scrolls: "
        f"{opened['scrollWidth']}px of content in a {opened['viewportWidth']}px "
        f"viewport"
    )


def test_fit_never_enlarges_a_diagram_smaller_than_the_window(page: Page) -> None:
    # ARRANGE — a small diagram in a wide window (1400x900).
    page.set_viewport_size(WIDE)
    render(page, SMALL_DIAGRAM)

    # ACT
    page.click("#zoom-fit")

    # ASSERT — Fit only ever shrinks; blowing a small diagram up to fill the
    # window reads as a rendering fault.
    assert geometry(page)["level"] == 100


def test_reset_returns_to_100_percent_and_the_sizer_grows_with_it(page: Page) -> None:
    # ARRANGE
    fitted = open_wide_diagram(page)
    page.click("#zoom-fit")
    refitted = geometry(page)
    assert refitted["level"] < 100

    # ACT
    page.click("#zoom-reset")

    # ASSERT — the readout says 100%, and the *scrollable* area grew with it.
    # A CSS transform alone would leave the scrollbars at the fitted size and
    # silently clip everything past the right edge.
    full = geometry(page)
    assert full["level"] == 100
    assert full["sizerWidth"] > refitted["sizerWidth"]
    assert full["scrollWidth"] > full["viewportWidth"], (
        "at 100% a diagram wider than the window must be scrollable, not clipped"
    )
    assert full["sizerWidth"] == pytest.approx(fitted["sizerWidth"], abs=2)


@pytest.mark.parametrize(
    "drive",
    [
        pytest.param("buttons", id="buttons"),
        pytest.param("keys", id="keyboard"),
    ],
)
def test_zoom_steps_through_the_fixed_stops(page: Page, drive: str) -> None:
    """Buttons and keys must agree — they are two doors onto one control."""
    # ARRANGE
    open_wide_diagram(page)

    def zoom_in() -> None:
        page.click("#zoom-in") if drive == "buttons" else page.keyboard.press("+")

    def zoom_out() -> None:
        page.click("#zoom-out") if drive == "buttons" else page.keyboard.press("-")

    def reset() -> None:
        page.click("#zoom-reset") if drive == "buttons" else page.keyboard.press("0")

    # ACT / ASSERT — the stops either side of 100% are 80 and 125.
    reset()
    assert geometry(page)["level"] == 100
    zoom_in()
    assert geometry(page)["level"] == 125
    zoom_in()
    assert geometry(page)["level"] == 150
    zoom_out()
    assert geometry(page)["level"] == 125
    zoom_out()
    assert geometry(page)["level"] == 100
    zoom_out()
    assert geometry(page)["level"] == 80
    reset()
    assert geometry(page)["level"] == 100


def test_the_scrollable_area_tracks_the_zoom(page: Page) -> None:
    """The sizer is the whole reason zooming in does not clip the diagram."""
    # ARRANGE
    at_100 = open_wide_diagram(page)

    # ACT — 100% -> 125% -> 150% -> 200%.
    for _ in range(3):
        page.click("#zoom-in")
    at_200 = geometry(page)

    # ASSERT
    assert at_200["level"] == 200
    assert at_200["sizerWidth"] == pytest.approx(2 * at_100["sizerWidth"], rel=0.02), (
        f"sizer is {at_200['sizerWidth']:.0f}px at 200% but "
        f"{at_100['sizerWidth']:.0f}px at 100% — the scrollable area is not "
        f"following the transform, so a zoomed-in diagram is being clipped"
    )


def test_dragging_pans_the_diagram(page: Page) -> None:
    # ARRANGE — 100%, wider than the window, scrolled to the left edge.
    start = open_wide_diagram(page)
    assert start["scrollLeft"] == 0

    # ACT — press inside the viewport and drag left by 200px.
    box = page.locator("#zoom-viewport").bounding_box()
    mid_x = box["x"] + box["width"] / 2
    mid_y = box["y"] + box["height"] / 2
    page.mouse.move(mid_x, mid_y)
    page.mouse.down()
    page.mouse.move(mid_x - 200, mid_y, steps=10)
    page.mouse.up()

    # ASSERT — the content moved with the pointer.
    assert geometry(page)["scrollLeft"] == pytest.approx(200, abs=5)


def test_the_zoom_bar_is_present_with_a_live_readout(page: Page) -> None:
    """The controls PR #7 added, at a real viewport rather than in markup."""
    # ARRANGE
    open_wide_diagram(page)

    # ASSERT — every control is visible, not merely in the DOM.
    for control in ("#zoom-out", "#zoom-in", "#zoom-reset", "#zoom-fit", "#zoom-level"):
        assert page.locator(control).is_visible(), f"{control} is not visible"

    # ACT / ASSERT — the readout is live, not a static "100%" in the template.
    page.click("#zoom-fit")
    assert page.locator("#zoom-level").inner_text().endswith("%")
    assert geometry(page)["level"] < 100
