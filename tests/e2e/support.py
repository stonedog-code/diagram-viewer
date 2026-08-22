"""Shared facts about the diagram set, kept out of `conftest.py`.

`conftest.py` is imported by pytest under a name of its own choosing, so a test
module that did `from conftest import ...` could end up with a *second* copy of
this module and a second, empty `EXAMINED` set — the count would then be
reported as zero however many diagrams ran. A plain module has no such
ambiguity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGRAMS_DIR = REPO_ROOT / "diagrams"
README = REPO_ROOT / "README.md"

# Slugs whose page this session actually loaded and asserted on. Printed at the
# end of the run; see `pytest_terminal_summary` in conftest.py.
EXAMINED: set[str] = set()

# `| `slug` | 4 | 2 | 2 |` — the rendered-shape table in README.md.
_ROW_RE = re.compile(
    r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$"
)


def _readme_counts() -> dict[str, dict[str, int]]:
    """The per-diagram shape counts recorded in README.md.

    Deliberately parsed rather than restated: a README that says one thing while
    the suite asserts another is worse than no README, and the counts are the
    only reason this tier can tell "the diagram rendered" from "the diagram
    rendered *whole*".
    """
    text = README.read_text(encoding="utf-8")
    counts: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if match:
            slug, nodes, subgraphs, edges = match.groups()
            counts[slug] = {
                "nodes": int(nodes),
                "subgraphs": int(subgraphs),
                "edges": int(edges),
            }
    return counts


def _diagram_slugs() -> list[str]:
    return sorted(path.stem for path in DIAGRAMS_DIR.glob("*.mer") if path.is_file())


def diagram_params() -> list:
    """Parametrisation over every `.mer` file — never an empty list.

    An empty `parametrize` argument list collects *zero* tests and the run stays
    green, which is precisely the "green over an empty set" failure this repo
    keeps writing down. So an empty diagram directory yields one case that
    fails and says why.
    """
    slugs = _diagram_slugs()
    if not slugs:
        return [pytest.param(None, id="NO-DIAGRAMS-FOUND")]
    return list(slugs)


CDN_HOST = "cdn.jsdelivr.net"

# What the browser reports for a diagram Mermaid could parse. A file it could
# not gets "error" here, 0 nodes, and eight `.error-icon`/`.error-text`
# elements — measured, not assumed (2026-08-22, mermaid@10).
GOOD_ROLE = "flowchart-v2"

_MEASURE_JS = """() => {
  const pane = document.getElementById('zoom-pane');
  const svg = pane && pane.querySelector('svg');
  if (!svg) return {svg: false};
  return {
    svg: true,
    role: svg.getAttribute('aria-roledescription'),
    errorMarks: svg.querySelectorAll('.error-icon, .error-text').length,
    nodes: svg.querySelectorAll('g.node').length,
    subgraphs: svg.querySelectorAll('g.cluster').length,
    edges: svg.querySelectorAll('path.flowchart-link').length,
    width: svg.viewBox.baseVal.width,
    height: svg.viewBox.baseVal.height,
  };
}"""


def render(page: Page, slug: str) -> dict:
    """Load a diagram page and wait until Mermaid has finished with it.

    Waits for the `<svg>` rather than for a *good* `<svg>`, deliberately: the
    error graphic is an svg as well, so waiting on quality would turn a broken
    diagram into a timeout whose message says nothing about the diagram. Wait
    for "Mermaid ran", then assert on what it produced.

    The wait is on `svg[aria-roledescription]`, not on `svg`. Mermaid measures
    text in a throwaway `<svg>` inside the pane before it draws anything, so a
    bare `svg` selector matches ~1s too early and every count reads zero — it
    looks exactly like a broken diagram. `aria-roledescription` is written on
    the finished element only, and it is written for the error graphic too
    (`"error"`), so this waits for "Mermaid is done" without waiting for
    "Mermaid is happy".
    """
    failed: list[str] = []
    page.on("requestfailed", lambda r: failed.append(f"{r.url} ({r.failure})"))
    response = page.goto(f"/diagram/{slug}", wait_until="load")
    # Check the page before waiting on it. A 404 has no `#zoom-pane` at all, so
    # without this a slug that no longer exists costs a 30s timeout per test and
    # then reports "Mermaid never produced an <svg>" — a true sentence about
    # entirely the wrong problem.
    assert response is not None and response.status == 200, (
        f"{slug}: /diagram/{slug} returned "
        f"{response.status if response else 'no response'}, not 200 — there is "
        f"no such diagram to render"
    )
    try:
        page.wait_for_selector(
            "#zoom-pane pre.mermaid[data-processed='true']",
            state="attached",
            timeout=30_000,
        )
        page.wait_for_selector(
            "#zoom-pane svg[aria-roledescription]", state="attached", timeout=30_000
        )
    except PlaywrightTimeoutError:
        cdn = [f for f in failed if CDN_HOST in f]
        raise AssertionError(
            f"{slug}: Mermaid never produced an <svg>. That is a different "
            f"failure from a broken diagram — the module is imported from "
            f"{CDN_HOST} at runtime, so an unreachable CDN looks like this. "
            f"Failed CDN requests: {cdn or 'none recorded'}"
        ) from None
    # The zoom script re-measures on a requestAnimationFrame after Mermaid's
    # mutations settle, so give it one frame before reading geometry.
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => r(null)))")
    return page.evaluate(_MEASURE_JS)
