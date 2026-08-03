import re
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse, unquote

from scraper.config import BASE, BLURB_LIMIT

# Hosts that wrap the real destination in a query param (affiliate/tracking).
# A leading dot matches any subdomain of the suffix (impact.com-style networks).
WRAPPER_HOSTS = [
    ("go.skimresources.com", ("url",)),
    ("shop-links.co", ("url",)),
    ("goto.walmart.com", ("u",)),
    ("click.linksynergy.com", ("murl",)),
    ("links.theverge.com", ("url", "u")),  # email link tracker
    ("howl.me", ("url", "u")),
    (".sjv.io", ("u",)),
    (".pxf.io", ("u",)),
    (".evyy.net", ("u",)),
]


def _wrapper_params(host: str) -> tuple[str, ...] | None:
    for suffix, params in WRAPPER_HOSTS:
        if suffix.startswith("."):
            if host.endswith(suffix) or host == suffix[1:]:
                return params
        elif host == suffix or host.endswith("." + suffix):
            return params
    return None

TRACKING_PARAMS = re.compile(r"^(utm_|ref$|ref_|cmpid$|smid$|ito$|sref$|ueid$)")


def _unwrap_sailthru(parts) -> str | None:
    """link.theverge.com/click/{id}/{urlsafe-b64-destination}/{n} (email tracker)."""
    import base64
    host = parts.netloc.lower().removeprefix("www.")
    if host != "link.theverge.com" and not host.endswith(".sailthru.com"):
        return None
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) < 2 or segs[0] != "click":
        return None
    for seg in segs[1:]:
        pad = seg + "=" * (-len(seg) % 4)
        try:
            decoded = base64.urlsafe_b64decode(pad).decode("utf-8", "ignore")
        except Exception:
            continue
        if decoded.startswith("http"):
            return decoded
    return None


def norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def slugify(text: str, maxlen: int = 48) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:maxlen].rstrip("-") or "item"


def clean_url(href: str | None, base: str = BASE) -> str | None:
    """Absolutize, unwrap affiliate/tracking redirects, strip tracking params."""
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "sms:", "#", "javascript:")):
        return None
    url = urljoin(base, href)
    for _ in range(3):  # unwrap nested wrappers
        parts = urlparse(url)
        host = parts.netloc.lower().removeprefix("www.")
        wrapped = _unwrap_sailthru(parts)
        if wrapped and wrapped.startswith("http"):
            url = wrapped
            continue
        params = _wrapper_params(host)
        wrapped = None
        if params:
            qs = parse_qs(parts.query)
            for p in params:
                if p in qs and qs[p]:
                    wrapped = unquote(qs[p][0])
                    break
        if not wrapped or not wrapped.startswith("http"):
            break
        url = wrapped
    parts = urlparse(url)
    if parts.scheme not in ("http", "https"):
        return None
    if parts.query:
        kept = [
            kv for kv in parts.query.split("&")
            if not TRACKING_PARAMS.match(kv.split("=")[0].lower())
        ]
        parts = parts._replace(query="&".join(kept))
    return urlunparse(parts)


def is_verge(url: str | None) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return host == "theverge.com" or host.endswith(".theverge.com")


LINK_MARKER = re.compile(r"\(\s*links?\s*\)", re.I)


def strip_link_markers(text: str) -> str:
    """Remove old-era '( link )' anchor markers left in prose."""
    text = LINK_MARKER.sub("", text or "")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return norm_ws(text)


SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-Z“\"'0-9])")


def sentence_containing(text: str, needle: str) -> str:
    """The first sentence of `text` containing `needle`; whole text if not found.

    Used to scope blurbs for links that appear mid-prose (SPEC §5.3) — the
    paragraph as a whole usually describes several different things.
    """
    text = norm_ws(text)
    if not needle:
        return text
    low = needle.lower()
    for sentence in SENTENCE_SPLIT.split(text):
        if low in sentence.lower():
            return sentence.strip()
    return text


def sentence_trim(text: str, limit: int = BLURB_LIMIT) -> str:
    """Trim to <= limit chars, preferring a sentence boundary, appending ellipsis."""
    text = norm_ws(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # last sentence end within the window (avoid cutting at "No." style abbreviations)
    best = -1
    for m in re.finditer(r"[.!?][\"”')\]]?\s", cut):
        best = m.end()
    if best > limit * 0.3:
        return cut[:best].strip()
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut).rstrip(",;:") + "…"
