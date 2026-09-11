"""Tests for get_rumor() against three frozen showrumor.php fixtures:

  - showrumor_hf.html:   a full-featured HF contest post (HA4XH, His Maj.
                          King of Spain 2018) - has Operating Time and
                          Location, which not every contest type reports.
  - showrumor_vhf.html:  a VHF contest post (N5ZY/R, ARRL June VHF 2026)
                          that leaves Operating Time and Location blank.
  - showrumor_zero.html: a post from a callsign containing the ham-radio
                          "slashed zero" (N0SS), to confirm normalization
                          survives the field-splitting logic end to end.
"""

from scores3830 import get_rumor

HF_URL = "https://www.3830scores.com/showrumor.php?arg=RvYizV0nunJYU"
VHF_URL = "https://www.3830scores.com/showrumor.php?arg=RvYizV7JY7x0JU"
ZERO_URL = "https://www.3830scores.com/showrumor.php?arg=RvYizV7JYnJn7U"


class TestHFContestRumor:
    def test_identity_fields(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert r.call == "HA4XH"
        assert r.operators == "HA4XH"
        assert r.station == "HA3DX"
        assert r.op_class == "SOAB HP"
        assert r.club == "Hungarian DX Club"

    def test_location_and_operating_time_present_on_hf_pages(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert r.qth == "Paks"
        assert r.op_time == "23:14"
        assert r.location == "Eastern Europe"

    def test_band_breakdown_matches_known_values(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        by_band = {b.band: (b.qsos, b.mults) for b in r.bands}
        assert by_band == {
            "160": (27, 19),
            "80": (107, 46),
            "40": (215, 71),
            "20": (275, 72),
            "15": (176, 65),
            "10": (107, 47),
        }

    def test_totals_match_known_values(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert r.total_qsos == 907
        assert r.total_mults == 320
        assert r.total_score == 456640

    def test_band_qsos_sum_to_total(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert sum(b.qsos for b in r.bands) == r.total_qsos
        assert sum(b.mults for b in r.bands) == r.total_mults

    def test_soapbox_fields_extracted(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert r.soapbox_date == "2018-06-02 06:31:50"
        assert "Carlos (HA4XH)" in r.soapbox_text
        assert len(r.soapbox_text) > 100  # this post has a long comment

    def test_source_url_is_preserved(self, fake_fetcher):
        r = get_rumor(HF_URL, fake_fetcher)
        assert r.source_url == HF_URL


class TestVHFContestRumorWithSparseFields:
    def test_identity_fields(self, fake_fetcher):
        r = get_rumor(VHF_URL, fake_fetcher)
        assert r.call == "N5ZY/R"
        assert r.operators == "N5ZY"
        assert r.op_class == "Rover LP"
        assert r.qth == "EM15"

    def test_operating_time_and_location_are_blank_not_bled_from_next_field(self, fake_fetcher):
        # Regression guard for a real bug: a naive whitespace-crossing
        # regex previously let a blank "Operating Time (hrs):" value eat
        # into the next section's "Summary:" table header, returning
        # "Summary:" as the op_time. Splitting on <br/> boundaries per <p>
        # fixed this - confirm both fields come back genuinely empty.
        r = get_rumor(VHF_URL, fake_fetcher)
        assert r.op_time == ""
        assert r.location == ""
        assert "Summary" not in r.op_time

    def test_bands_include_zero_qso_vhf_bands_as_none(self, fake_fetcher):
        r = get_rumor(VHF_URL, fake_fetcher)
        by_band = {b.band: (b.qsos, b.mults) for b in r.bands}
        assert by_band["6"] == (150, 87)
        assert by_band["2"] == (24, 12)
        assert by_band["902"] == (None, None)
        assert by_band["24G"] == (None, None)

    def test_totals_match_known_values(self, fake_fetcher):
        r = get_rumor(VHF_URL, fake_fetcher)
        assert r.total_qsos == 186
        assert r.total_mults == 109
        assert r.total_score == 23166

    def test_soapbox_text_is_the_long_narrative_comment(self, fake_fetcher):
        r = get_rumor(VHF_URL, fake_fetcher)
        assert "Mount Magazine" in r.soapbox_text
        assert r.soapbox_date == "2026-06-22 23:45:54"


class TestSlashedZeroCallsignRumor:
    def test_call_is_normalized_to_plain_digit_zero(self, fake_fetcher):
        r = get_rumor(ZERO_URL, fake_fetcher)
        assert r.call == "N0SS"
        assert "Ø" not in r.call
        assert "ø" not in r.call
