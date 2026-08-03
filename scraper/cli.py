import argparse
import sys
from pathlib import Path

from scraper import build, discover, enrich, fetch, parse


def _actionable(posts: dict) -> list[str]:
    return [u for u, m in posts.items() if m.get("status") in ("pending", "confirmed")]


def cmd_fetch(_args) -> int:
    state = discover.load_state()
    todo = _actionable(state["posts"])
    print(f"fetch: {len(todo)} URLs (cached ones are free)")
    fetched = errors = 0
    for url in todo:
        try:
            fetch.get(url)
            fetched += 1
        except Exception as e:
            print(f"  ! {url}: {e}")
            state["posts"][url]["status"] = "error"
            errors += 1
    discover.save_state(state)
    print(f"fetch: done ({fetched} ok, {errors} errors)")
    return 0


def cmd_parse(args) -> int:
    if args.email:
        src = Path(args.email)
        title, date = args.title, args.date
        if src.suffix.lower() == ".eml":
            import email as email_mod
            import email.policy
            from email.utils import parsedate_to_datetime
            msg = email_mod.message_from_bytes(src.read_bytes(), policy=email.policy.default)
            body = msg.get_body(preferencelist=("html",))
            if body is None:
                print(f"parse: no HTML part in {src.name}")
                return 1
            html = body.get_content()
            title = title or str(msg["Subject"] or "")
            if not date and msg["Date"]:
                date = parsedate_to_datetime(msg["Date"]).date().isoformat()
        else:
            html = src.read_text(encoding="utf-8")
        date = date or src.stem[:10]
        issue = parse.parse_email(html, date=date, title=title, number=args.number)
        path, action = parse.write_issue(issue, body=None, force=args.force)
        print(f"parse: {action} {path} — No. {issue['number']}, "
              f"{len(issue['recommendations'])} recs, sections: {issue['sections_found']}")
        return 0

    state = discover.load_state()
    posts = state["posts"]
    seen_canonical = {
        m["canonical"]: u for u, m in posts.items() if m.get("canonical")
    }
    parsed = rejected = skipped = 0
    try:
        for url, meta in posts.items():
            if meta.get("status") in ("rejected", "duplicate", "error"):
                continue
            if args.date and meta.get("date") != args.date:
                continue
            if meta.get("file") and (parse.ISSUES / meta["file"]).exists() and not args.force:
                skipped += 1
                continue
            try:
                _, html = fetch.get(url)
            except Exception as e:
                print(f"  ! fetch {url}: {e}")
                meta["status"] = "error"
                continue
            page = parse.extract_page(html)
            if not parse.is_installer_post(page["soup"]):
                meta["status"] = "rejected"
                rejected += 1
                continue
            canon = page["canonical"] or url
            owner = seen_canonical.get(canon)
            if owner and owner != url:
                meta["status"] = "duplicate"
                meta["canonical"] = canon
                continue
            seen_canonical[canon] = url
            try:
                issue = parse.build_issue(page)
            except Exception as e:
                print(f"  ! parse {url}: {e}")
                meta["status"] = "error"
                continue
            path, action = parse.write_issue(issue, parse.body_html(page["body"]), args.force)
            meta.update({
                "status": "confirmed",
                "canonical": canon,
                "date": issue["date"],
                "title": issue["title"],
                "number": issue["number"],
                "file": Path(path).name.replace(".proposed", ""),
            })
            flag = " ⚑review" if issue["needs_review"] else ""
            num = f"No. {issue['number']}" if issue["number"] else "No. ???"
            print(f"  {action}: {issue['date']} {num:>8} [{issue['post_type']:7}] "
                  f"{len(issue['recommendations']):3} recs{flag}  {issue['title'][:56]}")
            parsed += 1
    finally:
        discover.save_state(state)
    print(f"parse: {parsed} parsed, {skipped} already curated, {rejected} rejected as non-Installer")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scraper", description="Installer Archive pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover", help="refresh candidate URL list")
    sub.add_parser("fetch", help="fill the raw page cache")

    p = sub.add_parser("parse", help="parse cached pages into issue JSON")
    p.add_argument("--date", help="only this issue date (YYYY-MM-DD)")
    p.add_argument("--force", action="store_true",
                   help="re-parse existing issues into .proposed.json")
    p.add_argument("--email", help="parse a saved newsletter email (.eml or .html)")
    p.add_argument("--title", help="issue title (email mode; default: Subject header)")
    p.add_argument("--number", type=int, help="issue number (email mode)")

    e = sub.add_parser("enrich", help="propose categories/tags")
    e.add_argument("--date", action="append", help="limit to issue date(s)")
    e.add_argument("--llm", action="store_true", help="use `claude -p` for leftovers")

    b = sub.add_parser("build", help="validate + compile site/data/archive.json")
    b.add_argument("--allow-shrink", action="store_true")

    sub.add_parser("validate", help="checks only, write nothing")
    sub.add_parser("update", help="discover + fetch + parse + enrich + build")

    args = ap.parse_args(argv)

    if args.cmd == "discover":
        discover.run()
        return 0
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "parse":
        return cmd_parse(args)
    if args.cmd == "enrich":
        enrich.run(dates=args.date, llm=args.llm)
        return 0
    if args.cmd == "build":
        return build.run(allow_shrink=args.allow_shrink)
    if args.cmd == "validate":
        return build.run(check_only=True)
    if args.cmd == "update":
        discover.run()
        cmd_fetch(args)
        rc = cmd_parse(argparse.Namespace(date=None, force=False, email=None, title=None))
        if rc:
            return rc
        enrich.run()
        return build.run()
    return 2


if __name__ == "__main__":
    sys.exit(main())
