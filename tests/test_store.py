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
