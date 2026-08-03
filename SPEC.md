# Installer Archive — Technical Spec

A clean, searchable index of everything recommended in [Installer](https://www.theverge.com/installer-newsletter), The Verge's weekly newsletter by David Pierce. Static site, open source, hosted at **installerarchive.alexmeub.com**.

- **Status:** Draft v1 (2026-08-03)
- **Stack:** Python (scrape/build) · vanilla HTML/CSS/JS (site) · S3 + CloudFront + Route53 (hosting)
- **Repo:** github.com/alexmeub/installer-archive (public, MIT for code)

## 1. Goals

1. Every recommendation from every Installer issue, in one place, instantly searchable.
2. Filter by category, tags, section, and year; sort by date or name.
3. New issues (published Saturdays ~8am ET) addable with one command + a quick review.
4. The UI **is** the product: fast, clean, keyboard-friendly. No frameworks, no build step for the frontend.
5. Phase 2: an optional Windows 98 theme as a fun alternate skin.

**Non-goals (v1):** republishing full newsletter text, user accounts, server-side anything, per-recommendation pages, comments.

## 2. Source analysis (verified 2026-08-03)

Findings from probing theverge.com — these drive the scraper design. Re-verify anything marked ⚠ during implementation.

### 2.1 URLs and discovery

- Hub page: `theverge.com/installer-newsletter`, paginated at `/installer-newsletter/archives/{n}` (n=2..4 currently have content; higher pages render empty chrome at ~148KB).
- **Three URL eras**, all still live:
  - `theverge.com/{id}/{slug}` (early 2023, no date/section — seen in sitemaps)
  - `theverge.com/{yyyy}/{m}/{d}/{id}/{slug}` (late 2023 – Jan 2025)
  - `theverge.com/tech/{id}/{slug}` (Feb 2025+, post-redesign)
- **The hub/archive pages do NOT server-render the full history.** Verified: Sept 2023 sitemap lists 4 issues; `archives/4` SSRs only 2 of them. The rest lazy-load via JS. So listing pages alone are insufficient for backfill.
- Monthly sitemaps are complete: `theverge.com/sitemaps/entries/{yyyy}/{m}` (plain XML, all posts that month).
- Slug filtering is a heuristic, not a guarantee: most issues end `-installer` (new era) or `-installer-newsletter` (old era), but at least one is truncated (`...-installe`) and some issues have no marker at all (e.g. `/tech/914429/the-ai-apps-are-coming-for-your-pc`).
- RSS: `theverge.com/rss/installer-newsletter/index.xml` — Atom, 10 entries, **summary-only** (~3.4KB/entry). Good for detecting a new issue, not for parsing it.
- Estimated total: **~120–140 issues** (weekly since 2023-08-13, with skip weeks — e.g. July 4th week 2026).
- The hub section also contains **non-issue posts**: reader-callout posts ("I need your help for Installer") and specials (gift guides, "best of 2025"). The data model must distinguish these.

**Discovery algorithm:** union of (a) all monthly sitemaps filtered by loose slug match `installe`, (b) hub + archive page links, (c) RSS entries → fetch each candidate → **confirm it's an Installer post via the Installer breadcrumb/label** (issue pages contain `href=".../installer-newsletter"` in the article header region — scope the check to avoid nav/footer false positives). Validation: flag any calendar month with <4 confirmed issues for manual review (catches issues that evade all three sources). Any confirmed gap can be filled from the subscriber email copy via the email-ingestion path (§5.3).

### 2.2 Page structure (the good news)

The Verge migrated to WordPress + a Next.js frontend in early 2025 and **re-renders old posts with the same markup** — the 2023-08-13 first issue and a 2026 issue use identical CSS classes. One parser handles all eras.

- Pages are fully server-rendered; plain `curl` with a browser-like UA gets complete content. **No paywall on newsletter posts** (no `isAccessibleForFree` restriction found).
- Article body elements carry class `duet--article--dangerously-set-cms-markup`. Section headings are `<h2>` with exactly that class (site chrome like "Most Popular" has extra classes — match the exact class or scope to the article container).
- Section names have been stable for 3 years (⚠ case varies: "Screen share" vs "Screen Share"):
  | Section | Content | Parse strategy |
  |---|---|---|
  | *(intro, untitled)* | Opening essay (the preamble) | **Not auto-extracted** — prose link-dumps made fragment-named items with repeated blurbs; notable finds are hand-added (§4.4) |
  | **The Drop** | The link list — the core recs | `<ul>` after the h2; each `<li>` = one rec |
  | **Pro Tips** (occasional) | Reader tips | Like Crowdsourced |
  | **Screen share** | Guest homescreen interview | Paragraphs `The phone:`, `The apps:`… — capture the guest's gear + apps (see §4.4) |
  | **Crowdsourced** | Reader recs | Paragraphs: `"quote with links" — Name` |
  | **Signing off** | Closing rec (often one link) | Extract links |
  Parser must **warn on unknown h2s** rather than silently skip — the format will drift again.
- **The Drop `<li>` anatomy:** `<a href="{url}">{Name}</a>. {blurb…}` — first anchor text = name, first anchor href = primary URL, remaining anchors = supplementary (often The Verge's own coverage, as relative URLs — resolve to absolute).
- **Affiliate wrappers:** some links go through Skimlinks (`go.skimresources.com/?...&url={encoded}`) — unwrap to the real destination (keep the clean URL only).
- Issue metadata from JSON-LD `NewsArticle`: headline, `datePublished`, author `Person`. Note `articleSection` says "Tech", not "Installer" — don't use it for confirmation. Titles are editorial (no "Installer No. N"), so **dates, not issue numbers, are the primary key**.

### 2.3 Crawling etiquette

- robots.txt: the generic `*` agent is allowed on all relevant paths, but **`python-requests` and `Scrapy` UAs are explicitly disallowed** — never use default library UAs. Use an honest custom UA:
  `InstallerArchiveBot/1.0 (+https://installerarchive.alexmeub.com; alexmeub@gmail.com)`
- Rate limit 1 request / 1.5s, exponential backoff on 429/5xx. Total load is trivial: ~130 pages once, then 1/week.
- Cache every fetched page to disk; **never re-fetch to re-parse.**

### 2.4 Content policy

We index, we don't republish. Per recommendation we store: name, link, category/tags (ours), a **short quoted blurb (≤300 chars, first sentence or two)**, and attribution + link to the source issue. The site's About section states it's an unofficial fan index, unaffiliated with The Verge/Vox Media, with a takedown contact. Every card links prominently to the issue it came from — the archive should *drive* clicks to The Verge, not replace it.

## 3. Architecture

```
theverge.com ──scrape──▶ data/raw/*.html        (full pages, gitignored cache)
                  │
                parse──▶ data/bodies/*.html     (extracted article bodies, committed ~30KB ea)
                  │                              → re-parseable forever without re-fetching
                  └────▶ data/issues/*.json     (SOURCE OF TRUTH — scraper writes once,
                  ▲                              humans curate, git tracks)
              enrich (heuristics + optional LLM assist)
                  │
                build──▶ site/data/archive.json (single compiled artifact, gitignored)
                  │
                  └────▶ site/  ──deploy──▶ S3 ──▶ CloudFront ──▶ installerarchive.alexmeub.com
```

Key principle: **scrape once, curate forever.** Scraper output is a starting point; hand corrections live in `data/issues/*.json` and are never clobbered (scraper skips existing files; `--force` writes to `*.proposed.json` for manual merge). The frontend consumes one compiled JSON artifact and does everything client-side.

## 4. Data model

### 4.1 Issue file — `data/issues/YYYY-MM-DD.json`

```jsonc
{
  "schema": 1,
  "date": "2026-05-30",                  // primary key (Saturday publish date)
  "post_type": "issue",                  // issue | special | callout
  "title": "007 First Light is the James Bond game we've been waiting for",
  "url": "https://www.theverge.com/tech/940092/007-first-light-oura-ring-5-installer",
  "author": "David Pierce",
  "number": 293,                         // REQUIRED (int); parser extracts from intro ("welcome to Installer No. N");
                                         // null only until backfilled (validator warns; gaps filled from email copies)
  "sections_found": ["intro", "the-drop", "screen-share", "crowdsourced", "signing-off"],
  "source": "web",                       // web | email (§5.3 email fallback)
  "scraped_at": "2026-08-03T18:00:00Z",
  "parser_version": 1,
  "needs_review": false,                 // true until a human has eyeballed it
  "recommendations": [
    {
      "id": "2026-05-30-halide-mark-iii", // date + slugified name (+ "-2" on collision)
      "name": "Halide Mark III",
      "url": "https://www.lux.camera/halide-mark-iii/",  // null if unlinked; affiliate-unwrapped
      "alt_urls": ["https://www.theverge.com/tech/938339/..."],
      "category": "app",                 // app | game | media | gadget | feature | other (§4.2)
      "tags": ["ios", "photography", "paid"],
      "blurb": "Halide is still the gold standard for third-party camera apps…",
      "section": "the-drop",             // intro | the-drop | pro-tips | screen-share | crowdsourced | signing-off
      "recommender": null                // null = the author; else "Allen (reader)" / guest name
    }
  ]
}
```

`callout` posts get `recommendations: []` but still get a file — keeps discovery idempotent (won't re-surface as "new" every run). `special` posts (gift guides) contain recs and are included, filterable.

### 4.2 Categories (closed enum)

`app · game · media · gadget · feature · other`

Broad on purpose — six chips you can scan in one glance, grounded in what Installer actually recommends. Format detail (tv vs. podcast vs. book) lives in tags (§4.3), so "Media" narrows without bloating the top level. Enforced by the validator.

| Category | Covers |
|---|---|
| `app` | Software & services you can use: mobile/desktop apps, web apps, sites, tools |
| `game` | Video games — frequent enough in Installer to earn its own chip |
| `media` | Things you watch/listen/read: TV, film, video, podcasts, music, books, articles |
| `gadget` | Physical products: hardware, accessories, gear ("gadget" over "physical product" — it's the house vocabulary) |
| `feature` | A capability of an existing product rather than the product itself — e.g. Spotify's running mode, a new Halide update, an OS beta feature |
| `other` | Escape hatch (rare; if it grows, the vocabulary needs a look) |

### 4.3 Tags (controlled vocabulary — `data/tags.json`)

```jsonc
{ "format":   ["tv", "movie", "video", "podcast", "music", "book", "article", "newsletter", "website"],
  "platform": ["ios", "android", "mac", "windows", "web", "cross-platform"],
  "price":    ["free", "paid", "subscription"],
  "topic":    ["productivity", "photography", "ai", "smart-home", "fitness",
               "social", "utilities", "travel", "…grows during curation"],
  "meta":     ["open-source", "beta", "kickstarter"] }
```

Rules: tags must exist in the vocabulary (validator-enforced); adding a tag = editing `tags.json` in the same commit. This keeps filters meaningful — 40 curated tags beat 400 organic ones. Category is required; tags are best-effort.

### 4.4 Curation guidelines (consistency across 3+ years of data)

- A "recommendation" = something the author/guest/reader affirmatively suggests. Sponsor links: **exclude**. **Links to The Verge's own articles: never captured** — the archive indexes what the newsletter recommends, not the Verge's self-coverage. (Verge anchors inside an item may land in `alt_urls` as context, but never become items themselves.)
- **Every list section is captured** — The Drop, Pro Tips, Screen share, Crowdsourced, Group Project, Signing off — and every item records its `section`, which is a first-class filter in the UI ("just show me Crowdsourced finds"). The **intro/preamble is the exception** (decided 2026-08-03): it's prose, and auto-extracting its link-dumps produced fragment names and one blurb repeated across 8 rows, degrading search. The parser skips it; a genuinely notable intro find gets hand-added to the issue file with `section: "intro"`, which the UI renders fine.
- **Screen share:** capture the guest's setup — hardware lines (phone, watch, e-reader…) as `gadget` items, listed apps as `app` items, all with `recommender` = the guest. Prune only bare OS defaults with zero commentary (Phone, Settings, Messages) during review.
- Unlinked-but-named items (common in Crowdsourced): parser extracts linked items automatically; add notable unlinked ones by hand with `url: null`.
- Blurbs: verbatim quote, ≤300 chars, trimmed at a sentence boundary, `…` for elisions.

## 5. Scraper (Python)

### 5.1 Layout & tooling

```
scraper/                    # python package (import name: scraper)
  __init__.py __main__.py cli.py   # argparse entrypoints via `python -m scraper`
  discover.py               # sitemaps ∪ hub/archives ∪ RSS → candidate URLs
  fetch.py                  # polite cached fetcher (UA, rate limit, backoff)
  parse.py                  # HTML body → issue JSON (sections → items)
  enrich.py                 # heuristic category/tags (+ optional LLM assist)
  build.py                  # issues/*.json → site/data/archive.json (+ validation)
  schema.py                 # jsonschema definitions
tests/
  fixtures/                 # 3 committed sanitized bodies (2023 / 2024 / 2026) + golden JSON
  test_parse.py test_enrich.py test_build.py
pyproject.toml              # PEP 621; deps: requests, beautifulsoup4, lxml, jsonschema
```

Python 3.12+ in a plain venv. No scraping frameworks — this is ~130 pages.

### 5.2 CLI

```
python -m scraper discover            # refresh candidate URL list → data/urls.json
python -m scraper fetch               # fill data/raw/ cache (skips cached)
python -m scraper parse [--date D] [--force] [--email F]   # raw → bodies/ + issues/*.json (never clobbers)
python -m scraper enrich [--date D] [--llm]                # fill category/tags proposals in-place
python -m scraper build               # validate + compile site/data/archive.json
python -m scraper update              # the Saturday one-shot: discover→fetch→parse→enrich→build
python -m scraper validate            # schema, tag vocab, dupe ids, URL lint, month-coverage check
```

Wrapped by a `Makefile`: `make setup update build serve deploy validate test` (`serve` = `python -m http.server -d site`). Uses a plain `.venv` (`make setup`); the pyproject is standard PEP 621, so `uv` works too if installed.

### 5.3 Parser strategy

1. Locate the article body container; extract elements with the exact cms-markup class → save minimal body HTML to `data/bodies/` (committed — enables re-parsing forever without re-fetching; ~130 × 30KB ≈ 4MB).
2. Split into sections on `<h2>` text (case-insensitive, known-name map; unknown headings → warn + `needs_review`).
3. Per-section item extraction (§2.2 table). For each item: name = first anchor text (fallback: leading `<strong>` text), url = first href (unwrap Skimlinks, resolve relative → absolute, strip UTM params), blurb = remaining text trimmed to sentence boundary ≤300 chars, extra hrefs → `alt_urls`. For links found in *prose* (non-bulleted paragraphs), the blurb is scoped to **the sentence containing the link**, not the whole paragraph; old-era "( link )" markers are stripped everywhere. Anchors pointing at theverge.com are never promoted to items of their own (§4.4); if an item's *only* link is a Verge article, url = the Verge link's ultimate subject if obvious, else `null` + `needs_review`.
4. Emit issue JSON with `needs_review: true` whenever: unknown section, zero recs in The Drop, an item with no anchors, or an unrecoverable generic name.

Fixtures-first development: commit three real bodies (one per era) with hand-verified golden JSON; `pytest` locks parser behavior. When The Verge changes markup, add a fixture, bump `parser_version`.

**Email fallback:** any issue the web discovery can't find (or that later goes 404) can be ingested from the newsletter email itself — drop the raw email HTML at `data/email/YYYY-MM-DD.html` and run `archive parse --email data/email/YYYY-MM-DD.html`. Email markup is inline-styled table soup, so this path matches on section heading *text* rather than CSS classes, marks the whole issue `needs_review`, and sets `"source": "email"`. It only needs to be good enough for a handful of gap issues — heavier manual cleanup is acceptable here.

### 5.4 Enrichment

- **Heuristic pass (deterministic):** domain → category/tags map, e.g. `apps.apple.com→app+ios`, `play.google.com→app+android`, `store.steampowered.com→game`, `themoviedb.org→media+tv|movie`, `netflix.com/max.com/…→media+tv`, `open.spotify.com→media+music|podcast`, `youtube.com→media+video`, `bookshop.org→media+book`, `amazon…/dp/→gadget`. Unmatched → `category: other` + `needs_review`. Note heuristics can't tell `feature` from `app` (Spotify's running mode links to spotify.com) — that distinction comes from the LLM pass or the curator.
- **LLM assist (optional, `--llm`):** pipe name+blurb+vocabulary through `claude -p` requesting JSON `{category, tags}` constrained to the enums; write proposals into the issue file. Always human-reviewed via git diff before commit — the LLM proposes, the curator disposes.

### 5.5 Weekly flow (Saturday, ~10 minutes)

```
make update          # detects the new issue via RSS/sitemap, fetches, parses, enriches
git diff data/       # review the one new file; fix names/categories/tags/blurbs
make validate build deploy
git commit -am "Installer 2026-08-08" && git push
```

Optional later: a GitHub Action (cron Sat 16:00 UTC) runs `archive update` and opens a PR with the new issue file; merging deploys. Not v1 — manual first, automate once the parser has proven itself for a month or two.

## 6. Build artifact — `site/data/archive.json`

```jsonc
{ "generated_at": "…", "issue_count": 132, "rec_count": 3140,
  "tags": { …vocabulary… },
  "issues": [ { "date", "title", "url", "author", "post_type" } ],
  "recommendations": [ { "id", "name", "url", "category", "tags", "blurb",
                         "section", "recommender", "date", "position" } ] }
```

Flat, denormalized where cheap (`date` on each rec; client joins to `issues` for titles). `position` preserves in-issue order for stable sorting. Build fails on: schema violation, unknown tag/category, duplicate id, rec count dropping vs. last build (deletion guard, `--allow-shrink` to override).

**Size estimate:** ~3,000 recs × ~450B ≈ 1.4MB raw → **~200–300KB with CloudFront brotli**. One file, loaded async. If it ever exceeds ~5MB raw, split by year and lazy-load older — explicitly not needed now.

## 7. Frontend

### 7.1 Stack decision

**No build step. No framework.** `index.html` + ES modules + CSS custom properties. Search via **MiniSearch** (~7KB gzipped, vendored into `site/vendor/` — no CDN, no npm). Rationale: the site is one interactive view over one JSON file; a framework adds a toolchain to a project whose Python side already handles data compilation. Everything CloudFront serves is exactly what's in git. (Alternative considered: Astro — better if we later want per-issue static pages; revisit then.)

```
site/
  index.html
  css/base.css css/theme-clean.css css/theme-98.css
  js/app.js js/search.js js/filters.js js/render.js js/urlstate.js
  vendor/minisearch.js
  data/archive.json        # build output (gitignored)
```

### 7.2 UI spec (the point of the whole project)

Layout — single-column **row list** (an index, not a card grid — rows scan better at 3,000 items):

```
┌────────────────────────────────────────────────────────────────┐
│  INSTALLER ARCHIVE          3,140 recommendations · 132 issues │
│  Everything The Verge's Installer has ever recommended. [About]│
│  ┌──────────────────────────────────────────────┐              │
│  │ 🔍  Search apps, games, gadgets…          [/]│  Sort: Newest│
│  └──────────────────────────────────────────────┘              │
│  [All] [Apps] [Games] [Media] [Gadgets] [Features] [Other]     │
│  Section: [The Drop] [Screen share] [Crowdsourced] [Intro] [+2]│
│  Tags: [free] [ios] [productivity] [ai] [+ 34 more]            │
├────────────────────────────────────────────────────────────────┤
│  Halide Mark III                                    APP · PAID │
│  "Still the gold standard for third-party camera apps…"        │
│  ios · photography     ↳ Installer, May 30 2026 · The Drop     │
├────────────────────────────────────────────────────────────────┤
│  Spider-Noir                                        MEDIA · TV │
│  …                                                             │
└────────────────────────────────────────────────────────────────┘
```

Each row: **name** (external link to the thing), category badge, blurb, tag chips (clickable → adds filter), source line linking to the issue on theverge.com, recommender when not the author.

Behavior:
- **Search:** MiniSearch over `name` (boost 3), `tags` (boost 2), `blurb`, `recommender`; prefix matching + slight fuzziness; debounced ~80ms; results update live with count ("214 results"). Structured filters apply as post-filter AND.
- **Filters:** category (single-select chips), section (Intro / The Drop / Pro Tips / Screen share / Crowdsourced / Signing off), tags (multi, AND), year. **Sort:** newest (default, date desc + position), oldest, A–Z, random (shuffle button — a browse mode, in the newsletter's discovery spirit).
- **URL state:** every search/filter/sort serializes to query params (`?q=camera&cat=app&tags=ios,free&year=2025&sort=az`) via `replaceState` — shareable/bookmarkable, back-button safe, and needs zero CloudFront routing config (no path rewrites).
- **Keyboard:** `/` focuses search, `Esc` clears, arrows navigate rows, `Enter` opens.
- **Rendering:** render first ~150 rows, extend on scroll (IntersectionObserver sentinel) — no virtual-scroll library.
- **A11y:** semantic `<ul>`, real `<a>`s, `aria-live="polite"` result count, visible focus, contrast ≥4.5:1, `prefers-reduced-motion` respected.
- **States:** loading skeleton while JSON fetches; friendly empty state with "clear filters".
- **Admin mode (curator-only):** `?admin=1` reveals a per-row ✕ that marks entries for deletion (localStorage; rows hide immediately). An admin bar offers Download deletions.json / Copy IDs / Un-mark all / Exit; `python -m scraper delete --file deletions.json` applies the marks to `data/issues/` permanently. On the public site the param only ever hides rows in the visitor's own browser.

Design (revised 2026-08-03): a **committed dark theme** (`css/theme.css`, no light variant) — deep neutral surfaces, violet accent, entries as bordered horizontal cards with hover lift. Full-bleed site bar (title + About), subtitle + stat figures, then a sticky toolbar carrying the search field *and* the category chips (horizontally scrollable on small screens); Section/Year/Tags collapse behind "More filters". Category badges carry inlined Lucide icons. All colors as custom properties on `:root`.

**Performance budget:** shell (HTML+CSS+JS) <50KB gzipped; interactive <1s on cable, <2.5s on 3G; search keystroke→paint <16ms; Lighthouse ≥95 across the board.

### 7.3 Windows 98 theme (built 2026-08-03, dropped same day)

A full 98.css-based skin was shipped and then removed: fun, but not readable enough for the site's actual purpose. The implementation lives in git history (`ebf59c3`, removed the following commit) if nostalgia ever wins — it was a viewport-height window on the teal desktop with an Explorer-style listview and per-row icons from win98icons.alexmeub.com. Effort now goes into refining the single modern theme.

**Filter disclosure (added with the removal):** category chips sit directly under the search bar as the primary filter; Section, Year, and Tag rows collapse behind a "More filters ▾" toggle. Deep links carrying hidden filters auto-expand the panel, and the collapsed button shows an active-filter count ("More filters (2) ▾").

## 8. Hosting & deploy

Standard alexmeub.com stack — nothing new required:

- Private S3 bucket (`installer-archive-site`) + CloudFront with OAC, ACM cert (us-east-1) for `installerarchive.alexmeub.com`, Route53 A/AAAA alias. Compression (brotli+gzip), HTTP/2+3, default root object `index.html`. No custom error pages needed (query-param routing only).
- **Cache strategy:** `index.html` + `data/archive.json` → `Cache-Control: public, max-age=300, must-revalidate`; css/js/vendor/fonts → `max-age=31536000, immutable` only if we later add content hashes — until then, 1 day + deploy-time invalidation.
- `scripts/deploy.sh`: `archive build` → `aws s3 sync site/ s3://… --delete` (with per-type cache-control) → `aws cloudfront create-invalidation --paths "/*"` (single-digit files; blanket invalidation is fine and free at this scale).

## 9. Milestones

| # | Deliverable | Acceptance |
|---|---|---|
| 0 | Repo scaffold: pyproject, Makefile, schema, README, this spec | `make validate` runs green on empty data |
| 1 | Discovery + fetcher | `data/urls.json` lists every issue; all pages cached; month-coverage check passes |
| 2 | Parser + fixtures | 3 era fixtures with golden JSON pass; full backfill parses with <15% `needs_review` |
| 3 | Backfill curation | All issues reviewed, categorized, tagged; `validate` green — **the dataset is the asset** |
| 4 | Site v1 (clean theme) | Search/filter/sort/URL-state/keyboard all work; perf budget met; deployed to prod |
| 5 | Weekly loop proven | Two consecutive Saturdays updated in <10 min each |
| 6 | Win98 theme | Toggle ships; theme parity on all states (loading/empty/error) |
| 7+ | Ideas parking lot | GoatCounter analytics (decided yes — wire up post-launch), dedupe view ("recommended 4×" grouped by canonical URL), stats page (most-recommended, per-year), per-issue pages, OG images, RSS feed of the archive itself |

Suggested build order runs data-first (milestones 1–3 before 4): the UI is the point, but it's only as good as the dataset under it, and curation is the long pole.

## 10. Decisions log

Resolved 2026-08-03:
- Verge self-links are never captured as items; every newsletter section (preamble through Signing off) is captured and section-tagged; categories are the broad six of §4.2 with `feature` for capabilities of existing products; email HTML from the subscriber inbox is the fallback source for issues the web archive can't supply.
- **Issue numbers are required.** The parser extracts them from the intro line ("welcome to Installer No. N"); the validator warns on nulls, gaps, and duplicates in the sequence; remaining nulls get filled manually from email copies. Displayed as "Installer No. N" throughout the UI.
- **Analytics: GoatCounter, post-launch.** `index.html` ships with the script tag present but commented out; wiring it up is a parking-lot item once the site is live and an account exists.
- **Verge ToS: accepted risk.** Proceeding as a light-touch, attributed, traffic-driving fan index with an honest UA and takedown contact.
