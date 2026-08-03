"""Parse Installer issue pages into issue JSON.

The Verge re-renders all eras of posts with the same CMS markup (SPEC §2.2):
body elements carry class `duet--article--dangerously-set-cms-markup`, section
headings are <h2> with exactly that class. Section names have been stable
since 2023 (The Drop / Pro Tips / Screen share / Crowdsourced / Signing off).

The parser is deliberately tolerant: anything surprising sets needs_review
rather than raising. Curated issue files are never overwritten (SPEC §3).
"""
import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

from scraper.config import (BLURB_LIMIT, BODIES, ISSUES, PARSER_VERSION,
                            SCHEMA_VERSION)
from scraper.util import (clean_url, is_verge, norm_ws, sentence_containing,
                          sentence_trim, slugify, strip_link_markers)

CMS = "duet--article--dangerously-set-cms-markup"

KNOWN_SECTIONS = {
    "the drop": "the-drop",
    "pro tips": "pro-tips",
    "pro tip": "pro-tips",
    "screen share": "screen-share",
    "crowdsourced": "crowdsourced",
    "group project": "group-project",  # recurring reader-collab segment
    "signing off": "signing-off",
}

GEAR_LINE = re.compile(
    r"^The (phone|watch|tablet|laptop|computer|desktop|keyboard|mouse|headphones|"
    r"earbuds|case|charger|camera|e-?reader|console|controller|monitor|bag|desk|speaker)s?\s*:",
    re.I,
)
NUMBER_RE = re.compile(r"Installer\s+No\.?\s*(\d{1,4})", re.I)
CALLOUT_TITLES = re.compile(r"i need your help|what are you into|tell me for installer", re.I)
SPECIAL_TITLES = re.compile(r"gift guide", re.I)


# ---------------------------------------------------------------- page level

def is_installer_post(soup: BeautifulSoup) -> bool:
    """A post self-identifies via an Installer hub link outside nav/footer."""
    for a in soup.find_all("a", href=True):
        path = a["href"].split("?")[0].rstrip("/")
        if path.endswith("/installer-newsletter"):
            if not any(p.name in ("nav", "footer") for p in a.parents):
                return True
    return False


def _jsonld_articles(soup: BeautifulSoup) -> list[dict]:
    found = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop(0)
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                types = node.get("@type", [])
                types = types if isinstance(types, list) else [types]
                if "NewsArticle" in types or "Article" in types:
                    found.append(node)
                stack.extend(v for v in node.values() if isinstance(v, (list, dict)))
    return found


def _meta(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return tag.get("content") if tag else None


def extract_page(html: str) -> dict:
    """Page-level metadata + ordered body elements."""
    soup = BeautifulSoup(html, "lxml")
    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        canonical = clean_url(link["href"])
    canonical = canonical or clean_url(_meta(soup, "og:url"))

    articles = _jsonld_articles(soup)
    main = None
    for art in articles:
        url = art.get("url") or art.get("mainEntityOfPage")
        if isinstance(url, dict):
            url = url.get("@id")
        if canonical and url and clean_url(url) == canonical:
            main = art
            break
    main = main or (articles[0] if articles else {})

    title = norm_ws(main.get("headline") or _meta(soup, "og:title") or "")
    date_raw = main.get("datePublished") or _meta(soup, "article:published_time") or ""
    date = date_raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", date_raw) else None

    authors = main.get("author") or []
    if isinstance(authors, dict):
        authors = [authors]
    author = ", ".join(
        norm_ws(a.get("name", "")) for a in authors if isinstance(a, dict) and a.get("name")
    ) or None

    return {
        "soup": soup,
        "canonical": canonical,
        "title": title,
        "date": date,
        "author": author,
        "body": body_elements(soup),
    }


CHROME_CLASS = re.compile(r"related|most-popular|newsletter-signup|table-of-contents|toc", re.I)


def _article_root(soup: BeautifulSoup) -> Tag | None:
    """Lowest ancestor containing (nearly) all cms-marked paragraphs."""
    ps = soup.find_all("p", class_=CMS)
    if not ps:
        return None
    total = len(ps)
    for anc in ps[0].parents:
        if not isinstance(anc, Tag):
            break
        if len(anc.find_all("p", class_=CMS)) >= max(2, int(0.8 * total)):
            return anc
    return None


def body_elements(soup: BeautifulSoup) -> list[Tag]:
    """Article-body elements in document order, chrome excluded."""
    root = _article_root(soup) or soup.body or soup
    kept: list[Tag] = []
    kept_ids: set[int] = set()

    def has_kept_ancestor(el: Tag) -> bool:
        return any(id(p) in kept_ids for p in el.parents)

    def in_chrome(el: Tag) -> bool:
        for p in el.parents:
            if p is root:
                break
            if not isinstance(p, Tag):
                continue
            if p.name in ("aside", "nav", "footer", "figure"):
                return True
            if CHROME_CLASS.search(" ".join(p.get("class") or [])):
                return True
        return False

    for el in root.descendants:
        if not isinstance(el, Tag) or has_kept_ancestor(el):
            continue
        classes = el.get("class") or []
        take = False
        if el.name == "h2":
            take = classes == [CMS]  # chrome h2s carry extra classes
        elif el.name in ("h3", "h4", "p", "blockquote"):
            take = CMS in classes
        elif el.name in ("ul", "ol"):
            # bare lists inside the article root are body content (The Drop)
            take = bool(el.find("li")) and not in_chrome(el)
        if take:
            kept.append(el)
            kept_ids.add(id(el))
    return kept


def body_html(elements: list[Tag]) -> str:
    return "\n".join(str(el) for el in elements)


# ------------------------------------------------------------- section level

def sectionize(elements: list[Tag]) -> tuple[list[tuple[str, list[Tag]]], list[str]]:
    """Split body elements on h2 headings. Returns (sections, unknown_headings)."""
    sections: list[tuple[str, list[Tag]]] = [("intro", [])]
    unknown: list[str] = []
    for el in elements:
        if el.name == "h2":
            label = re.sub(r"[^a-z ]", "", norm_ws(el.get_text()).lower()).strip()
            key = KNOWN_SECTIONS.get(label)
            if key is None:
                key = slugify(label or "section", 32)
                unknown.append(norm_ws(el.get_text()))
            sections.append((key, []))
        else:
            sections[-1][1].append(el)
    return sections, unknown


GENERIC_ANCHOR = {
    "link", "links", "here", "this", "this one", "download", "app store",
    "google play", "play store", "website", "site", "buy", "watch", "listen", "read",
}


def _anchors(el: Tag) -> list[tuple[Tag, str, str]]:
    """(tag, text, cleaned_url) for each usable anchor."""
    out = []
    for a in el.find_all("a", href=True):
        url = clean_url(a["href"])
        if url:
            out.append((a, norm_ws(a.get_text(" ")), url))
    return out


def _fix_name(a: Tag, a_text: str, container_text: str) -> tuple[str, bool]:
    """Old-era style is `Name (link)` — recover the real name for generic
    anchor texts from the nearest preceding bold run in the same p/li."""
    if a_text.lower() not in GENERIC_ANCHOR and len(a_text) >= 3:
        return a_text, False
    prev = a.find_previous(["strong", "b"])
    if prev is not None and prev.find_parent(["p", "li"]) is a.find_parent(["p", "li"]):
        cand = norm_ws(prev.get_text()).strip(" (:—–-")
        if 2 <= len(cand) <= 80:
            return cand, False
    head = norm_ws(container_text.split("(")[0])
    if 2 <= len(head) <= 60:
        return head, False
    return a_text or "unknown", True


def _item(name, url, blurb, section, *, alt_urls=None, category=None, recommender=None):
    return {
        "name": norm_ws(name)[:120],
        "url": url,
        "alt_urls": alt_urls or [],
        "category": category,
        "tags": [],
        "blurb": sentence_trim(strip_link_markers(blurb), BLURB_LIMIT),
        "section": section,
        "recommender": recommender,
    }


def _items_from_li(li: Tag, section: str) -> dict | None:
    text = norm_ws(li.get_text(" "))
    if not text:
        return None
    primary = None
    alts = []
    for a, a_text, url in _anchors(li):
        if is_verge(url) or primary is not None:
            alts.append(url)
        else:
            primary = (a, a_text, url)
    if primary:
        a, a_text, url = primary
        name, _ = _fix_name(a, a_text, text)
    else:
        name, url = text.split(".")[0][:80], None
    rest = text
    if name and rest.lower().startswith(name.lower()):
        rest = rest[len(name):].lstrip(" .:—–-")
    return _item(name, url, rest or text, section, alt_urls=alts)


def _split_attribution(text: str) -> tuple[str, str | None]:
    for dash in ("—", "–", " -- "):
        if dash in text:
            quote, _, tail = text.rpartition(dash)
            tail = norm_ws(tail).strip('"“”')
            if tail and len(tail) <= 48 and not tail.endswith("."):
                return norm_ws(quote).strip('"“”'), tail
    return text.strip('"“”'), None


def extract_items(sections: list[tuple[str, list[Tag]]]) -> tuple[list[dict], dict]:
    items: list[dict] = []
    stats = {"drop_items": 0, "unlinked": 0, "generic_names": 0}

    def linked_items(el: Tag, section: str, blurb: str | None = None,
                     recommender: str | None = None, category: str | None = None,
                     skip: set | None = None) -> int:
        n = 0
        local_seen: set = set()
        el_text = norm_ws(el.get_text(" "))
        for a, a_text, url in _anchors(el):
            if is_verge(url) or url in local_seen or (skip and url in skip):
                continue
            local_seen.add(url)
            name, generic = _fix_name(a, a_text, el_text)
            if generic:
                stats["generic_names"] += 1
            if len(name) < 2:
                continue
            if skip is not None:
                skip.add(url)
            # prose links get just the sentence around them, not the whole
            # paragraph — paragraphs here usually describe several things
            item_blurb = blurb if blurb is not None else sentence_containing(el_text, a_text or name)
            items.append(_item(name, url, item_blurb, section,
                               recommender=recommender, category=category))
            n += 1
        return n

    for section, els in sections:
        if section == "intro":
            # Prose, not a list — auto-extracting the intro's link-dumps produced
            # fragment names and repeated blurbs (SPEC §4.4). Notable intro finds
            # are hand-added to the issue file with section: "intro".
            continue

        elif section in ("crowdsourced", "pro-tips"):
            for el in els:
                text = norm_ws(el.get_text(" "))
                if not text or "installer@theverge.com" in text:
                    continue  # the standing "tell me what you're into" prompt
                if el.name in ("ul", "ol"):
                    for li in el.find_all("li"):
                        item = _items_from_li(li, section)
                        if item and item["url"]:  # unlinked lis here are tips/quotes, not things
                            quote, who = _split_attribution(item["blurb"])
                            item["blurb"] = sentence_trim(quote)
                            item["recommender"] = f"{who} (reader)" if who else None
                            items.append(item)
                elif el.name in ("p", "blockquote"):
                    quote, who = _split_attribution(text)
                    who = f"{who} (reader)" if who else None
                    linked_items(el, section, blurb=quote, recommender=who)

        elif section == "screen-share":
            section_text = norm_ws(" ".join(e.get_text(" ") for e in els))
            m = re.search(r"asked ([A-Z][^,.]{2,40}?) to (?:share|walk)", section_text)
            guest = norm_ws(m.group(1)) if m else None
            texts = [norm_ws(e.get_text(" ")) for e in els]
            gear_idx = [i for i, t in enumerate(texts) if GEAR_LINE.match(t)]
            first_gear = gear_idx[0] if gear_idx else -1
            seen: set = set()
            for i, el in enumerate(els):
                text = texts[i]
                gear = GEAR_LINE.match(text)
                if gear:
                    if gear.group(1).lower() == "wallpaper":
                        continue
                    name = text.split(":", 1)[1].strip().split(".")[0][:80]
                    if not name:
                        continue
                    url = next((u for _, _, u in _anchors(el) if not is_verge(u)), None)
                    if url:
                        seen.add(url)
                    items.append(_item(name, url, text, section,
                                       category="gadget", recommender=guest))
                elif first_gear == -1 or i > first_gear:
                    # anchors before the first gear line are the guest's bio links;
                    # category stays None — the guest lists shows/books too, let
                    # domain enrichment (or the curator) decide app vs media
                    if el.name in ("p", "ul", "ol", "blockquote"):
                        linked_items(el, section, recommender=guest, skip=seen)

        elif section == "signing-off":
            for el in els:
                if el.name == "p":
                    linked_items(el, section)

        else:
            # The Drop and any unknown section: list items first, else linked paragraphs
            lis = [li for el in els if el.name in ("ul", "ol") for li in el.find_all("li")]
            if lis:
                for li in lis:
                    item = _items_from_li(li, section)
                    if item:
                        items.append(item)
                        if section == "the-drop":
                            stats["drop_items"] += 1
            else:
                for el in els:
                    if el.name == "p":
                        n = linked_items(el, section)
                        if section == "the-drop":
                            stats["drop_items"] += n

    stats["unlinked"] = sum(1 for i in items if not i["url"])
    return items, stats


# --------------------------------------------------------------- issue level

def _dedupe_and_id(items: list[dict], date: str) -> list[dict]:
    seen_keys: set[str] = set()
    used_ids: set[str] = set()
    out = []
    for item in items:
        key = item["url"] or f"name:{item['name'].lower()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        base = f"{date}-{slugify(item['name'])}"
        rec_id, n = base, 2
        while rec_id in used_ids:
            rec_id, n = f"{base}-{n}", n + 1
        used_ids.add(rec_id)
        out.append({"id": rec_id, **item})
    return out


def build_issue(page: dict, source: str = "web") -> dict:
    title, date = page["title"], page["date"]
    if not date:
        raise ValueError("page has no publish date")

    sections, unknown = sectionize(page["body"])
    full_text = norm_ws(" ".join(el.get_text(" ") for el in page["body"]))
    m = NUMBER_RE.search(full_text)
    number = int(m.group(1)) if m else None

    post_type = "issue"
    if CALLOUT_TITLES.search(title):
        post_type = "callout"
    elif SPECIAL_TITLES.search(title):
        post_type = "special"

    if post_type == "callout":
        items, stats = [], {"drop_items": 0, "unlinked": 0, "generic_names": 0}
    else:
        items, stats = extract_items(sections)
    items = _dedupe_and_id(items, date)

    needs_review = bool(
        unknown
        or stats["unlinked"]
        or stats["generic_names"]
        or number is None
        or (post_type == "issue" and stats["drop_items"] == 0)
    )

    return {
        "schema": SCHEMA_VERSION,
        "date": date,
        "post_type": post_type,
        "title": title,
        "url": page["canonical"],
        "author": page["author"],
        "number": number,
        "sections_found": [s for s, _ in sections][:12],
        "source": source,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parser_version": PARSER_VERSION,
        "needs_review": needs_review,
        "recommendations": items,
    }


def issue_filename(issue: dict) -> str:
    if issue["post_type"] == "issue":
        return f"{issue['date']}.json"
    return f"{issue['date']}-{slugify(issue['title'], 24)}.json"


def write_issue(issue: dict, body: str | None, force: bool = False) -> tuple[str, str]:
    """Write bodies/ and issues/ files. Returns (path, action)."""
    ISSUES.mkdir(parents=True, exist_ok=True)
    BODIES.mkdir(parents=True, exist_ok=True)
    name = issue_filename(issue)
    if body is not None:
        (BODIES / name.replace(".json", ".html")).write_text(body, encoding="utf-8")
    path = ISSUES / name
    if path.exists():
        if not force:
            return str(path), "exists"
        path = ISSUES / name.replace(".json", ".proposed.json")
    path.write_text(json.dumps(issue, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path), "wrote"


# -------------------------------------------------------------- email source

EMAIL_TRACKING_PARAMS = ("url", "u", "redirect", "dest")


def parse_email(html: str, date: str, title: str | None = None,
                number: int | None = None) -> dict:
    """Best-effort parse of a newsletter email (inline-styled table soup).

    Matches section heading *text* instead of CSS classes; always needs_review.
    """
    soup = BeautifulSoup(html, "lxml")
    text_all = norm_ws(soup.get_text(" "))
    m = NUMBER_RE.search(text_all)

    # linear walk: mark section boundaries by heading text, bucket anchors
    current = "intro"
    buckets: dict[str, list[tuple[str, str, str]]] = {}
    for el in soup.find_all(True):
        if el.name in ("h1", "h2", "h3", "strong", "b", "span", "td", "p"):
            heading = norm_ws(el.get_text())
            label = re.sub(r"[^a-z ]", "", heading.lower()).strip()
            if label in KNOWN_SECTIONS and len(heading) < 30:
                current = KNOWN_SECTIONS[label]
                continue
            # unknown-but-heading-shaped (real <h1-3>, short): new slug section,
            # mirroring how the web parser slugs unknown h2s
            if el.name in ("h1", "h2", "h3") and label and len(heading) < 40:
                current = slugify(label, 32)
                continue
        if el.name == "a" and el.get("href"):
            url = clean_url(el["href"])
            name = norm_ws(el.get_text(" "))
            if not url or is_verge(url) or len(name) < 2:
                continue
            parent_text = norm_ws(el.parent.get_text(" ")) if el.parent else name
            buckets.setdefault(current, []).append((name, url, parent_text))

    items = []
    for section, found in buckets.items():
        if section == "intro":
            continue  # same policy as the web parser
        for name, url, blurb in found:
            items.append(_item(name, url, sentence_containing(blurb, name), section))
    items = _dedupe_and_id(items, date)

    final_title = norm_ws(title or (soup.title.string if soup.title else "") or f"Installer {date}")
    post_type = "issue"
    if CALLOUT_TITLES.search(final_title):
        post_type = "callout"
    elif SPECIAL_TITLES.search(final_title):
        post_type = "special"

    return {
        "schema": SCHEMA_VERSION,
        "date": date,
        "post_type": post_type,
        "title": final_title,
        "url": None,
        "author": "David Pierce",
        "number": number if number is not None else (int(m.group(1)) if m else None),
        "sections_found": list(buckets.keys()),
        "source": "email",
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parser_version": PARSER_VERSION,
        "needs_review": True,
        "recommendations": items,
    }
