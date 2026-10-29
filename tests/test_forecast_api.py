"""The forecast as the web app calls it: numbers in, a forward-sale answer out."""

import pytest

from carbonstack.api import dispatch
from carbonstack.forecast_api import ForecastError, forecast_request


def body(**over):
    base = {
        "project_id": "P1", "track": "rice", "enrolled_units": 12, "trials": 600,
        "projections": [
            {"year": 2025, "net_t": 9.4, "relative_uncertainty": 0.1, "settled": True},
            {"year": 2026, "net_t": 9.0, "relative_uncertainty": 0.1},
            {"year": 2027, "net_t": 9.0, "relative_uncertainty": 0.1},
        ],
    }
    return {**base, **over}


def test_safe_volume_sits_below_the_projection():
    out = forecast_request(body())
    f = out["forecast"]
    assert 0 < f["safe_total_t"] < f["projected_total_t"]
    assert [y["year"] for y in f["years"]] == [2025, 2026, 2027]
    assert out["offtake"] is None


def test_it_is_reproducible():
    assert forecast_request(body()) == forecast_request(body())


def test_more_farmers_means_a_larger_safe_share():
    curve = forecast_request(body())["aggregation"]
    units = [row["units"] for row in curve]
    assert 12 in units, "the project's own size is on the curve"
    assert curve[-1]["safe_t"] >= curve[0]["safe_t"]


def test_supplied_rates_replace_the_placeholders():
    harsh = forecast_request(body(risk={"dropout_per_year": 0.5, "practice_lapse_per_year": 0.5}))
    mild = forecast_request(body(risk={"dropout_per_year": 0.0, "practice_lapse_per_year": 0.0}))
    assert harsh["forecast"]["safe_total_t"] < mild["forecast"]["safe_total_t"]
    assert "supplied by the project" in harsh["risk"]["source"]


def test_an_oversized_sale_is_not_signable():
    out = forecast_request(body(offtake={"committed_t": 27.0, "replacement_price": 30}))
    assert out["offtake"]["delivery_probability"] < 0.9
    assert "sign" in out["offtake"]["verdict"] or "under-collateralised" in out["offtake"]["verdict"]
    small = forecast_request(body(offtake={"committed_t": 1.0, "replacement_price": 30}))
    assert small["offtake"]["verdict"].startswith("signable")


@pytest.mark.parametrize("change,message", [
    ({"track": "biochar"}, "track must be one of"),
    ({"projections": []}, "at least one year"),
    ({"projections": [{"year": 2025, "net_t": 1}, {"year": 2025, "net_t": 2}]}, "appears twice"),
    ({"projections": [{"year": 2025, "net_t": -1}]}, "net_t for 2025"),
    ({"confidence": 1.0}, "confidence"),
    ({"risk": {"dropout_per_year": 2}}, "dropout_per_year"),
])
def test_bad_requests_say_what_to_fix(change, message):
    with pytest.raises(ForecastError, match=message):
        forecast_request(body(**change))


def test_the_api_route_maps_bad_input_to_422():
    status, payload = dispatch(None, "POST", "/api/forecast", {}, {"track": "x"})
    assert status == 422 and "track" in payload["error"]
