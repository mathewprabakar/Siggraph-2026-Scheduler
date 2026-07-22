#!/usr/bin/env python3
"""Layout + functional smoke tests for index.html.

Run this after any change to index.html:

    uv sync --extra test
    uv run playwright install chromium webkit   # one-time
    uv run tests/check_page.py
    uv run tests/check_page.py --all-browsers   # full cross-browser run

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
import argparse
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
DEFAULT_ENGINES = ["chromium"]
ALL_ENGINES = ["chromium", "webkit"]

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
        hour_label_wraps = page.evaluate("""
            () => [...document.querySelectorAll('.hour .lbl')]
              .some(el => el.getBoundingClientRect().height > 16)
        """)
        record(not hour_label_wraps, f"{name} ({w}x{h}) My Day hour labels stay on one line")
        hourline_count = page.evaluate("document.querySelectorAll('.lane .hourline').length")
        record(hourline_count > 0, f"{name} ({w}x{h}) My Day grid shows hour-aligned guide lines",
               f"hour lines={hourline_count}")
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
          titleIconInline: [...document.querySelectorAll('.cat-title a')].every(link => {
            const tail = link.querySelector('.title-link-tail');
            return !!tail && !!tail.querySelector('.ext-arrow') && getComputedStyle(tail).whiteSpace === 'nowrap';
          }),
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
    record(browse_regs["titleIconInline"], "browse title external-link icons stay with title text")
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
            titleIconInline: (() => {
              const tail = pop.querySelector('.pop-title-link .title-link-tail');
              return !!tail && !!tail.querySelector('.ico') && getComputedStyle(tail).whiteSpace === 'nowrap';
            })(),
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
    record(popup["titleIconInline"], "session popup external-link icon stays with title text")
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

    offsite_location = page.evaluate("""
        () => {
          const offsite = App.catalog.find(c =>
            c.day && c.s0 != null && c.e0 != null &&
            /jw marriott|exchange la|hotel per la|prank bar/i.test(c.room || '')
          );
          if (!offsite) return { available: false, shown: true, link: true };
          App.picked.clear();
          App.togglePick(offsite);
          document.getElementById('swDay').click();
          const tile = [...document.querySelectorAll('.ev')].find(el => el.dataset.id === offsite.id);
          tile.click();
          const floorBtn = App.pop.querySelector('#popFloorBtn');
          const floorRect = floorBtn.getBoundingClientRect();
          floorBtn.click();
          const mapPop = document.getElementById('mapPop');
          const mapRect = mapPop.getBoundingClientRect();
          return {
            available: true,
            shown: mapPop.classList.contains('show'),
            link: !!mapPop.querySelector('a[href*="google.com/maps"]'),
            positionedNearButton: Math.abs(mapRect.left - floorRect.left) < 24 &&
              (Math.abs(mapRect.top - floorRect.bottom - 6) < 2 ||
               Math.abs(mapRect.bottom - floorRect.top + 6) < 2),
          };
        }
    """)
    record(offsite_location["shown"] and offsite_location["link"] and offsite_location["positionedNearButton"],
           "session popup opens external location map links from My Day",
           "no off-site catalog session found" if not offsite_location["available"] else offsite_location)

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
          const token = new URLSearchParams(url.split('#')[1]).get('p');
          const bytes = Uint8Array.from(atob(token.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((token.length + 3) % 4)), c => c.charCodeAt(0));
          return {
            url,
            appUrl,
            optedOut,
            defaultLabel,
            label: document.querySelector('#sharePop .share-url').textContent,
            bytes: [...bytes],
            titles: cands.map(c => c.t),
          };
        }
    """)
    record(shared["optedOut"], "Share QR defaults to app-only")
    record(shared["defaultLabel"] == "App link", "app share UI uses a friendly link label")
    record("#p=" in shared["url"], "Share QR link includes encoded picks")
    record(shared["bytes"][:3] == [83, 52, 4], "shared schedule uses compact stable-ID payloads")
    record((shared["bytes"][3] | (shared["bytes"][4] << 8)) == 2 and len(shared["bytes"]) == 11,
           "small shared schedule stores normal picks in 3 bytes each",
           f"bytes={len(shared['bytes'])}")
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

    repeated = page.evaluate("""
        () => {
          App.picked.clear();
          const groups = new Map();
          App.catalog.filter(c => c.sid).forEach(c => groups.set(c.sid, [...(groups.get(c.sid) || []), c]));
          const cands = [...groups.values()].find(items => items.length > 1).slice(0, 2);
          cands.forEach(c => App.togglePick(c));
          const url = App.shareUrl(true);
          const token = new URLSearchParams(url.split('#')[1]).get('p');
          const bytes = Uint8Array.from(atob(token.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((token.length + 3) % 4)), c => c.charCodeAt(0));
          return { url, ids: cands.map(c => c.id).sort(), bytes: [...bytes] };
        }
    """)
    record(len(repeated["bytes"]) == 11, "repeated sid picks stay compact with day/start disambiguation",
           f"bytes={len(repeated['bytes'])}")
    repeated_context = browser.new_context(viewport={"width": 390, "height": 844})
    repeated_page = repeated_context.new_page()
    repeated_page.goto(repeated["url"])
    repeated_page.wait_for_function("window.App && App.picked.size === 2", timeout=10000)
    repeated_restored = repeated_page.evaluate("() => [...App.picked.values()].map(e => e.id).sort()")
    record(repeated_restored == repeated["ids"], "shared link restores distinct repeated sid occurrences",
           f"restored={repeated_restored}")
    repeated_context.close()

    fallback = page.evaluate("""
        () => {
          App.picked.clear();
          const cand = App.catalog.find(c => !c.sid && c.day && c.s0 != null && c.e0 != null);
          App.togglePick(cand);
          const url = App.shareUrl(true);
          const token = new URLSearchParams(url.split('#')[1]).get('p');
          const bytes = Uint8Array.from(atob(token.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((token.length + 3) % 4)), c => c.charCodeAt(0));
          const packed = bytes[5] | (bytes[6] << 8) | (bytes[7] << 16);
          return { url, id: cand.id, title: cand.t, sidNum: packed & 1023, fallbackLen: bytes[8], bytes: bytes.length };
        }
    """)
    record(fallback["sidNum"] == 1023 and fallback["fallbackLen"] > 0,
           "no-sid shared pick uses compact escape row", f"len={fallback['fallbackLen']}")
    fallback_context = browser.new_context(viewport={"width": 390, "height": 844})
    fallback_page = fallback_context.new_page()
    fallback_page.goto(fallback["url"])
    fallback_page.wait_for_function("window.App && App.picked.size === 1", timeout=10000)
    fallback_restored = fallback_page.evaluate("() => [...App.picked.values()][0].id")
    record(fallback_restored == fallback["id"], "shared link restores no-sid fallback picks",
           f"restored={fallback_restored}")
    fallback_context.close()

    record(len(errors) == 0, "no console/page errors while creating share link", "; ".join(errors))
    record(len(shared_errors) == 0, "no console/page errors while opening share link", "; ".join(shared_errors))
    shared_context.close()
    context.close()


def check_mobile_share_button(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: mobile Share button ==")
    context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True)
    page, errors = fresh_page(context, index_url)

    hit = page.evaluate("""
        () => {
          const btn = document.getElementById('btnShare');
          const icon = btn.querySelector('svg');
          const r = icon.getBoundingClientRect();
          const x = r.left + r.width / 2;
          const y = r.top + r.height / 2;
          const target = document.elementFromPoint(x, y);
          return {
            x,
            y,
            targetTag: target?.tagName || '',
            targetId: target?.id || '',
            targetInsideButton: !!target?.closest?.('#btnShare'),
          };
        }
    """)
    page.touchscreen.tap(hit["x"], hit["y"])
    page.wait_for_timeout(50)
    opened = page.evaluate("""
        () => ({
          shown: document.getElementById('sharePop').classList.contains('show'),
          label: document.querySelector('#sharePop .share-url')?.textContent.trim() || '',
          centered: (() => {
            const pop = document.getElementById('sharePop').getBoundingClientRect();
            const qr = document.querySelector('#sharePop .qr-box').getBoundingClientRect();
            return Math.abs((qr.left - pop.left) - (pop.right - qr.right)) < 1 &&
              (qr.left - pop.left) >= 13 && (pop.right - qr.right) >= 13;
          })(),
        })
    """)
    record(hit["targetInsideButton"], "mobile Share icon tap targets a descendant of the Share button",
           f"target={hit['targetTag']}#{hit['targetId']}")
    record(opened["shown"], "mobile Share icon tap opens and keeps the popover open")
    record(opened["label"] == "App link", "mobile Share popover renders the app QR immediately",
           opened["label"])
    record(opened["centered"], "mobile Share app QR is centered with balanced margins")
    record(len(errors) == 0, "no console/page errors during mobile Share tap", "; ".join(errors))
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
          const fallback = document.querySelector('.qr-fallback');
          const rect = (canvas || fallback).getBoundingClientRect();
          const pop = document.getElementById('sharePop').getBoundingClientRect();
          const qrBox = document.querySelector('#sharePop .qr-box').getBoundingClientRect();
          return {
            label: document.querySelector('#sharePop .share-url').textContent,
            fallback: fallback?.textContent.trim() || '',
            width: rect.width,
            height: rect.height,
            backingWidth: canvas?.width || 0,
            urlLength: App.shareUrl(true).length,
            centered: Math.abs((qrBox.left - pop.left) - (pop.right - qrBox.right)) < 1 &&
              (qrBox.left - pop.left) >= 13 && (pop.right - qrBox.right) >= 13,
          };
        }
    """)
    record(qr["label"].startswith("Schedule link"), "large share UI summarizes the schedule link")
    record(qr["width"] <= 216 and qr["height"] <= 216, "large schedule share preview keeps a stable display size",
           f"{qr['width']}x{qr['height']}")
    record(not qr["fallback"] and qr["backingWidth"] >= qr["width"], "large schedule QR renders with compact stable payload",
           f"fallback={qr['fallback']} backing={qr['backingWidth']} display={qr['width']}")
    record(qr["centered"], "large schedule QR is centered with balanced margins")
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


def check_registration_badge_toggle(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: registration badge display toggle ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context, index_url)

    hidden = page.evaluate("""
        () => {
          const toggle = document.getElementById('regBadgeToggle');
          const before = {
            checked: toggle?.checked,
            state: document.querySelector('.display-toggle .toggle-state')?.textContent.trim(),
            browse: document.querySelectorAll('.cat-item .reg-bubble').length,
          };
          toggle.click();
          const picked = App.catalog.find(c => c.day && c.s0 != null && c.e0 != null && c.reg.length);
          App.togglePick(picked);
          document.getElementById('swDay').click();
          document.querySelector('.ev').click();
          return {
            before,
            checked: toggle.checked,
            state: document.querySelector('.display-toggle .toggle-state')?.textContent.trim(),
            stored: localStorage.getItem('s2026-show-reg-badges'),
            browse: document.querySelectorAll('.cat-item .reg-bubble').length,
            popup: document.querySelectorAll('#pop .reg-bubble').length,
          };
        }
    """)
    record(hidden["before"]["checked"] is True and hidden["before"]["state"] == "Show badges",
           "registration badges are shown by default")
    record(hidden["before"]["browse"] > 0, "browse shows registration badges before toggle")
    record(hidden["checked"] is False and hidden["state"] == "Show badges" and hidden["stored"] == "0",
           "registration badge toggle saves the hidden preference")
    record(hidden["browse"] == 0, "registration badge toggle hides Browse badges",
           f"badges={hidden['browse']}")
    record(hidden["popup"] == 0, "registration badge toggle hides popup badges",
           f"badges={hidden['popup']}")

    page.reload()
    page.wait_for_function("window.App && App.catalog.length > 0", timeout=10000)
    persisted = page.evaluate("""
        () => ({
          checked: document.getElementById('regBadgeToggle').checked,
          state: document.querySelector('.display-toggle .toggle-state')?.textContent.trim(),
          stored: localStorage.getItem('s2026-show-reg-badges'),
          browse: document.querySelectorAll('.cat-item .reg-bubble').length,
        })
    """)
    record(persisted["checked"] is False and persisted["state"] == "Show badges" and persisted["stored"] == "0",
           "registration badge hidden preference persists after reload")
    record(persisted["browse"] == 0, "reloaded Browse keeps registration badges hidden",
           f"badges={persisted['browse']}")
    record(len(errors) == 0, "no console/page errors during registration badge toggle", "; ".join(errors))
    context.close()


def check_browse_scroll_stability(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: Browse scroll stability ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context, index_url)

    setup = page.evaluate("""
        () => {
          const catalog = document.getElementById('catalog');
          const groups = new Map();
          App.catalog.filter(c => c.day && c.s0 != null && c.e0 != null).forEach(c => {
            if (!groups.has(c.day)) groups.set(c.day, []);
            groups.get(c.day).push(c);
          });
          const daySessions = [...groups.values()].sort((a, b) => {
            const ap = new Set(a.map(c => c.program)).size;
            const bp = new Set(b.map(c => c.program)).size;
            return bp - ap;
          })[0];
          daySessions.forEach(c => {
            if (!App.picked.has(c.id)) App.togglePick(c);
          });
          catalog.scrollTop = Math.floor(catalog.scrollHeight * 0.42);
          const browseBox = catalog.getBoundingClientRect();
          const items = [...document.querySelectorAll('.cat-item')];
          const visible = items.filter(el => {
            const r = el.getBoundingClientRect();
            return r.bottom > browseBox.top && r.top < Math.min(browseBox.bottom, window.innerHeight);
          });
          const target = visible[Math.floor(visible.length / 2)];
          const index = items.indexOf(target);
          const rect = target.getBoundingClientRect();
          window.__browseStabilityTarget = target;
          return {
            index,
            legendPrograms: new Set(daySessions.map(c => c.program)).size,
            baseline: {
              windowScroll: window.scrollY,
              scrollTop: catalog.scrollTop,
              clientHeight: catalog.clientHeight,
              panelHeight: document.querySelector('#browseCol .panel').getBoundingClientRect().height,
              top: rect.top,
              height: rect.height,
              nodeStable: true,
            },
          };
        }
    """)

    snapshots = [setup["baseline"]]
    for _ in range(6):
        page.locator(".cat-item").nth(setup["index"]).locator(".add-btn").click()
        page.wait_for_timeout(120)
        snapshots.append(page.evaluate("""
            (index) => {
              const catalog = document.getElementById('catalog');
              const target = document.querySelectorAll('.cat-item')[index];
              const rect = target.getBoundingClientRect();
              return {
                windowScroll: window.scrollY,
                scrollTop: catalog.scrollTop,
                clientHeight: catalog.clientHeight,
              panelHeight: document.querySelector('#browseCol .panel').getBoundingClientRect().height,
              top: rect.top,
              height: rect.height,
              nodeStable: target === window.__browseStabilityTarget,
            };
          }
        """, setup["index"]))

    base = snapshots[0]
    max_window_delta = max(abs(s["windowScroll"] - base["windowScroll"]) for s in snapshots)
    max_scroll_delta = max(abs(s["scrollTop"] - base["scrollTop"]) for s in snapshots)
    max_top_delta = max(abs(s["top"] - base["top"]) for s in snapshots)
    max_height_delta = max(abs(s["height"] - base["height"]) for s in snapshots)
    nodes_stable = all(s["nodeStable"] for s in snapshots)

    record(nodes_stable, "Browse add/remove updates the existing card instead of rebuilding it")
    record(max_window_delta < 1, "page scroll stays stable during repeated Browse add/remove",
           f"max delta={max_window_delta}")
    record(max_scroll_delta < 1, "Browse scroll offset stays stable during repeated add/remove",
           f"max delta={max_scroll_delta}")
    record(max_top_delta < 1, "visible Browse card position stays stable during repeated add/remove",
           f"max delta={max_top_delta:.1f}")
    record(max_height_delta < 1, "visible Browse card height stays stable during repeated add/remove",
           f"max delta={max_height_delta:.1f}")
    record(setup["legendPrograms"] > 1, "Browse stability check exercises a multi-program legend",
           f"programs={setup['legendPrograms']}")
    record(len(errors) == 0, "no console/page errors during Browse scroll stability check", "; ".join(errors))
    context.close()


def check_theme_switch_preserves_scroll(engine: str, browser, index_url: str) -> None:
    print(f"\n== {engine}: theme switch preserves scroll state ==")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page, errors = fresh_page(context, index_url)

    theme_state = page.evaluate("""
        () => {
          App.catalog.filter(c => c.day && c.s0 != null && c.e0 != null).slice(0, 12)
            .forEach(c => App.togglePick(c));
          const catalog = document.getElementById('catalog');
          const grid = document.querySelector('.grid-scroll');
          catalog.scrollTop = 260;
          grid.scrollTop = 320;
          const firstCard = document.querySelector('.cat-item');
          const firstTile = document.querySelector('.ev');
          const swatches = [...document.querySelectorAll('.cat-item .swatch[data-program-color]')];
          const before = {
            catalogScroll: catalog.scrollTop,
            gridScroll: grid.scrollTop,
            cardColors: swatches.map(el => getComputedStyle(el).backgroundColor),
            tileColor: getComputedStyle(firstTile).backgroundColor,
          };
          const sel = document.getElementById('themeSelect');
          sel.value = 'light';
          sel.dispatchEvent(new Event('change', { bubbles: true }));
          const swatchesAfter = [...document.querySelectorAll('.cat-item .swatch[data-program-color]')];
          return {
            before,
            after: {
              catalogScroll: catalog.scrollTop,
              gridScroll: grid.scrollTop,
              cardSame: firstCard === document.querySelector('.cat-item'),
              tileSame: firstTile === document.querySelector('.ev'),
              cardColors: swatchesAfter.map(el => getComputedStyle(el).backgroundColor),
              cardNodesSame: swatches.every((el, i) => el === swatchesAfter[i]),
              tileColor: getComputedStyle(firstTile).backgroundColor,
            },
          };
        }
    """)
    record(theme_state["after"]["catalogScroll"] == theme_state["before"]["catalogScroll"],
           "theme switch keeps Browse scroll position",
           f"before={theme_state['before']['catalogScroll']} after={theme_state['after']['catalogScroll']}")
    record(theme_state["after"]["gridScroll"] == theme_state["before"]["gridScroll"],
           "theme switch keeps My Day scroll position",
           f"before={theme_state['before']['gridScroll']} after={theme_state['after']['gridScroll']}")
    record(theme_state["after"]["cardSame"], "theme switch does not rebuild Browse cards")
    record(theme_state["after"]["tileSame"], "theme switch does not rebuild My Day tiles")
    record(theme_state["after"]["cardNodesSame"], "theme switch keeps Browse swatch nodes")
    card_recolored = any(
        after != before
        for before, after in zip(theme_state["before"]["cardColors"], theme_state["after"]["cardColors"])
    )
    record(card_recolored,
           "theme switch recolors Browse program swatches in place")
    record(theme_state["after"]["tileColor"] != theme_state["before"]["tileColor"],
           "theme switch recolors My Day tiles in place")
    record(len(errors) == 0, "no console/page errors during theme switching", "; ".join(errors))
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
          const conflictsHidden = !document.getElementById('conflictStrip').classList.contains('show')
            && !document.querySelector('.day-tab.hasconflict')
            && !document.querySelector('.ev.conflict');
          document.getElementById('btnClear').click();
          const opened = document.getElementById('confirmOverlay').classList.contains('show');
          document.getElementById('btnCancelClear').click();
          const cancelled = App.picked.size === 2 && !document.getElementById('confirmOverlay').classList.contains('show');
          document.getElementById('btnClear').click();
          document.getElementById('btnConfirmClear').click();
          return {
            conflictsHidden,
            opened,
            cancelled,
            cleared: App.picked.size === 0 && !document.getElementById('confirmOverlay').classList.contains('show'),
          };
        }
    """)
    record(flow["conflictsHidden"], "overlapping sessions do not show conflict warnings")
    record(flow["opened"], "Clear opens the app confirmation dialog")
    record(flow["cancelled"], "Cancel keeps selected sessions")
    record(flow["cleared"], "Confirm clears selected sessions")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SIGGRAPH scheduler smoke tests.")
    parser.add_argument(
        "--all-browsers",
        action="store_true",
        help="run the suite in Chromium and WebKit; default is Chromium only",
    )
    parser.add_argument(
        "--engine",
        choices=ALL_ENGINES,
        help="run the suite in one browser engine",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engines = ALL_ENGINES if args.all_browsers else DEFAULT_ENGINES
    if args.engine:
        engines = [args.engine]

    httpd, server_thread, index_url = _start_server()
    try:
        with sync_playwright() as p:
            for engine in engines:
                browser = getattr(p, engine).launch()
                try:
                    check_layout(engine, browser, index_url)
                    check_session_flow(engine, browser, index_url)
                    check_shared_schedule_link(engine, browser, index_url)
                    check_mobile_share_button(engine, browser, index_url)
                    check_large_share_qr(engine, browser, index_url)
                    check_filter_chips(engine, browser, index_url)
                    check_registration_badge_toggle(engine, browser, index_url)
                    check_browse_scroll_stability(engine, browser, index_url)
                    check_theme_switch_preserves_scroll(engine, browser, index_url)
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
