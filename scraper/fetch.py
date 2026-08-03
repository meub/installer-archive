import hashlib
import json
import time
from datetime import datetime, timezone

import requests

from scraper.config import RAW, RAW_INDEX, RATE_LIMIT_SECONDS, USER_AGENT

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_hit = 0.0


def _index() -> dict:
    if RAW_INDEX.exists():
        return json.loads(RAW_INDEX.read_text())
    return {}


def _save_index(idx: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    RAW_INDEX.write_text(json.dumps(idx, indent=1, sort_keys=True))


def _throttle() -> None:
    global _last_hit
    wait = RATE_LIMIT_SECONDS - (time.monotonic() - _last_hit)
    if wait > 0:
        time.sleep(wait)
    _last_hit = time.monotonic()


def get(url: str, cache: bool = True) -> tuple[str, str]:
    """Fetch a URL politely. Returns (final_url, text). Caches to data/raw/."""
    idx = _index()
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    path = RAW / f"{key}.html"
    if cache and url in idx and path.exists():
        return idx[url]["final_url"], path.read_text(encoding="utf-8")

    last_err: Exception | None = None
    for attempt in range(3):
        _throttle()
        try:
            resp = _session.get(url, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{resp.status_code} for {url}")
            resp.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(resp.text, encoding="utf-8")
            idx[url] = {
                "file": path.name,
                "final_url": resp.url,
                "status": resp.status_code,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            _save_index(idx)
            return resp.url, resp.text
        except requests.HTTPError as e:
            # don't retry hard 404s
            if "404" in str(e):
                raise
            last_err = e
        except requests.RequestException as e:
            last_err = e
        time.sleep(2 * (2 ** attempt))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")
