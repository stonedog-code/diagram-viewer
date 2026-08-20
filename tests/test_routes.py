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
