"""Soil organic carbon: stocks, equivalent soil mass, sampling and VMD0053.

The soil pathway is the one place a number cannot come from a satellite, and
the two ways it goes wrong are both tested here: a fixed-depth comparison that
credits compaction as sequestration, and a model nobody validated standing in
for measurement.
"""

from datetime import date

import pytest

from carbonstack.soil import (
    CARBON_TO_CO2E, ModelValidation, SamplingDesign, SoilCore, SoilLayer,
    Stratum, esm_stock_change, soc_at_equivalent_mass,
)


def core(plot="P1", when=date(2025, 5, 1), ref="LAB/1", layers=None):
    return SoilCore(plot, when, ref, layers or [
        SoilLayer(0, 10, 1.10, 1.32),
        SoilLayer(10, 30, 0.72, 1.45),
        SoilLayer(30, 40, 0.50, 1.50),
    ])


# --- the arithmetic ---------------------------------------------------------

def test_soil_mass_matches_the_hand_calculation():
    """30 cm at bulk density 1.3 is 3,900 t/ha, which is the 0-3.9 Gg/ha range
    VM0042 works in. If this is wrong every downstream number is wrong."""
    layer = SoilLayer(0, 30, 1.0, 1.3)
    assert layer.soil_mass_t_ha == pytest.approx(3900.0)


def test_carbon_stock_matches_the_hand_calculation():
    """1% carbon at BD 1.3 over 30 cm is 39 t C/ha."""
    layer = SoilLayer(0, 30, 1.0, 1.3)
    assert layer.soc_t_ha == pytest.approx(39.0)


def test_coarse_fragments_are_excluded_from_the_stock():
    """Stones hold no carbon, and counting their volume as soil inflates every
    stock on a gravelly site."""
    solid = SoilLayer(0, 30, 1.0, 1.3)
    stony = SoilLayer(0, 30, 1.0, 1.3, coarse_fragment_frac=0.25)
    assert stony.soc_t_ha == pytest.approx(solid.soc_t_ha * 0.75)


def test_impossible_layers_are_refused_at_construction():
    with pytest.raises(ValueError, match="no thickness"):
        SoilLayer(10, 10, 1.0, 1.3)
    with pytest.raises(ValueError, match="bulk density"):
        SoilLayer(0, 30, 1.0, 0.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        SoilLayer(0, 30, -1.0, 1.3)
    with pytest.raises(ValueError, match="coarse fragment"):
        SoilLayer(0, 30, 1.0, 1.3, coarse_fragment_frac=1.0)


def test_overlapping_layers_are_refused():
    with pytest.raises(ValueError, match="overlap"):
        SoilCore("P1", date(2025, 5, 1), "LAB/1",
                 [SoilLayer(0, 20, 1.0, 1.3), SoilLayer(10, 30, 1.0, 1.3)])


def test_a_partial_layer_is_prorated_to_the_comparison_depth():
    c = core(layers=[SoilLayer(0, 10, 1.0, 1.3), SoilLayer(10, 40, 1.0, 1.3)])
    # 30 cm takes all of the first layer and two thirds of the second.
    assert c.soc_t_ha(30.0) == pytest.approx(13.0 + 39.0 * (20 / 30))


def test_a_core_without_a_lab_reference_is_not_evidence():
    assert any("lab reference" in p
               for p in core(ref="  ").issues)


def test_a_core_that_misses_the_surface_is_flagged():
    c = SoilCore("P1", date(2025, 5, 1), "LAB/1", [SoilLayer(5, 30, 1.0, 1.3)])
    assert any("surface layer" in p for p in c.issues)


# --- equivalent soil mass ---------------------------------------------------

def test_compaction_alone_reads_as_a_gain_at_fixed_depth():
    """The finding this whole module exists for. The same 30 cm of a denser
    soil holds more carbon without a gram having been sequestered."""
    base = core(layers=[SoilLayer(0, 10, 1.20, 1.25), SoilLayer(10, 30, 0.90, 1.35),
                        SoilLayer(30, 45, 0.60, 1.45)])
    compacted = core(when=date(2028, 5, 1), ref="LAB/2", layers=[
        SoilLayer(0, 10, 1.09, 1.38), SoilLayer(10, 30, 0.82, 1.49),
        SoilLayer(30, 45, 0.55, 1.58)])

    change = esm_stock_change(base, compacted)
    assert change.fixed_depth_change_t_ha > 0      # looks like sequestration
    assert change.change_t_ha < 0                  # it is not
    assert change.compaction_artefact_t_ha > 2.0
    assert any("bulk density moved" in w for w in change.warnings)


def test_a_real_gain_survives_the_correction():
    base = core()
    better = core(when=date(2028, 5, 1), ref="LAB/2", layers=[
        SoilLayer(0, 10, 1.34, 1.24), SoilLayer(10, 30, 0.86, 1.38),
        SoilLayer(30, 40, 0.55, 1.47)])
    change = esm_stock_change(base, better)
    assert change.change_t_ha > 0
    assert change.change_t_co2e_ha == pytest.approx(
        change.change_t_ha * CARBON_TO_CO2E)


def test_identical_cores_show_no_change():
    change = esm_stock_change(core(), core(when=date(2028, 5, 1), ref="LAB/2"))
    assert change.change_t_ha == pytest.approx(0.0, abs=1e-9)


def test_extrapolating_past_the_bottom_of_a_core_is_refused():
    """Sampling only to the comparison depth means a loosened soil can never
    reach the reference mass, and inventing the missing carbon is not an
    option. The error says what to do instead."""
    shallow = core(layers=[SoilLayer(0, 10, 1.10, 1.32),
                           SoilLayer(10, 30, 0.72, 1.45)])
    looser = SoilCore("P1", date(2028, 5, 1), "LAB/2",
                      [SoilLayer(0, 10, 1.20, 1.15), SoilLayer(10, 30, 0.80, 1.28)])
    with pytest.raises(ValueError, match="sample deeper"):
        esm_stock_change(shallow, looser)


def test_cores_from_different_plots_or_out_of_order_are_refused():
    with pytest.raises(ValueError, match="different plots"):
        esm_stock_change(core("P1"), core("P2", when=date(2028, 5, 1)))
    with pytest.raises(ValueError, match="not later"):
        esm_stock_change(core(when=date(2028, 5, 1)), core(when=date(2025, 5, 1)))


def test_soc_at_equivalent_mass_interpolates_within_a_layer():
    c = core(layers=[SoilLayer(0, 30, 1.0, 1.3)])       # 3900 t/ha, 39 t C/ha
    assert soc_at_equivalent_mass(c, 1950.0) == pytest.approx(19.5)
    assert soc_at_equivalent_mass(c, 3900.0) == pytest.approx(39.0)


# --- sampling design --------------------------------------------------------

def design(**kw):
    return SamplingDesign(strata=[
        Stratum("clay loam", 320.0, 9.5),
        Stratum("sandy loam", 180.0, 14.0),
        Stratum("saline patch", 40.0, 6.0)], **kw)


def test_samples_go_where_the_variance_is():
    """Neyman allocation. An even split over these strata buys less precision
    for the same number of cores, and cores dominate the cost."""
    required = design().required_samples()
    assert required["sandy loam"] > required["saline patch"]
    assert all(n >= 3 for n in required.values())


def test_a_tighter_margin_costs_more_cores():
    loose = sum(design(target_margin_t_ha=4.0).required_samples().values())
    tight = sum(design(target_margin_t_ha=1.0).required_samples().values())
    assert tight > loose * 3


def test_every_stratum_gets_at_least_three_cores():
    """A stratum with one or two cores has no usable variance of its own,
    whatever the formula says."""
    tiny = SamplingDesign(strata=[Stratum("a", 1000.0, 0.01),
                                  Stratum("b", 1.0, 0.01)])
    assert min(tiny.required_samples().values()) >= 3


def test_the_design_says_to_sample_deeper_than_the_comparison_depth():
    """The constraint that prevents the unreachable-reference-mass failure
    years later, when the core can no longer be extended."""
    plan = design().plan()
    assert plan["recommended_sampling_depth_cm"] > plan["comparison_depth_cm"]
    assert "headroom" in plan["depth_note"]


def test_outstanding_samples_net_off_what_is_already_collected():
    d = SamplingDesign(strata=[Stratum("a", 100.0, 10.0, existing_samples=5)])
    plan = d.plan()
    assert plan["outstanding_samples"]["a"] == max(
        0, plan["required_samples"]["a"] - 5)


def test_a_stratum_with_no_area_is_refused():
    with pytest.raises(ValueError, match="no area"):
        Stratum("a", 0.0, 10.0)


# --- VMD0053 model validation ----------------------------------------------

def perfect(n=14):
    return ModelValidation("DayCent", "2026.1", [(40.0 + i, 40.0 + i)
                                                 for i in range(n)])


def test_a_perfect_model_has_no_error():
    v = perfect()
    assert v.rmse_t_ha == pytest.approx(0.0)
    assert v.bias_t_ha == pytest.approx(0.0)
    assert v.r_squared == pytest.approx(1.0)
    assert v.acceptable


def test_bias_is_added_to_scatter_rather_than_averaged_away():
    """A systematic offset does not cancel across plots the way noise does, so
    treating the two the same understates the error of the worse model."""
    noisy = ModelValidation("m", "1", [(50.0, 50.0 + (-1) ** i * 5)
                                       for i in range(14)])
    biased = ModelValidation("m", "1", [(50.0, 55.0) for _ in range(14)])
    assert noisy.bias_t_ha == pytest.approx(0.0, abs=1e-9)
    assert biased.bias_t_ha == pytest.approx(5.0)
    assert biased.relative_uncertainty > noisy.relative_uncertainty


def test_a_model_scored_on_its_training_data_is_not_accepted():
    v = ModelValidation("m", "1", [(40.0 + i, 40.0 + i) for i in range(14)],
                        held_out=False)
    assert not v.acceptable
    assert any("independent validation set" in p for p in v.issues())


def test_too_few_pairs_cannot_characterise_performance():
    v = perfect(n=4)
    assert not v.acceptable
    assert any("cannot be characterised" in p for p in v.issues())


def test_an_unversioned_model_cannot_be_reproduced():
    v = ModelValidation("DayCent", "  ", [(40.0 + i, 40.0 + i) for i in range(14)])
    assert any("no version pinned" in p for p in v.issues())


def test_the_validation_report_cites_vmd0053():
    report = perfect().report()
    assert any("VMD0053" in c for c in report.citations)
    labels = [t.label for t in report]
    assert "RMSE" in labels and "bias" in labels and "R squared" in labels
