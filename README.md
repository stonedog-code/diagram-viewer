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
bash run.sh test                 # the test suite, all three tiers
bash run.sh test tests/e2e       # just the browser tier
```

`run.sh test` fetches the Chromium build the E2E tier drives before running
pytest. That is a one-off download; once the build is present the call makes no
network request at all, so it costs nothing on every run after the first.

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
| `/scratchpad` | write Mermaid, press Render, save it as a new diagram |

The slug is the filename without `.mer`.

### The scratchpad

Write Mermaid in the box, press **Render** (or <kbd>Ctrl</kbd>+<kbd>Enter</kbd>)
and the picture appears beside it. Give it a title and press **Save as a new
diagram**: it is written to `diagrams/` as a `.mer` file and you land on its own
page, zoom controls and all. From then on it is an ordinary diagram — there is
nothing special about a file the scratchpad wrote.

The file name is optional; leave it blank and it comes from the title
(`Architecture Flowchart` → `architecture-flowchart.mer`).

**Rendering happens in the browser, saving on the server**, and the split is
deliberate. Every diagram page already draws client-side, so a Render button
that posted to the server would be a second rendering path to keep in agreement
with the first — and the two disagreeing is a preview that lies.

Three rules the Save button follows, each of which is a way this could go wrong:

- **An existing diagram is never overwritten.** A name already taken is refused
  and says so. The author of the file that would be replaced is not the person
  clicking Save, and the file they would lose is not on screen.
- **A refused save never costs you the source.** The page comes back with the
  textarea still populated *and the diagram re-drawn*. The text is the only
  thing on that page that took any effort.
- **A name is a file name, and is validated as one.** Lowercase letters, digits
  and dashes, starting with a letter or digit. That admits no `.`, no `/` and no
  `..` — which is what makes building `diagrams/<name>.mer` safe at all. This is
  the only place in the app where something typed into a form becomes a path;
  everywhere else looks a diagram up by scanning the directory, which is why
  `find_diagram` needs no validation of its own.

Mermaid's parse errors are shown where the picture would be. That matters more
than it sounds: Mermaid draws its *own* error graphic as an `<svg>`, so "an svg
appeared" is not evidence of a successful render — which is why the E2E tests
check `aria-roledescription` rather than the presence of an element.

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
├── diagrams/           # one .mer file per diagram — the scratchpad writes here
├── templates/          # base.html + index.html + diagram.html + scratchpad.html
├── tests/              # unit (loader) + integration (routes) + e2e (browser)
├── scripts/uv-env.sh   # sourced by run.sh; picks .venv / .venv-macos
├── pyproject.toml      # deps (fastapi, uvicorn, jinja2)
├── uv.lock             # exact pinned versions
└── .python-version     # 3.12; uv downloads it if the machine lacks it
```

### Keeping the diagrams outside the checkout

`DIAGRAM_VIEWER_DIAGRAMS_DIR` points the app at another directory:

```bash
DIAGRAM_VIEWER_DIAGRAMS_DIR=~/diagrams bash run.sh
```

Useful for a self-hosted instance whose diagrams are not this repository's, and
it is what the E2E tier uses to give the scratchpad a writable directory that is
*not* `diagrams/` — a test that saved into the real one would leave a diagram
behind for every future run, and would pass while doing it.

## Adding a diagram

Two ways, and they produce the same thing. Use `/scratchpad` if you want to see
it as you write it; drop the file in yourself if you already have the source.

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
- **Add a row to the shape-count table below in the same commit.** The E2E tier
  reads that table as its fixture, so a new `.mer` file with no row fails the
  gate on purpose — an undocumented diagram is one nothing can tell has stopped
  drawing properly.

## What it says at startup

```
INFO [diagram-viewer] app: scanned /…/diagram-viewer/diagrams — 7 diagram(s): slack-detailed, …
```

**That count is the point.** `DIAGRAMS_DIR` is relative to `loader.py` and the
diagrams are read per request, so a wrong working directory, a container missing
a mount, or a file saved as `.mmd` instead of `.mer` all produce the same thing:
a server that starts cleanly, answers 200, and shows an empty gallery — which is
indistinguishable from a project whose diagrams have not been added yet. Nothing
used to say which of the two it was.

An empty result adds a warning naming the directory and the required extension.
A request for a diagram that does not exist logs what was asked for, because a
bare 404 tells an operator nothing they can act on. Successful requests log
nothing: uvicorn already has an access log, and duplicating it would bury the
lines above.

Logging is [`stonedog-logs`](https://pypi.org/project/stonedog-logs/), shared
with the other Python tools here. `LOG_LEVEL` and `STONEDOG_LOGS_JSON=1` work as
you would expect; it is configured only if nothing else has, because
`uvicorn app:app` configures uvicorn's own loggers and would otherwise leave
these lines with nowhere to go.

## Testing

```bash
bash run.sh test         # 55 tests — unit + integration + e2e
```

- **unit** (`tests/test_loader.py`) — header parsing, the metadata/code split,
  discovery, sorting, and the path-traversal refusal.
- **integration** (`tests/test_routes.py`) — the real routes against the real
  templates and the real files: the index lists one card per `.mer` file, every
  link resolves 200, an unknown slug is 404, titles are escaped, every diagram
  page ships all eight zoom-control ids, the zoom pane encloses the Mermaid
  block, and no `.mer` label carries an unbalanced `"`.
- **e2e** (`tests/e2e/`) — Playwright against a real uvicorn in a real Chromium:
  every diagram draws, draws *whole*, and the zoom controls behave at a named
  viewport.

**Why the third tier is not optional here.** Rendering is client-side, so a
`.mer` file Mermaid cannot parse still produces a perfectly valid 200 with a
perfectly valid `<pre>` in it — every unit and integration test passes, and the
page shows an error graphic. `TestClient` never executes the CDN module, so
there is no assertion either of those tiers could add that would see it. The
same goes for the zoom controls: jsdom has no layout engine, so it reports every
box as zero-sized and would happily agree that a 3000px diagram fits a 375px
window.

**Two things in the E2E tier are load-bearing:**

- **"An `<svg>` appeared" is not an assertion.** Mermaid's error graphic *is* an
  `<svg>`. The suite checks `aria-roledescription` — `flowchart-v2` for a
  diagram it parsed, `error` for one it did not — and then checks the shape
  counts, which is what catches a diagram that renders but has quietly lost half
  of itself.
- **The table below is the fixture.** `tests/e2e/support.py` parses these rows
  out of this file rather than restating them, so the documented numbers and the
  asserted numbers cannot drift apart, and a `.mer` file with no row fails.

**Non-vacuity was checked rather than assumed.** For the integration tier
(2026-08-21), each of the three zoom-related tests was made to fail on purpose —
renaming `id="zoom-fit"`, moving the `<pre>` out of the pane, and planting a
literal `"` inside a label — and each was caught by exactly one test.

For the E2E tier (2026-08-22), five failures were planted and the tree restored
to green after each:

| Planted | Caught by | Reported |
|---|---|---|
| a Mermaid syntax error | `test_diagram_renders_an_svg_…` | `aria-roledescription='error'`, 3 failed / 52 passed |
| an unbalanced `"` in a label | the same test, **and** the integration guard | 4 failed / 51 passed |
| one edge deleted — still renders | `test_diagram_shape_counts_…` only | `README {edges: 2}` vs `rendered {edges: 1}`, 1 failed / 54 passed |
| `diagrams/` emptied | the input-set guard | `e2e: examined 0 diagram(s)`, 11 failed — an empty set FAILS |
| a row deleted from the table below | the input-set guard | `in diagrams/ but not README: ['test-htmx']` |

The third row is the one worth reading twice: the diagram still drew, so the
"is there an svg" test passed and only the counts caught it. The fourth is the
house rule about a green result over an empty set, implemented — every run
prints the size of its input set, and 7-of-7 became 6-of-7 in the runs above.

Counts asserted on every run, and verified by hand in a real browser on Linux
2026-08-21 before they were:

| Diagram | Nodes | Subgraphs | Edges |
|---|---|---|---|
| `spa-vs-htmx` | 4 | 2 | 2 |
| `slack-highlevel` | 6 | 0 | 8 |
| `slack-edge-server` | 17 | 3 | 17 |
| `slack-test-server` | 10 | 1 | 15 |
| `slack-detailed` | 21 | 2 | 24 |
| `test-traditional-rest` | 8 | 4 | 9 |
| `test-htmx` | 17 | 5 | 19 |

Nodes are `g.node`, subgraphs are `g.cluster`, edges are `path.flowchart-link`
in the rendered SVG. The fit percentage a page opens at is deliberately **not**
in the table — it depends on the viewport width, so it is not comparable between
runs. `tests/e2e/test_zoom_controls.py` asserts it as a *relationship* instead,
at a stated 700x800 viewport: a diagram wider than the window opens below 100%
and does not scroll, Fit never enlarges one that already fits, the stops either
side of 100% are 80% and 125%, the buttons and the keyboard agree, dragging
pans, and the sizer's width doubles between 100% and 200% — which is the check
that the sizer is doing its job and a zoomed-in diagram is not being clipped.
Each of those tests asserts its own precondition (that the diagram really is
wider than the viewport), so a future diagram set that happens to fit fails
loudly rather than proving nothing.

## Notes

- **The CDN import means the page needs internet to draw — and so does CI.**
  The server returns 200 offline and the diagrams simply stay blank. The E2E
  tier therefore needs outbound network, which was a deliberate choice over
  vendoring the bundle: mermaid@10's ESM entry point *lazy-loads* its diagram
  implementations, so one page load pulls **15** files from the CDN (measured
  2026-08-22), and a single vendored `mermaid.esm.min.mjs` would not be a
  faithful stand-in for what a reader's browser does. Testing the page as it is
  actually served is worth the dependency, and the suite is built to tell the
  two failures apart: an unreachable CDN produces no `<svg>` at all and fails
  with a message naming the CDN, where a broken diagram produces the error
  graphic and fails naming the diagram. If flake ever makes that trade a bad
  one, the fix is to vendor the whole `dist/` tree and serve it locally.
- **The page degrades offline rather than breaking.** The zoom controls still
  work with no `<svg>` to pin: they fall back to scaling the raw Mermaid source.
  Measured 2026-08-21 by pointing the import at an unreachable host — no SVG,
  source still on screen, fit 53% → in 65% → out 50% → reset 100%, scroll width
  tracking throughout.
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
