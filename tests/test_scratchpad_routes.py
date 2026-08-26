"""Integration tier — the scratchpad routes, real templates, real files.

The seam this tier exists for is the one the unit tier cannot see: that the
route hands `save_diagram` what the form actually posted, that a refusal comes
back as a page rather than a stack trace, and — the thing worth the most — that
the source the author typed is still in the textarea afterwards.

Every test here points `loader.DIAGRAMS_DIR` at `tmp_path`. A test that saved
into the repository's own `diagrams/` would leave a file behind that the E2E
tier then reports as an undocumented diagram, and it would pass while doing it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import loader
from app import app

GRAPH = "graph TD\n    A[Client] --> B(API)\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client whose app writes to, and reads from, a throwaway directory."""
    monkeypatch.setattr(loader, "DIAGRAMS_DIR", tmp_path)
    with TestClient(app) as test_client:
        yield test_client


# --- the editor ------------------------------------------------------------


def test_the_scratchpad_page_offers_an_editor_and_both_buttons(client):
    response = client.get("/scratchpad")
    assert response.status_code == 200
    assert 'id="code"' in response.text
    assert 'id="render"' in response.text
    assert 'id="save"' in response.text
    assert 'action="/scratchpad"' in response.text


def test_the_gallery_links_to_the_scratchpad(client):
    assert 'href="/scratchpad"' in client.get("/").text


def test_the_editor_starts_empty(client):
    """`?code=` is deliberately not accepted: a link that fills someone's
    editor with arbitrary text, directly above a Save button, is a link worth
    not having."""
    response = client.get("/scratchpad?code=graph+TD%3B+A--%3EB")
    assert "A--&gt;B" not in response.text
    assert "A-->B" not in response.text


# --- saving ----------------------------------------------------------------


def test_a_valid_save_writes_the_file_and_redirects_to_it(client, tmp_path):
    response = client.post(
        "/scratchpad",
        data={
            "code": GRAPH,
            "title": "My New Chart",
            "description": "What it shows",
            "slug": "my-new-chart",
        },
        follow_redirects=False,
    )
    # 303 rather than 302, so reloading the diagram page does not re-post.
    assert response.status_code == 303
    assert response.headers["location"] == "/diagram/my-new-chart"

    written = tmp_path / "my-new-chart.mer"
    assert written.is_file()
    assert "%% title: My New Chart" in written.read_text(encoding="utf-8")

    page = client.get("/diagram/my-new-chart")
    assert page.status_code == 200
    assert "My New Chart" in page.text
    assert "A[Client] --&gt; B(API)" in page.text

    assert 'href="/diagram/my-new-chart"' in client.get("/").text


def test_an_omitted_name_is_taken_from_the_title(client, tmp_path):
    response = client.post(
        "/scratchpad",
        data={"code": GRAPH, "title": "Derived From Title", "description": "", "slug": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/diagram/derived-from-title"
    assert (tmp_path / "derived-from-title.mer").is_file()


# --- refusals, and the source surviving them -------------------------------


def _refused(client, **data):
    payload = {"code": GRAPH, "title": "T", "description": "", "slug": "ok-name"}
    payload.update(data)
    return client.post("/scratchpad", data=payload, follow_redirects=False)


def test_a_duplicate_name_is_refused_with_409_and_the_existing_file_intact(
    client, tmp_path
):
    (tmp_path / "taken.mer").write_text("graph TD\n    ORIGINAL --> X\n", encoding="utf-8")

    response = _refused(client, slug="taken")

    assert response.status_code == 409
    assert "already exists" in response.text
    assert "ORIGINAL" in (tmp_path / "taken.mer").read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", ["../evil", "Upper Case", "under_score", ".hidden"])
def test_a_malformed_name_is_refused_with_400(client, slug):
    response = _refused(client, slug=slug)
    assert response.status_code == 400
    assert "lowercase letters, digits and dashes" in response.text


def test_a_title_with_no_usable_slug_is_refused_rather_than_guessed(client):
    response = _refused(client, slug="", title="!!!")
    assert response.status_code == 400


def test_an_empty_diagram_is_refused(client, tmp_path):
    response = _refused(client, code="   \n")
    assert response.status_code == 400
    assert "no Mermaid source" in response.text
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [("slug", "../evil"), ("slug", "Upper Case"), ("slug", "taken"), ("title", "!!!")],
)
def test_a_refused_save_gives_the_source_back(client, tmp_path, field, value):
    """THE RULE THIS ROUTE IS BUILT AROUND.

    The text in the textarea is the only thing on that page that took any
    effort, and a redirect-with-a-flash or a bare 400 loses it.

    Two things about the shape of this test. The probe is the ESCAPED form,
    because the template autoescapes and asserting on the raw string would pass
    against a page that had lost it. And the empty-source refusal is NOT in this
    list: there the source IS the reason, so there is nothing to give back —
    `test_an_empty_diagram_is_refused` covers that one instead. A parametrised
    case that overwrote `code` with the empty string was asserting that the page
    gives back text nobody submitted.
    """
    (tmp_path / "taken.mer").write_text("graph TD\n    A --> B\n", encoding="utf-8")
    typed = "graph TD\n    KEEP_ME[Do not lose this] --> B\n"
    payload = {"code": typed, "slug": "", "title": "T"}
    payload[field] = value
    response = _refused(client, **payload)

    assert response.status_code in (400, 409)
    assert "KEEP_ME[Do not lose this] --&gt; B" in response.text


def test_a_refused_save_gives_the_metadata_back_too(client):
    response = _refused(
        client, slug="../evil", title="Kept Title", description="Kept description"
    )
    assert 'value="Kept Title"' in response.text
    assert 'value="Kept description"' in response.text
    assert 'value="../evil"' in response.text


def test_nothing_is_written_outside_the_diagram_directory(client, tmp_path):
    """The traversal check again, this time through the real route — the unit
    tier proves the function refuses, this proves nothing between the form and
    the function undoes that."""
    outside = tmp_path.parent / "outside-the-gallery"
    outside.mkdir(exist_ok=True)
    for name in ("../outside-the-gallery/pwned", "../../tmp/pwned"):
        assert _refused(client, slug=name).status_code == 400
    assert list(outside.iterdir()) == []
