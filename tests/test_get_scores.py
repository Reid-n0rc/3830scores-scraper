"""Tests for get_scores(), which auto-detects and parses two different page
layouts (breakdownscores.php and editionscores.php). Fixtures cover three
concrete shapes seen on the live site:

  - breakdownscores_bands.html:   per-band Q/Mlt columns + class grouping
                                   in the same row (His Maj. King of Spain,
                                   2018 - 6 HF bands)
  - breakdownscores_nomults.html: a contest that reports only Call/Score/QSOs
                                   with no Mults or band columns at all
                                   (10-10 Int. Summer Contest SSB, 2026)
  - editionscores_grouped.html:   grouped by class header rows, OpMode/Club
                                   columns, no per-band breakdown
                                   (ARRL June VHF, 2026)
"""

from scores3830 import get_scores

BANDS_URL = "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV00JDU"
NOMULTS_URL = "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV77x7DU"
GROUPED_URL = "https://www.3830scores.com/editionscores.php?arg=RvYizV77exuU"


class TestBreakdownScoresWithBands:
    def test_title_includes_contest_name_and_date(self, fake_fetcher):
        result = get_scores(BANDS_URL, fake_fetcher)
        assert "His Maj. King of Spain Contest, CW" in result.title
        assert "2018" in result.title

    def test_returns_multiple_rows(self, fake_fetcher):
        result = get_scores(BANDS_URL, fake_fetcher)
        assert len(result.rows) > 1

    def test_first_row_matches_known_values(self, fake_fetcher):
        result = get_scores(BANDS_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "N1SOH")
        assert row.score == 5632
        assert row.qsos == 80
        assert row.mults == 25
        assert row.op_class == "Multi-Op HP"

    def test_band_names_are_real_band_labels_not_placeholders(self, fake_fetcher):
        # Regression guard for a real bug: an earlier version emitted
        # "col0"/"col1"/... placeholder names instead of reading the band
        # labels ("160","80","40","20","15","10") from the header row.
        result = get_scores(BANDS_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "N1SOH")
        band_names = [b.band for b in row.bands]
        assert band_names == ["160", "80", "40", "20", "15", "10"]

    def test_band_values_stay_positionally_aligned_around_blank_bands(self, fake_fetcher):
        # Regression guard for a real bug: filtering out empty <td> cells
        # (a station with 0 QSOs on a band renders as an EMPTY cell, not a
        # literal "0") desynced every band's data after the first blank one.
        # N1SOH worked no QSOs on 160 or 10 - those must show as (None, None)
        # in the correct slots, not be dropped and shift later bands left.
        result = get_scores(BANDS_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "N1SOH")
        by_band = {b.band: (b.qsos, b.mults) for b in row.bands}
        assert by_band["160"] == (None, None)
        assert by_band["80"] == (1, 1)
        assert by_band["40"] == (20, 4)
        assert by_band["20"] == (57, 19)
        assert by_band["15"] == (2, 1)
        assert by_band["10"] == (None, None)

    def test_band_qso_and_mult_totals_are_self_consistent(self, fake_fetcher):
        # Cross-check: summed per-band QSOs should equal the row's own
        # reported total QSOs, for a row with no blank bands.
        result = get_scores(BANDS_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "ED1B")
        assert sum(b.qsos for b in row.bands) == row.qsos
        assert sum(b.mults for b in row.bands) == row.mults

    def test_class_grouping_assigns_correct_op_class_per_row(self, fake_fetcher):
        result = get_scores(BANDS_URL, fake_fetcher)
        classes = {r.call: r.op_class for r in result.rows if r.call in ("N1SOH", "ED1B")}
        assert classes["N1SOH"] == "Multi-Op HP"
        assert classes["ED1B"] == "Multi-Op LP"

    def test_every_row_has_a_rumor_url(self, fake_fetcher):
        result = get_scores(BANDS_URL, fake_fetcher)
        assert all(r.rumor_url.startswith("https://www.3830scores.com/showrumor.php?arg=") for r in result.rows)

    def test_scores_sorted_descending_within_first_class_group(self, fake_fetcher):
        # breakdownscores.php lists each class group already sorted by
        # score - a quick sanity check that we aren't scrambling row order.
        result = get_scores(BANDS_URL, fake_fetcher)
        first_class = result.rows[0].op_class
        same_class_scores = [r.score for r in result.rows if r.op_class == first_class]
        assert same_class_scores == sorted(same_class_scores, reverse=True)


class TestBreakdownScoresWithoutMults:
    def test_parses_without_error_when_mults_and_bands_absent(self, fake_fetcher):
        result = get_scores(NOMULTS_URL, fake_fetcher)
        assert len(result.rows) > 0

    def test_row_has_score_and_qsos_but_no_mults_or_bands(self, fake_fetcher):
        result = get_scores(NOMULTS_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "N5XZ")
        assert row.score == 394
        assert row.qsos == 317
        assert row.mults is None  # this contest just doesn't report mults
        assert row.bands == []


class TestEditionScoresGrouped:
    def test_returns_multiple_rows(self, fake_fetcher):
        result = get_scores(GROUPED_URL, fake_fetcher)
        assert len(result.rows) > 10

    def test_known_row_has_expected_values(self, fake_fetcher):
        result = get_scores(GROUPED_URL, fake_fetcher)
        row = next(r for r in result.rows if r.call == "AA4ZZ")
        assert row.op_class == "Limited Multi-Op HP"
        assert row.score == 460056
        assert row.qsos == 1106
        assert row.mults == 348
        assert row.club == "CDXA"

    def test_no_per_band_breakdown_on_this_layout(self, fake_fetcher):
        result = get_scores(GROUPED_URL, fake_fetcher)
        assert all(r.bands == [] for r in result.rows)

    def test_slashed_zero_in_callsign_is_normalized(self, fake_fetcher):
        # N&#216;SS / N&#216;LBY in the raw HTML -> must come back as
        # plain digit zeros, per _clean()'s Ø-normalization.
        result = get_scores(GROUPED_URL, fake_fetcher)
        calls = [r.call for r in result.rows]
        assert "N0SS(@N0LBY)" in calls
        assert not any("Ø" in c or "ø" in c for c in calls)

    def test_multiple_distinct_class_groups_present(self, fake_fetcher):
        result = get_scores(GROUPED_URL, fake_fetcher)
        classes = {r.op_class for r in result.rows}
        assert "Limited Multi-Op HP" in classes
        assert "Limited Multi-Op LP" in classes


def test_unrecognized_url_with_no_score_table_returns_empty_rows(fake_fetcher):
    # get_scores should degrade gracefully (empty rows), not raise, if a
    # page happens to have no table containing a showrumor.php link.
    result = get_scores("https://www.3830scores.com/contests.php", fake_fetcher)
    assert result.rows == []
