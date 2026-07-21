# ---- project layout ----
# The app is served over HTTP (GitHub Pages), so it is split across files rather
# than inlined into one index.html:
#   index.html                  markup shell; references the CSS/JS below
#   styles/app.css              page styles
#   js/app.js                   application logic (ES module)
#   js/qr.js                    vendored QR-code encoder (imported by app.js)
#   assets/data/                session catalog fetched at startup
#   assets/maps/                floor-plan maps fetched on demand
#   tools/                      catalog refresh tooling
#   tests/                      Playwright smoke tests
#
# Because it uses fetch()/ES modules, it must be SERVED, not opened as a file://.
# Local dev:  python -m http.server   (then open http://localhost:8000/)

uv lock

# refresh the catalog (assets/data/siggraph2026-catalog.json) — the app fetches it automatically
uv sync --extra fast
uv run tools/refresh_siggraph.py

# saved-page fallback
uv sync --extra fast
uv run tools/refresh_siggraph.py "Full Schedule - SIGGRAPH 2026 ....htm"

# after changing index.html: layout + functional smoke tests (Chromium + WebKit)
uv sync --extra test
uv run playwright install chromium webkit
uv run tests/check_page.py

