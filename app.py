"""diagram-viewer — a FastAPI front end for the diagrams in `diagrams/`.

Two routes: an index listing every `.mer` file, and a page per file showing the
rendered diagram. Diagrams are read on each request so `--reload` is not needed
to pick up an edit to a `.mer` file — only to a `.py` one.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from loader import find_diagram, load_diagrams

app = FastAPI(title="Diagram Viewer")

# Autoescaping is why the markup moved out of an f-string: `title` and
# `description` now come from files on disk, so a `<` in one must not be able
# to break the page. It is also correct for the Mermaid body — the browser
# decodes the entities back into textContent, which is what Mermaid parses.
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"diagrams": load_diagrams()},
    )


@app.get("/diagram/{slug}", response_class=HTMLResponse)
async def diagram(request: Request, slug: str):
    found = find_diagram(slug)
    if found is None:
        raise HTTPException(status_code=404, detail=f"No diagram named {slug!r}")
    return templates.TemplateResponse(
        request=request,
        name="diagram.html",
        context={"diagram": found},
    )
