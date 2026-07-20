uv lock

# file mode (saved page)
uv run refresh_siggraph.py "Full Schedule - SIGGRAPH 2026 ....htm"

# with lxml
uv sync --extra fast
uv run refresh_siggraph.py page.htm

# live render mode
uv sync --extra render
uv run playwright install chromium
uv run refresh_siggraph.py --render

# after changing index.html: layout + functional smoke tests (Chromium + WebKit)
uv sync --extra test
uv run playwright install chromium webkit
uv run check_page.py

