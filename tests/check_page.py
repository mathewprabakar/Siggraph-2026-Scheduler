#!/usr/bin/env python3
"""Layout + functional smoke tests for index.html.

Run this after any change to index.html:

    uv sync --extra test
    uv run playwright install chromium webkit   # one-time
    uv run tests/check_page.py

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

REPO_DIR = Path(__file__).parent.parent.resolve()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def log_message(self, *args) -> None:  # silence per-request logging
        pass


def _start_server() -> tuple[socketserver.TCPServer, threading.Thread, str]:
    """Serve the repo over HTTP. The app now fetches catalog/SVG files at runtime,
    so it must be served (as it is on GitHub Pages), not opened via file://."""
    handler = functools.partial(_QuietHandler, directory=str(REPO_DIR))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    index_url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    return httpd, server_thread, index_url

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


def fresh_page(context, index_url: str) -> tuple[Page, list[str]]:
    """Load index.html with a clean localStorage and a live console/page-error log."""
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(index_url)
    page.evaluate("localStorage.clear()")
    page.reload()
    # The catalog now loads asynchronously via fetch(); wait for it before checking.
    page.wait_for_function("window.App && App.catalog.length > 0", timeout=10000)
    return page, errors


def check_layout(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: layout / overflow / console errors ==")
    for name, w, h in VIEWPORTS:
        context = browser.new_context(viewport={"width": w, "height": h})
        page, errors = fresh_page(context, index_url)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        record(overflow <= 1, f"{name} ({w}x{h}) no horizontal overflow",
               f"content is {overflow}px wider than the viewport")
        record(len(errors) == 0, f"{name} ({w}x{h}) no console/page errors", "; ".join(errors))
        if w > 920:
            day_chip_rows = page.evaluate("""
                () => {
                  document.getElementById('liveChip').classList.add('show');
                  const tops = [...document.querySelectorAll('#dayChips .chip')]
                    .filter(el => getComputedStyle(el).display !== 'none')
                    .map(el => Math.round(el.getBoundingClientRect().top));
                  return new Set(tops).size;
                }
            """)
            record(day_chip_rows == 1, f"{name} ({w}x{h}) day filters stay on one line with Live",
                   f"rows={day_chip_rows}")
        day_tab_rows = page.evaluate("""
            () => {
              const tops = [...document.querySelectorAll('#dayTabs .day-tab')]
                .map(el => Math.round(el.getBoundingClientRect().top));
              return new Set(tops).size;
            }
        """)
        record(day_tab_rows == 1, f"{name} ({w}x{h}) My Day rail stays on one line",
               f"rows={day_tab_rows}")
        context.close()


def check_session_flow(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: add / remove / undo session flow ==")
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page, errors = fresh_page(context, index_url)

    browse_regs = page.evaluate("""
        () => ({
          count: document.querySelectorAll('.cat-item .reg-bubble').length,
          labels: [...document.querySelectorAll('.cat-item .reg-bubble')].slice(0, 4).map(b => b.textContent.trim()),
          titles: [...document.querySelectorAll('.cat-item .reg-bubble')].slice(0, 4).map(b => b.getAttribute('title')),
          ownLine: (() => {
            const card = document.querySelector('.cat-item:has(.reg-bubbles)');
            if (!card) return false;
            const meta = card.querySelector('.cat-meta').getBoundingClientRect();
            const regs = card.querySelector('.reg-bubbles').getBoundingClientRect();
            return regs.top > meta.bottom - 1;
          })(),
          stableColors: (() => {
            const bubbles = [...document.querySelectorAll('.cat-item .reg-bubble')].slice(0, 4);
            const light = bubbles.map(b => getComputedStyle(b).backgroundColor);
            document.documentElement.dataset.theme = 'dark';
            const dark = bubbles.map(b => getComputedStyle(b).backgroundColor);
            document.documentElement.dataset.theme = 'siggraph';
            return light.every((c, i) => c === dark[i]);
          })(),
        })
    """)
    record(browse_regs["count"] > 0, "browse session entries show registration bubbles")
    record(all(label for label in browse_regs["labels"]), "browse registration bubbles use compact labels",
           f"labels={browse_regs['labels']}")
    record(all(title for title in browse_regs["titles"]), "browse registration bubbles expose full category titles",
           f"titles={browse_regs['titles']}")
    record(browse_regs["ownLine"], "browse registration bubbles sit on their own line")
    record(browse_regs["stableColors"], "registration bubble colors stay consistent between themes")

    picked = page.evaluate("""
        () => {
          const day = App.catalog.find(c => c.day && c.s0 != null && c.e0 != null && c.reg.length).day;
          const cands = App.catalog.filter(c => c.day === day && c.s0 != null && c.e0 != null && c.reg.length).slice(0, 2);
          cands.forEach(c => App.togglePick(c));
          document.getElementById('swDay').click();
          return { pickedCount: App.picked.size, tileCount: document.querySelectorAll('.ev').length,
                   xCount: document.querySelectorAll('.ev .x').length,
                   saveNote: document.getElementById('saveNote').textContent };
        }
    """)
    record(picked["pickedCount"] == 2, "two sessions added to My Day", f"picked.size={picked['pickedCount']}")
    record(picked["tileCount"] == 2, "both sessions render as grid tiles", f"tiles={picked['tileCount']}")
    record(picked["xCount"] == 0, "grid tiles have no '.x' delete control")
    record("saved" not in picked["saveNote"].lower(), "header status does not duplicate My Day saved count",
           picked["saveNote"])

    opened = page.evaluate("""
        () => {
          const picked = [...App.picked.values()][0];
          const tile = [...document.querySelectorAll('.ev')].find(el => el.dataset.id === picked.id);
          tile.click();
          return App.pop.classList.contains('show');
        }
    """)
    record(opened, "tapping a tile opens the priority popup")

    popup = page.evaluate("""
        () => {
          const pop = App.pop;
          const picked = [...App.picked.values()][0];
          const rowText = sel => pop.querySelector(sel)?.textContent.trim() || '';
          const iconHref = sel => pop.querySelector(sel + ' use')?.getAttribute('href') || '';
          return {
            titleLink: !!pop.querySelector('.pop-title-link[href]'),
            program: rowText('.pop-program'),
            programColor: getComputedStyle(pop.querySelector('.pop-program')).color,
            dateIcon: iconHref('.pop-date'),
            date: rowText('.pop-date'),
            timeIcon: iconHref('.pop-time'),
            time: rowText('.pop-time'),
            durationIcon: iconHref('.pop-duration'),
            duration: rowText('.pop-duration'),
            regLabels: [...pop.querySelectorAll('.pop-reg .reg-bubble')].map(b => b.textContent.trim()),
            regTitles: [...pop.querySelectorAll('.pop-reg .reg-bubble')].map(b => b.getAttribute('title')),
            regAfterLocation: (() => {
              const location = pop.querySelector('.pop-row-action').getBoundingClientRect();
              const regs = pop.querySelector('.pop-reg').getBoundingClientRect();
              return regs.top > location.bottom - 1;
            })(),
            locationIcon: iconHref('.pop-row-action'),
            location: rowText('.pop-row-action'),
            removeLabel: pop.querySelector('.remove')?.getAttribute('aria-label'),
            priorityLabels: [...pop.querySelectorAll('.pri-btns button')].map(b => b.textContent.trim()),
            oldHintGone: !pop.textContent.includes('Higher priority sits'),
            oldRemoveGone: !pop.textContent.includes('Remove from my day'),
            expectedProgram: picked.program,
            expectedRoom: picked.room,
          };
        }
    """)
    record(popup["titleLink"], "session popup title links to the schedule site")
    record(popup["program"] == popup["expectedProgram"], "session popup shows the program as colored text",
           f"program={popup['program']}")
    record(popup["programColor"] != "", "session popup applies a program text color")
    record(popup["dateIcon"] == "#i-calendar", "session popup uses a calendar icon for the date",
           popup["dateIcon"])
    record(popup["date"] != "", "session popup shows the session date")
    record(popup["timeIcon"] == "#i-clock", "session popup uses a clock icon for the time",
           popup["timeIcon"])
    record(" - " in popup["time"] and ("AM" in popup["time"] or "PM" in popup["time"]),
           "session popup shows a full spaced time range", popup["time"])
    record(popup["durationIcon"] == "#i-hourglass", "session popup uses an hourglass icon for duration",
           popup["durationIcon"])
    record("min" in popup["duration"] or "hr" in popup["duration"], "session popup shows duration",
           popup["duration"])
    record(len(popup["regLabels"]) > 0, "session popup shows registration bubbles",
           f"labels={popup['regLabels']}")
    record(all(title for title in popup["regTitles"]), "session popup registration bubbles expose full titles",
           f"titles={popup['regTitles']}")
    record(popup["regAfterLocation"], "session popup registration bubbles sit after location")
    record(popup["locationIcon"] == "#i-pin", "session popup uses a pin icon for location",
           popup["locationIcon"])
    record(popup["location"] == popup["expectedRoom"], "session popup location is a quiet room action",
           f"location={popup['location']}")
    record(popup["removeLabel"] == "Remove from My Day", "session popup has an icon-only remove action")
    record(popup["priorityLabels"] == ["High", "Normal", "Low"], "session popup uses modern priority labels",
           f"labels={popup['priorityLabels']}")
    record(popup["oldHintGone"], "session popup removes the old priority explainer")
    record(popup["oldRemoveGone"], "session popup removes the old full-width remove label")

    removed = page.evaluate("""
        () => {
          App.pop.querySelector('.remove').click();
          const t = document.getElementById('toast');
          return {
            popClosed: !App.pop.classList.contains('show'),
            toastShown: t.classList.contains('show') && t.classList.contains('with-action'),
            pickedCount: App.picked.size,
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
          return { pickedCount: App.picked.size, tileCount: document.querySelectorAll('.ev').length };
        }
    """)
    record(undone["pickedCount"] == 2, "Undo restores the removed session", f"picked.size={undone['pickedCount']}")
    record(undone["tileCount"] == 2, "restored session's tile reappears in the grid", f"tiles={undone['tileCount']}")

    no_reg_popup = page.evaluate("""
        () => {
          const noReg = App.catalog.find(c => c.day && c.s0 != null && c.e0 != null && (!c.reg || !c.reg.length));
          if (!noReg) return { available: false, noBlank: true };
          App.togglePick(noReg);
          document.getElementById('swDay').click();
          const tile = [...document.querySelectorAll('.ev')].find(el => el.dataset.id === noReg.id);
          tile.click();
          return { available: true, noBlank: !App.pop.querySelector('.pop-reg') };
        }
    """)
    record(no_reg_popup["noBlank"], "session popup omits registration row when there are no categories",
           "no matching catalog session found" if not no_reg_popup["available"] else "")

    record(len(errors) == 0, "no console/page errors during the flow", "; ".join(errors))
    context.close()


def check_shared_schedule_link(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: shared schedule link ==")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page, errors = fresh_page(context, index_url)

    shared = page.evaluate("""
        () => {
          const cands = App.catalog.filter(c => c.day && c.s0 != null && c.e0 != null).slice(0, 2);
          cands.forEach(c => App.togglePick(c));
          document.getElementById('btnShare').click();
          const defaultUrl = App.shareUrl(false);
          const optIn = document.getElementById('shareIncludeSchedule');
          const optedOut = !optIn.checked && !defaultUrl.includes('#p=');
          const defaultLabel = document.querySelector('#sharePop .share-url').textContent;
          optIn.click();
          const url = App.shareUrl(true);
          const appUrl = App.shareUrl(false);
          return {
            url,
            appUrl,
            optedOut,
            defaultLabel,
            label: document.querySelector('#sharePop .share-url').textContent,
            titles: cands.map(c => c.t),
          };
        }
    """)
    record(shared["optedOut"], "Share QR defaults to app-only")
    record(shared["defaultLabel"] == "App link", "app share UI uses a friendly link label")
    record("#p=" in shared["url"], "Share QR link includes encoded picks")
    record(len(shared["url"]) < len(shared["appUrl"]) + 40, "small shared schedules use a compact sparse link")
    record(shared["label"].startswith("Schedule link"), "schedule share UI uses a friendly link label")

    shared_context = browser.new_context(viewport={"width": 390, "height": 844})
    shared_page = shared_context.new_page()
    shared_errors: list[str] = []
    shared_page.on("pageerror", lambda exc: shared_errors.append(str(exc)))
    shared_page.on("console", lambda msg: shared_errors.append(msg.text) if msg.type == "error" else None)
    shared_page.goto(shared["url"])
    shared_page.wait_for_function("window.App && App.picked.size === 2", timeout=10000)
    restored = shared_page.evaluate("""
        () => ({
          titles: [...App.picked.values()].map(e => e.t).sort(),
          url: location.href,
        })
    """)
    record(restored["titles"] == sorted(shared["titles"]), "shared link restores the selected sessions",
           f"restored={restored['titles']}")
    record(restored["url"] == shared["appUrl"], "shared link is removed from the address bar after loading",
           f"url={restored['url']}")
    record(len(errors) == 0, "no console/page errors while creating share link", "; ".join(errors))
    record(len(shared_errors) == 0, "no console/page errors while opening share link", "; ".join(shared_errors))
    shared_context.close()
    context.close()


def check_large_share_qr(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: large share QR sizing ==")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page, errors = fresh_page(context, index_url)

    qr = page.evaluate("""
        () => {
          App.catalog.filter(c => c.day && c.s0 != null && c.e0 != null).slice(0, 120)
            .forEach(c => App.togglePick(c));
          document.getElementById('btnShare').click();
          document.getElementById('shareIncludeSchedule').click();
          const canvas = document.getElementById('qrCanvas');
          const rect = canvas.getBoundingClientRect();
          return {
            label: document.querySelector('#sharePop .share-url').textContent,
            width: rect.width,
            height: rect.height,
            backingWidth: canvas.width,
            urlLength: App.shareUrl(true).length,
          };
        }
    """)
    record(qr["label"].startswith("Schedule link"), "large share UI summarizes the schedule link")
    record(qr["width"] <= 216 and qr["height"] <= 216, "large schedule QR keeps a stable display size",
           f"{qr['width']}x{qr['height']}")
    record(qr["backingWidth"] >= qr["width"], "large schedule QR keeps enough backing pixels",
           f"backing={qr['backingWidth']} display={qr['width']}")
    record(len(errors) == 0, "no console/page errors while rendering large share QR", "; ".join(errors))
    context.close()


def check_filter_chips(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: active filter chips ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context, index_url)

    chip_state = page.evaluate("""
        () => {
          const dayChip = [...document.querySelectorAll('#dayChips .chip')]
            .find(chip => chip.dataset.val && chip.textContent.includes('Thu 23'));
          dayChip.click();
          const chip = document.querySelector('#activeFilters .filter-chip');
          const shown = chip && chip.textContent.includes('Thu 23');
          chip.querySelector('button').click();
          return {
            shown,
            cleared: !document.querySelector('#activeFilters .filter-chip') &&
              dayChip.getAttribute('aria-pressed') === 'false',
          };
        }
    """)
    record(chip_state["shown"], "day filter creates a removable active chip")
    record(chip_state["cleared"], "active filter chip clears the day filter")
    record(len(errors) == 0, "no console/page errors during filter chip use", "; ".join(errors))
    context.close()


def check_clear_confirmation(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: clear confirmation dialog ==")
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page, errors = fresh_page(context, index_url)

    flow = page.evaluate("""
        () => {
          const timed = App.catalog.filter(c => c.day && c.s0 != null && c.e0 != null);
          let pair = timed.slice(0, 2);
          for (let i = 0; i < timed.length; i++) {
            const match = timed.find((c, j) => j > i && c.day === timed[i].day && timed[i].s0 < c.e0 && c.s0 < timed[i].e0);
            if (match) { pair = [timed[i], match]; break; }
          }
          pair.forEach(c => App.togglePick(c));
          document.getElementById('swDay').click();
          const conflictShown = document.getElementById('conflictStrip').classList.contains('show');
          document.getElementById('btnClear').click();
          const opened = document.getElementById('confirmOverlay').classList.contains('show');
          document.getElementById('btnCancelClear').click();
          const cancelled = App.picked.size === 2 && !document.getElementById('confirmOverlay').classList.contains('show');
          document.getElementById('btnClear').click();
          document.getElementById('btnConfirmClear').click();
          return {
            conflictShown,
            opened,
            cancelled,
            cleared: App.picked.size === 0 && !document.getElementById('confirmOverlay').classList.contains('show'),
            conflictCleared: !document.getElementById('conflictStrip').classList.contains('show'),
          };
        }
    """)
    record(flow["conflictShown"], "test schedule shows a conflict before clearing")
    record(flow["opened"], "Clear opens the app confirmation dialog")
    record(flow["cancelled"], "Cancel keeps selected sessions")
    record(flow["cleared"], "Confirm clears selected sessions")
    record(flow["conflictCleared"], "Confirm clear hides the conflict banner")
    record(len(errors) == 0, "no console/page errors during clear confirmation", "; ".join(errors))
    context.close()


def check_floorplan(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: floor plan (warmed maps) ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context, index_url)

    page.wait_for_function(
        """() => [1, 2].every(n =>
          performance.getEntriesByName(new URL(`assets/maps/lacc-level${n}.svg`, location.href).href).length > 0
        )""",
        timeout=10000,
    )
    warmed = page.evaluate("""
        () => performance.getEntriesByType('resource').map(e => e.name)
    """)
    record(any("lacc-level1.svg" in u for u in warmed),
           "Level 1 SVG is warmed before first floor-plan open", f"resources: {warmed}")
    record(any("lacc-level2.svg" in u for u in warmed),
           "Level 2 SVG is warmed before first floor-plan open", f"resources: {warmed}")

    # Open a Level-1 room; its SVG should load and the room highlight should land.
    l1 = page.evaluate("""
        async () => {
          await App.openFloorPlan('Hall K');
          const hl = document.querySelector('#fpLevel1Wrap .fp-zone-outline.hl');
          return { open: document.getElementById('fpOverlay').classList.contains('show'),
                   svgInjected: !!document.querySelector('#fpLevel1Wrap svg'),
                   highlighted: hl ? hl.dataset.zone : null };
        }
    """)
    record(l1["open"], "floor-plan modal opens")
    record(l1["svgInjected"], "Level 1 SVG is injected on open")
    record(l1["highlighted"] == "hallk", "Hall K highlights on Level 1", f"hl={l1['highlighted']}")
    record(any("lacc-level1.svg" in u for u in warmed), "Level 1 SVG resource is available from warmup/open")

    # Open a Level-2 room; Level 2's SVG should load lazily too.
    l2 = page.evaluate("""
        async () => {
          await App.openFloorPlan('411 Theatre');
          const hl = document.querySelector('#fpLevel2Wrap .fp-zone-outline.hl');
          return { svgInjected: !!document.querySelector('#fpLevel2Wrap svg'),
                   highlighted: hl ? hl.dataset.zone : null };
        }
    """)
    record(l2["svgInjected"], "Level 2 SVG is injected on open")
    record(l2["highlighted"] == "r411", "411 Theatre highlights on Level 2", f"hl={l2['highlighted']}")
    warmed = page.evaluate("""
        () => performance.getEntriesByType('resource').map(e => e.name)
    """)
    record(any("lacc-level2.svg" in u for u in warmed), "Level 2 SVG resource is available from warmup/open")

    dark_levels = page.evaluate("""
        () => {
          document.documentElement.dataset.theme = 'dark';
          const active = getComputedStyle(document.getElementById('fpLv2'));
          const inactive = getComputedStyle(document.getElementById('fpLv1'));
          return {
            activeBg: active.backgroundColor,
            inactiveBg: inactive.backgroundColor,
            activeColor: active.color,
            inactiveColor: inactive.color,
          };
        }
    """)
    record(dark_levels["activeBg"] != dark_levels["inactiveBg"],
           "dark theme preserves the active floor-plan level indicator",
           f"active={dark_levels['activeBg']} inactive={dark_levels['inactiveBg']}")

    record(len(errors) == 0, "no console/page errors during floor-plan use", "; ".join(errors))
    context.close()


def main() -> int:
    httpd, server_thread, index_url = _start_server()
    try:
        with sync_playwright() as p:
            for engine in ENGINES:
                browser = getattr(p, engine).launch()
                try:
                    check_layout(engine, browser, index_url)
                    check_session_flow(engine, browser, index_url)
                    check_shared_schedule_link(engine, browser, index_url)
                    check_large_share_qr(engine, browser, index_url)
                    check_filter_chips(engine, browser, index_url)
                    check_clear_confirmation(engine, browser, index_url)
                    check_floorplan(engine, browser, index_url)
                finally:
                    browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        server_thread.join(timeout=5)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
