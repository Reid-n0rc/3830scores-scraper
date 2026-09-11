"""Unit tests for the low-level text-cleaning helpers (_clean, _int)."""

from scores3830 import _clean, _int


class TestClean:
    def test_none_returns_empty_string(self):
        assert _clean(None) == ""

    def test_strips_leading_trailing_whitespace(self):
        assert _clean("  hello  ") == "hello"

    def test_collapses_internal_whitespace_runs(self):
        assert _clean("a   b\n\nc\t\td") == "a b c d"

    def test_unescapes_html_entities(self):
        assert _clean("Rock &amp; Roll") == "Rock & Roll"
        assert _clean("&lt;tag&gt;") == "<tag>"

    def test_decodes_numeric_character_references(self):
        # This is how the site actually encodes the slashed zero: &#216;
        assert _clean("N&#216;LD") == "N0LD"

    def test_nbsp_collapses_to_nothing_when_alone(self):
        assert _clean("&nbsp;") == ""
        assert _clean("&nbsp;&nbsp;") == ""

    def test_nbsp_between_words_becomes_single_space(self):
        assert _clean("foo&nbsp;bar") == "foo bar"

    # --- slashed-zero normalization: the core of this feature ---

    def test_uppercase_slashed_zero_literal_char_becomes_digit_zero(self):
        assert _clean("NØLD") == "N0LD"  # Ø U+00D8

    def test_lowercase_slashed_zero_literal_char_becomes_digit_zero(self):
        assert _clean("nøld") == "n0ld"  # ø U+00F8

    def test_multiple_slashed_zeros_in_one_string(self):
        assert _clean("NØSS(@NØLBY)") == "N0SS(@N0LBY)"

    def test_plain_digit_zero_is_left_alone(self):
        # Regression guard: normalization must not touch callsigns that
        # were never slash-zero'd in the source HTML to begin with.
        assert _clean("N0LD") == "N0LD"

    def test_slashed_zero_via_html_entity_also_normalizes(self):
        # &#216; is the HTML numeric entity for Ø - unescape happens before
        # the Ø->0 replacement, so this must also come out as a digit zero.
        assert _clean("N&#216;SS") == "N0SS"
        assert _clean("n&#248;ss") == "n0ss"

    def test_letter_o_is_never_touched(self):
        # Sanity check that we're normalizing Ø specifically, not O broadly.
        assert _clean("NOLD") == "NOLD"


class TestInt:
    def test_parses_plain_integer(self):
        assert _int("42") == 42

    def test_strips_thousands_separators(self):
        assert _int("456,640") == 456640
        assert _int("1,234,567") == 1234567

    def test_empty_string_returns_none(self):
        assert _int("") is None

    def test_nbsp_only_returns_none(self):
        assert _int("&nbsp;") is None

    def test_non_numeric_text_returns_none(self):
        assert _int("N/A") is None
        assert _int("Rover LP") is None

    def test_negative_number(self):
        assert _int("-5") == -5

    def test_whitespace_padded_number(self):
        assert _int("  907  ") == 907
