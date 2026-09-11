"""
Shared test fixtures for scores3830.

All tests run fully offline against saved HTML snapshots in tests/fixtures/
- no test ever makes a real request to 3830scores.com. FakeFetcher below is
a drop-in replacement for scores3830.Fetcher that serves fixture files
keyed by exact URL instead of hitting the network, so it exercises the same
soup()/get() call sites the real code uses.

If 3830scores.com changes its page layout, these fixtures will NOT reflect
that - they're frozen snapshots. Regenerate them (see
tests/fixtures/REGENERATE.md) if a real request starts producing different
parsed results than these tests expect.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scores3830 import Fetcher

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Exact URL -> fixture filename. Must match the URLs the code under test
# actually builds (see each test module for which function call produces
# which URL).
URL_TO_FIXTURE = {
    "https://www.3830scores.com/findcall.php?call=N5ZY": "findcall_n5zy.html",
    "https://www.3830scores.com/contests.php": "contests.html",
    "https://www.3830scores.com/listeditions.php?arg=Rv00izVYU": "listeditions.html",
    "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV00JDU": "breakdownscores_bands.html",
    "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV77x7DU": "breakdownscores_nomults.html",
    "https://www.3830scores.com/editionscores.php?arg=RvYizV77exuU": "editionscores_grouped.html",
    "https://www.3830scores.com/showrumor.php?arg=RvYizV0nunJYU": "showrumor_hf.html",
    "https://www.3830scores.com/showrumor.php?arg=RvYizV7JY7x0JU": "showrumor_vhf.html",
    "https://www.3830scores.com/showrumor.php?arg=RvYizV7JYnJn7U": "showrumor_zero.html",
}


class FakeFetcher(Fetcher):
    """Fetcher subclass that never touches the network. Raises AssertionError
    (not a silent empty page) if the code under test asks for a URL no test
    has provided a fixture for, so a missing mapping fails loudly instead of
    producing a confusing downstream parse failure."""

    def __init__(self):
        # Deliberately skip Fetcher.__init__: no requests.Session, no cache
        # dir, no rate limiting - none of that is relevant once network
        # access is stubbed out.
        self.requested_urls: list[str] = []

    def get(self, url: str) -> str:
        self.requested_urls.append(url)
        fixture = URL_TO_FIXTURE.get(url)
        if fixture is None:
            raise AssertionError(
                f"FakeFetcher has no fixture mapped for URL: {url!r}\n"
                f"Known URLs: {sorted(URL_TO_FIXTURE)}"
            )
        return (FIXTURES_DIR / fixture).read_text(encoding="utf-8")


@pytest.fixture
def fake_fetcher() -> FakeFetcher:
    return FakeFetcher()
