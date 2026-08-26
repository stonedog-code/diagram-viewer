"""diagram-viewer — a FastAPI front end for the diagrams in `diagrams/`.

Three surfaces: an index listing every `.mer` file, a page per file showing the
rendered diagram, and a scratchpad for writing a new one. Diagrams are read on
each request so `--reload` is not needed to pick up an edit to a `.mer` file —
only to a `.py` one.

The scratchpad renders in the BROWSER and saves on the SERVER, and the split is
the whole design. Rendering is what Mermaid already does client-side on every
diagram page, so a Render button that posted to the server would be a second
rendering path to keep in agreement with the first. Saving cannot be done in the
browser at all, and it is the only place in this app where a form field becomes
a filename — so that is where the validation lives (`loader.save_diagram`).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from stonedog_logs import configure as configure_logging

import loader
from loader import (
    DiagramExists,
    SaveError,
    find_diagram,
    load_diagrams,
    save_diagram,
    slugify,
)

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

    `loader.DIAGRAMS_DIR` is read through the module rather than imported by
    name, here and everywhere below. `from loader import DIAGRAMS_DIR` makes a
    SECOND binding of one fact, and the two can then disagree — the scan would
    read one directory while this line named another, which is exactly the
    "which directory did it look in" question the announcement exists to answer.
    """
    configure_logging(service_name=SERVICE_NAME, only_if_unconfigured=True)

    found = load_diagrams()
    log.info(
        "scanned %s — %d diagram(s): %s",
        loader.DIAGRAMS_DIR,
        len(found),
        ", ".join(d.slug for d in found) or "none",
    )
    if not found:
        log.warning(
            "no diagrams found in %s — the gallery will render empty. Files must "
            "end in .mer",
            loader.DIAGRAMS_DIR,
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
        log.info("no diagram named %r in %s", slug, loader.DIAGRAMS_DIR)
        raise HTTPException(status_code=404, detail=f"No diagram named {slug!r}")
    return templates.TemplateResponse(
        request=request,
        name="diagram.html",
        context={"diagram": found},
    )


@app.get("/scratchpad", response_class=HTMLResponse)
async def scratchpad(request: Request):
    """The editor. Empty by default; `?code=` is not accepted.

    Prefilling from a query string would make a link that puts arbitrary text
    in someone's editor, and the Save button is right underneath it.
    """
    return templates.TemplateResponse(
        request=request,
        name="scratchpad.html",
        context={"form": {"title": "", "description": "", "slug": "", "code": ""}},
    )


@app.post("/scratchpad", response_class=HTMLResponse)
async def scratchpad_save(
    request: Request,
    code: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    slug: str = Form(""),
):
    """Save the scratchpad as a new diagram, or say why not.

    THE RULE THIS ROUTE IS BUILT AROUND: never lose the source. Every refusal
    re-renders the page with the submitted text still in the textarea and the
    reason above it. A redirect-with-a-flash, or a bare 400, would cost the
    author the diagram they just wrote, which is the only thing on this page
    that took any effort.

    Success is a 303 to the saved diagram, so a reload of the destination does
    not re-submit the form.
    """
    submitted = {
        "title": title,
        "description": description,
        "slug": slug,
        "code": code,
    }

    # An empty name is not an error — it is the common case, and the title is
    # right there. `slugify` returns "" when a title has nothing usable in it,
    # and save_diagram then reports that as the invalid name it is.
    wanted = slug.strip() or slugify(title)

    try:
        saved = save_diagram(wanted, title, description, code)
    except SaveError as refused:
        log.info("scratchpad save refused for %r: %s", wanted, refused)
        return templates.TemplateResponse(
            request=request,
            name="scratchpad.html",
            context={"form": submitted, "error": str(refused)},
            # 409 for a name already taken, 400 for anything malformed. Both
            # keep the body; the distinction is for whatever reads the log.
            status_code=409 if isinstance(refused, DiagramExists) else 400,
        )

    log.info("scratchpad saved %s.mer in %s", saved.slug, loader.DIAGRAMS_DIR)
    return RedirectResponse(url=f"/diagram/{saved.slug}", status_code=303)
