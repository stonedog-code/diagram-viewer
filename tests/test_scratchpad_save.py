"""Unit tier — turning a form field into a file, and refusing to.

`save_diagram` is the only code in this app that builds a path from something a
person typed. Everything else reads the directory and matches by slug, which is
why `find_diagram` needs no validation at all. So the assertions here are mostly
about what is REFUSED, and each refusal is checked in both directions: the bad
input fails, and an ordinary one still succeeds. A guard observed only rejecting
is indistinguishable from a guard that rejects everything.

No HTTP and no app import — `tmp_path` is the whole environment.
"""

from __future__ import annotations

import pytest

import loader
from loader import (
    DiagramExists,
    EmptyDiagram,
    InvalidSlug,
    load_diagrams,
    parse_diagram,
    render_source,
    save_diagram,
    slugify,
)

pytestmark = pytest.mark.unit

GRAPH = "graph TD\n    A[Client] --> B(API)\n"


# --- slugify ---------------------------------------------------------------


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Architecture Flowchart", "architecture-flowchart"),
        ("  Spaced  Out  ", "spaced-out"),
        ("Test vs. Traditional REST", "test-vs-traditional-rest"),
        ("SPA_vs_HTMX", "spa-vs-htmx"),
        ("C4 — Context (Level 1)", "c4-context-level-1"),
        ("100% coverage!", "100-coverage"),
    ],
)
def test_slugify_produces_a_valid_slug(title, expected):
    assert slugify(title) == expected
    assert loader.SLUG_RE.match(slugify(title)), "slugify produced a slug save_diagram would refuse"


@pytest.mark.parametrize("title", ["", "   ", "!!!", "---", "…"])
def test_slugify_returns_empty_rather_than_inventing_a_name(title):
    """A title with nothing usable in it has no slug.

    Falling back to something like `diagram` would save the file under a name
    the author never chose and never saw — and the next save would then collide
    with it for a reason nobody could read off the page.
    """
    assert slugify(title) == ""


# --- render_source, and the round trip -------------------------------------


def test_render_source_round_trips_through_parse_diagram():
    """The invariant that keeps a saved title from silently reverting.

    `render_source` writes the header `parse_diagram` reads. If they disagree,
    the save appears to work and the diagram comes back titled after its slug.
    """
    text = render_source("My Chart", "What it shows", GRAPH)
    back = parse_diagram("my-chart", text)
    assert back.title == "My Chart"
    assert back.description == "What it shows"
    assert back.code == GRAPH.strip()


def test_a_newline_in_a_title_cannot_break_out_of_the_header():
    """A raw newline would end the header block and push the rest into the
    diagram body — a title that silently becomes Mermaid source."""
    text = render_source("Line one\nline two", "a\n\nb", GRAPH)
    back = parse_diagram("x", text)
    assert back.title == "Line one line two"
    assert back.description == "a b"
    assert back.code == GRAPH.strip()


def test_no_header_lines_are_written_when_there_is_nothing_to_write():
    assert render_source("", "", GRAPH) == GRAPH.strip() + "\n"


# --- saving ----------------------------------------------------------------


def test_saves_a_file_that_the_gallery_then_finds(tmp_path):
    saved = save_diagram("my-chart", "My Chart", "What it shows", GRAPH, tmp_path)

    written = tmp_path / "my-chart.mer"
    assert written.is_file()
    assert saved.slug == "my-chart"

    found = load_diagrams(tmp_path)
    assert [d.slug for d in found] == ["my-chart"]
    assert found[0].title == "My Chart"
    assert found[0].code == GRAPH.strip()


def test_the_directory_is_created_if_it_does_not_exist(tmp_path):
    target = tmp_path / "not-yet"
    save_diagram("a", "A", "", GRAPH, target)
    assert (target / "a.mer").is_file()


def test_a_missing_directory_argument_uses_the_module_global(tmp_path, monkeypatch):
    """Resolved per call, exactly as `load_diagrams` does — a default argument
    would bind at import and ignore any later change."""
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", tmp_path)
    save_diagram("from-global", "From Global", "", GRAPH)
    assert (tmp_path / "from-global.mer").is_file()


def test_no_temporary_file_is_left_behind(tmp_path):
    """The write is write-then-rename, so a `.tmp` surviving the call means the
    rename did not happen and something else is about to read a partial file."""
    save_diagram("clean", "Clean", "", GRAPH, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clean.mer"]


# --- refusals --------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "   ",
        "../evil",
        "../../etc/passwd",
        "a/b",
        "a\\b",
        "Uppercase",
        "under_score",
        "-leading-dash",
        ".hidden",
        "evil.mer",
        "trailing space ",
        "sp ace",
        "x" * 81,
    ],
)
def test_a_slug_that_is_not_a_plain_file_name_is_refused(tmp_path, slug):
    with pytest.raises(InvalidSlug):
        save_diagram(slug, "T", "", GRAPH, tmp_path)


def test_a_refused_slug_writes_absolutely_nothing(tmp_path):
    """The other half of the check above. A guard that raises after writing is
    not a guard, and a traversal that raises after writing is the whole bug."""
    outside = tmp_path / "outside"
    outside.mkdir()
    inside = tmp_path / "diagrams"
    inside.mkdir()

    with pytest.raises(InvalidSlug):
        save_diagram("../outside/pwned", "T", "", GRAPH, inside)

    assert list(outside.iterdir()) == []
    assert list(inside.iterdir()) == []


def test_an_ordinary_slug_is_not_refused(tmp_path):
    """The positive control for the parametrised refusals above: without it,
    a `save_diagram` that raised `InvalidSlug` unconditionally would pass every
    one of them."""
    saved = save_diagram("perfectly-ordinary-9", "Fine", "", GRAPH, tmp_path)
    assert saved.slug == "perfectly-ordinary-9"


@pytest.mark.parametrize("code", ["", "   ", "\n\n\t\n"])
def test_an_empty_diagram_is_refused(tmp_path, code):
    with pytest.raises(EmptyDiagram):
        save_diagram("empty", "Empty", "", code, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_existing_diagram_is_never_overwritten(tmp_path):
    """Refusing is the point. The author of the file being replaced is not the
    person clicking Save, and the file they would lose is not on screen."""
    save_diagram("taken", "First", "", "graph TD\n    A --> B\n", tmp_path)

    with pytest.raises(DiagramExists):
        save_diagram("taken", "Second", "", "graph TD\n    C --> D\n", tmp_path)

    assert (tmp_path / "taken.mer").read_text(encoding="utf-8").count("A --> B") == 1
    assert "C --> D" not in (tmp_path / "taken.mer").read_text(encoding="utf-8")
