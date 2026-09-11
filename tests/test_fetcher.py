"""Tests for the Fetcher HTTP layer itself: caching, rate limiting, header
setup, and URL building. These mock requests.Session.get directly (never
touching the network) since they're testing Fetcher's own plumbing, not
page parsing - that's covered via FakeFetcher in the other test modules."""

from unittest.mock import MagicMock, patch

import pytest

from scores3830 import BASE, USER_AGENT, Fetcher


def _mock_response(text: str, status: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return resp


class TestHeaders:
    def test_sets_browser_user_agent(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path)
        assert f.session.headers["User-Agent"] == USER_AGENT
        assert "Mozilla" in USER_AGENT  # must look like a browser, not a bot


class TestCaching:
    def test_second_call_for_same_url_does_not_hit_network(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=True, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("hello")) as mock_get:
            first = f.get("https://www.3830scores.com/foo.php")
            second = f.get("https://www.3830scores.com/foo.php")
        assert first == "hello"
        assert second == "hello"
        mock_get.assert_called_once()

    def test_different_urls_are_cached_separately(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=True, min_interval=0)
        responses = iter([_mock_response("page-a"), _mock_response("page-b")])
        with patch.object(f.session, "get", side_effect=lambda *a, **k: next(responses)):
            a = f.get("https://www.3830scores.com/a.php")
            b = f.get("https://www.3830scores.com/b.php")
        assert a == "page-a"
        assert b == "page-b"

    def test_use_cache_false_always_hits_network(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("hello")) as mock_get:
            f.get("https://www.3830scores.com/foo.php")
            f.get("https://www.3830scores.com/foo.php")
        assert mock_get.call_count == 2

    def test_expired_cache_entry_triggers_a_refetch(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=True, cache_ttl=0, min_interval=0)
        responses = iter([_mock_response("old"), _mock_response("new")])
        with patch.object(f.session, "get", side_effect=lambda *a, **k: next(responses)):
            first = f.get("https://www.3830scores.com/foo.php")
            second = f.get("https://www.3830scores.com/foo.php")  # ttl=0 -> instantly stale
        assert first == "old"
        assert second == "new"

    def test_cache_file_keyed_by_url_hash_not_raw_url(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=True, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("hello")):
            f.get("https://www.3830scores.com/foo.php?arg=weird/../chars")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".html"


class TestHostAllowlist:
    """Fetcher.get() takes a URL that ultimately traces back to caller input
    (a CLI arg, an agent-supplied URL) - without a host check this is an
    open fetch of anything on the internet using this tool's identity.
    These confirm the guard actually blocks off-site URLs and doesn't
    accidentally block legitimate 3830scores.com ones."""

    def test_rejects_a_completely_different_domain(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with pytest.raises(ValueError, match="refusing to fetch"):
            f.get("https://evil.example.com/steal-stuff")

    def test_rejects_an_internal_ip_address(self, tmp_path):
        # The concrete SSRF shape this guards against: pointing the fetcher
        # at an internal/link-local address instead of the public site.
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with pytest.raises(ValueError, match="refusing to fetch"):
            f.get("http://169.254.169.254/latest/meta-data/")

    def test_rejects_lookalike_domain_with_3830scores_com_as_a_prefix(self, tmp_path):
        # "3830scores.com.evil.com" must NOT pass an endswith() check -
        # confirms the guard checks the actual hostname, not a naive
        # substring/prefix match on the URL string.
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with pytest.raises(ValueError, match="refusing to fetch"):
            f.get("https://3830scores.com.evil.com/showrumor.php")

    def test_rejects_lookalike_domain_with_3830scores_com_as_a_suffix_of_a_longer_label(self, tmp_path):
        # "evil3830scores.com" ends with "3830scores.com" as a raw string
        # but is a different registrable domain entirely - the guard must
        # compare against a "." + suffix boundary, not str.endswith(suffix).
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with pytest.raises(ValueError, match="refusing to fetch"):
            f.get("https://evil3830scores.com/showrumor.php")

    def test_allows_the_bare_apex_domain(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("ok")):
            assert f.get("https://3830scores.com/contests.php") == "ok"

    def test_allows_the_www_subdomain(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("ok")):
            assert f.get("https://www.3830scores.com/contests.php") == "ok"

    def test_rejection_happens_before_any_network_call(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get") as mock_get:
            with pytest.raises(ValueError):
                f.get("https://evil.example.com/")
        mock_get.assert_not_called()

    def test_soup_also_enforces_the_allowlist_for_absolute_urls(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with pytest.raises(ValueError, match="refusing to fetch"):
            f.soup("https://evil.example.com/")


class TestRaisesOnHTTPError:
    def test_4xx_response_raises(self, tmp_path):
        import requests
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("blocked", status=403)):
            with pytest.raises(requests.HTTPError):
                f.get("https://www.3830scores.com/foo.php")


class TestRateLimiting:
    def test_sleeps_between_consecutive_requests(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=5)
        f._last_request = 1000.0
        with patch("scores3830.time.time", return_value=1000.1), \
             patch("scores3830.time.sleep") as mock_sleep, \
             patch.object(f.session, "get", return_value=_mock_response("x")):
            f.get("https://www.3830scores.com/foo.php")
        mock_sleep.assert_called_once()
        slept_for = mock_sleep.call_args[0][0]
        assert 4.8 < slept_for <= 5.0

    def test_no_sleep_when_enough_time_has_already_passed(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=1)
        f._last_request = 1000.0
        with patch("scores3830.time.time", return_value=1005.0), \
             patch("scores3830.time.sleep") as mock_sleep, \
             patch.object(f.session, "get", return_value=_mock_response("x")):
            f.get("https://www.3830scores.com/foo.php")
        mock_sleep.assert_not_called()


class TestSoupUrlBuilding:
    def test_relative_path_resolves_against_base(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("<html></html>")) as mock_get:
            f.soup("contests.php")
        called_url = mock_get.call_args[0][0]
        assert called_url == BASE + "contests.php"

    def test_absolute_url_passed_through_unchanged(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("<html></html>")) as mock_get:
            f.soup("https://www.3830scores.com/showrumor.php?arg=XYZ")
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://www.3830scores.com/showrumor.php?arg=XYZ"

    def test_params_are_url_encoded_onto_relative_path(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("<html></html>")) as mock_get:
            f.soup("findcall.php", params={"call": "N5ZY"})
        called_url = mock_get.call_args[0][0]
        assert called_url == BASE + "findcall.php?call=N5ZY"

    def test_soup_returns_a_parsed_beautifulsoup_object(self, tmp_path):
        f = Fetcher(cache_dir=tmp_path, use_cache=False, min_interval=0)
        with patch.object(f.session, "get", return_value=_mock_response("<title>Hi</title>")):
            soup = f.soup("index.php")
        assert soup.title.text == "Hi"
