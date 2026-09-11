"""End-to-end tests for the CLI entry point (main()): argument parsing,
dispatch to the right function, and valid-JSON output on stdout - this is
the interface an agent shells out to, so it's tested as a black box via
sys.argv + captured stdout, with the network layer swapped for the offline
FakeFetcher."""

import json
import sys

import pytest

import scores3830
from tests.conftest import FakeFetcher


@pytest.fixture(autouse=True)
def patch_fetcher_construction(monkeypatch):
    """main() constructs `Fetcher(use_cache=not args.no_cache)` itself, so
    swap the class it resolves to `Fetcher` with one that returns our
    offline FakeFetcher regardless of the kwargs it's called with."""
    monkeypatch.setattr(scores3830, "Fetcher", lambda *a, **k: FakeFetcher())


def run_cli(args, capsys):
    sys.argv = ["scores3830.py"] + args
    scores3830.main()
    return capsys.readouterr().out


def test_find_call_outputs_valid_json_list(capsys):
    out = run_cli(["find-call", "N5ZY"], capsys)
    data = json.loads(out)
    assert isinstance(data, list)
    assert data[0]["call_used"] == "N5ZY/R"


def test_list_contests_outputs_valid_json_object(capsys):
    out = run_cli(["list-contests"], capsys)
    data = json.loads(out)
    assert isinstance(data, dict)
    assert "10-10 Int. Summer Contest, SSB" in data


def test_search_contests_outputs_valid_json_list_and_respects_limit(capsys):
    out = run_cli(["search-contests", "sprint", "--limit", "2"], capsys)
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) <= 2


def test_list_editions_outputs_valid_json(capsys):
    out = run_cli(
        ["list-editions", "https://www.3830scores.com/listeditions.php?arg=Rv00izVYU"],
        capsys,
    )
    data = json.loads(out)
    assert len(data) == 20
    assert data[0]["year"] == "2026"


def test_get_scores_outputs_valid_json(capsys):
    out = run_cli(
        ["get-scores", "https://www.3830scores.com/breakdownscores.php?arg=RvJ0nizV00JDU"],
        capsys,
    )
    data = json.loads(out)
    assert "rows" in data
    assert any(row["call"] == "N1SOH" for row in data["rows"])


def test_get_rumor_outputs_valid_json_with_soapbox_fields(capsys):
    out = run_cli(
        ["get-rumor", "https://www.3830scores.com/showrumor.php?arg=RvYizV0nunJYU"],
        capsys,
    )
    data = json.loads(out)
    assert data["call"] == "HA4XH"
    assert "soapbox_text" in data
    assert "soapbox_date" in data


def test_missing_subcommand_exits_nonzero(capsys):
    sys.argv = ["scores3830.py"]
    with pytest.raises(SystemExit) as exc_info:
        scores3830.main()
    assert exc_info.value.code != 0
