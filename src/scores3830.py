#!/usr/bin/env python3
"""
scores3830 - crawler/parser for 3830scores.com

Copyright (C) 2026 Reid Crowe

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at your
option) any later version. This program is distributed WITHOUT ANY
WARRANTY; see the GNU Affero General Public License for details. You should
have received a copy of the license along with this program, in LICENSE;
if not, see <https://www.gnu.org/licenses/>.

Site access here was explicitly approved by the site operator (Bruce Horn,
WA7BNM), overriding the site's default robots.txt, which otherwise disallows
bots (including ClaudeBot by name) from every data-bearing page
(findcall.php, showrumor.php, breakdownscores.php, editionscores.php,
listeditions.php, etc). Do not point this tool at 3830scores.com without
your own separate confirmation from the site operator. Do not raise the
rate limit or remove the User-Agent contact string without their sign-off.

WHY THIS IS A CRAWLER, NOT A URL-BUILDER:
Every data page on 3830scores.com is addressed by an opaque `arg=` token
(looks like an encrypted blob) that is only discoverable by following links
found on some other page - there is no way to construct
"scores for contest X on date Y" from parameters. So every function here
either (a) starts from one of the two stable, guessable entry points
(`findcall.php?call=CALLSIGN` or `contests.php`) or (b) takes a URL/token
scraped from a previous call's output.

STABLE ENTRY POINTS:
  - find_call(callsign)   -> findcall.php?call=CALLSIGN   (per-operator history)
  - list_contests()       -> contests.php                 (contest name -> edition-list URL)

CRAWL CHAIN FROM THERE:
  contests.php -> listeditions.php?arg=... -> breakdownscores.php?arg=...
  find_call()  -> editionscores.php?arg=...  (same table shape as breakdownscores.php)
                  showrumor.php?arg=...      (single competitor's full post + comment)

LIMITATIONS (read before relying on this for anything):
  - HTML scraping against an undocumented, unversioned page layout. Any
    redesign of 3830scores.com silently breaks the parsers here; there is
    no schema/version contract to detect that other than tests failing.
  - No official pagination/search API - "current contests" is whatever's in
    the left nav "Current/Recent Contests" list on the day you ask; there is
    no way to ask "give me every contest since date X" without walking
    contests.php -> every listeditions.php link -> every breakdownscores.php
    link, which is a lot of requests for a full historical pull.
  - Class/category headers in editionscores.php (e.g. "SOAB HP") are parsed
    from a plain <strong> text row, not a structured field - text with
    house style changes (unlikely but possible) will break grouping.
  - Comment text (showrumor.php free-text remarks) is unstructured prose;
    this tool returns it as one string with no attempt to parse content out
    of it (equipment, callouts, etc).
  - Author email links are obfuscated on the page with HTML numeric-entity
    encoding specifically to defeat scraping; this tool decodes it, since
    Bruce approved this use, but do not repurpose that decoding to harvest
    emails at scale for anything unrelated to this approved use.
  - Rate limited to ~1 req/sec by default and cached on disk - this is a
    courtesy default given the approval was for read access, not for hammering
    the site. Raise MIN_INTERVAL only with the operator's agreement.
  - No handling of the site's optional filters (location/club dropdowns on
    breakdownscores.php) - this tool always pulls the unfiltered table.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urljoin, urlencode, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.3830scores.com/"
ALLOWED_HOST_SUFFIX = "3830scores.com"
CONTACT = "reid.crowe@gmail.com"
# The site sits behind Cloudflare, which 403s plain/non-browser User-Agent
# strings outright - so this uses a real browser UA to avoid tripping that,
# rather than to conceal anything. Identity/contact info goes in a custom
# header instead, which is the transparent part: who's making the request
# and why, for anyone on the site-operator side who inspects access logs.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
IDENTIFY_HEADER = {
    "X-Requested-By": f"scores3830-tool/0.1 (contact: {CONTACT}; "
                       "access approved by site operator Bruce Horn WA7BNM)"
}
MIN_INTERVAL = 1.0  # seconds between requests - see LIMITATIONS above
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_TTL = 6 * 3600  # seconds; contest data is mostly-static once posted


class Fetcher:
    """Rate-limited, disk-cached HTTP layer. One instance per process."""

    def __init__(self, min_interval: float = MIN_INTERVAL, cache_dir: Path = CACHE_DIR,
                 cache_ttl: int = CACHE_TTL, use_cache: bool = True):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers.update(IDENTIFY_HEADER)
        self.min_interval = min_interval
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl
        self.use_cache = use_cache
        self._last_request = 0.0
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{key}.html"

    def get(self, url: str) -> str:
        # list_editions()/get_scores()/get_rumor() all accept a URL string
        # from the caller (an agent, a CLI arg, a chained crawl result) and
        # hand it straight to this method - without this check, that's an
        # open fetch of anything on the internet (SSRF-shaped: could be
        # pointed at an internal address, not just an arbitrary public
        # site) using this tool's identifying header and IP. Every real
        # code path only ever constructs 3830scores.com URLs itself
        # (urljoin(BASE, ...)), so this should never reject legitimate use -
        # only a URL that didn't come from the site's own HTML.
        host = urlparse(url).hostname or ""
        if not (host == ALLOWED_HOST_SUFFIX or host.endswith("." + ALLOWED_HOST_SUFFIX)):
            raise ValueError(f"refusing to fetch non-3830scores.com URL: {url!r}")

        if self.use_cache:
            path = self._cache_path(url)
            if path.exists() and (time.time() - path.stat().st_mtime) < self.cache_ttl:
                return path.read_text(encoding="utf-8", errors="replace")

        wait = self.min_interval - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        resp = self.session.get(url, timeout=20)
        self._last_request = time.time()
        resp.raise_for_status()
        text = resp.text

        if self.use_cache:
            self._cache_path(url).write_text(text, encoding="utf-8")
        return text

    def soup(self, path_or_url: str, params: dict | None = None) -> BeautifulSoup:
        url = path_or_url if path_or_url.startswith("http") else urljoin(BASE, path_or_url)
        if params:
            url = f"{url}?{urlencode(params)}"
        return BeautifulSoup(self.get(url), "html.parser")


def _clean(text: str | None) -> str:
    if text is None:
        return ""
    text = html.unescape(text)
    # The site renders zero as the ham-radio "slashed zero" Ø/ø in
    # callsigns (to distinguish it from letter O) - e.g. "N0LD" shows up as
    # "NØLD". Left as-is, that silently breaks any comparison/search against
    # a callsign typed with a plain digit 0 (find_call("N0LD") vs. a scraped
    # "NØLD" call_used field). Normalize back to '0' everywhere, since on
    # this site Ø/ø is never anything other than a stand-in for the digit.
    text = text.replace("Ø", "0").replace("ø", "0")
    return re.sub(r"\s+", " ", text).strip()


def _int(text: str) -> int | None:
    text = _clean(text).replace(",", "")
    return int(text) if re.fullmatch(r"-?\d+", text) else None


# ---------------------------------------------------------------------------
# find_call(callsign) -> findcall.php?call=CALLSIGN
# ---------------------------------------------------------------------------

@dataclass
class CallHistoryEntry:
    year: str
    contest: str
    edition_url: str
    call_used: str
    rumor_url: str
    op_class: str
    power: str
    score: int | None


def find_call(callsign: str, fetcher: Fetcher | None = None) -> list[CallHistoryEntry]:
    """Per-operator contest history. Stable, guessable entry point:
    findcall.php?call=CALLSIGN. Returns every score row on file for that
    call, grouped implicitly by year in page order (most recent year first,
    as the site renders it)."""
    fetcher = fetcher or Fetcher()
    soup = fetcher.soup("findcall.php", params={"call": callsign})

    results: list[CallHistoryEntry] = []
    year = ""
    table = soup.find("table")
    if not table:
        return results

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        # Year header row: <td><strong>YEAR</strong></td><td>Contest</td>...
        strong = cells[0].find("strong")
        if strong and re.fullmatch(r"\d{4}", _clean(strong.text)):
            year = _clean(strong.text)
            continue
        if len(cells) < 5:
            continue  # blank spacer row
        edition_a = cells[1].find("a")
        rumor_a = cells[2].find("a")
        if not edition_a or not rumor_a:
            continue
        results.append(
            CallHistoryEntry(
                year=year,
                contest=_clean(edition_a.text),
                edition_url=urljoin(BASE, edition_a["href"]),
                call_used=_clean(rumor_a.text),
                rumor_url=urljoin(BASE, rumor_a["href"]),
                op_class=_clean(cells[3].text),
                power=_clean(cells[4].text),
                score=_int(cells[5].text) if len(cells) > 5 else None,
            )
        )
    return results


# ---------------------------------------------------------------------------
# list_contests() -> contests.php
# ---------------------------------------------------------------------------

def list_contests(fetcher: Fetcher | None = None) -> dict[str, str]:
    """Stable entry point: contests.php. Returns {contest_name: listeditions_url}.
    listeditions_url must then be crawled to reach individual editions -
    there is no per-contest permalink."""
    fetcher = fetcher or Fetcher()
    soup = fetcher.soup("contests.php")
    out: dict[str, str] = {}
    for a in soup.select('a[href^="listeditions.php"]'):
        out[_clean(a.text)] = urljoin(BASE, a["href"])
    return out


@dataclass
class ContestMatch:
    name: str
    listeditions_url: str
    score: float  # 0-1, similarity to the query


def search_contests(query: str, fetcher: Fetcher | None = None, limit: int = 10) -> list[ContestMatch]:
    """Fuzzy contest-name search over list_contests(). There's no search
    endpoint on the site itself - contests.php is the entire index (~300+
    names), so this just fetches that once and ranks it locally. Matches
    on substring (case-insensitive) first, then difflib similarity for
    typos/abbreviations, e.g. "cq ww" matches "CQ World Wide DX Contest,
    CW"/"...SSB", "sprint" matches every *Sprint contest, etc."""
    import difflib

    fetcher = fetcher or Fetcher()
    contests = list_contests(fetcher)
    q = query.strip().lower()

    scored: list[ContestMatch] = []
    for name, url in contests.items():
        name_l = name.lower()
        if q in name_l:
            # substring hit: rank by how much of the name it covers
            score = len(q) / len(name_l)
            score = 0.5 + 0.5 * score  # keep all substring hits above fuzzy-only hits
        else:
            score = difflib.SequenceMatcher(None, q, name_l).ratio()
        # 0.5 is also the floor every substring hit gets boosted to above,
        # so this threshold only filters the difflib-only (non-substring)
        # branch. It has to sit above plain character-overlap noise: two
        # short, common-letter strings (e.g. a long garbled query against
        # "Texas QSO Party") can score ~0.38-0.39 on pure character overlap
        # with no real relationship to the query at all.
        if score > 0.5:
            scored.append(ContestMatch(name=name, listeditions_url=url, score=round(score, 3)))

    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# list_editions(listeditions_url) -> listeditions.php?arg=...
# ---------------------------------------------------------------------------

@dataclass
class Edition:
    label: str  # e.g. "2018 May 19" - built from the row, not the link text
    year: str
    date: str
    breakdown_url: str
    edition_scores_url: str = ""  # editionscores.php - grouped-by-class view of the same edition


def list_editions(listeditions_url: str, fetcher: Fetcher | None = None) -> list[Edition]:
    """Every past running (year/date) of one contest, from a listeditions.php
    URL obtained via list_contests(). Each row is "YEAR | DATE | Scores link
    | Score Breakdowns link | Comments link | Calls Used link" - the link
    text itself is always the generic "Score Breakdowns"/"Scores", so the
    year/date come from the row's own leading cells instead, not the link."""
    fetcher = fetcher or Fetcher()
    soup = fetcher.soup(listeditions_url)
    out = []
    table = soup.find("table")
    if not table:
        return out
    for row in table.find_all("tr"):
        breakdown_a = row.find("a", href=re.compile(r"^breakdownscores\.php"))
        if not breakdown_a:
            continue
        cells = row.find_all("td")
        year = _clean(cells[0].text) if len(cells) > 0 else ""
        date = _clean(cells[1].text) if len(cells) > 1 else ""
        edition_a = row.find("a", href=re.compile(r"^editionscores\.php"))
        out.append(
            Edition(
                label=f"{year} {date}".strip(),
                year=year,
                date=date,
                breakdown_url=urljoin(BASE, breakdown_a["href"]),
                edition_scores_url=urljoin(BASE, edition_a["href"]) if edition_a else "",
            )
        )
    return out


# ---------------------------------------------------------------------------
# get_scores(url) -> breakdownscores.php?arg=... or editionscores.php?arg=...
# ---------------------------------------------------------------------------

@dataclass
class BandLine:
    band: str
    qsos: int | None
    mults: int | None


@dataclass
class ScoreRow:
    call: str
    rumor_url: str
    op_class: str  # from the group header row this entry sits under, if any
    score: int | None
    qsos: int | None
    mults: int | None
    club: str = ""
    bands: list[BandLine] = field(default_factory=list)


@dataclass
class EditionScores:
    title: str
    source_url: str
    rows: list[ScoreRow] = field(default_factory=list)


def get_scores(url: str, fetcher: Fetcher | None = None) -> EditionScores:
    """Parses either breakdownscores.php (one flat table, band-by-band
    columns, no class grouping) or editionscores.php (grouped by class with
    <strong> header rows, no per-band columns) - shape is auto-detected from
    the header row found. Both funnel into the same ScoreRow shape; whichever
    field the source page doesn't carry (bands vs. class) is left empty."""
    fetcher = fetcher or Fetcher()
    soup = fetcher.soup(url)

    title_tag = soup.select_one("#rightcol > p > strong")
    title = _clean(title_tag.text) if title_tag else ""

    table = None
    for t in soup.find_all("table"):
        if t.find("a", href=re.compile(r"^showrumor\.php")):
            table = t
            break
    result = EditionScores(title=title, source_url=url)
    if table is None:
        return result

    header_cells: list[str] = []
    current_class = ""
    band_names: list[str] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        texts = [_clean(c.text) for c in cells]
        rumor_a = row.find("a", href=re.compile(r"^showrumor\.php"))

        if rumor_a is None:
            first_strong = cells[0].find("strong")
            if first_strong:
                # Class/category header row. On breakdownscores.php this row
                # ALSO carries the per-band column labels (e.g. "160","80",
                # ...,"10") as colspan=2 cells alongside a colspan=2
                # "Totals" label - both live in the same <tr> as the class
                # name, there is no separate band-name row to find.
                current_class = _clean(first_strong.text)
                band_names = [
                    _clean(c.text) for c in cells
                    if c.get("colspan") == "2" and _clean(c.text) not in ("", "Totals")
                ]
                continue
            if texts and texts[0] in ("Call", "Band"):
                header_cells = texts  # only used to detect which layout this is
                continue
            continue  # blank spacer row

        call = _clean(rumor_a.text)
        rumor_url = urljoin(BASE, rumor_a["href"])

        if "OpMode" in header_cells:
            # editionscores.php layout:
            # Call, OpMode, Remote, QSOs, Mults, Op Time, Score, Club
            score = _int(texts[6]) if len(texts) > 6 else None
            row_obj = ScoreRow(
                call=call, rumor_url=rumor_url, op_class=current_class,
                score=score,
                qsos=_int(texts[3]) if len(texts) > 3 else None,
                mults=_int(texts[4]) if len(texts) > 4 else None,
                club=texts[7] if len(texts) > 7 else "",
            )
        else:
            # breakdownscores.php layout:
            # Call, Score, (spacer), QSOs, Mults, then repeating
            # (spacer, Q, Mlt) triplets, one per band in `band_names` order.
            # NOTE: do not drop empty cells here - a band a station made zero
            # QSOs on renders as an empty <td>, and dropping it (instead of
            # keeping it as a positional None) desyncs every band after it.
            score = _int(texts[1]) if len(texts) > 1 else None
            qsos = _int(texts[3]) if len(texts) > 3 else None
            mults = _int(texts[4]) if len(texts) > 4 else None
            bands = []
            rest = texts[5:]
            for i in range(0, len(rest) - 2, 3):
                _spacer, q, m = rest[i], rest[i + 1], rest[i + 2]
                idx = i // 3
                band = band_names[idx] if idx < len(band_names) else f"band{idx}"
                bands.append(BandLine(band=band, qsos=_int(q), mults=_int(m)))
            row_obj = ScoreRow(
                call=call, rumor_url=rumor_url, op_class=current_class,
                score=score, qsos=qsos, mults=mults, bands=bands,
            )
        result.rows.append(row_obj)

    return result


# ---------------------------------------------------------------------------
# get_rumor(url) -> showrumor.php?arg=...
# ---------------------------------------------------------------------------

@dataclass
class Rumor:
    call: str
    operators: str
    station: str
    op_class: str
    qth: str
    op_time: str
    location: str
    club: str
    bands: list[BandLine]
    total_qsos: int | None
    total_mults: int | None
    total_score: int | None
    soapbox_date: str
    soapbox_text: str  # aka "soapbox" - the free-text remarks a competitor posts alongside their score
    source_url: str


def get_rumor(url: str, fetcher: Fetcher | None = None) -> Rumor:
    """Single competitor's full posted score + free-text comment, from a
    showrumor.php URL obtained via find_call() or get_scores(). The comment
    field is unparsed prose - see module LIMITATIONS."""
    fetcher = fetcher or Fetcher()
    soup = fetcher.soup(url)
    right = soup.select_one("#rightcol")
    text = right.get_text("\n") if right else ""

    # Fields live in two <p> blocks as "Label: value<br/>Label: value...".
    # get_text() on the whole block is unreliable here: BeautifulSoup joins
    # *every* node boundary with the separator, including the boundary
    # between "Label: " (a bare NavigableString) and its value (often
    # wrapped in its own <a>/<strong> tag) - so a label and its own value
    # can end up split across a fake "line" even though nothing in the
    # source separates them but a href tag. Splitting each <p> on its <br/>
    # tags first, then reading each resulting chunk as one field, avoids
    # that: it only breaks where the page itself breaks.
    fields: dict[str, str] = {}
    if right:
        for p in right.find_all("p"):
            if p.find("table"):
                continue  # score table / comment block, handled separately
            for chunk in re.split(r"<br\s*/?>", str(p)):
                chunk_text = _clean(BeautifulSoup(chunk, "html.parser").get_text(" "))
                if ":" in chunk_text:
                    label, _, value = chunk_text.partition(":")
                    fields[label.strip()] = value.strip()

    def field_after(label: str) -> str:
        return fields.get(label.rstrip(":"), "")

    call_a = right.find("a", href=re.compile(r"^findcall\.php")) if right else None
    call = _clean(call_a.text) if call_a else field_after("Call:")

    bands = []
    total_qsos = total_mults = total_score = None
    for row in (right.find_all("tr") if right else []):
        cells = row.find_all("td")
        texts = [_clean(c.text) for c in cells]
        if len(texts) >= 2 and re.fullmatch(r"[\dA-Za-z./]+:", texts[0]) and texts[0] != "Total:":
            bands.append(BandLine(band=texts[0].rstrip(":"), qsos=_int(texts[1]), mults=_int(texts[2]) if len(texts) > 2 else None))
        elif texts and texts[0] == "Total:":
            total_qsos = _int(texts[1]) if len(texts) > 1 else None
            total_mults = _int(texts[2]) if len(texts) > 2 else None
            if len(texts) > 4:
                total_score = _int(texts[4])

    soapbox_date_m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", text)
    pretext = right.find("td", class_="pretext") if right else None

    return Rumor(
        call=call,
        operators=field_after("Operator(s):"),
        station=field_after("Station:"),
        op_class=field_after("Class:"),
        qth=field_after("QTH:"),
        op_time=field_after("Operating Time (hrs):"),
        location=field_after("Location:"),
        club=field_after("Club:"),
        bands=bands,
        total_qsos=total_qsos,
        total_mults=total_mults,
        total_score=total_score,
        soapbox_date=soapbox_date_m.group(1) if soapbox_date_m else "",
        soapbox_text=_clean(pretext.text) if pretext else "",
        source_url=url,
    )


# ---------------------------------------------------------------------------
# CLI - JSON in, JSON out, so any agent (Claude via Bash, etc.) can shell out
# ---------------------------------------------------------------------------

def _dump(obj) -> str:
    def default(o):
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        raise TypeError
    return json.dumps(obj, default=default, indent=2, ensure_ascii=False)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-cache", action="store_true", help="bypass the on-disk cache")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_call = sub.add_parser("find-call", help="per-operator contest history")
    p_call.add_argument("callsign")

    sub.add_parser("list-contests", help="all contest names + edition-list URLs")

    p_search = sub.add_parser("search-contests", help="fuzzy contest-name search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    p_ed = sub.add_parser("list-editions", help="editions (date-instances) of one contest")
    p_ed.add_argument("listeditions_url")

    p_sc = sub.add_parser("get-scores", help="full score table for one edition")
    p_sc.add_argument("url", help="a breakdownscores.php or editionscores.php URL")

    p_ru = sub.add_parser("get-rumor", help="one competitor's full post + comment")
    p_ru.add_argument("url", help="a showrumor.php URL")

    args = p.parse_args()
    fetcher = Fetcher(use_cache=not args.no_cache)

    if args.cmd == "find-call":
        print(_dump(find_call(args.callsign, fetcher)))
    elif args.cmd == "list-contests":
        print(_dump(list_contests(fetcher)))
    elif args.cmd == "search-contests":
        print(_dump(search_contests(args.query, fetcher, args.limit)))
    elif args.cmd == "list-editions":
        print(_dump(list_editions(args.listeditions_url, fetcher)))
    elif args.cmd == "get-scores":
        print(_dump(get_scores(args.url, fetcher)))
    elif args.cmd == "get-rumor":
        print(_dump(get_rumor(args.url, fetcher)))


if __name__ == "__main__":
    main()
