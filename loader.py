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

import re
from dataclasses import dataclass
from pathlib import Path

DIAGRAMS_DIR = Path(__file__).parent / "diagrams"

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
