"""diagram-viewer — a FastAPI front end for the diagrams in `diagrams/`.

Two routes: an index listing every `.mer` file, and a page per file showing the
rendered diagram. Diagrams are read on each request so `--reload` is not needed
to pick up an edit to a `.mer` file — only to a `.py` one.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from stonedog_logs import configure as configure_logging

from loader import DIAGRAMS_DIR, find_diagram, load_diagrams

log = logging.getLogger(__name__)

SERVICE_NAME = "diagram-viewer"


@asynccontextmanager
async def _announce_what_was_scanned(app: FastAPI):
    """Say which directory holds the diagrams, and how many are in it.

    THE FAILURE THIS EXISTS FOR. `DIAGRAMS_DIR` is relative to this file and the
    diagrams are read per request, so a wrong working directory, a container
    missing a mount, or a file saved as `.mmd` instead of `.mer` all produce the
    same thing: a server that starts cleanly, answers 200, and shows an empty
    gallery. That is indistinguishable from a server whose diagrams simply have
    not been added yet — and nothing said which of the two it was.

    The count is the only thing that separates them, so the count is printed.

    `only_if_unconfigured=True` because `uvicorn app:app` configures uvicorn's
    own loggers and nothing else, so this line would go nowhere; and because a
    host that has already set logging up must not get a second handler and every
    line twice.
    """
    configure_logging(service_name=SERVICE_NAME, only_if_unconfigured=True)

    found = load_diagrams()
    log.info(
        "scanned %s — %d diagram(s): %s",
        DIAGRAMS_DIR,
        len(found),
        ", ".join(d.slug for d in found) or "none",
    )
    if not found:
        log.warning(
            "no diagrams found in %s — the gallery will render empty. Files must "
            "end in .mer",
            DIAGRAMS_DIR,
        )
    yield


app = FastAPI(title="Diagram Viewer", lifespan=_announce_what_was_scanned)

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
        # A 404 tells the person nothing an operator can act on. This says what
        # was actually asked for, which is what turns "the link is broken" into
        # "that file is not in the directory".
        log.info("no diagram named %r in %s", slug, DIAGRAMS_DIR)
        raise HTTPException(status_code=404, detail=f"No diagram named {slug!r}")
    return templates.TemplateResponse(
        request=request,
        name="diagram.html",
        context={"diagram": found},
    )
