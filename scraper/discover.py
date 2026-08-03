"""Find candidate Installer post URLs.

Union of three sources (none is complete on its own — see SPEC §2.1):
  1. Monthly sitemaps, filtered by loose slug match ("installe" catches a
     known truncated slug). Complete per month, but misses issues whose slug
     lacks the marker.
  2. Hub + archive listing pages. Catches marker-less slugs, but the pages
     lazy-load and only server-render part of the history.
  3. RSS (last ~10 entries). Cheap detection of the newest issue.

Candidates go to data/urls.json as status=pending; parse confirms or rejects
each one by looking at the fetched page itself.
"""
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

from scraper.config import BASE, HUB, RSS, URLS_FILE, FIRST_MONTH
from scraper import fetch

# Post-URL path shapes across all three URL eras.
POST_PATH = re.compile(
    r"^/(?:"
    r"\d{4}/\d{1,2}/\d{1,2}/\d+/[a-z0-9-]+"  # /2023/9/3/23855448/slug
    r"|\d{5,}/[a-z0-9-]+"                    # /23885600/slug (early, no date)
    r"|[a-z][a-z0-9-]*/\d{5,}/[a-z0-9-]+"    # /tech/940092/slug (2025+)
    r")/?$"
)
NON_POST_PREFIXES = ("/rss/", "/sitemaps", "/sp/", "/users/", "/authors/")


def _months() -> list[tuple[int, int]]:
    today = date.today()
    y, m = FIRST_MONTH
    out = []
    while (y, m) <= (today.year, today.month):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _current_months() -> set[tuple[int, int]]:
    """Months whose sitemaps still change — bypass cache for these."""
    months = _months()
    return set(months[-2:])


def sitemap_candidates() -> set[str]:
    urls: set[str] = set()
    for y, m in _months():
        sm_url = f"{BASE}/sitemaps/entries/{y}/{m}"
        try:
            _, xml_text = fetch.get(sm_url, cache=(y, m) not in _current_months())
        except Exception as e:  # a missing month shouldn't kill discovery
            print(f"  ! sitemap {y}/{m}: {e}")
            continue
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            continue
        for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            url = (loc.text or "").strip()
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            if "installe" in slug:
                urls.add(url)
    return urls


def listing_candidates(max_pages: int = 15) -> set[str]:
    urls: set[str] = set()
    for n in range(1, max_pages + 1):
        page_url = HUB if n == 1 else f"{HUB}/archives/{n}"
        try:
            _, html = fetch.get(page_url, cache=False)
        except Exception as e:
            print(f"  ! listing page {n}: {e}")
            break
        found = set()
        for href in re.findall(r'href="(/[^"]+)"', html):
            path = href.split("?")[0].split("#")[0]
            if path.startswith(NON_POST_PREFIXES):
                continue
            if POST_PATH.match(path):
                found.add(BASE + path)
        new = found - urls
        urls |= found
        if n > 1 and not new:
            break
    return urls


def rss_candidates() -> set[str]:
    urls: set[str] = set()
    try:
        _, xml_text = fetch.get(RSS, cache=False)
        root = ET.fromstring(xml_text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for link in root.findall(".//a:entry/a:link", ns):
            href = link.get("href")
            if href:
                urls.add(href.split("?")[0])
    except Exception as e:
        print(f"  ! rss: {e}")
    return urls


def load_state() -> dict:
    if URLS_FILE.exists():
        return json.loads(URLS_FILE.read_text())
    return {"posts": {}}


def save_state(state: dict) -> None:
    state["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["posts"] = dict(sorted(state["posts"].items()))
    URLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    URLS_FILE.write_text(json.dumps(state, indent=1) + "\n")


def run() -> dict:
    state = load_state()
    posts = state["posts"]
    before = len(posts)
    print("discover: sitemaps…")
    cands = sitemap_candidates()
    print(f"  {len(cands)} sitemap candidates")
    print("discover: listing pages…")
    listed = listing_candidates()
    print(f"  {len(listed)} listing candidates")
    cands |= listed
    cands |= rss_candidates()
    for url in sorted(cands):
        posts.setdefault(url, {"status": "pending"})
    save_state(state)
    pending = sum(1 for p in posts.values() if p["status"] == "pending")
    print(f"discover: {len(posts)} known URLs ({len(posts) - before} new, {pending} pending)")
    return state
