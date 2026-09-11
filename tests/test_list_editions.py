"""Tests for list_editions() against the frozen listeditions.html fixture
(His Maj. King of Spain Contest, CW - 20 editions from 2007-2026)."""

from scores3830 import list_editions

URL = "https://www.3830scores.com/listeditions.php?arg=Rv00izVYU"


def test_returns_all_twenty_editions(fake_fetcher):
    editions = list_editions(URL, fake_fetcher)
    assert len(editions) == 20


def test_most_recent_edition_first(fake_fetcher):
    editions = list_editions(URL, fake_fetcher)
    assert editions[0].year == "2026"
    assert editions[0].date == "May 16"


def test_oldest_edition_last(fake_fetcher):
    editions = list_editions(URL, fake_fetcher)
    assert editions[-1].year == "2007"
    assert editions[-1].date == "May 19"


def test_label_combines_year_and_date_not_the_generic_link_text(fake_fetcher):
    # Regression guard: the <a> tag's own text is always the generic
    # "Score Breakdowns" string - the label must come from the row's
    # year/date cells instead, or every edition looks identical.
    editions = list_editions(URL, fake_fetcher)
    labels = {e.label for e in editions}
    assert "Score Breakdowns" not in labels
    assert "2026 May 16" in labels


def test_breakdown_urls_are_absolute_and_distinct(fake_fetcher):
    editions = list_editions(URL, fake_fetcher)
    urls = [e.breakdown_url for e in editions]
    assert all(u.startswith("https://www.3830scores.com/breakdownscores.php?arg=") for u in urls)
    assert len(set(urls)) == len(urls)

def test_edition_scores_url_also_populated(fake_fetcher):
    editions = list_editions(URL, fake_fetcher)
    assert all(e.edition_scores_url.startswith(
        "https://www.3830scores.com/editionscores.php?arg="
    ) for e in editions)


def test_known_edition_arg_matches_breakdown_and_editionscores_pair(fake_fetcher):
    # The 2018 edition's arg token is reused across get_scores tests -
    # pin it here so a future refactor can't silently swap the pairing.
    editions = list_editions(URL, fake_fetcher)
    ed_2018 = next(e for e in editions if e.year == "2018")
    assert ed_2018.breakdown_url == "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV00JDU"
    assert ed_2018.edition_scores_url == "https://www.3830scores.com/editionscores.php?arg=RvJ0nizV00JDU"
