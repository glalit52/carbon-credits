import math

from carbonstack.geo import area_ha, bbox, centroid, validate_ring


def square(lon, lat, side_deg):
    return [(lon, lat), (lon + side_deg, lat),
            (lon + side_deg, lat + side_deg), (lon, lat + side_deg)]


def test_area_matches_analytic_value_near_equator():
    # 0.01 deg of latitude is ~1.1132 km; at the equator so is 0.01 deg of longitude.
    ring = square(0.0, 0.0, 0.01)
    expected_ha = (0.01 * math.pi / 180 * 6_371_008.8) ** 2 / 10_000
    assert area_ha(ring) == abs(area_ha(ring))
    assert abs(area_ha(ring) - expected_ha) / expected_ha < 0.001


def test_area_shrinks_with_latitude():
    """Longitude degrees converge toward the poles. A model that ignores this
    over-states high-latitude plots, and hectares are what we get paid on."""
    assert area_ha(square(0, 0, 0.01)) > area_ha(square(0, 60, 0.01))


def test_winding_order_does_not_change_area():
    ring = square(78.4, 17.4, 0.01)
    assert area_ha(ring) == area_ha(list(reversed(ring)))


def test_explicitly_closed_ring_is_not_double_counted():
    ring = square(78.4, 17.4, 0.01)
    assert abs(area_ha(ring) - area_ha([*ring, ring[0]])) < 1e-9


def test_centroid_of_square_is_its_middle():
    lon, lat = centroid(square(10.0, 20.0, 0.02))
    assert abs(lon - 10.01) < 1e-6
    assert abs(lat - 20.01) < 1e-6


def test_bbox():
    assert bbox(square(1.0, 2.0, 0.5)) == (1.0, 2.0, 1.5, 2.5)


def test_validate_accepts_a_plausible_plot():
    assert validate_ring(square(78.4, 17.4, 0.003)) == []


def test_validate_rejects_self_intersection():
    problems = validate_ring([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert any("self-intersect" in p for p in problems)


def test_validate_rejects_degenerate_and_out_of_range():
    assert validate_ring([(0, 0), (1, 1)]) != []
    assert any("out of range" in p for p in validate_ring(
        [(0, 0), (200, 0), (200, 1), (0, 1)]))


def test_validate_flags_implausible_sizes():
    assert any("small" in p for p in validate_ring(square(78.4, 17.4, 0.00001)))
    assert any("large" in p for p in validate_ring(square(78.4, 17.4, 5.0)))
