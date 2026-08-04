"""Repair names that are sentence fragments instead of the thing itself.

The parser takes an item's name from its anchor text, which usually works
("Halide Mark III") but sometimes captures a phrase from the sentence around
the link: "this ESR one", "his love letter to landlines". This walks those
entries and recovers a real title, preferring sources in order of reliability:

  1. YouTube oEmbed  - a public, key-free endpoint that returns the video title
  2. The page itself - og:title, else <title>, with the site-name suffix trimmed
  3. `claude -p`     - infers a name from the blurb when there's no link to read

Names only ever change for entries matching VAGUE; everything else is left
alone, and ids stay as they are so pending deletion lists keep working.
"""
import json
import re
import subprocess
import time
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from scraper.config import DATA, ISSUES, USER_AGENT
from scraper.util import norm_ws

# A demonstrative or possessive lead-in is never a real title.
DEMONSTRATIVE = re.compile(
    r"^(this|that|these|those|his|her|their|its|my|our|another|it|here|there)\s", re.I)
# An article is only a fragment when what follows is lowercase: "a two-hour
# video" needs fixing, while "A Million Miles Away" is the actual film.
INDEFINITE = re.compile(r"^(a|an|one|some|more|two|three)\s+([\w'-]+)", re.I)

CACHE_FILE = DATA / "title-cache.json"
RATE_LIMIT = 1.0
# " … - The Verge" / " … | Polygon": drop a trailing site name, not a real dash
SITE_SUFFIX = re.compile(r"\s*[|–—-]\s*[^|–—-]{2,28}$")
JUNK_TITLE = re.compile(
    r"^(just a moment|attention required|access denied|are you a robot|"
    r"page not found|404|home|error|log in|sign in|redirecting)", re.I)
STORE_PREFIX = re.compile(r"^(watch|listen to|stream|buy|shop|download)\s+", re.I)
# "Name on Instagram: \"the whole caption…\"" is the post's text, not a title
SOCIAL_DUMP = re.compile(r"\son (instagram|threads|x|facebook|tiktok|bluesky)\s*:", re.I)


def is_vague(name: str) -> bool:
    n = (name or "").strip()
    if DEMONSTRATIVE.match(n):
        return True
    m = INDEFINITE.match(n)
    return bool(m and m.group(2)[:1].islower())


def _cache() -> dict:
    return json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")


STORE_LISTING = re.compile(r"^Amazon\.[a-z.]+\s*:\s*", re.I)


DANGLING = re.compile(r"\s+(with|and|for|from|by|the|an?|of|in|on|at|to|feat\.?)\s*\S*$", re.I)


def shorten(title: str, limit: int = 78) -> str:
    """Trim a source title down to the thing's name.

    Retail listings pile specs after the first comma ("Anker PowerCore Fusion
    10K, 20W USB-C Portable Charger…"), and video titles pack the series, the
    episode, and the channel between pipes. Cut to the part that names it.
    """
    raw = norm_ws(title)
    listing = bool(STORE_LISTING.match(raw))
    t = STORE_LISTING.sub("", raw).strip()
    if " | " in t:
        # the longest pipe-separated part names the thing; the rest is channel
        t = max((p.strip() for p in t.split(" | ")), key=len)
    if listing and "," in t:
        head = t.split(",")[0].strip()
        if len(head) >= 10:
            t = head
    # drop a short trailing publication name after a dash
    for sep in (" — ", " – ", " - "):
        idx = t.rfind(sep)
        if idx >= 20 and len(t) - idx - len(sep) <= 30:
            t = t[:idx].strip()
            break
    if len(t) > limit:
        # a dash usually separates the real title from a subtitle or outlet list
        for sep in (" — ", " – ", " - "):
            idx = t.find(sep)
            if 20 <= idx <= limit:
                t = t[:idx]
                break
        else:
            head = t.split(",")[0].strip()
            if "," in t and len(head) >= 12:
                t = head
            if len(t) > limit:
                t = DANGLING.sub("", t[:limit].rsplit(" ", 1)[0])
    t = t.strip()
    if t[:1] in '"“' and t[-1:] in '"”':  # unwrap only a matched pair
        t = t[1:-1].strip()
    return t.rstrip(" ,-–—:;") or raw[:limit]


def clean_title(title: str, url: str) -> str | None:
    title = norm_ws(title).strip("|-–— ")
    if not title or len(title) < 3 or JUNK_TITLE.match(title) or SOCIAL_DUMP.search(title):
        return None
    title = STORE_PREFIX.sub("", title).strip() or title
    parts = urlparse(url)
    host = parts.netloc.lower().removeprefix("www.")
    # A page deep in a site that reports the site's own name is serving its
    # default title (a JS-rendered app, usually), not the thing we linked to.
    brand = re.split(r"[.\-]", host)[0]
    first = re.sub(r"[^a-z0-9]", "", title.split()[0].lower())
    if first and first == brand and parts.path.strip("/"):
        return None
    stripped = SITE_SUFFIX.sub("", title).strip()
    # keep the trim only if it removed a site name and left something usable
    if len(stripped) >= 8:
        tail = title[len(stripped):].lower()
        brand = host.split(".")[0]
        if brand[:5] in tail.replace(" ", "") or len(tail) <= 18:
            title = stripped
    return shorten(title) or None


def fetch_title(url: str, session: requests.Session) -> str | None:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    try:
        if host in ("youtube.com", "youtu.be", "m.youtube.com"):
            r = session.get(
                f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json",
                timeout=20)
            if r.status_code == 200:
                return clean_title(r.json().get("title", ""), url)
            return None
        r = session.get(url, timeout=20, allow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return None
        soup = BeautifulSoup(r.text[:400_000], "lxml")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            found = clean_title(og["content"], url)
            if found:
                return found
        if soup.title and soup.title.string:
            return clean_title(soup.title.string, url)
    except Exception:
        return None
    return None


LLM_PROMPT = """These entries in an index of tech recommendations have placeholder \
names taken from the sentence around a link, instead of the name of the thing itself.

Using each blurb (and URL if present), give the actual name of the thing being \
recommended. Output ONE line of JSON per entry: {{"id": "...", "name": "..."}}
Use a proper name only when the text clearly supports it. If you cannot tell, \
output the id with "name": null. Never guess a brand or title that isn't implied.
No other text.

Entries:
{entries}"""


def llm_names(pending: list[dict], model: str) -> dict:
    if not pending:
        return {}
    entries = "\n".join(json.dumps(p, ensure_ascii=False) for p in pending)
    try:
        out = subprocess.run(
            ["claude", "-p", LLM_PROMPT.format(entries=entries), "--model", model],
            capture_output=True, text=True, timeout=600).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  ! claude unavailable, skipping LLM step")
        return {}
    found = {}
    for line in out.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = norm_ws(p.get("name") or "")
        if p.get("id") and name and not is_vague(name):
            found[p["id"]] = name[:120]
    return found


def run(dry_run: bool = False, llm: bool = True, model: str = "claude-opus-5",
        limit: int | None = None) -> None:
    issues = [(p, json.loads(p.read_text())) for p in sorted(ISSUES.glob("*.json"))]
    targets = [(path, issue, rec)
               for path, issue in issues
               for rec in issue["recommendations"] if is_vague(rec["name"])]
    if limit:
        targets = targets[:limit]
    print(f"titles: {len(targets)} vague names to repair")

    cache = _cache()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept-Language"] = "en-US,en;q=0.9"

    fixed, unresolved = {}, []
    last_hit = 0.0
    for n, (_, _, rec) in enumerate(targets, 1):
        url = rec["url"]
        if not url:
            unresolved.append(rec)
            continue
        if url in cache:
            title = cache[url]
        else:
            wait = RATE_LIMIT - (time.monotonic() - last_hit)
            if wait > 0:
                time.sleep(wait)
            last_hit = time.monotonic()
            title = fetch_title(url, session)
            cache[url] = title
            if n % 25 == 0:
                _save_cache(cache)
                print(f"  … {n}/{len(targets)}")
        if title and not is_vague(title):
            fixed[rec["id"]] = title
        else:
            unresolved.append(rec)
    _save_cache(cache)
    print(f"titles: {len(fixed)} recovered from the source, {len(unresolved)} left")

    if llm and unresolved:
        payload = [{"id": r["id"], "placeholder": r["name"],
                    "blurb": r["blurb"][:200], "url": r["url"] or ""}
                   for r in unresolved]
        got = llm_names(payload, model)
        print(f"titles: {len(got)} more inferred from blurbs")
        fixed.update(got)

    changed = 0
    for path, issue in issues:
        dirty = False
        for rec in issue["recommendations"]:
            new = fixed.get(rec["id"])
            if new and new != rec["name"]:
                print(f"  {rec['name'][:38]:38} -> {new[:52]}")
                rec["name"] = new
                dirty = True
                changed += 1
        if dirty and not dry_run:
            path.write_text(json.dumps(issue, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print(f"titles: {changed} renamed{' (dry run, nothing written)' if dry_run else ''}")
