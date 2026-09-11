"""Tests for find_call() against the frozen findcall_n5zy.html fixture."""

from scores3830 import find_call


def test_returns_a_nonempty_list(fake_fetcher):
    results = find_call("N5ZY", fake_fetcher)
    assert len(results) > 0


def test_requests_the_expected_stable_url(fake_fetcher):
    find_call("N5ZY", fake_fetcher)
    assert fake_fetcher.requested_urls == [
        "https://www.3830scores.com/findcall.php?call=N5ZY"
    ]


def test_first_entry_matches_known_fixture_content(fake_fetcher):
    results = find_call("N5ZY", fake_fetcher)
    first = results[0]
    assert first.year == "2026"
    assert first.contest == "ARRL June VHF Jun 13"
    assert first.call_used == "N5ZY/R"
    assert first.op_class == "Rover"
    assert first.power == "LP"
    assert first.score == 23166
    assert first.edition_url == "https://www.3830scores.com/editionscores.php?arg=RvYizV77exuU"
    assert first.rumor_url == "https://www.3830scores.com/showrumor.php?arg=RvYizV7JY7x0JU"


def test_every_row_has_a_year_assigned(fake_fetcher):
    # The year comes from a preceding <strong>YYYY</strong> header row that
    # isn't repeated per-row in the HTML - make sure every entry inherited
    # one and none leaked through as "".
    results = find_call("N5ZY", fake_fetcher)
    assert all(r.year for r in results)


def test_years_are_four_digit_strings(fake_fetcher):
    results = find_call("N5ZY", fake_fetcher)
    for r in results:
        assert r.year.isdigit() and len(r.year) == 4


def test_urls_are_absolute(fake_fetcher):
    results = find_call("N5ZY", fake_fetcher)
    for r in results:
        assert r.edition_url.startswith("https://www.3830scores.com/")
        assert r.rumor_url.startswith("https://www.3830scores.com/")


def test_scores_are_ints_or_none(fake_fetcher):
    results = find_call("N5ZY", fake_fetcher)
    for r in results:
        assert r.score is None or isinstance(r.score, int)


def test_known_older_entry_present(fake_fetcher):
    # Regression guard against the parser silently truncating to only the
    # most recent year's block.
    results = find_call("N5ZY", fake_fetcher)
    contests_2019 = [r for r in results if r.year == "2019"]
    assert any("ARRL Jan VHF" in r.contest for r in contests_2019)
