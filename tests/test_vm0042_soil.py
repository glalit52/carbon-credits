"""VM0042's measure-and-model soil pathway.

Kept out of the provider-driven registry on purpose: soil takes physical
cores, a lab reference and a VMD0053 validation report, not a satellite
retrieval. These tests pin the refusals that make the pathway defensible.
"""

from datetime import date

import pytest

from carbonstack import methodology
from carbonstack.methodology.vm0042_soil import UNVALIDATED_MODEL_UNCERTAINTY
from carbonstack.sites import THANJAVUR, as_project
from carbonstack.soil import ModelValidation, SoilCore, SoilLayer

BASE_LAYERS = [SoilLayer(0, 10, 1.10, 1.32), SoilLayer(10, 30, 0.72, 1.45),
               SoilLayer(30, 40, 0.50, 1.50)]
GAIN_LAYERS = [SoilLayer(0, 10, 1.34, 1.24), SoilLayer(10, 30, 0.86, 1.38),
               SoilLayer(30, 40, 0.55, 1.47)]
LOSS_LAYERS = [SoilLayer(0, 10, 0.92, 1.30), SoilLayer(10, 30, 0.60, 1.44),
               SoilLayer(30, 40, 0.44, 1.49)]


@pytest.fixture
def project():
    return as_project(THANJAVUR)


@pytest.fixture
def plot_id(project):
    return next(iter(project.plots))


def cores(plot_id, layers):
    return (
        {plot_id: SoilCore(plot_id, date(2025, 5, 1), "LAB/1", BASE_LAYERS)},
        {plot_id: SoilCore(plot_id, date(2028, 5, 1), "LAB/2", layers)},
    )


def validated(n=14, spread=2.2):
    return ModelValidation("DayCent", "2026.1",
                           [(40.0 + i, 40.0 + i + (-1) ** i * spread)
                            for i in range(n)])


def run(project, plot_id, layers=GAIN_LAYERS, validation=None, year=2028):
    base, mon = cores(plot_id, layers)
    return methodology.soil_pathway(validation=validation).quantify(
        project, baseline_cores=base, monitoring_cores=mon, reporting_year=year)


# --- identity ---------------------------------------------------------------

def test_the_soil_pathway_is_not_in_the_provider_registry():
    """Its quantify takes cores, not a Provider, so resolving it by id would
    hand callers something they cannot drive the same way."""
    assert "VM0042" in methodology.available()
    assert methodology.soil_pathway().credits_soil_carbon is True
    assert methodology.get("VM0042").id == "VM0042"


def test_soil_carries_a_buffer_unlike_avoided_methane():
    """Soil carbon is a stock and a single tillage pass can release it, which
    is exactly the difference from VM0051's avoided methane."""
    meth = methodology.soil_pathway()
    assert meth.buffer_fraction > 0
    assert "tillage" in meth.buffer_basis


# --- quantification ---------------------------------------------------------

def test_a_measured_gain_credits(project, plot_id):
    result = run(project, plot_id, validation=validated())
    assert result.gross_t > 0
    assert result.net_t > 0
    assert result.net_t < result.gross_t          # the buffer bites


def test_a_measured_loss_credits_nothing_and_says_so(project, plot_id):
    """Crediting only the gains and ignoring the losses is how a portfolio
    drifts upward without anyone lying."""
    result = run(project, plot_id, layers=LOSS_LAYERS, validation=validated())
    assert result.gross_t == 0.0
    assert result.net_t == 0.0
    assert any("no net soil carbon gain" in w for w in result.warnings)


def test_an_unvalidated_model_gets_the_punitive_default(project, plot_id):
    """VMD0053's point is that unvalidated model output is not evidence. This
    is what assuming it anyway costs."""
    with_model = run(project, plot_id, validation=validated())
    without = run(project, plot_id, validation=None)

    assert without.relative_uncertainty == UNVALIDATED_MODEL_UNCERTAINTY
    assert without.relative_uncertainty > with_model.relative_uncertainty
    assert without.net_t < with_model.net_t
    assert any("no VMD0053 model validation" in w for w in without.warnings)


def test_a_model_scored_on_training_data_is_treated_as_unvalidated(project, plot_id):
    bad = ModelValidation("m", "1", [(40.0 + i, 40.0 + i) for i in range(14)],
                          held_out=False)
    result = run(project, plot_id, validation=bad)
    assert result.relative_uncertainty == UNVALIDATED_MODEL_UNCERTAINTY
    assert any("independent validation set" in w for w in result.warnings)


def test_a_better_model_issues_more_credits(project, plot_id):
    """The commercial case for calibration, in one test: the same cores, the
    same carbon, a tighter model."""
    loose = run(project, plot_id, validation=validated(spread=9.0))
    tight = run(project, plot_id, validation=validated(spread=1.0))
    assert loose.gross_t == pytest.approx(tight.gross_t)
    assert tight.net_t > loose.net_t


def test_plots_without_paired_cores_contribute_nothing(project, plot_id):
    """Soil is credited on what was measured, not on what was assumed about
    the plots nobody visited."""
    base, _ = cores(plot_id, GAIN_LAYERS)
    result = methodology.soil_pathway(validation=validated()).quantify(
        project, baseline_cores=base, monitoring_cores={}, reporting_year=2028)
    assert result.gross_t == 0.0
    assert any("no paired baseline and monitoring core" in w
               for w in result.warnings)


def test_an_unreachable_reference_mass_is_reported_not_guessed(project, plot_id):
    shallow = {plot_id: SoilCore(plot_id, date(2025, 5, 1), "LAB/1",
                                 [SoilLayer(0, 10, 1.10, 1.32),
                                  SoilLayer(10, 30, 0.72, 1.45)])}
    looser = {plot_id: SoilCore(plot_id, date(2028, 5, 1), "LAB/2",
                                [SoilLayer(0, 10, 1.20, 1.15),
                                 SoilLayer(10, 30, 0.80, 1.28)])}
    result = methodology.soil_pathway(validation=validated()).quantify(
        project, baseline_cores=shallow, monitoring_cores=looser,
        reporting_year=2028)
    assert result.gross_t == 0.0
    assert any("sample deeper" in w for w in result.warnings)


def test_the_compaction_warning_reaches_the_vintage(project, plot_id):
    compacted = [SoilLayer(0, 10, 1.05, 1.46), SoilLayer(10, 30, 0.69, 1.60),
                 SoilLayer(30, 40, 0.48, 1.65)]
    result = run(project, plot_id, layers=compacted, validation=validated())
    assert any("bulk density moved" in w for w in result.warnings)


# --- the derivation ---------------------------------------------------------

def test_the_derivation_cites_vmd0053_and_the_esm_basis(project, plot_id):
    result = run(project, plot_id, validation=validated())
    joined = " ".join(c for calc in result.calculations for c in calc.citations)
    assert "VMD0053" in joined
    assert "equivalent soil mass" in joined.lower()

    summary = result.calculations[-1]
    labels = [t.label for t in summary]
    assert "area with paired cores" in labels
    assert "model uncertainty" in labels


def test_programme_gaps_still_surface_on_the_soil_pathway(project, plot_id):
    project.methodology_version = ""
    project.consultation = None
    result = run(project, plot_id, validation=validated())
    assert any("methodology version" in w for w in result.warnings)
