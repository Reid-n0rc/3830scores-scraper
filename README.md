# scores3830

A crawler/parser for [3830scores.com](https://www.3830scores.com/), the
ham radio contest "score rumors" site.

## Why this is a crawler, not a URL-builder

Every data page on 3830scores.com is addressed by an opaque, encrypted-looking
`arg=` token that only shows up by following a link from some other page —
there's no way to construct "scores for contest X on date Y" from parameters.
So this tool always starts from one of two stable, guessable entry points and
crawls from there:

- `find_call(callsign)` → `findcall.php?call=CALLSIGN` — one operator's full
  contest history
- `list_contests()` → `contests.php` — every contest name mapped to its
  edition-list URL

From either you follow the chain the site itself defines:

```
contests.php ──────────────► listeditions.php?arg=… ──────► breakdownscores.php?arg=…
findcall.php?call=X ───┬───► editionscores.php?arg=…
                        └───► showrumor.php?arg=…   (one competitor's full post + comment)
```

## Install

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Test

```
pip install -r requirements-dev.txt
pytest
```

All 100+ tests run fully offline against frozen HTML snapshots in
`tests/fixtures/` (via `tests/conftest.py`'s `FakeFetcher`) — no test ever
makes a real request to 3830scores.com. Coverage includes each parser
(across the different page layouts the site actually uses), the
slashed-zero (`Ø`→`0`) normalization, the HTTP layer's caching/rate-limiting,
the host-allowlist SSRF guard (see [SECURITY.md](SECURITY.md)), and the CLI
end to end.

## Use from a shell / by an agent

Every subcommand prints JSON to stdout — this is the intended interface for
Claude or any other agent to shell out to via a Bash-style tool, no Python
import needed:

```
python3 src/scores3830.py find-call N5ZY
python3 src/scores3830.py list-contests
python3 src/scores3830.py search-contests "sprint" --limit 5
python3 src/scores3830.py list-editions "https://www.3830scores.com/listeditions.php?arg=..."
python3 src/scores3830.py get-scores "https://www.3830scores.com/breakdownscores.php?arg=..."
python3 src/scores3830.py get-rumor "https://www.3830scores.com/showrumor.php?arg=..."
```

`search-contests` fuzzy-matches against the ~300+ names in `list_contests()`
(there's no search endpoint on the site itself, so this fetches the full
index once and ranks it locally) — good for "sprint" → every *Sprint
contest, weaker for abbreviations with no literal substring match (e.g.
`"cq ww"` doesn't score highly against "CQ World Wide DX Contest" since
that exact substring isn't in the name). Try the fuller name if a query
comes back thin.

`get_rumor()` / `get-rumor` returns each competitor's soapbox post as
`soapbox_text` + `soapbox_date` (labeled "Comments:" on the page itself —
"soapbox" is the term used elsewhere in contesting, kept here for
clarity). It's unparsed free-text prose; see Limitations.

Add `--no-cache` to any of them to bypass the on-disk response cache (default
TTL 6h, in `.cache/`).

## Use as a library

The module lives in `src/`, so either run with `PYTHONPATH=src` or add
`src/` to `sys.path` yourself:

```python
import sys
sys.path.insert(0, "src")

from scores3830 import Fetcher, find_call, get_rumor

f = Fetcher()
history = find_call("N5ZY", f)
rumor = get_rumor(history[0].rumor_url, f)
print(rumor.total_score, rumor.soapbox_text)
```

## Limitations

- **Undocumented, unversioned HTML.** There's no schema contract — a site
  redesign silently breaks these parsers, and the only signal you'll get is
  a test failing or fields coming back empty/`None`.
- **No bulk/date-range query.** "Current contests" is whatever's in the nav
  on the day you ask. Pulling full history means walking `contests.php` →
  every `listeditions.php` link → every `breakdownscores.php` link, which is
  a lot of requests for a full historical crawl. Rate-limited to ~1 req/sec
  by default on purpose.
- **Two different table layouts, auto-detected, imperfectly.**
  `breakdownscores.php` gives one flat table with per-band Q/Mlt columns and
  a combined class-header+band-name row; `editionscores.php` groups rows
  under plain class-name header rows with no per-band breakdown at all.
  `get_scores()` picks a branch based on whether it sees an `OpMode` column
  header — an unusual page could confuse that heuristic.
  Also, not every contest type on this site tracks a "Mults" column at all
  (e.g. simple contests like 10-10 SSB just show Call/Score/QSOs) — a
  `None` for `mults`/`bands` can mean "this contest doesn't report that,"
  not "parsing failed."
- **Rumor comment text is unparsed prose.** `get_rumor()` returns the
  free-text comment as one string; no attempt is made to extract structured
  info (equipment, callouts, etc.) from it.
- **Field layout varies by contest type.** VHF-contest rumor pages, for
  example, often omit "Operating Time" and "Location" entirely — expect
  empty strings there, not an error.
- **No handling of the site's own filters** (location/club dropdowns on
  breakdownscores.php) — this always pulls the unfiltered table.
- **Email addresses are obfuscated** on `showrumor.php` via HTML numeric
  character references, specifically to defeat scraping. This tool doesn't
  even attempt to decode/harvest them — repurposing any of this for email
  harvesting is out of scope for what Bruce approved.

## License

GNU Affero General Public License v3.0 (AGPLv3) — see [LICENSE](LICENSE).
Note this is separate from, and doesn't affect, the site-access
authorization described above: the AGPL governs reuse of this *code*,
not permission to access 3830scores.com itself.
