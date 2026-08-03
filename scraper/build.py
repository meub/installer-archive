"""Validate curated issue files and compile the site's archive.json."""
import json
from collections import Counter
from datetime import datetime, timezone

import jsonschema

from scraper.config import FIRST_MONTH, ISSUES, SITE_DATA, TAGS_FILE
from scraper.schema import CANON_SECTIONS, ISSUE_SCHEMA

ARTIFACT = SITE_DATA / "archive.json"


def load_issues() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(ISSUES.glob("*.json")):
        if path.name.endswith(".proposed.json"):
            continue
        out.append((path.name, json.loads(path.read_text())))
    return out


def _months_between(first: tuple[int, int], last: tuple[int, int]) -> list[str]:
    y, m = first
    out = []
    while (y, m) <= last:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def run(check_only: bool = False, allow_shrink: bool = False) -> int:
    issues = load_issues()
    if not issues:
        print("build: no issue files yet — nothing to do")
        return 0

    groups = json.loads(TAGS_FILE.read_text())
    tag_vocab = {t for tags in groups.values() for t in tags}
    validator = jsonschema.Draft202012Validator(ISSUE_SCHEMA)

    errors: list[str] = []
    warnings: list[str] = []
    all_recs: list[dict] = []
    issue_meta: list[dict] = []
    id_counts: Counter = Counter()

    for fname, issue in issues:
        for err in validator.iter_errors(issue):
            errors.append(f"{fname}: {err.message} (at {'/'.join(str(p) for p in err.path)})")
        if issue.get("number") is None and issue.get("post_type") == "issue":
            warnings.append(f"{fname}: number is null")
        if issue.get("needs_review"):
            warnings.append(f"{fname}: needs_review")
        for pos, rec in enumerate(issue.get("recommendations", [])):
            id_counts[rec["id"]] += 1
            if rec.get("category") is None:
                warnings.append(f"{fname}: {rec['id']}: no category")
            for t in rec.get("tags", []):
                if t not in tag_vocab:
                    errors.append(f"{fname}: {rec['id']}: tag '{t}' not in data/tags.json")
            if rec.get("section") not in CANON_SECTIONS:
                warnings.append(f"{fname}: {rec['id']}: non-canonical section '{rec.get('section')}'")
            if rec.get("url") and not rec["url"].startswith(("http://", "https://")):
                errors.append(f"{fname}: {rec['id']}: bad url {rec['url']}")
            if len(rec.get("blurb", "")) > 320:
                warnings.append(f"{fname}: {rec['id']}: blurb over limit")
            all_recs.append({
                "id": rec["id"],
                "name": rec["name"],
                "url": rec["url"],
                "category": rec["category"],
                "tags": rec.get("tags", []),
                "blurb": rec.get("blurb", ""),
                "section": rec.get("section"),
                "recommender": rec.get("recommender"),
                "date": issue["date"],
                "position": pos,
            })
        issue_meta.append({
            "date": issue["date"],
            "number": issue.get("number"),
            "title": issue["title"],
            "url": issue["url"],
            "author": issue.get("author"),
            "post_type": issue.get("post_type", "issue"),
        })

    for rec_id, n in id_counts.items():
        if n > 1:
            errors.append(f"duplicate rec id across issues: {rec_id} (x{n})")

    # issue-number sequence sanity
    numbered = sorted(
        [(i["date"], i["number"]) for i in issue_meta if i["number"] is not None and i["post_type"] == "issue"]
    )
    num_counts = Counter(n for _, n in numbered)
    for n, c in num_counts.items():
        if c > 1:
            warnings.append(f"issue number {n} appears {c}x")
    for (d1, n1), (d2, n2) in zip(numbered, numbered[1:]):
        if n2 < n1:
            warnings.append(f"issue number decreases {n1}->{n2} ({d1} -> {d2})")
        elif n2 - n1 > 1:
            warnings.append(f"issue number gap {n1}->{n2} ({d1} -> {d2})")

    # month coverage: a month with <4 real issues may mean discovery missed some
    real_issues = [i for i in issue_meta if i["post_type"] == "issue"]
    if real_issues:
        by_month = Counter(i["date"][:7] for i in real_issues)
        last = max(i["date"] for i in real_issues)
        months = _months_between(FIRST_MONTH, (int(last[:4]), int(last[5:7])))
        for month in months[:-1]:  # current month is allowed to be partial
            if by_month.get(month, 0) < 4:
                warnings.append(f"month {month}: only {by_month.get(month, 0)} issues — check for missed weeks")

    # newest issue first, in-issue order preserved
    all_recs.sort(key=lambda r: (r["date"], -r["position"]))
    all_recs.reverse()
    issue_meta.sort(key=lambda i: i["date"], reverse=True)

    artifact = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "issue_count": len(real_issues),
        "rec_count": len(all_recs),
        "tags": groups,
        "issues": issue_meta,
        "recommendations": all_recs,
    }

    if ARTIFACT.exists() and not allow_shrink:
        old = json.loads(ARTIFACT.read_text())
        if len(all_recs) < old.get("rec_count", 0):
            errors.append(
                f"rec count shrank {old['rec_count']} -> {len(all_recs)} (pass --allow-shrink if intended)"
            )

    for w in warnings[:40]:
        print(f"  warn: {w}")
    if len(warnings) > 40:
        print(f"  … and {len(warnings) - 40} more warnings")
    for e in errors:
        print(f"  ERROR: {e}")

    print(
        f"{'validate' if check_only else 'build'}: {len(real_issues)} issues, "
        f"{len(all_recs)} recommendations, {len(warnings)} warnings, {len(errors)} errors"
    )
    if errors:
        return 1
    if not check_only:
        SITE_DATA.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n",
                            encoding="utf-8")
        print(f"build: wrote {ARTIFACT} ({ARTIFACT.stat().st_size // 1024} KB)")
    return 0
