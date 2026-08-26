"""Reading Mermaid diagrams off disk.

Pure functions plus one directory scan — no FastAPI, no HTML. `parse_diagram`
takes text and returns a Diagram, which is what makes the metadata rules
testable without touching the filesystem.

A `.mer` file is plain Mermaid source. Optional metadata rides in leading `%%`
comments, which Mermaid ignores, so a file with a header still renders as-is if
you paste it into any other Mermaid tool:

    %% title: Architecture Flowchart
    %% description: High-level overview of services and pipelines
    graph TD
        A --> B
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# Where the `.mer` files live. Overridable by environment so a self-hosted
# instance can point at its own directory — and so a test can give the app a
# WRITABLE directory that is not this repository's own. The scratchpad writes
# here, and a test that saves into `diagrams/` leaves a file behind that the
# next run reports as an undocumented diagram.
DIAGRAMS_DIR = Path(
    os.environ.get("DIAGRAM_VIEWER_DIAGRAMS_DIR") or Path(__file__).parent / "diagrams"
)

# A slug is a filename, so this is the boundary between a form field and the
# filesystem. Lowercase, digits and dashes only, and it must start with an
# alphanumeric: that admits no `.`, no `/` and no `..`, which is what makes
# `directory / f"{slug}.mer"` safe to build at all. `find_diagram` avoids path
# arithmetic entirely by scanning; saving cannot, so it validates instead.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")

# `%% key: value` at the top of the file. Only the keys below are consumed;
# any other `%%` comment is left in the code as an ordinary Mermaid comment.
_META_RE = re.compile(r"^\s*%%\s*(title|description)\s*:\s*(.*?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Diagram:
    slug: str
    title: str
    description: str
    code: str


def parse_diagram(slug: str, text: str) -> Diagram:
    """Split a `.mer` file's text into metadata and Mermaid code.

    Metadata is only read from the leading comment block: the first line that
    is not a `%% key: value` header ends it, so a `%% note` further down the
    diagram stays part of the code where the author put it.
    """
    meta: dict[str, str] = {}
    lines = text.splitlines()
    body_start = 0

    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            continue
        match = _META_RE.match(line)
        if not match:
            body_start = i
            break
        meta[match.group(1).lower()] = match.group(2)
        body_start = i + 1

    return Diagram(
        slug=slug,
        title=meta.get("title") or slug_to_title(slug),
        description=meta.get("description", ""),
        code="\n".join(lines[body_start:]).strip(),
    )


def slug_to_title(slug: str) -> str:
    """`entity-relationship-diagram` -> `Entity Relationship Diagram`."""
    return slug.replace("-", " ").replace("_", " ").strip().title()


def slugify(title: str) -> str:
    """`My New Chart!` -> `my-new-chart`, or `""` if nothing survives.

    The empty return is deliberate rather than a fallback like `diagram`: a
    title of `!!!` has no slug, and inventing one would silently save the file
    somewhere the author did not choose. The caller reports it instead.
    """
    lowered = re.sub(r"[^a-z0-9]+", "-", title.strip().lower())
    return lowered.strip("-")[:80].strip("-")


def load_diagrams(directory: Path | None = None) -> list[Diagram]:
    """Every `.mer` file in `directory`, sorted by title.

    `directory` is resolved per call rather than bound as a default argument,
    so `DIAGRAMS_DIR` can be pointed elsewhere after import — a default
    argument is evaluated once at import and silently ignores any later change.

    A missing directory yields an empty list rather than raising — an empty
    gallery is a state the index page renders, not a 500.
    """
    directory = DIAGRAMS_DIR if directory is None else directory
    if not directory.is_dir():
        return []

    diagrams = [
        parse_diagram(path.stem, path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.mer"))
        if path.is_file()
    ]
    return sorted(diagrams, key=lambda d: d.title.lower())


def find_diagram(slug: str, directory: Path | None = None) -> Diagram | None:
    """Look a diagram up by slug.

    Deliberately a lookup over the scanned set rather than building a path from
    `slug`: a request for `../../etc/passwd` matches nothing and returns None,
    with no path arithmetic to get wrong.
    """
    for diagram in load_diagrams(directory):
        if diagram.slug == slug:
            return diagram
    return None


# ── Saving a new diagram ──────────────────────────────────────────────────
#
# Everything above this line reads. This part writes, and it is the only code
# in the app that turns a form field into a filename — so the checks live here
# rather than in the route, where a second entry point could miss them.


class SaveError(ValueError):
    """A save that was refused, with a message fit to show the author.

    A plain 500 loses the diagram somebody just typed. Every refusal below
    carries a sentence the page can render next to their still-populated
    textarea, because the text is the expensive thing on that page.
    """


class InvalidSlug(SaveError):
    pass


class DiagramExists(SaveError):
    pass


class EmptyDiagram(SaveError):
    pass


def render_source(title: str, description: str, code: str) -> str:
    """Build `.mer` text: the metadata header, then the Mermaid body.

    The inverse of `parse_diagram`, and the round trip is asserted — a header
    this writes and that cannot read is a diagram whose title silently reverts
    to its slug the moment it is reloaded.

    A newline in a title would end the header block and push the rest into the
    body, so titles are flattened rather than trusted. Nothing is escaped
    beyond that: `%%` is a Mermaid comment, and the values are only ever read
    back by `_META_RE`, which stops at the end of the line.
    """
    header = []
    flat_title = " ".join(title.split())
    flat_description = " ".join(description.split())
    if flat_title:
        header.append(f"%% title: {flat_title}")
    if flat_description:
        header.append(f"%% description: {flat_description}")
    body = code.strip()
    return "\n".join([*header, body]) + "\n"


def save_diagram(
    slug: str,
    title: str,
    description: str,
    code: str,
    directory: Path | None = None,
) -> Diagram:
    """Write a new `.mer` file and return the Diagram it parses back to.

    Refuses rather than overwrites. A scratchpad whose Save button can replace
    an existing diagram is one keystroke away from destroying work that is not
    on screen, and the author of the file being replaced is not the person
    clicking.

    `directory` is resolved per call, exactly as `load_diagrams` does, so
    pointing `DIAGRAMS_DIR` elsewhere after import works here too.
    """
    directory = DIAGRAMS_DIR if directory is None else directory

    if not SLUG_RE.match(slug or ""):
        raise InvalidSlug(
            "A name may use lowercase letters, digits and dashes only, must "
            "start with a letter or digit, and must be at most 80 characters."
        )
    if not code.strip():
        raise EmptyDiagram("There is no Mermaid source to save.")

    path = directory / f"{slug}.mer"

    # The regex already makes this unreachable. It is here anyway because the
    # regex is one edit away from admitting a dot or a slash, and the cost of
    # being wrong is a write outside the diagram directory. Asserted in the
    # tests in both directions: a traversal attempt is refused, and an ordinary
    # slug is NOT.
    if path.resolve().parent != directory.resolve():
        raise InvalidSlug(f"{slug!r} does not name a file in the diagram directory.")

    if path.exists():
        raise DiagramExists(
            f"A diagram named {slug!r} already exists. Choose another name."
        )

    directory.mkdir(parents=True, exist_ok=True)
    text = render_source(title, description, code)

    # Write-then-rename. A half-written file is still a `.mer` file, and the
    # gallery scans per request — so a crash mid-write would publish a truncated
    # diagram that renders as Mermaid's error graphic. `os.replace` is atomic
    # within a directory, and the temp file is made in the SAME directory so it
    # cannot land on another filesystem where the rename would not be.
    tmp = directory / f".{slug}.mer.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    return parse_diagram(slug, text)
