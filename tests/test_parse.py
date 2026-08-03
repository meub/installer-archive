"""Parser invariants locked against real committed body fixtures.

Fixtures are extracted article bodies (one per markup era). When The Verge
changes markup: add a new fixture, keep these passing, bump PARSER_VERSION.
"""
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from scraper.parse import (NUMBER_RE, body_elements, extract_items, sectionize)

FIXTURES = Path(__file__).parent / "fixtures"


def load_body(name: str):
    soup = BeautifulSoup((FIXTURES / name).read_text(encoding="utf-8"), "lxml")
    root = soup.body or soup
    return [el for el in root.children if isinstance(el, Tag)]


@pytest.fixture(scope="module")
def new_era():
    els = load_body("2026-05-30-body.html")
    sections, unknown = sectionize(els)
    items, stats = extract_items(sections)
    return els, sections, unknown, items, stats


@pytest.fixture(scope="module")
def old_era():
    els = load_body("2023-08-13-body.html")
    sections, unknown = sectionize(els)
    items, stats = extract_items(sections)
    return els, sections, unknown, items, stats


def by_section(items, section):
    return [i for i in items if i["section"] == section]


def names(items):
    return {i["name"] for i in items}


# ------------------------------------------------------------------ new era

def test_new_era_sections(new_era):
    _, sections, unknown, _, _ = new_era
    assert [s for s, _ in sections] == [
        "intro", "the-drop", "screen-share", "crowdsourced", "signing-off"]
    assert unknown == []


def test_new_era_drop(new_era):
    _, _, _, items, stats = new_era
    drop = by_section(items, "the-drop")
    assert stats["drop_items"] == len(drop) == 10
    assert {"007 First Light", "Halide Mark III", "Spider-Noir"} <= names(drop)
    halide = next(i for i in drop if i["name"] == "Halide Mark III")
    assert halide["url"] == "https://www.lux.camera/halide-mark-iii/"
    # supplementary Verge coverage goes to alt_urls, never becomes an item
    assert any("theverge.com" in u for u in halide["alt_urls"])
    assert not any("theverge.com" in (i["url"] or "") for i in items)


def test_new_era_affiliate_unwrapped(new_era):
    _, _, _, items, _ = new_era
    oura = next(i for i in items if "Oura" in i["name"])
    assert "skimresources" not in oura["url"]
    assert "ouraring.com" in oura["url"]


def test_new_era_screen_share(new_era):
    _, _, _, items, _ = new_era
    ss = by_section(items, "screen-share")
    gadgets = [i for i in ss if i["category"] == "gadget"]
    assert any("iPhone 14 Pro" in i["name"] for i in gadgets)
    # the guest's own bio link must not become an item
    assert not any("daniellesteussy" in (i["url"] or "") for i in ss)
    assert all(i["recommender"] == "Danielle" for i in ss)


def test_new_era_crowdsourced_attribution(new_era):
    _, _, _, items, _ = new_era
    cs = by_section(items, "crowdsourced")
    assert len(cs) >= 8
    imgburn = next(i for i in cs if i["name"] == "ImgBurn")
    assert imgburn["recommender"] == "Allen (reader)"


def test_new_era_number(new_era):
    els, _, _, _, _ = new_era
    text = " ".join(el.get_text(" ") for el in els)
    m = NUMBER_RE.search(text)
    assert m and m.group(1) == "130"


# ------------------------------------------------------------------ old era

def test_old_era_sections(old_era):
    _, sections, unknown, _, _ = old_era
    assert [s for s, _ in sections] == [
        "intro", "the-drop", "pro-tips", "screen-share", "crowdsourced", "signing-off"]
    assert unknown == []


def test_old_era_drop(old_era):
    _, _, _, items, stats = old_era
    drop = by_section(items, "the-drop")
    assert stats["drop_items"] == len(drop) == 8
    assert {"Callsheet", "Shortwave for Android", "The Lego Concorde"} <= names(drop)


def test_old_era_generic_link_names_recovered(old_era):
    """2023 style is `Name (link)` — names must come from the bold run."""
    _, _, _, items, _ = old_era
    cs = by_section(items, "crowdsourced")
    assert {"SoundHound", "Flighty", "Beeper"} <= names(cs)
    assert "link" not in names(items)


def test_old_era_protips_skip_unlinked_tips(old_era):
    _, _, _, items, _ = old_era
    pro = by_section(items, "pro-tips")
    assert names(pro) == {"Arc"}  # the five usage-tip bullets are not items


def test_intro_not_extracted(new_era, old_era):
    """Intro is prose, not a list — no auto-extraction (SPEC §4.4)."""
    for era in (new_era, old_era):
        assert by_section(era[3], "intro") == []


def test_blurb_limit(new_era, old_era):
    for era in (new_era, old_era):
        for item in era[3]:
            assert len(item["blurb"]) <= 320


def test_blurbs_dont_leak_names(new_era):
    _, _, _, items, _ = new_era
    halide = next(i for i in items if i["name"] == "Halide Mark III")
    assert not halide["blurb"].lower().startswith("halide mark iii")
