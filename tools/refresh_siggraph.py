#!/usr/bin/env python3
"""
refresh_siggraph.py  -  Build the SIGGRAPH 2026 catalog JSON for the timetable app.

Why this exists: a browser page (especially a local file) can't fetch the schedule
site directly -- CORS blocks cross-origin reads. A terminal has no CORS wall, and
the schedule page advertises the per-day HTML snippets it loads, so the default
path fetches those snippets directly.

Two ways to use it
------------------
1) Fully automated (default; fetches the live page's per-day schedule snippets):
     python tools/refresh_siggraph.py

2) From a saved page:
     - Open https://s2026.conference-schedule.org/  in your browser
     - Save Page As -> "Webpage, HTML Only"
     - python tools/refresh_siggraph.py "Full Schedule - SIGGRAPH 2026 ....htm"

Either way it writes  assets/data/siggraph2026-catalog.json , which the app fetches at startup
(it's the single source of truth for the catalog). Commit the regenerated JSON and
the app picks it up on next load.
Requires:  pip install beautifulsoup4
"""
import sys, json, argparse, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

PDT = timezone(timedelta(hours=-7))  # SIGGRAPH week is July -> PDT is a fixed UTC-7
DEFAULT_URL = 'https://s2026.conference-schedule.org/'
DEFAULT_OUTPUT = Path('assets/data/siggraph2026-catalog.json')
FETCH_ATTEMPTS = 4
FETCH_TIMEOUT = 45

# Map the per-item type labels to the site's Program-filter names (plural forms)
PLURAL = {
    'Course': 'Courses', 'Technical Paper': 'Technical Papers',
    'Industry Session': 'Industry Sessions', 'Poster': 'Posters',
    'Production Session': 'Production Sessions', 'Technical Workshop': 'Technical Workshops',
    'Stage Session': 'Stage Sessions', "Educator's Day Session": "Educator's Day Sessions",
    'Panel': 'Panels', 'Keynote Speaker': 'Keynote Speakers', 'Art Paper': 'Art Papers',
}


def _normalize_line_endings(text):
    """Keep parser input and generated JSON stable across Windows/macOS/Linux."""
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _clean_text(text):
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


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
        v = _clean_text(d.get_text(' ', strip=True))
        if v and v not in out:
            out.append(v)
    return out


def _url_param(url, key):
    if not url:
        return ''
    return (parse_qs(urlparse(url).query).get(key) or [''])[0]


def _fallback_id(day, start, title):
    return f"{day}|{start}|{title}".lower().replace('  ', ' ')[:140]


def _occurrence_id(item):
    return f"{item['sid']}|{item['day']}|{item['s']}" if item.get('sid') else _fallback_id(item['day'], item['s'], item['t'])


def _assign_ids(catalog):
    sid_counts = {}
    for item in catalog:
        sid = item.get('sid')
        if sid:
            sid_counts[sid] = sid_counts.get(sid, 0) + 1
    for item in catalog:
        sid = item.get('sid')
        item['id'] = sid if sid and sid_counts[sid] == 1 else _occurrence_id(item)
    return catalog


def _write_catalog_json(output, out):
    """Write the historical catalog shape: compact header, sorted item keys, LF."""
    generated = json.dumps(out["generated"], ensure_ascii=False)
    with output.open('w', encoding='utf-8', newline='\n') as f:
        f.write('{"v": 2, "source": "SIGGRAPH 2026", ')
        f.write(f'"count": {out["count"]}, "generated": {generated}, "catalog": [\n')
        for i, item in enumerate(out["catalog"]):
            stable_item = {k: item[k] for k in sorted(item)}
            rendered = json.dumps(stable_item, ensure_ascii=False, indent=2)
            if i:
                f.write(',\n')
            f.write('\n'.join('  ' + line for line in rendered.split('\n')))
        f.write('\n]}')


def _stable_generated(output, out):
    if not output.exists():
        return out
    try:
        old = json.loads(output.read_text(encoding='utf-8'))
    except Exception:
        return out
    old_cmp = dict(old)
    new_cmp = dict(out)
    old_cmp.pop('generated', None)
    new_cmp.pop('generated', None)
    if old_cmp == new_cmp and old.get('generated'):
        out = dict(out)
        out['generated'] = old['generated']
    return out


def _fetch_text(url, attempts=FETCH_ATTEMPTS, timeout=FETCH_TIMEOUT):
    headers = {'User-Agent': 'Siggraph-2026-Scheduler catalog refresh'}
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as res:
                if getattr(res, 'status', 200) >= 400:
                    raise RuntimeError(f"HTTP {res.status}")
                return _normalize_line_endings(res.read().decode('utf-8', errors='replace'))
        except (OSError, TimeoutError, URLError, RuntimeError) as e:
            last_error = e
            if attempt < attempts:
                wait = min(2 ** attempt, 10)
                print(f"  fetch failed ({attempt}/{attempts}) for {url}: {e}; retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"could not fetch {url}: {last_error}")


def _discover_snippet_urls(index_html, base_url):
    pattern = r'wp-content/linklings_snippets/wp_program_view_all_\d{4}-\d{2}-\d{2}\.txt(?:\?v=\d+)?'
    urls = []
    for path in re.findall(pattern, index_html):
        url = urljoin(base_url, path)
        if url not in urls:
            urls.append(url)
    urls.sort()
    return urls


def _snippet_days(snippet_urls):
    days = []
    for url in snippet_urls:
        m = re.search(r'wp_program_view_all_(\d{4}-\d{2}-\d{2})\.txt', url)
        if m and m.group(1) not in days:
            days.append(m.group(1))
    return sorted(days)


def fetch_live_snippets(url):
    """Fetch the same per-day schedule snippets that the live page loads via XHR."""
    index_html = _fetch_text(url)
    snippet_urls = _discover_snippet_urls(index_html, url)
    if not snippet_urls:
        raise RuntimeError("could not find schedule snippet URLs in the live page")
    print(f"Found {len(snippet_urls)} schedule snippet files", file=sys.stderr)
    fragments = []
    for snippet_url in snippet_urls:
        print(f"  fetching {snippet_url}", file=sys.stderr)
        text = _fetch_text(snippet_url)
        if 'agenda-item' not in text:
            raise RuntimeError(f"schedule snippet had no agenda items: {snippet_url}")
        fragments.append(text)
    return '\n'.join(fragments), _snippet_days(snippet_urls)


def _catalog_days(catalog):
    by_day = {}
    for c in catalog:
        by_day[c['day']] = by_day.get(c['day'], 0) + 1
    return by_day


def _validate_catalog(catalog, output, expected_days=None):
    by_day = _catalog_days(catalog)
    missing_days = [day for day in (expected_days or []) if by_day.get(day, 0) == 0]
    if missing_days:
        raise RuntimeError(
            f"parsed catalog looks partial: {len(catalog)} sessions, by day {by_day}, "
            f"missing days {missing_days}"
        )
    if output.exists():
        try:
            old = json.loads(output.read_text(encoding='utf-8'))
            old_count = int(old.get('count') or len(old.get('catalog') or []))
        except Exception:
            old_count = 0
        if old_count > 0 and len(catalog) < old_count * 0.9:
            raise RuntimeError(
                f"refusing to replace {old_count} existing sessions with only {len(catalog)} parsed sessions"
            )
    return by_day


def parse_html(html):
    soup = _soup(html)
    catalog = []
    for it in soup.select('.agenda-item'):
        title_el = it.select_one('.presentation-title')
        if not title_el:
            continue
        t = _clean_text(title_el.get_text(' ', strip=True))
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
            v = _clean_text(e.get_text(' ', strip=True))
            if v and v not in etypes:
                etypes.append(v)
        if not etypes:
            pt = it.select_one('.presentation-type')
            etypes = [_clean_text(pt.get_text(' ', strip=True))] if pt else ['Session']
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
        if url:
            url = urljoin(DEFAULT_URL, url)
        sid = _url_param(url, 'sess')
        pid = _url_param(url, 'id')
        s = _fmt(smin)
        item = {
            "t": t, "program": programs[0], "programs": programs,
            "day": day, "s": s, "e": _fmt(min(emin, 1439)),
            "room": _clean_text(loc.get_text(' ', strip=True)) if loc else "",
            "url": url,
            "sid": sid,
            "pid": pid,
            "ia": _tags(it, 'interest-area'),
            "kw": _tags(it, 'keyword'),
            "reg": _tags(it, 'registration-category'),
            "_smin": smin,
        }
        catalog.append(item)
    catalog.sort(key=lambda c: (c['day'], c['_smin'], c['t']))
    for c in catalog:
        del c['_smin']
    return _assign_ids(catalog)


def main():
    ap = argparse.ArgumentParser(description="Build siggraph2026-catalog.json for the timetable app.")
    ap.add_argument('input', nargs='?', help="a saved schedule .htm/.html file")
    ap.add_argument('-o', '--output', default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            ap.error(f"saved HTML file not found: {input_path}")
        html = _normalize_line_endings(input_path.read_text(encoding='utf-8', errors='replace'))
        expected_days = None
    else:
        print(f"Fetching schedule snippets from {DEFAULT_URL} ...", file=sys.stderr)
        html, expected_days = fetch_live_snippets(DEFAULT_URL)

    catalog = parse_html(html)
    if len(catalog) < 50:
        print(f"WARNING: only {len(catalog)} sessions parsed. The input may be incomplete.", file=sys.stderr)

    output = Path(args.output)
    by_day = _validate_catalog(catalog, output, expected_days)
    out = {"v": 2, "source": "SIGGRAPH 2026", "count": len(catalog),
           "generated": datetime.now(timezone.utc).isoformat(), "catalog": catalog}
    output.parent.mkdir(parents=True, exist_ok=True)
    out = _stable_generated(output, out)
    _write_catalog_json(output, out)

    print(f"Wrote {len(catalog)} sessions to {output}")
    print("By day:", {k: by_day[k] for k in sorted(by_day)})
    print("Commit the updated JSON; the app fetches it automatically on next load.")


if __name__ == '__main__':
    main()
