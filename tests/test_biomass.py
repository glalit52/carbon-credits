import pytest

from carbonstack.audit import Calculation
from carbonstack.biomass import CO2_PER_C, Allometry, co2e_per_ha


def test_zero_height_is_zero_stock():
    value, sigma = co2e_per_ha(0.0)
    assert value == 0.0
    assert sigma == 0.0


def test_stock_increases_with_height():
    heights = [2, 5, 10, 15, 20]
    values = [co2e_per_ha(h)[0] for h in heights]
    assert values == sorted(values)


def test_chain_matches_hand_calculation():
    allo = Allometry(a=1.0, b=2.0, relative_error=0.0)
    agb = 1.0 * 10 ** 2
    expected = (agb + agb * 0.27) * 0.47 * CO2_PER_C
    value, _ = co2e_per_ha(10.0, allometry=allo, root_shoot=0.27)
    assert value == pytest.approx(expected)


def test_height_error_is_amplified_by_the_exponent():
    """A power law with b=1.85 turns a 10% height error into an 18.5% biomass
    error. Under-propagating this is how a project walks into a punitive
    uncertainty deduction it did not budget for."""
    allo = Allometry(relative_error=0.0)
    _, sigma = co2e_per_ha(10.0, allometry=allo, height_uncertainty_m=1.0)
    value, _ = co2e_per_ha(10.0, allometry=allo)
    assert sigma / value == pytest.approx(allo.b * 0.1, rel=1e-6)


def test_errors_combine_in_quadrature():
    allo = Allometry(relative_error=0.25)
    value, sigma = co2e_per_ha(10.0, allometry=allo, height_uncertainty_m=1.0)
    expected_rel = (allo.b * 0.1) ** 2 + 0.25 ** 2
    assert (sigma / value) ** 2 == pytest.approx(expected_rel)


def test_calculation_records_every_step():
    calc = Calculation("stock", "tCO2e/ha")
    co2e_per_ha(8.0, height_uncertainty_m=1.0, calc=calc)
    labels = [t.label for t in calc]
    assert "above-ground biomass" in labels
    assert "below-ground biomass" in labels
    assert "carbon" in labels
    assert calc.result > 0
    assert calc.citations
