# diagram-viewer

FastAPI serving the Mermaid diagrams in `diagrams/` — an index, a page per
`.mer` file, and a `/scratchpad` that writes new ones. Rendering is client-side
everywhere, including the scratchpad's Render button; saving is the one server
path that turns a form field into a filename, so its validation lives in
`loader.save_diagram` rather than in the route. Run it with `bash run.sh`
(:8000); the gate is `bash run.sh test`. Details in `README.md`.
