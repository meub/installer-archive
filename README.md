# Installer Archive

A clean, searchable index of everything recommended in [Installer](https://www.theverge.com/installer-newsletter), The Verge's weekly newsletter by David Pierce.

**Live site:** https://installerarchive.alexmeub.com · **Repo:** https://github.com/meub/installer-archive

Every app, game, show, gadget, and reader find from every issue — captured, tagged, and filterable by category, newsletter section, and year. See [SPEC.md](SPEC.md) for the full technical design.

## How it works

```
theverge.com → scraper (Python) → data/issues/*.json (curated, in git)
                                        ↓ build
                          site/data/archive.json → static site (vanilla JS) → S3/CloudFront
```

- `data/issues/*.json` is the source of truth: the scraper writes each issue once, humans curate categories/tags, git tracks it. The scraper never overwrites curated files.
- The site is a no-build static page that searches the compiled JSON client-side.

## Development

```bash
make setup      # create .venv and install deps
make update     # discover + fetch + parse + enrich + build (the Saturday one-shot)
make serve      # local site at http://localhost:8321
make test       # parser tests against committed fixtures
make validate   # schema + vocabulary + coverage checks
make deploy     # build + s3 sync + CloudFront invalidation
```

Weekly flow when a new issue lands (Saturdays ~8am ET): `make update`, review the new file under `data/issues/` in a git diff, fix tags/categories, `make deploy`, commit.

Issues the web archive can't supply can be ingested from the newsletter email itself: save the raw HTML to `data/email/YYYY-MM-DD.html` and run `.venv/bin/python -m scraper parse --email data/email/YYYY-MM-DD.html`.

## Disclaimer

Unofficial fan project — not affiliated with The Verge or Vox Media. The archive stores only names, links, and short attributed excerpts, and every entry links back to the issue it came from. Content concerns: alexmeub@gmail.com. Code is MIT licensed.
