from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
BODIES = DATA / "bodies"
ISSUES = DATA / "issues"
EMAIL = DATA / "email"
SITE = ROOT / "site"
SITE_DATA = SITE / "data"
URLS_FILE = DATA / "urls.json"
TAGS_FILE = DATA / "tags.json"
RAW_INDEX = RAW / "index.json"

BASE = "https://www.theverge.com"
HUB = f"{BASE}/installer-newsletter"
RSS = f"{BASE}/rss/installer-newsletter/index.xml"

# robots.txt disallows python-requests/Scrapy UAs; the generic agent is allowed
# on these paths. Identify honestly.
USER_AGENT = "InstallerArchiveBot/1.0 (+https://installerarchive.alexmeub.com; alexmeub@gmail.com)"
RATE_LIMIT_SECONDS = 1.5
FIRST_MONTH = (2023, 8)  # Installer No. 1: 2023-08-13

SCHEMA_VERSION = 1
PARSER_VERSION = 1

CATEGORIES = ["app", "game", "media", "gadget", "feature", "other"]
SECTIONS = ["intro", "the-drop", "pro-tips", "screen-share", "crowdsourced",
            "group-project", "signing-off"]
POST_TYPES = ["issue", "special", "callout"]
BLURB_LIMIT = 300
