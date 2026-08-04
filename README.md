# Installer Archive

A searchable index of everything recommended in [Installer](https://www.theverge.com/installer-newsletter), The Verge's weekly newsletter by David Pierce.

**Live site:** https://installerarchive.alexmeub.com

Every app, game, show, gadget, and reader find from every issue, tagged and filterable by category, newsletter section, tag, and year. Anything recommended more than once collapses into a single entry that still lists each mention. [SPEC.md](SPEC.md) has the full technical design.

## How it works

```
theverge.com → scraper (Python) → data/issues/*.json (curated, in git)
                                        ↓ build
                          site/data/archive.json → static site (vanilla JS) → S3/CloudFront
```

The issue files under `data/issues/` are the source of truth. The scraper writes each one once and never overwrites it, so corrections to categories, tags, and titles survive every later run. Git tracks the result.

The site is a static page with no build step. It loads the compiled JSON and does all searching and filtering in the browser.

## Development

```bash
make setup      # create .venv and install deps
make update     # discover + fetch + parse + enrich (the Saturday one-shot)
make serve      # local site at http://localhost:8321
make test       # parser tests against committed fixtures
make validate   # schema + vocabulary + coverage checks
make deploy     # build + s3 sync + CloudFront invalidation
```

A new issue lands Saturday morning. Run `make update`, read the new file under `data/issues/` in a git diff, fix whatever the parser got wrong, then `make deploy` and commit.

A few issues never made it into the web archive at all. For those, save the newsletter email (the raw `.eml` works) into `data/email/` and parse it directly:

```bash
.venv/bin/python -m scraper parse --email data/email/2024-11-30.eml --number 62
```

Adding `?admin=1` to the site URL turns on a cleanup mode with a delete button on every entry. Marks collect in the browser, export as `deletions.json`, and `python -m scraper delete --file deletions.json` applies them to the issue files.

## Disclaimer

This is an unofficial fan project, not affiliated with The Verge or Vox Media. The archive stores names, links, and short attributed excerpts, and every entry links back to the issue it came from. Content concerns: alexmeub@gmail.com. The code is MIT licensed.
