"""Facts cannot exist without a history, and staleness must survive."""

from __future__ import annotations

from datetime import timedelta

import pytest

from aicio.provenance import (
    AUTHORITATIVE, Fact, FactSheet, Provenance, SourceKind, assumption, utcnow,
)


def _prov(days_old: int = 0, kind: SourceKind = SourceKind.MARKET_DATA) -> Provenance:
    return Provenance(kind, "test", utcnow() - timedelta(days=days_old))


def test_fact_id_is_content_addressed():
    """The same fact computed twice is the same fact, which is what makes a
    recommendation reproducible."""
    source = _prov()
    left = Fact("nav", 78.12, "INR", source)
    right = Fact("nav", 78.12, "INR", source)
    assert left.id == right.id
    assert Fact("nav", 78.13, "INR", source).id != left.id


def test_fact_id_includes_when_it_was_observed():
    """Today's NAV and yesterday's are different facts even at the same value,
    because a recommendation built on one is not built on the other."""
    assert Fact("nav", 78.12, "INR", _prov(0)).id != Fact("nav", 78.12, "INR", _prov(1)).id


def test_float_noise_does_not_change_identity():
    base = _prov()
    assert Fact("x", 1.0, "u", base).id == Fact("x", 1.0 + 1e-12, "u", base).id


def test_market_data_goes_stale():
    assert not Fact("nav", 1.0, "", _prov(1)).is_stale()
    assert Fact("nav", 1.0, "", _prov(30)).is_stale()


def test_confidence_decays_with_age_but_never_to_zero():
    fresh = Fact("nav", 1.0, "", _prov(0)).confidence()
    old = Fact("nav", 1.0, "", _prov(30)).confidence()
    assert fresh == pytest.approx(1.0)
    assert 0.19 < old < fresh


def test_model_and_assumption_are_not_authoritative():
    assert SourceKind.MODEL not in AUTHORITATIVE
    assert SourceKind.ASSUMPTION not in AUTHORITATIVE
    assert not Fact("guess", 1.0, "", assumption("a guess")).authoritative


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        Provenance(SourceKind.MODEL, "x", utcnow(), confidence=1.4)


def test_derive_records_its_inputs():
    source = _prov()
    derived = source.derive("aicio.engine", "summed", inputs=["f_1", "f_2"])
    assert derived.kind is SourceKind.DERIVED
    assert derived.inputs == ("f_1", "f_2")


def test_factsheet_tracks_limitations_and_weakest_link():
    sheet = FactSheet("test")
    sheet.record("a", 1.0, "u", _prov(0))
    sheet.record("b", 2.0, "u", _prov(40))
    sheet.note("something is missing")
    assert sheet.value("a") == 1.0
    assert len(sheet.stale()) == 1
    assert sheet.weakest_confidence() < 1.0
    assert "something is missing" in sheet.render()


def test_provenance_round_trips_through_json():
    original = _prov(3)
    assert Provenance.from_dict(original.to_dict()) == original
