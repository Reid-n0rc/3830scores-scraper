"""Tests for list_contests() and search_contests(), against the frozen
contests.html fixture (322 contests as of the snapshot)."""

from scores3830 import list_contests, search_contests


class TestListContests:
    def test_requests_contests_php(self, fake_fetcher):
        list_contests(fake_fetcher)
        assert fake_fetcher.requested_urls == ["https://www.3830scores.com/contests.php"]

    def test_returns_dict_of_name_to_url(self, fake_fetcher):
        contests = list_contests(fake_fetcher)
        assert isinstance(contests, dict)
        assert len(contests) > 100  # sanity floor well below the known 322

    def test_known_contest_maps_to_expected_url(self, fake_fetcher):
        contests = list_contests(fake_fetcher)
        assert contests["10-10 Int. Summer Contest, SSB"] == (
            "https://www.3830scores.com/listeditions.php?arg=RvnLeizVYU"
        )

    def test_all_values_are_listeditions_urls(self, fake_fetcher):
        contests = list_contests(fake_fetcher)
        for url in contests.values():
            assert url.startswith("https://www.3830scores.com/listeditions.php?arg=")

    def test_no_duplicate_urls_for_distinct_names(self, fake_fetcher):
        contests = list_contests(fake_fetcher)
        # Every contest should have its own edition-list token.
        assert len(set(contests.values())) == len(contests)


class TestSearchContests:
    def test_substring_match_is_case_insensitive(self, fake_fetcher):
        results = search_contests("sprint", fake_fetcher)
        names = [r.name for r in results]
        assert any("Sprint" in n for n in names)

    def test_substring_matches_outrank_pure_fuzzy_matches(self, fake_fetcher):
        results = search_contests("sprint", fake_fetcher)
        # Every returned name should actually contain "sprint" (substring
        # hits are boosted above 0.5 and there are more than `limit` of them
        # for this query, so fuzzy-only matches shouldn't appear at all).
        assert all("sprint" in r.name.lower() for r in results)

    def test_results_sorted_descending_by_score(self, fake_fetcher):
        results = search_contests("contest", fake_fetcher)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_respects_limit(self, fake_fetcher):
        results = search_contests("contest", fake_fetcher, limit=3)
        assert len(results) <= 3

    def test_exact_name_match_scores_highest_possible(self, fake_fetcher):
        results = search_contests("10-10 Int. Summer Contest, SSB", fake_fetcher, limit=1)
        assert results[0].name == "10-10 Int. Summer Contest, SSB"
        assert results[0].score == 1.0

    def test_nonsense_query_returns_no_results(self, fake_fetcher):
        # Deliberately no real words in here - a query that happens to
        # embed a common word (e.g. "contest") legitimately matches names
        # containing it, so isn't a good "nonsense" test case.
        results = search_contests("xqzvbkjhmwprtyzq", fake_fetcher)
        assert results == []

    def test_result_carries_usable_listeditions_url(self, fake_fetcher):
        results = search_contests("10-10", fake_fetcher, limit=5)
        assert all(r.listeditions_url.startswith("https://www.3830scores.com/listeditions.php?arg=") for r in results)

    def test_only_fetches_contests_page_once(self, fake_fetcher):
        # search_contests should reuse list_contests() rather than issuing
        # its own separate request pattern.
        search_contests("sprint", fake_fetcher)
        assert fake_fetcher.requested_urls == ["https://www.3830scores.com/contests.php"]
