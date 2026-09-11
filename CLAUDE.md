# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only crawler/parser for 3830scores.com (ham radio contest score
rumors), built as a single-file CLI/library (`src/scores3830.py`) so an AI
agent can shell out to it (JSON in/out) or import it directly.

Don't raise `MIN_INTERVAL`, remove the `X-Requested-By` identifying header,
or point this tool's fetching logic at any other site without checking
`SECURITY.md` for the host-allowlist guard that enforces where it's allowed
to fetch from in code.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt + pytest

pytest                                 # full suite (~107 tests, offline, <2s)
pytest tests/test_get_scores.py        # one file
pytest tests/test_get_scores.py::TestBreakdownScoresWithBands::test_band_names_are_real_band_labels_not_placeholders  # one test

python3 src/scores3830.py find-call N5ZY   # CLI, JSON to stdout; see README for all subcommands
```

There is no build/compile step and no linter run locally by convention
(flake8 config in `.flake8` exists only for the conda CI workflow below).
Source lives under `src/`; `pytest.ini` sets `pythonpath = src` so tests
import `scores3830` directly — a library caller outside pytest needs
`PYTHONPATH=src` (or an equivalent `sys.path` insert) for the same import
to work.

### CI

- `.github/workflows/tests.yml` — pip install + pytest, the primary CI check.
- `.github/workflows/python-package-conda.yml` — same test suite via a
  conda env built from `environment.yml`. Keep `environment.yml`'s pinned
  deps and this workflow's Python version in sync with `requirements.txt`
  and `tests.yml` if either changes.
- `.github/dependabot.yml` — weekly PRs bumping `requests`/`beautifulsoup4`/
  `pytest`; `tests.yml` gates whether a bump PR is safe to merge.

## Architecture

### It's a crawler, not a URL-builder — this is the load-bearing fact

Every data page on 3830scores.com is addressed by an opaque `arg=` token
that looks encrypted and is only discoverable by following a link found on
some other page. There is no way to construct "scores for contest X on
date Y" from parameters. Consequently every function in `src/scores3830.py`
either starts from one of two stable, guessable entry points or takes a
URL scraped from a previous call's output:

```
contests.php ──────────────► listeditions.php?arg=… ──► breakdownscores.php?arg=…
findcall.php?call=X ───┬───► editionscores.php?arg=…
                        └───► showrumor.php?arg=…   (one competitor's full post + soapbox)
```

`find_call()` and `list_contests()` are the two stable entries;
`search_contests()` is a local fuzzy-match layer over `list_contests()`
(the site has no search endpoint of its own). Everything downstream
(`list_editions`, `get_scores`, `get_rumor`) takes a URL harvested from a
prior call and has no other way to be reached.

### `get_scores()` auto-detects two incompatible table layouts

`breakdownscores.php` (flat table, per-band Q/Mlt columns, class name +
band-name labels combined into one header `<tr>`) and `editionscores.php`
(grouped by class under separate `<strong>` header rows, OpMode/Club
columns, no per-band breakdown) are structurally different pages that both
funnel into the same `ScoreRow` shape. The branch is chosen by checking for
an `OpMode` column header — see the two failure modes already fixed once
(band values desyncing when a blank `<td>` was dropped instead of kept as a
positional `None`; band names coming out as placeholder `"col0"`/`"col1"`
instead of the real header text) before touching that function again.

### `_clean()` is where cross-cutting text normalization lives

Two site-wide quirks are handled centrally in this one helper rather than
per-caller: HTML entity decoding, and normalizing the ham-radio "slashed
zero" (`Ø`/`ø`, used in callsigns to distinguish `0` from letter `O`) back
to a plain digit `0`. Any new field-extraction code should route text
through `_clean()` rather than reimplementing either.

### Testing pattern: `FakeFetcher`, not mocked HTTP

`tests/conftest.py`'s `FakeFetcher` subclasses `Fetcher` and serves frozen
HTML snapshots from `tests/fixtures/` keyed by **exact URL** in
`URL_TO_FIXTURE`. It raises loudly (not silently) if code under test
requests a URL with no fixture mapped. Adding a test against a new page
shape means fetching that page once for real, saving it under
`tests/fixtures/`, and adding it to `URL_TO_FIXTURE` — see the fixture doc
comments in `conftest.py` and `test_get_scores.py`/`test_get_rumor.py` for
what each existing fixture covers (which layout/edge case it's pinned to).
`Fetcher`'s own plumbing (caching, rate limiting, the host allowlist) is
tested separately in `test_fetcher.py` by mocking `requests.Session.get`
directly, since that's testing the HTTP layer itself rather than page
parsing.

### The host allowlist is a security control, not incidental validation

`Fetcher.get()` rejects any URL whose hostname isn't `3830scores.com` or a
subdomain of it, checked via `urlparse().hostname` (not string
matching — lookalikes like `evil3830scores.com` must still be rejected).
This exists because `get_scores(url)`/`get_rumor(url)`/`list_editions(url)`
all accept a URL from the caller; without the check this tool is an open
fetcher of anything on the internet, SSRF included. Don't loosen this to a
substring/`startswith` check when touching that code.
