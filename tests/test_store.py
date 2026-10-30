from datetime import date

import pytest

from carbonstack.domain import Observation
from carbonstack.sites import NYERI, THANJAVUR, as_project
from carbonstack.store import SCHEMA_VERSION, Store, StoreError


@pytest.fixture
def store():
    with Store(":memory:", actor="tester") as s:
        yield s


def test_schema_migrates_and_is_idempotent(tmp_path):
    path = tmp_path / "a.db"
    with Store(path) as a:
        assert a.conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] \
            == SCHEMA_VERSION
    with Store(path) as b:                       # reopening must not re-run DDL
        assert b.list_projects() == []


def test_project_round_trips_with_everything_that_affects_credits(store):
    original = as_project(THANJAVUR)
    store.save_project(original, methodology_id="VM0042")
    back = store.load_project(original.id)

    assert back.id == original.id
    assert back.track == original.track
    assert back.area_ha == pytest.approx(original.area_ha)
    assert back.creditable_area_ha() == pytest.approx(original.creditable_area_ha())
    assert {p.fingerprint for p in back.plots.values()} == \
           {p.fingerprint for p in original.plots.values()}
    assert [e.practice for e in back.enrollments] == \
           [e.practice for e in original.enrollments]


def test_loading_an_unknown_project_is_refused(store):
    with pytest.raises(StoreError):
        store.load_project("nope")


def test_saving_twice_updates_rather_than_duplicates(store):
    p = as_project(NYERI)
    store.save_project(p, methodology_id="VM0047")
    store.save_project(p, methodology_id="VM0047")
    assert len(store.list_projects()) == 1
    kinds = [e["kind"] for e in store.events()]
    assert kinds == ["project.saved", "project.updated"]


def test_reingesting_the_same_pass_is_a_no_op(store):
    """Providers backfill. A pipeline re-run over a processed window must not
    duplicate observations, or every vintage after it is wrong."""
    p = as_project(NYERI)
    store.save_project(p, methodology_id="VM0047")
    plot_id = next(iter(p.plots))
    obs = [Observation(plot_id=plot_id, observed_on=date(2026, 6, 1),
                       variable="canopy_height_m", value=3.1, unit="m",
                       source="sentinel2+gedi", uncertainty=0.6)]

    assert store.add_observations(obs) == 1
    assert store.add_observations(obs) == 0
    assert store.observation_count(p.id) == 1


def test_a_different_source_is_a_different_observation(store):
    """A field measurement and a satellite retrieval on the same day are two
    facts, not one, and a verifier will want to see both."""
    p = as_project(NYERI)
    store.save_project(p, methodology_id="VM0047")
    plot_id = next(iter(p.plots))
    common = dict(plot_id=plot_id, observed_on=date(2026, 6, 1),
                  variable="canopy_height_m", value=3.1, unit="m")

    store.add_observations([Observation(**common, source="sentinel2+gedi")])
    store.add_observations([Observation(**common, source="field_plot")])
    assert store.observation_count(p.id) == 2


def test_latest_observation_date(store):
    p = as_project(NYERI)
    store.save_project(p, methodology_id="VM0047")
    plot_id = next(iter(p.plots))
    assert store.latest_observation_date(p.id) is None
    store.add_observations([
        Observation(plot_id=plot_id, observed_on=d, variable="x", value=1.0,
                    unit="m", source="s")
        for d in (date(2026, 1, 1), date(2026, 5, 5), date(2026, 3, 3))
    ])
    assert store.latest_observation_date(p.id) == date(2026, 5, 5)


def test_add_observations_with_nothing_does_nothing(store):
    assert store.add_observations([]) == 0


# --- the event chain --------------------------------------------------------

def test_every_event_links_to_its_predecessor(store):
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    store.record("verifier.visit", "project", NYERI.id, {"body": "VVB"})
    events = store.events()
    assert len(events) == 2
    assert events[0]["prev_hash"] == "0" * 64
    assert events[1]["prev_hash"] == events[0]["hash"]


def test_chain_verifies_clean(store):
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    assert store.verify_chain() == (True, None)


def test_chain_detects_an_edited_payload(store):
    """The point of the whole mechanism: a row changed behind the application
    is found, and the log says where."""
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    store.record("vintage.quantified", "vintage", "x:2026", {"net_t": 10.0})
    store.record("vintage.issued", "vintage", "x:2026", {"quantity": 10})
    store.conn.commit()

    store.conn.execute(
        "UPDATE events SET payload_json = ? WHERE kind = 'vintage.quantified'",
        ('{"net_t":999.0}',))
    store.conn.commit()

    intact, bad = store.verify_chain()
    assert intact is False
    assert bad == "2"


def test_chain_detects_a_deleted_event(store):
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    for i in range(3):
        store.record("note", "project", NYERI.id, {"i": i})
    store.conn.commit()
    store.conn.execute("DELETE FROM events WHERE id = 3")
    store.conn.commit()
    assert store.verify_chain()[0] is False


def test_events_filter_by_subject(store):
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    store.record("note", "vintage", "v1", {})
    store.record("note", "vintage", "v2", {})
    assert len(store.events("vintage")) == 2
    assert len(store.events("vintage", "v1")) == 1


def test_actor_is_recorded_and_overridable(store):
    store.save_project(as_project(NYERI), methodology_id="VM0047")
    store.record("note", "project", NYERI.id, {}, actor="priya")
    events = store.events()
    assert events[0]["actor"] == "tester"
    assert events[1]["actor"] == "priya"


# --- soil: the pathway whose evidence is physical ---------------------------

def _core(plot_id, when, ref="LAB/1"):
    from carbonstack.soil import SoilCore, SoilLayer
    return SoilCore(plot_id, when, ref, [
        SoilLayer(0, 10, 1.10, 1.32), SoilLayer(10, 30, 0.72, 1.45),
        SoilLayer(30, 40, 0.50, 1.50)])


def _validation(n=14, held_out=True, version="2026.1"):
    from carbonstack.soil import ModelValidation
    return ModelValidation("DayCent", version,
                           [(40.0 + i, 40.0 + i + (-1) ** i * 2.2)
                            for i in range(n)], held_out=held_out)


@pytest.fixture
def rice_store(store):
    store.save_project(as_project(THANJAVUR), methodology_id="VM0042")
    return store, THANJAVUR.id, f"{THANJAVUR.id}-P1"


def test_cores_round_trip_with_their_layers(rice_store):
    store, pid, plot = rice_store
    original = _core(plot, date(2025, 5, 1))
    store.add_soil_core(pid, original, role="baseline")

    back = store.soil_cores(pid, "baseline")[plot]
    assert back.lab_reference == original.lab_reference
    assert back.max_depth_cm == original.max_depth_cm
    assert back.soc_t_ha(30.0) == pytest.approx(original.soc_t_ha(30.0))


def test_a_core_the_lab_cannot_be_traced_to_is_refused(rice_store):
    """An unattributable result is not evidence, and storing it invites it
    into a claim later."""
    store, pid, plot = rice_store
    with pytest.raises(StoreError, match="lab reference"):
        store.add_soil_core(pid, _core(plot, date(2025, 5, 1), ref="  "),
                            role="baseline")


def test_an_unknown_core_role_is_refused(rice_store):
    store, pid, plot = rice_store
    with pytest.raises(StoreError, match="baseline or monitoring"):
        store.add_soil_core(pid, _core(plot, date(2025, 5, 1)), role="whenever")


def test_reingesting_the_same_sampling_does_not_duplicate(rice_store):
    store, pid, plot = rice_store
    core = _core(plot, date(2025, 5, 1))
    store.add_soil_core(pid, core, role="baseline")
    store.add_soil_core(pid, core, role="baseline")
    assert store.conn.execute(
        "SELECT COUNT(*) FROM soil_cores").fetchone()[0] == 1


def test_baseline_and_monitoring_are_separate_roles(rice_store):
    store, pid, plot = rice_store
    store.add_soil_core(pid, _core(plot, date(2025, 5, 1)), role="baseline")
    store.add_soil_core(pid, _core(plot, date(2028, 5, 1), "LAB/2"),
                        role="monitoring")
    assert len(store.soil_cores(pid, "baseline")) == 1
    assert len(store.soil_cores(pid, "monitoring")) == 1


def test_only_an_accepted_validation_is_returned(rice_store):
    """A rejected validation is kept, because a verifier asking why the
    punitive uncertainty applied deserves the evidence -- but it must never be
    handed back as if it justified a number."""
    store, pid, _ = rice_store
    store.add_model_validation(pid, _validation(held_out=False))
    assert store.latest_model_validation(pid) is None

    store.add_model_validation(pid, _validation())
    accepted = store.latest_model_validation(pid)
    assert accepted is not None and accepted.model_name == "DayCent"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM model_validations").fetchone()[0] == 2


def test_an_unversioned_model_is_not_accepted(rice_store):
    store, pid, _ = rice_store
    store.add_model_validation(pid, _validation(version="  "))
    assert store.latest_model_validation(pid) is None


def test_soil_work_lands_in_the_event_chain(rice_store):
    store, pid, plot = rice_store
    store.add_soil_core(pid, _core(plot, date(2025, 5, 1)), role="baseline",
                        actor="field")
    store.add_model_validation(pid, _validation(), actor="science")

    kinds = [e["kind"] for e in store.events() if e["kind"].startswith("soil.")]
    assert kinds == ["soil.core_stored", "soil.model_validated"]
    stored = [e for e in store.events() if e["kind"] == "soil.core_stored"][0]
    assert stored["actor"] == "field"
    assert stored["payload"]["lab_reference"] == "LAB/1"
    assert store.verify_chain() == (True, None)
