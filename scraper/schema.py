from scraper.config import CATEGORIES, POST_TYPES, SECTIONS

REC_SCHEMA = {
    "type": "object",
    "required": ["id", "name", "url", "category", "tags", "blurb", "section", "recommender"],
    "properties": {
        "id": {"type": "string", "minLength": 3},
        "name": {"type": "string", "minLength": 1},
        "url": {"type": ["string", "null"]},
        "alt_urls": {"type": "array", "items": {"type": "string"}},
        "category": {"enum": CATEGORIES + [None]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "blurb": {"type": "string"},
        "section": {"type": "string", "minLength": 1},
        "recommender": {"type": ["string", "null"]},
    },
    "additionalProperties": True,
}

ISSUE_SCHEMA = {
    "type": "object",
    "required": [
        "schema", "date", "post_type", "title", "url", "author", "number",
        "source", "scraped_at", "parser_version", "needs_review", "recommendations",
    ],
    "properties": {
        "schema": {"const": 1},
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "post_type": {"enum": POST_TYPES},
        "title": {"type": "string", "minLength": 1},
        "url": {"type": ["string", "null"]},
        "author": {"type": ["string", "null"]},
        "number": {"type": ["integer", "null"]},
        "sections_found": {"type": "array", "items": {"type": "string"}},
        "source": {"enum": ["web", "email"]},
        "needs_review": {"type": "boolean"},
        "recommendations": {"type": "array", "items": REC_SCHEMA},
    },
    "additionalProperties": True,
}

CANON_SECTIONS = set(SECTIONS)
