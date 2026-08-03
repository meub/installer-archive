"""Fill category/tags proposals on parsed issues.

Deterministic domain heuristics first; optional `--llm` pass (via `claude -p`)
for whatever is still uncategorized. Both only ever FILL missing values or ADD
tags — curated values are never overwritten. Review happens in git diff.
"""
import json
import re
import subprocess
from urllib.parse import urlparse

from scraper.config import CATEGORIES, ISSUES, TAGS_FILE

# (host suffix, path regex or None, category, tags)
RULES = [
    ("apps.apple.com", None, "app", ["ios"]),
    ("testflight.apple.com", None, "app", ["ios", "beta"]),
    ("play.google.com", None, "app", ["android"]),
    ("apps.microsoft.com", None, "app", ["windows"]),
    ("chromewebstore.google.com", None, "app", ["web"]),
    ("chrome.google.com", r"/webstore", "app", ["web"]),
    ("github.com", None, "app", ["open-source"]),
    ("store.steampowered.com", None, "game", []),
    ("nintendo.com", None, "game", []),
    ("playstation.com", None, "game", []),
    ("xbox.com", None, "game", []),
    ("itch.io", None, "game", []),
    ("epicgames.com", None, "game", []),
    ("gog.com", None, "game", []),
    ("themoviedb.org", r"/tv/", "media", ["tv"]),
    ("themoviedb.org", r"/movie/", "media", ["movie"]),
    ("imdb.com", None, "media", []),
    ("netflix.com", None, "media", []),
    ("max.com", None, "media", []),
    ("hulu.com", None, "media", []),
    ("peacocktv.com", None, "media", []),
    ("disneyplus.com", None, "media", []),
    ("tv.apple.com", None, "media", []),
    ("youtube.com", None, "media", ["video"]),
    ("youtu.be", None, "media", ["video"]),
    ("open.spotify.com", r"/(show|episode)/", "media", ["podcast"]),
    ("open.spotify.com", r"/(album|track|artist)/", "media", ["music"]),
    ("podcasts.apple.com", None, "media", ["podcast"]),
    ("music.apple.com", None, "media", ["music"]),
    ("bandcamp.com", None, "media", ["music"]),
    ("bookshop.org", None, "media", ["book"]),
    ("goodreads.com", None, "media", ["book"]),
    ("audible.com", None, "media", ["book"]),
    ("substack.com", None, "media", ["newsletter"]),
    ("kickstarter.com", None, "gadget", ["kickstarter"]),
    ("amazon.com", None, "gadget", []),
    ("bestbuy.com", None, "gadget", []),
    ("store.google.com", None, "gadget", []),
    ("ikea.com", None, "gadget", []),
]


def vocab() -> set[str]:
    groups = json.loads(TAGS_FILE.read_text())
    return {t for tags in groups.values() for t in tags}


def classify(url: str | None) -> tuple[str | None, list[str]]:
    if not url:
        return None, []
    parts = urlparse(url)
    host = parts.netloc.lower().removeprefix("www.")
    for suffix, path_re, category, tags in RULES:
        if host == suffix or host.endswith("." + suffix):
            if path_re and not re.search(path_re, parts.path):
                continue
            return category, list(tags)
    return None, []


def enrich_issue(issue: dict) -> bool:
    changed = False
    for rec in issue["recommendations"]:
        cat, tags = classify(rec["url"])
        if rec["category"] is None and cat:
            rec["category"] = cat
            changed = True
        for t in tags:
            if t not in rec["tags"]:
                rec["tags"].append(t)
                changed = True
    return changed


LLM_PROMPT = """You are tagging entries for an index of recommendations from The Verge's Installer newsletter.

Categories (pick exactly one): app (software/services/sites), game (video games), media (things you watch/listen/read: tv, movies, podcasts, music, books, articles, videos), gadget (physical products), feature (a capability of an existing product rather than the product itself, e.g. "Spotify's running mode"), other.

Allowed tags (pick 0-4 that clearly apply): {vocab}

For each entry below, output ONE line of JSON: {{"id": "...", "category": "...", "tags": [...]}}
No other text.

Entries:
{entries}"""


LLM_BATCH = 80


def llm_pass(issues: list[dict]) -> int:
    pending = []
    for issue in issues:
        for rec in issue["recommendations"]:
            if rec["category"] is None:
                pending.append({"id": rec["id"], "name": rec["name"], "blurb": rec["blurb"][:160]})
    if not pending:
        return 0
    allowed = sorted(vocab())

    proposals = {}
    batches = [pending[i:i + LLM_BATCH] for i in range(0, len(pending), LLM_BATCH)]
    print(f"  llm: {len(pending)} recs in {len(batches)} batches")
    for n, batch in enumerate(batches, 1):
        entries = "\n".join(json.dumps(p, ensure_ascii=False) for p in batch)
        prompt = LLM_PROMPT.format(vocab=", ".join(allowed), entries=entries)
        try:
            out = subprocess.run(
                ["claude", "-p", prompt], capture_output=True, text=True, timeout=600,
            ).stdout
        except FileNotFoundError:
            print("  ! claude CLI not found — skipping LLM pass")
            return 0
        except subprocess.TimeoutExpired:
            print(f"  ! claude timed out on batch {n}/{len(batches)} — continuing")
            continue
        got = 0
        for line in out.splitlines():
            line = line.strip().strip("`")
            if not line.startswith("{"):
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            if p.get("id") and p.get("category") in CATEGORIES:
                proposals[p["id"]] = p
                got += 1
        print(f"  llm: batch {n}/{len(batches)} -> {got}/{len(batch)} categorized")

    applied = 0
    allowed_set = set(allowed)
    for issue in issues:
        for rec in issue["recommendations"]:
            p = proposals.get(rec["id"])
            if p and rec["category"] is None:
                rec["category"] = p["category"]
                for t in p.get("tags", []):
                    if t in allowed_set and t not in rec["tags"]:
                        rec["tags"].append(t)
                applied += 1
    return applied


def run(dates: list[str] | None = None, llm: bool = False) -> None:
    paths = sorted(ISSUES.glob("*.json"))
    if dates:
        paths = [p for p in paths if any(p.name.startswith(d) for d in dates)]
    loaded = [(p, json.loads(p.read_text())) for p in paths]
    changed_paths = set()

    for path, issue in loaded:
        if enrich_issue(issue):
            changed_paths.add(path)
    if llm:
        if llm_pass([i for _, i in loaded]):
            changed_paths.update(p for p, _ in loaded)

    for path, issue in loaded:
        if path in changed_paths:
            path.write_text(json.dumps(issue, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    uncategorized = sum(
        1 for _, i in loaded for r in i["recommendations"] if r["category"] is None
    )
    print(f"enrich: {len(changed_paths)} files updated, {uncategorized} recs still uncategorized")
