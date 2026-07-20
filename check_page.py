#!/usr/bin/env python3
"""Layout + functional smoke tests for index.html.

Run this after any change to index.html:

    uv sync --extra test
    uv run playwright install chromium webkit   # one-time
    uv run check_page.py

Checks, on both Chromium and WebKit (WebKit is Safari's engine — the closest
automated proxy to real iOS behavior):
  - no horizontal overflow at phone / tablet / laptop / desktop viewport widths
  - no JS console or page errors on load
  - the "My Day" add / remove / undo session flow works end to end
  - grid tiles expose no click-to-remove "x" (removal is popup-only)
  - the removal toast shows an Undo action and stays on a single line

Exits 0 if everything passes, 1 otherwise (with a summary of what failed).
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO_DIR = Path(__file__).parent.resolve()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence per-request logging
        pass


def _start_server() -> tuple[socketserver.TCPServer, int]:
    """Serve the repo over HTTP. The app now fetches catalog/SVG files at runtime,
    so it must be served (as it is on GitHub Pages), not opened via file://."""
    handler = functools.partial(_QuietHandler, directory=str(REPO_DIR))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


_httpd, _port = _start_server()
INDEX_URL = f"http://127.0.0.1:{_port}/index.html"

VIEWPORTS = [
    ("phone-android", 360, 800),
    ("phone-iphone", 390, 844),
    ("tablet-portrait", 768, 1024),
    ("tablet-landscape", 1024, 768),
    ("laptop", 1280, 800),
    ("desktop-large", 1920, 1080),
]
ENGINES = ["chromium", "webkit"]

failures: list[str] = []


def record(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{label}: {detail}" if detail else label)


def fresh_page(context) -> tuple[Page, list[str]]:
    """Load index.html with a clean localStorage and a live console/page-error log."""
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(INDEX_URL)
    page.evaluate("localStorage.clear()")
    page.reload()
    # The catalog now loads asynchronously via fetch(); wait for it before checking.
    page.wait_for_function("typeof catalog !== 'undefined' && catalog.length > 0", timeout=10000)
    return page, errors


def check_layout(engine: str, browser) -> None:
    print(f"\n== {engine}: layout / overflow / console errors ==")
    for name, w, h in VIEWPORTS:
        context = browser.new_context(viewport={"width": w, "height": h})
        page, errors = fresh_page(context)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        record(overflow <= 1, f"{name} ({w}x{h}) no horizontal overflow",
               f"content is {overflow}px wider than the viewport")
        record(len(errors) == 0, f"{name} ({w}x{h}) no console/page errors", "; ".join(errors))
        context.close()


def check_session_flow(engine: str, browser) -> None:
    print(f"\n== {engine}: add / remove / undo session flow ==")
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page, errors = fresh_page(context)

    picked = page.evaluate("""
        () => {
          const day = catalog.find(c => c.day && c.s0 != null && c.e0 != null).day;
          const cands = catalog.filter(c => c.day === day && c.s0 != null && c.e0 != null).slice(0, 2);
          cands.forEach(c => togglePick(c));
          document.getElementById('swDay').click();
          return { pickedCount: picked.size, tileCount: document.querySelectorAll('.ev').length,
                   xCount: document.querySelectorAll('.ev .x').length };
        }
    """)
    record(picked["pickedCount"] == 2, "two sessions added to My Day", f"picked.size={picked['pickedCount']}")
    record(picked["tileCount"] == 2, "both sessions render as grid tiles", f"tiles={picked['tileCount']}")
    record(picked["xCount"] == 0, "grid tiles have no '.x' delete control")

    opened = page.evaluate("""
        () => { document.querySelector('.ev').click(); return pop.classList.contains('show'); }
    """)
    record(opened, "tapping a tile opens the priority popup")

    removed = page.evaluate("""
        () => {
          pop.querySelector('.remove').click();
          const t = document.getElementById('toast');
          return {
            popClosed: !pop.classList.contains('show'),
            toastShown: t.classList.contains('show') && t.classList.contains('with-action'),
            pickedCount: picked.size,
          };
        }
    """)
    record(removed["popClosed"], "popup closes immediately on remove")
    record(removed["toastShown"], "bottom toast shows with an Undo action")
    record(removed["pickedCount"] == 1, "session removed from picked", f"picked.size={removed['pickedCount']}")

    toast_metrics = page.evaluate("""
        () => {
          const t = document.getElementById('toast');
          const span = t.querySelector('span');
          return { toastWidth: t.getBoundingClientRect().width, spanHeight: span.getBoundingClientRect().height };
        }
    """)
    record(toast_metrics["spanHeight"] < 24, "toast text stays on a single line",
           f"message span height={toast_metrics['spanHeight']:.1f}px (>=24px implies wrapping)")
    record(toast_metrics["toastWidth"] <= 390 - 40, "toast fits within the viewport width",
           f"toast width={toast_metrics['toastWidth']:.1f}px")

    undone = page.evaluate("""
        () => {
          document.querySelector('#toast .toast-undo').click();
          return { pickedCount: picked.size, tileCount: document.querySelectorAll('.ev').length };
        }
    """)
    record(undone["pickedCount"] == 2, "Undo restores the removed session", f"picked.size={undone['pickedCount']}")
    record(undone["tileCount"] == 2, "restored session's tile reappears in the grid", f"tiles={undone['tileCount']}")

    record(len(errors) == 0, "no console/page errors during the flow", "; ".join(errors))
    context.close()


def check_floorplan(engine: str, browser) -> None:
    print(f"\n== {engine}: floor plan (lazy-loaded maps) ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context)

    svg_reqs: list[str] = []
    page.on("request", lambda r: svg_reqs.append(r.url) if r.url.endswith(".svg") else None)

    # The two ~250KB maps must NOT load until the user opens the floor plan.
    record(not any("lacc-level" in u for u in svg_reqs),
           "floor-plan SVGs are not fetched on initial load", f"requested: {svg_reqs}")

    # Open a Level-1 room; its SVG should load and the room highlight should land.
    l1 = page.evaluate("""
        async () => {
          await openFloorPlan('Hall K');
          const hl = document.querySelector('#fpLevel1Wrap .fp-zone-outline.hl');
          return { open: document.getElementById('fpOverlay').classList.contains('show'),
                   svgInjected: !!document.querySelector('#fpLevel1Wrap svg'),
                   highlighted: hl ? hl.dataset.zone : null };
        }
    """)
    record(l1["open"], "floor-plan modal opens")
    record(l1["svgInjected"], "Level 1 SVG is injected on open")
    record(l1["highlighted"] == "hallk", "Hall K highlights on Level 1", f"hl={l1['highlighted']}")
    record(any("lacc-level1.svg" in u for u in svg_reqs), "Level 1 SVG fetched on open")

    # Open a Level-2 room; Level 2's SVG should load lazily too.
    l2 = page.evaluate("""
        async () => {
          await openFloorPlan('411 Theatre');
          const hl = document.querySelector('#fpLevel2Wrap .fp-zone-outline.hl');
          return { svgInjected: !!document.querySelector('#fpLevel2Wrap svg'),
                   highlighted: hl ? hl.dataset.zone : null };
        }
    """)
    record(l2["svgInjected"], "Level 2 SVG is injected on open")
    record(l2["highlighted"] == "r411", "411 Theatre highlights on Level 2", f"hl={l2['highlighted']}")
    record(any("lacc-level2.svg" in u for u in svg_reqs), "Level 2 SVG fetched on open")

    record(len(errors) == 0, "no console/page errors during floor-plan use", "; ".join(errors))
    context.close()


def main() -> None:
    with sync_playwright() as p:
        for engine in ENGINES:
            browser = getattr(p, engine).launch()
            try:
                check_layout(engine, browser)
                check_session_flow(engine, browser)
                check_floorplan(engine, browser)
            finally:
                browser.close()

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
