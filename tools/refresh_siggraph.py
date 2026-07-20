#!/usr/bin/env python3
"""
refresh_siggraph.py  -  Build the SIGGRAPH 2026 catalog JSON for the timetable app.

Why this exists: a browser page (especially a local file) can't fetch the schedule
site directly -- CORS blocks cross-origin reads, and the main schedule page renders
its sessions with JavaScript, so raw HTML is an empty shell. A terminal has no CORS,
and a headless browser runs the page's JS, so both walls disappear here.

Two ways to use it
------------------
1) Fully automated (default; renders the live page for you):
     python tools/refresh_siggraph.py

2) From a saved page (no browser dependency, 100% reliable):
     - Open https://s2026.conference-schedule.org/  in your browser
     - Save Page As -> "Webpage, HTML Only"
     - python tools/refresh_siggraph.py "Full Schedule - SIGGRAPH 2026 ....htm"

Either way it writes  assets/data/siggraph2026-catalog.json , which the app fetches at startup
(it's the single source of truth for the catalog). Commit the regenerated JSON and
the app picks it up on next load.
Requires:  pip install beautifulsoup4
"""
import sys, json, argparse, re
from datetime import datetime, timedelta, timezone
from pathlib import Path

PDT = timezone(timedelta(hours=-7))  # SIGGRAPH week is July -> PDT is a fixed UTC-7
DEFAULT_URL = 'https://s2026.conference-schedule.org/'
DEFAULT_OUTPUT = Path('assets/data/siggraph2026-catalog.json')

# Map the per-item type labels to the site's Program-filter names (plural forms)
PLURAL = {
    'Course': 'Courses', 'Technical Paper': 'Technical Papers',
    'Industry Session': 'Industry Sessions', 'Poster': 'Posters',
    'Production Session': 'Production Sessions', 'Technical Workshop': 'Technical Workshops',
    'Stage Session': 'Stage Sessions', "Educator's Day Session": "Educator's Day Sessions",
    'Panel': 'Panels', 'Keynote Speaker': 'Keynote Speakers', 'Art Paper': 'Art Papers',
}


def _soup(html):
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, 'lxml')        # faster if available
    except Exception:
        return BeautifulSoup(html, 'html.parser')  # stdlib fallback, no extra deps


def _fmt(mins):
    h, m = divmod(mins, 60)
    ap = 'am' if h < 12 else 'pm'
    hh = h % 12 or 12
    return f"{hh}:{m:02d}{ap}"


def _pdt(utc_str):
    """ISO 'Z' timestamp -> (YYYY-MM-DD local date, minutes-since-midnight local)."""
    dt = datetime.fromisoformat(utc_str.replace('Z', '+00:00')).astimezone(PDT)
    return dt.date().isoformat(), dt.hour * 60 + dt.minute


def _tags(item, cls):
    grp = item.select_one('.' + cls)
    if not grp:
        return []
    out = []
    for d in grp.select('.program-track'):
        v = d.get_text(strip=True)
        if v and v not in out:
            out.append(v)
    return out


def parse_html(html):
    soup = _soup(html)
    catalog = []
    for it in soup.select('.agenda-item'):
        title_el = it.select_one('.presentation-title')
        if not title_el:
            continue
        t = title_el.get_text(' ', strip=True)
        if not t:
            continue
        st = it.select_one('.dateTimeInfo.start-time')
        su = st.get('utc_time') if st else None
        if not su:
            continue
        day, smin = _pdt(su)
        en = it.select_one('.dateTimeInfo.end-time')
        eu = en.get('utc_time') if en else None
        if eu:
            eday, emin = _pdt(eu)
            if eday > day:
                emin += 1440
        else:
            emin = smin + 30

        etypes = []
        for e in it.select('.small-etypes .event-type-name'):
            v = e.get_text(strip=True)
            if v and v not in etypes:
                etypes.append(v)
        if not etypes:
            pt = it.select_one('.presentation-type')
            etypes = [pt.get_text(' ', strip=True)] if pt else ['Session']
        programs = [PLURAL.get(x, x) for x in etypes]

        loc = it.select_one('.presentation-location')
        link = title_el.select_one('a')
        url = link.get('href', '').strip() if link else ''
        if not url and link:
            # Session-group headers have no href, just a JS toggle like
            # onclick="full_program_toggle_session_contents('sess172')" --
            # rebuild the site's own session-page link from that id.
            m = re.search(r"toggle_session_contents\('(sess\d+)'\)", link.get('onclick', ''))
            if m:
                url = f"https://s2026.conference-schedule.org/?post_type=page&p=16&sess={m.group(1)}"
        s = _fmt(smin)
        uid = f"{day}|{s}|{t}".lower().replace('  ', ' ')[:140]
        catalog.append({
            "id": uid, "t": t, "program": programs[0], "programs": programs,
            "day": day, "s": s, "e": _fmt(min(emin, 1439)),
            "room": loc.get_text(' ', strip=True) if loc else "",
            "url": url,
            "ia": _tags(it, 'interest-area'),
            "kw": _tags(it, 'keyword'),
            "reg": _tags(it, 'registration-category'),
        })
    catalog.sort(key=lambda c: (c['day'], c['s'], c['t']))
    return catalog


def render_live(url):
    """Load the live page in a headless browser so its JS builds the session list."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=90000)
            page.wait_for_selector('.agenda-item', timeout=90000)
            return page.content()
        finally:
            browser.close()


def main():
    ap = argparse.ArgumentParser(description="Build siggraph2026-catalog.json for the timetable app.")
    ap.add_argument('input', nargs='?', help="a saved schedule .htm/.html file")
    ap.add_argument('--render', metavar='URL', nargs='?',
                    const=DEFAULT_URL,
                    help="fetch & render a live schedule page via Playwright")
    ap.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()

    if args.input and args.render:
        ap.error("choose either a saved HTML input or --render, not both")

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            ap.error(f"saved HTML file not found: {input_path}")
        html = input_path.read_text(encoding='utf-8', errors='replace')
    else:
        url = args.render or DEFAULT_URL
        print(f"Rendering {url} in a headless browser ...", file=sys.stderr)
        html = render_live(url)

    catalog = parse_html(html)
    if len(catalog) < 50:
        print(f"WARNING: only {len(catalog)} sessions parsed. If you fetched the live page "
              f"without --render, it was probably an un-rendered shell.", file=sys.stderr)

    out = {"v": 2, "source": "SIGGRAPH 2026", "count": len(catalog),
           "generated": datetime.now(timezone.utc).isoformat(), "catalog": catalog}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    by_day = {}
    for c in catalog:
        by_day[c['day']] = by_day.get(c['day'], 0) + 1
    print(f"Wrote {len(catalog)} sessions to {output}")
    print("By day:", {k: by_day[k] for k in sorted(by_day)})
    print("Commit the updated JSON; the app fetches it automatically on next load.")


if __name__ == '__main__':
    main()
