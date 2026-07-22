# Development Notes

## Project Layout

The app is served over HTTP, such as GitHub Pages, so it is split across files
rather than inlined into one `index.html`.

- `index.html`: markup shell; references the CSS and JavaScript below
- `styles/app.css`: page styles
- `js/app.js`: application logic as an ES module
- `js/qr.js`: vendored QR-code encoder imported by `app.js`
- `assets/data/`: session catalog fetched at startup
- `assets/maps/`: floor-plan maps fetched on demand
- `tools/`: catalog refresh tooling
- `tests/`: Playwright smoke tests

Because the app uses `fetch()` and ES modules, it must be served over HTTP. Do
not open it directly with `file://`.

```bash
python -m http.server
```

Then open `http://localhost:8000/`.

## Catalog Refresh

The catalog lives at `assets/data/siggraph2026-catalog.json`. The app fetches it
automatically on startup.

```bash
uv lock
uv sync --extra fast
uv run tools/refresh_siggraph.py
```

Saved-page fallback:

```bash
uv sync --extra fast
uv run tools/refresh_siggraph.py "Full Schedule - SIGGRAPH 2026 ....htm"
```

## Tests

After changing the app, run the layout and functional smoke tests:

```bash
uv sync --extra test
uv run playwright install chromium webkit
uv run tests/check_page.py
```

Use the full cross-browser run when needed:

```bash
uv run tests/check_page.py --all-browsers
```
