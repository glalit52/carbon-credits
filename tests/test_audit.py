import pytest

from carbonstack.audit import Calculation


def test_add_returns_the_value_so_call_sites_read_as_arithmetic():
    c = Calculation("x")
    assert c.add("a", 3.0) * 2 == 6.0


def test_result_before_finish_is_an_error():
    c = Calculation("x")
    c.add("a", 1.0)
    with pytest.raises(ValueError):
        _ = c.result


def test_render_includes_terms_and_sources():
    c = Calculation("demo", "tCO2e")
    c.add("area", 10.0, "ha", "from boundary")
    c.cite("VM0047 v1.1")
    c.finish(42.0)
    out = c.render()
    assert "area" in out and "10" in out
    assert "from boundary" in out
    assert "VM0047 v1.1" in out
    assert "42" in out


def test_cite_is_idempotent():
    c = Calculation("demo")
    c.cite("a")
    c.cite("a")
    assert c.citations == ["a"]


def test_to_dict_round_trips_the_trail():
    c = Calculation("demo", "tCO2e")
    c.add("area", 10.0, "ha")
    c.finish(1.0)
    d = c.to_dict()
    assert d["result"] == 1.0
    assert d["terms"][0]["label"] == "area"
