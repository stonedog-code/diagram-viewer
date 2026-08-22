"""E2E: every diagram really draws, and draws whole.

The defect this tier exists to catch is a `.mer` file Mermaid cannot parse. That
file still produces a 200 with a well-formed page, so the unit and integration
tiers pass; in the browser it produces Mermaid's *error* graphic, which is an
`<svg>` too. "An svg appeared" is therefore not an assertion — hence the
`aria-roledescription` check and the shape counts from the README table.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from support import (
    EXAMINED,
    GOOD_ROLE,
    _diagram_slugs,
    _readme_counts,
    diagram_params,
    render,
)


def test_readme_table_covers_every_diagram_and_is_not_empty() -> None:
    """The guard on the input set: it must be non-empty and fully documented.

    A zero here fails rather than quietly making every parametrised test below
    disappear.
    """
    slugs = _diagram_slugs()
    counts = _readme_counts()

    assert slugs, (
        "no .mer files in diagrams/ — this tier would otherwise pass over an "
        "empty set"
    )
    assert counts, "no shape-count table found in README.md"
    assert set(counts) == set(slugs), (
        "README's shape-count table and diagrams/ disagree.\n"
        f"  in diagrams/ but not README: {sorted(set(slugs) - set(counts))}\n"
        f"  in README but not diagrams/: {sorted(set(counts) - set(slugs))}\n"
        "Add a row when you add a diagram — the table is what tells the next "
        "run whether it examined the same set."
    )
    print(f"\ne2e input set: {len(slugs)} diagram(s) — {', '.join(slugs)}")


@pytest.mark.parametrize("slug", diagram_params())
def test_diagram_renders_an_svg_that_is_not_the_error_graphic(
    page: Page, slug: str | None
) -> None:
    assert slug is not None, (
        "diagrams/ contains no .mer files, so there is nothing to render"
    )
    measured = render(page, slug)

    assert measured["svg"], f"{slug}: no <svg> inside #zoom-pane"
    assert measured["role"] == GOOD_ROLE, (
        f"{slug}: Mermaid rendered its ERROR graphic "
        f"(aria-roledescription={measured['role']!r}). The page is still a "
        f"valid 200 — this is exactly the failure no other tier can see. "
        f"Check the .mer source for a syntax error or an unbalanced quote."
    )
    assert measured["errorMarks"] == 0, (
        f"{slug}: {measured['errorMarks']} error element(s) in the rendered svg"
    )
    assert measured["width"] > 0 and measured["height"] > 0, (
        f"{slug}: rendered svg has an empty viewBox {measured['width']}x"
        f"{measured['height']}"
    )
    EXAMINED.add(slug)


@pytest.mark.parametrize("slug", diagram_params())
def test_diagram_shape_counts_match_the_readme_table(
    page: Page, slug: str | None
) -> None:
    """Nodes, subgraphs and edges, against the numbers recorded in README.md.

    This is the half that catches a diagram which still renders but has lost
    half of itself — an edge that silently stopped resolving, a subgraph that
    collapsed. "An svg appeared" would pass all of those.
    """
    assert slug is not None, (
        "diagrams/ contains no .mer files, so there is nothing to render"
    )
    expected = _readme_counts().get(slug)
    assert expected is not None, f"{slug}: no row in README's shape-count table"

    measured = render(page, slug)
    assert measured["role"] == GOOD_ROLE, (
        f"{slug}: Mermaid rendered its error graphic; counts are meaningless"
    )
    actual = {k: measured[k] for k in ("nodes", "subgraphs", "edges")}
    assert actual == expected, (
        f"{slug}: rendered shape counts differ from README.md\n"
        f"  README   : {expected}\n"
        f"  rendered : {actual}\n"
        "Either the diagram lost something, or the table needs updating in the "
        "same commit as the diagram."
    )
    EXAMINED.add(slug)
