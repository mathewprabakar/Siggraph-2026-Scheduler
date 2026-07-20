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

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

INDEX_URL = (Path(__file__).parent / "index.html").resolve().as_uri()

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


def main() -> None:
    with sync_playwright() as p:
        for engine in ENGINES:
            browser = getattr(p, engine).launch()
            try:
                check_layout(engine, browser)
                check_session_flow(engine, browser)
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
