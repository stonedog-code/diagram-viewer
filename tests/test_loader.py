"""Unit tier — parsing and discovery, no HTTP."""

import pytest

from loader import Diagram, find_diagram, load_diagrams, parse_diagram, slug_to_title


def test_parses_title_and_description_from_header():
    d = parse_diagram("x", "%% title: My Chart\n%% description: What it shows\ngraph TD\n    A --> B\n")
    assert d.title == "My Chart"
    assert d.description == "What it shows"
    assert d.code == "graph TD\n    A --> B"


def test_header_keys_are_case_insensitive_and_whitespace_tolerant():
    d = parse_diagram("x", "%%TITLE:  Spaced Out  \n%%   Description:Tight\ngraph TD\n")
    assert d.title == "Spaced Out"
    assert d.description == "Tight"


def test_title_falls_back_to_the_slug_when_no_header():
    d = parse_diagram("entity-relationship-diagram", "erDiagram\n    A ||--o{ B : has\n")
    assert d.title == "Entity Relationship Diagram"
    assert d.description == ""
    assert d.code.startswith("erDiagram")


def test_header_block_ends_at_the_first_non_header_line():
    # A `%% note` inside the diagram body is Mermaid's, not ours — it stays
    # in the code rather than being swallowed as metadata.
    d = parse_diagram("x", "%% title: T\ngraph TD\n%% description: not metadata\n    A --> B\n")
    assert d.description == ""
    assert "%% description: not metadata" in d.code


def test_unknown_header_keys_stay_in_the_code():
    d = parse_diagram("x", "%% author: someone\ngraph TD\n")
    assert "%% author: someone" in d.code


def test_leading_blank_lines_do_not_end_the_header():
    d = parse_diagram("x", "\n\n%% title: Late Header\ngraph TD\n")
    assert d.title == "Late Header"


@pytest.mark.parametrize(
    "slug,expected",
    [("flowchart", "Flowchart"), ("a-b", "A B"), ("snake_case_name", "Snake Case Name")],
)
def test_slug_to_title(slug, expected):
    assert slug_to_title(slug) == expected


def _write(directory, name, text):
    (directory / name).write_text(text, encoding="utf-8")


def test_load_diagrams_reads_only_mer_files(tmp_path):
    _write(tmp_path, "one.mer", "%% title: One\ngraph TD\n")
    _write(tmp_path, "notes.md", "%% title: Two\ngraph TD\n")
    _write(tmp_path, "two.mermaid", "graph TD\n")

    loaded = load_diagrams(tmp_path)

    assert [d.slug for d in loaded] == ["one"]


def test_load_diagrams_sorts_by_title(tmp_path):
    _write(tmp_path, "z.mer", "%% title: Alpha\ngraph TD\n")
    _write(tmp_path, "a.mer", "%% title: zeta\ngraph TD\n")
    _write(tmp_path, "m.mer", "%% title: Mid\ngraph TD\n")

    assert [d.title for d in load_diagrams(tmp_path)] == ["Alpha", "Mid", "zeta"]


def test_missing_directory_is_an_empty_gallery_not_an_error(tmp_path):
    assert load_diagrams(tmp_path / "nope") == []


def test_find_diagram_returns_the_match(tmp_path):
    _write(tmp_path, "one.mer", "%% title: One\ngraph TD\n")
    found = find_diagram("one", tmp_path)
    assert isinstance(found, Diagram)
    assert found.slug == "one"


def test_find_diagram_returns_none_for_an_unknown_slug(tmp_path):
    _write(tmp_path, "one.mer", "graph TD\n")
    assert find_diagram("two", tmp_path) is None


@pytest.mark.parametrize("slug", ["../secret", "../../secret", "sub/../../secret", "/etc/passwd"])
def test_find_diagram_refuses_path_traversal(tmp_path, slug):
    """A slug must not be able to name a `.mer` file outside the gallery.

    `secret.mer` is planted one level *up* and is a perfectly loadable diagram,
    so anything that builds a path from the slug serves it. The lookup does not
    build a path at all, so it matches nothing.
    """
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    _write(gallery, "one.mer", "graph TD\n")
    _write(tmp_path, "secret.mer", "%% title: Secret\ngraph TD\n    A --> B\n")

    assert find_diagram(slug, gallery) is None


def test_shipped_diagrams_all_parse():
    diagrams = load_diagrams()
    assert len(diagrams) >= 3
    for d in diagrams:
        assert d.title, f"{d.slug} has no title"
        assert d.code, f"{d.slug} has no code"
        assert not d.code.startswith("%% title:"), f"{d.slug} kept its header in the code"
