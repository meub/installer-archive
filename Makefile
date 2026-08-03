VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup discover fetch parse enrich build validate update serve test deploy

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e ".[dev]"

discover:
	$(PY) -m scraper discover

fetch:
	$(PY) -m scraper fetch

parse:
	$(PY) -m scraper parse

enrich:
	$(PY) -m scraper enrich

build:
	$(PY) -m scraper build

validate:
	$(PY) -m scraper validate

# The Saturday one-shot: discover -> fetch -> parse -> enrich -> build
update:
	$(PY) -m scraper update

serve:
	@echo "http://localhost:8321"
	$(PY) -m http.server 8321 -d site

test:
	$(VENV)/bin/pytest -q

deploy: build
	./scripts/deploy.sh
