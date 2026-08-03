from scraper.util import clean_url, is_verge, sentence_trim, slugify


def test_skimlinks_unwrap():
    wrapped = ("https://go.skimresources.com/?id=1025X1701640&xs=1"
               "&url=https%3A%2F%2Fouraring.com%2Fstore%2Frings%2Foura-ring-5")
    assert clean_url(wrapped) == "https://ouraring.com/store/rings/oura-ring-5"


def test_impact_style_unwrap():
    wrapped = "https://hatch.sjv.io/c/482924/1067883/13693?u=https%3A%2F%2Fwww.hatch.co%2F"
    assert clean_url(wrapped) == "https://www.hatch.co/"


def test_relative_verge_resolved():
    assert clean_url("/tech/938339/some-story") == "https://www.theverge.com/tech/938339/some-story"
    assert is_verge(clean_url("/tech/938339/some-story"))


def test_tracking_params_stripped():
    assert clean_url("https://example.com/x?utm_source=verge&id=5") == "https://example.com/x?id=5"


def test_junk_schemes_dropped():
    assert clean_url("mailto:installer@theverge.com") is None
    assert clean_url("#section") is None


def test_sentence_trim():
    text = "First sentence here. " + "word " * 100
    out = sentence_trim(text, 60)
    assert out == "First sentence here."
    assert len(sentence_trim("x" * 500, 300)) <= 301  # ellipsis allowed


def test_slugify():
    assert slugify("Halide Mark III") == "halide-mark-iii"
    assert slugify("Spider-Noir!") == "spider-noir"
