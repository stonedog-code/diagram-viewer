"""Integration tier — the real routes, real templates, real files on disk."""

import pytest
from fastapi.testclient import TestClient

import loader
from app import app

client = TestClient(app)


def test_index_returns_200_and_lists_every_diagram():
    response = client.get("/")
    assert response.status_code == 200

    diagrams = loader.load_diagrams()
    assert diagrams, "fixture check: no diagrams on disk to list"
    assert response.text.count('class="card"') == len(diagrams)
    for d in diagrams:
        assert f'href="/diagram/{d.slug}"' in response.text
        assert d.title in response.text


def test_each_diagram_has_its_own_page():
    diagrams = loader.load_diagrams()
    assert diagrams, "fixture check: no diagrams on disk to visit"
    for d in diagrams:
        response = client.get(f"/diagram/{d.slug}")
        assert response.status_code == 200, d.slug
        assert d.title in response.text
        assert 'class="mermaid"' in response.text
        # The Mermaid body is present, whitespace and all, once entities are
        # decoded — this is what the browser hands Mermaid as textContent.
        first_line = d.code.splitlines()[0]
        assert first_line in response.text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")


def test_index_links_resolve():
    # Every href on the index must be a page that exists — a listing that
    # links to 404s is the failure this catches.
    response = client.get("/")
    for d in loader.load_diagrams():
        assert client.get(f"/diagram/{d.slug}").status_code == 200
    assert response.status_code == 200


def test_unknown_diagram_is_404():
    assert client.get("/diagram/no-such-diagram").status_code == 404


@pytest.mark.parametrize("slug", ["..%2F..%2Fetc%2Fpasswd", "..%2Floader", "%2Fetc%2Fpasswd"])
def test_traversal_attempts_do_not_serve_files(slug):
    response = client.get(f"/diagram/{slug}")
    assert response.status_code == 404
    assert "root:" not in response.text


def test_mermaid_cdn_is_loaded():
    assert "mermaid.esm.min.mjs" in client.get("/").text


def test_titles_and_descriptions_are_escaped(tmp_path, monkeypatch):
    # Values come from files now, so an unescaped `<` would break the page.
    (tmp_path / "xss.mer").write_text(
        "%% title: <script>alert(1)</script>\n%% description: 5 < 6\ngraph TD\n    A --> B\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", tmp_path)

    body = client.get("/diagram/xss").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    assert "5 &lt; 6" in body


def test_empty_diagrams_directory_renders_an_empty_gallery(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="card"' not in response.text


def test_every_diagram_page_ships_the_zoom_controls():
    # The zoom UI is three cooperating pieces — a scrolling viewport, a sizer
    # that carries the scrollable area, and the pane that is actually scaled.
    # Losing any one of them leaves a page that still renders and still passes
    # every other test here, so each id is asserted by name.
    required = [
        'id="zoom-viewport"',
        'id="zoom-sizer"',
        'id="zoom-pane"',
        'id="zoom-in"',
        'id="zoom-out"',
        'id="zoom-reset"',
        'id="zoom-fit"',
        'id="zoom-level"',
    ]
    diagrams = loader.load_diagrams()
    assert diagrams, "fixture check: no diagrams on disk to visit"
    for d in diagrams:
        body = client.get(f"/diagram/{d.slug}").text
        for marker in required:
            assert marker in body, f"{d.slug} is missing {marker}"


def test_zoom_pane_wraps_the_mermaid_block():
    # Order matters: the pane must ENCLOSE the diagram, not sit beside it.
    # A pane that does not contain the <pre> scales an empty box.
    body = client.get(f"/diagram/{loader.load_diagrams()[0].slug}").text
    pane = body.index('id="zoom-pane"')
    mermaid = body.index('class="mermaid"', pane)
    closing = body.index("</pre>", mermaid)
    assert pane < mermaid < closing


def test_diagram_source_is_not_double_quoted_inside_mermaid_labels():
    # A literal `"` inside a label terminates it and Mermaid renders a syntax
    # error instead of the diagram — invisible to every other test here,
    # because the route still returns 200 with the text intact.
    #
    # Quote COUNTING does not catch it: the real defect that prompted this test
    # (`<i>"no inbound"</i>` inside a label) left an even number of quotes on
    # the line. What actually distinguishes a label from a stray quote is what
    # sits either side of it, so pair the quotes up and check the neighbours.
    # Mermaid has many shape delimiters — `["…"]`, `[("…")]`, `{"…"}`, `|"…"|`,
    # and the bare `-- "…" -->` edge form — so the test is written against the
    # characters that may abut a quote rather than against a list of shapes.
    OPENERS = set('[({|>')
    CLOSERS = set('])}|>')

    for d in loader.load_diagrams():
        for lineno, line in enumerate(d.code.splitlines(), 1):
            if line.lstrip().startswith("%%"):
                continue  # a comment may say anything
            quotes = [i for i, ch in enumerate(line) if ch == '"']
            assert len(quotes) % 2 == 0, f"{d.slug}:{lineno} has an odd number of quotes"
            for opening, closing in zip(quotes[::2], quotes[1::2]):
                before = line[opening - 1] if opening else ""
                after = line[closing + 1] if closing + 1 < len(line) else ""
                assert before in OPENERS or before.isspace() or before == "-", (
                    f"{d.slug}:{lineno} opens a label after {before!r} — "
                    f"a stray quote inside another label"
                )
                assert after in CLOSERS or after.isspace() or after == "-", (
                    f"{d.slug}:{lineno} closes a label before {after!r} — "
                    f"a stray quote inside another label"
                )
