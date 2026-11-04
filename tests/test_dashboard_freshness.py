"""The staleness checker.

It guards a real risk -- the dashboard ships pre-built, so it can drift from
the code behind it -- and a checker that silently always passes would be worse
than not having one. These tests pin both halves: that it ignores what is
honestly not reproducible, and that it still catches what is.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location(
        "check_fresh", ROOT / "scripts" / "check_dashboard_fresh.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_specific_values_are_normalised_away(checker):
    """These come from the clock and from uuid4 on every run. Comparing them
    would make the check fail constantly and train everyone to ignore it."""
    a = {"at": "2026-09-11T08:38:44+00:00", "hash": "aaa",
         "id": "iss-121900313cb0", "quantified_at": "2026-09-11T08:38:44+00:00"}
    b = {"at": "2026-09-11T09:58:28+00:00", "hash": "bbb",
         "id": "iss-f41f8c6e6a59", "quantified_at": "2026-09-11T09:58:28+00:00"}
    assert checker.normalise(a) == checker.normalise(b)


def test_content_dates_are_not_normalised(checker):
    """`day` and `enrolled_on` are observations and enrolment facts. If those
    could drift unnoticed the check would be worthless."""
    a = {"day": "2026-01-01", "enrolled_on": "2025-06-01", "year": 2025}
    b = {"day": "2026-01-06", "enrolled_on": "2025-06-01", "year": 2025}
    assert checker.normalise(a) != checker.normalise(b)


def test_a_natural_id_is_not_mistaken_for_a_generated_one(checker):
    """Only ids with a generated prefix are volatile. A project id is content."""
    a = {"id": "IN-TNJ-01"}
    b = {"id": "KE-NYR-01"}
    assert checker.normalise(a) != checker.normalise(b)
    assert checker.normalise({"id": "IN-TNJ-01"})["id"] == "IN-TNJ-01"


def test_normalisation_reaches_into_nested_structures(checker):
    a = {"sites": {"x": {"issuances": [{"id": "iss-1", "quantity": 3}]}}}
    b = {"sites": {"x": {"issuances": [{"id": "iss-2", "quantity": 3}]}}}
    assert checker.normalise(a) == checker.normalise(b)

    c = {"sites": {"x": {"issuances": [{"id": "iss-2", "quantity": 4}]}}}
    assert checker.normalise(a) != checker.normalise(c)


def test_first_difference_names_the_path(checker):
    """A failure that says "files differ" wastes the reader's time."""
    a = {"economics": {"per_site": [{"breakeven_mrv_per_ha": 2.53}]}}
    b = {"economics": {"per_site": [{"breakeven_mrv_per_ha": 2.75}]}}
    diff = checker.first_difference(a, b)
    assert "economics.per_site[0].breakeven_mrv_per_ha" in diff
    assert "2.53" in diff and "2.75" in diff


def test_first_difference_reports_added_removed_and_length(checker):
    assert "added" in checker.first_difference({}, {"x": 1})
    assert "removed" in checker.first_difference({"x": 1}, {})
    assert "length" in checker.first_difference({"x": [1]}, {"x": [1, 2]})
    assert checker.first_difference({"x": [1, 2]}, {"x": [1, 2]}) is None


def test_committed_payload_records_the_date_it_was_built_for(checker):
    """The build is a snapshot as of a stated date -- which vintages have
    settled depends on it. Without that recorded, the committed file cannot be
    reproduced and the checker has nothing to pin the rebuild to."""
    import json

    payload = json.loads(checker.COMMITTED.read_text())
    assert payload.get("generated_at"), (
        "data.json must record generated_at so the rebuild can be pinned to it")


def test_the_page_check_is_wired_in(checker, tmp_path):
    """index.html is generated from the template plus the data. Without this
    half of the check, editing the template and forgetting to rebuild ships a
    page that is quietly out of date."""
    assert checker.page_is_current(tmp_path) is None


def test_the_page_check_notices_a_template_edit(checker, tmp_path, monkeypatch):
    template = checker.ROOT / "dashboard" / "template.html"
    original = template.read_text()
    try:
        template.write_text(original.replace("<title>", "<title>Edited "))
        assert checker.page_is_current(tmp_path) is not None
    finally:
        template.write_text(original)
    assert checker.page_is_current(tmp_path) is None
