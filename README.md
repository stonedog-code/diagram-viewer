# diagram-viewer

A FastAPI app that serves the Mermaid diagrams in `diagrams/`: an index listing
every diagram, and a page per diagram that renders it in the browser via the
Mermaid CDN bundle. Add a diagram by dropping a `.mer` file into `diagrams/` —
there is no code to edit and nothing to restart.

```
diagrams/architecture-flowchart.mer   ->   /diagram/architecture-flowchart
```

---

## Setup

The only prerequisite is **[uv](https://docs.astral.sh/uv/)**, which manages the
dependencies *and* Python itself — you do not need a system Python of any
particular version. `.python-version` pins 3.12 and uv downloads it if the
machine lacks it, which is what keeps Linux and macOS on the same interpreter.

### Linux

```bash
# 1. uv, if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh     # installs to ~/.local/bin
#    ...and make sure that's on PATH:
export PATH="$HOME/.local/bin:$PATH"                # add to ~/.bashrc

# 2. the app
git clone git@github.com:nehsa-net/diagram-viewer.git
cd diagram-viewer
bash run.sh
```

### macOS

```bash
# 1. uv, if you don't have it
brew install uv                                     # or the curl line above
#    the curl installer puts it in ~/.local/bin:
export PATH="$HOME/.local/bin:$PATH"                # add to ~/.zshrc

# 2. the app
git clone git@github.com:nehsa-net/diagram-viewer.git
cd diagram-viewer
bash run.sh
```

Either way, `run.sh` creates the environment from `uv.lock` on first run and
then starts the server. Open <http://localhost:8000>.

> **Invoke it as `bash run.sh`, not `./run.sh`.** Both work on a normal clone,
> but the executable bit does not always survive a network share, and `bash`
> works either way.

### Running it

```bash
bash run.sh                      # serve on :8000 with --reload
bash run.sh serve --port 9000    # extra arguments go to uvicorn
bash run.sh test                 # the test suite
```

### If the checkout is shared between two machines

Skip this unless the working tree lives on a network share that a Mac and a
Linux box both mount — an SMB/NFS export, for example. This project began life
that way, and it is why `run.sh` exists at all.

A `.venv` is **not portable**: it holds compiled extensions for one
architecture, an absolute-path shebang in every console script, and a
`bin/python` symlink into that machine's uv toolchain. Two machines sharing one
checkout share the `.venv` too, and the second one to use it fails like this:

```
error: Failed to spawn: `uvicorn`
  Caused by: No such file or directory (os error 2)
```

That message names the wrong file. `uvicorn` is right there; its shebang points
at `.venv/bin/python`, that symlink targets an interpreter the other machine
does not have, and `execve` reports a **missing shebang interpreter as ENOENT
against the script**. Nothing mentions the interpreter, so it reads as "uvicorn
is not installed" — and `uv sync` does not fix it, because the site-packages are
the wrong platform's binaries too.

`run.sh` sources `scripts/uv-env.sh`, which sends macOS to `.venv-macos` and
everything else to `.venv`, so the two never collide. On an ordinary
single-machine clone the split costs nothing. To use a bare `uv run` on a Mac,
export the same variable:

```bash
export UV_PROJECT_ENVIRONMENT=.venv-macos     # add to ~/.zshrc
```

An explicit `UV_PROJECT_ENVIRONMENT` always wins over the script's choice.

---

## Routes

| Route | Shows |
|---|---|
| `/` | every `.mer` file in `diagrams/`, title and description, linked |
| `/diagram/{slug}` | that one diagram rendered, plus its source in a `<details>` |

The slug is the filename without `.mer`.

### Zooming a diagram

A diagram page carries its own zoom controls, because the interesting diagrams
here are far wider than a browser window and the page-level browser zoom shrinks
the text along with everything else.

| Control | Key | Does |
|---|---|---|
| **&minus;** / **+** | <kbd>-</kbd> / <kbd>+</kbd> | step down/up through fixed stops, 10% to 400% |
| **Reset** | <kbd>0</kbd> | back to 100% |
| **Fit** | <kbd>F</kbd> | shrink until the whole width is visible — never enlarges past 100% |
| drag | — | pan, anywhere in the diagram area |

**A page opens fitted to width, not at 100%**, and stays that way until you
touch a control — a diagram that opens scrolled off the right edge reads as
broken. Once you have zoomed, the page stops re-fitting itself.

Two implementation notes, both of which are load-bearing and neither of which
is obvious:

- **The scaled element is not the one the scrollbars measure.** A CSS transform
  does not affect layout, so scaling the diagram alone leaves the scrollable
  area stuck at its unzoomed size and clips everything past it. A sizer element
  wraps the scaled pane and is given the scaled dimensions explicitly.
- **Mermaid's `<svg>` is pinned to its own `viewBox` after rendering.** It ships
  as `width: 100%; max-width: <natural>px`, which is responsive but has no
  definite width to resolve against inside a shrink-to-fit box — it collapses to
  the CSS default 300px and the diagram renders as a thumbnail.

## Layout

```
diagram-viewer/
├── run.sh              # start it — picks the right venv per platform
├── app.py              # the two routes
├── loader.py           # reading and parsing .mer files — no HTTP, no HTML
├── diagrams/           # one .mer file per diagram
├── templates/          # base.html + index.html + diagram.html (Jinja2)
├── tests/              # unit (loader) + integration (routes)
├── scripts/uv-env.sh   # sourced by run.sh; picks .venv / .venv-macos
├── pyproject.toml      # deps (fastapi, uvicorn, jinja2)
├── uv.lock             # exact pinned versions
└── .python-version     # 3.12; uv downloads it if the machine lacks it
```

## Adding a diagram

Drop a `.mer` file into `diagrams/`. Nothing else — the directory is scanned per
request, so a new file appears on the next page load even without `--reload`.

```
%% title: Architecture Flowchart
%% description: High-level overview of services and pipelines
graph TD
    A[Client] --> B(API Gateway)
```

`title` and `description` are optional metadata carried in leading `%%`
comments. Mermaid treats `%%` as a comment, so the file is still valid Mermaid
source you can paste into any other tool. Rules:

- Only the **leading** comment block is read as metadata. The first line that is
  not a `%% key: value` header ends it, so a `%% note` inside the diagram stays
  in the diagram.
- Only `title` and `description` are consumed; any other `%%` line is left in
  the code.
- With no `title`, the filename is used — `entity-relationship-diagram.mer`
  becomes "Entity Relationship Diagram".

## Testing

```bash
bash run.sh test         # 32 tests
```

- **unit** (`tests/test_loader.py`) — header parsing, the metadata/code split,
  discovery, sorting, and the path-traversal refusal.
- **integration** (`tests/test_routes.py`) — the real routes against the real
  templates and the real files: the index lists one card per `.mer` file, every
  link resolves 200, an unknown slug is 404, titles are escaped, every diagram
  page ships all eight zoom-control ids, the zoom pane encloses the Mermaid
  block, and no `.mer` label carries an unbalanced `"`.

**Non-vacuity was checked rather than assumed** (2026-08-21). Each of the three
zoom-related tests was made to fail on purpose — renaming `id="zoom-fit"`,
moving the `<pre>` out of the pane, and planting a literal `"` inside a label —
and each failure was caught by exactly one test, with the restored tree back to
32 passing.

**No E2E tier in the repo.** Mermaid actually producing SVG is the one thing
neither tier can see — `TestClient` never runs the CDN module — and it is
checked by hand in a browser rather than by a committed Playwright suite. Do not
describe this project as fully tested until that suite exists.

Verified in a real browser on Linux 2026-08-21, driving the running app. Every
diagram in `diagrams/` produced SVG with no syntax error:

| Diagram | Nodes | Subgraphs | Edges |
|---|---|---|---|
| `spa-vs-htmx` | 4 | 2 | 2 |
| `slack-highlevel` | 6 | 0 | 8 |
| `slack-edge-server` | 17 | 3 | 17 |
| `slack-test-server` | 10 | 1 | 15 |
| `slack-detailed` | 21 | 2 | 24 |
| `test-traditional-rest` | 8 | 4 | 9 |
| `test-htmx` | 17 | 5 | 19 |

Counts, not a pass/fail: they are what tells you the next run examined the same
set. The fit percentage a page opens at is deliberately **not** in the table —
it depends on the viewport width, so it is not comparable between runs. The zoom controls were exercised on
`slack-detailed`: fit 26% → in 40% → in 50% → out 40% → reset 100% → fit 25%,
with the keyboard bindings agreeing, and the viewport's scrollable width
tracking the zoom at every step (779px fitted, 3081px at 100%) — which is the
check that the sizer is doing its job and the diagram is not being clipped.

## Notes

- **The CDN import means the page needs internet to draw.** The server returns
  200 offline and the diagrams simply stay blank. To fix that, vendor
  `mermaid.esm.min.mjs` and serve it locally. The zoom controls still work in
  that state — with no `<svg>` to pin they fall back to scaling the raw Mermaid
  source, so the page degrades rather than breaking. Measured 2026-08-21 by
  pointing the import at an unreachable host: no SVG, source still on screen,
  fit 53% → in 65% → out 50% → reset 100%, scroll width tracking throughout.
- **A slug never becomes a path.** `find_diagram` looks up the scanned set
  rather than building `diagrams/<slug>.mer`, so a slug cannot name a file
  outside the gallery. There is a test that plants a `.mer` file one directory
  up and confirms it stays unreachable — written after a weaker version of that
  test passed against a deliberately vulnerable implementation.
- **Why the markup is in `templates/` and not an f-string.** There are two
  pages, and `title`/`description` now come from files on disk where an
  unescaped `<` would break the page. Jinja2 autoescaping handles both,
  including inside the Mermaid block — the browser decodes the entities back
  into `textContent`, which is what Mermaid parses.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Copyright 2026 nehsa.net.

Mermaid itself is not vendored here: the browser loads it from a CDN at runtime,
under its own MIT license.
