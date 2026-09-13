"""Shared fixtures for the Personal AI CIO tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aicio.analysis import analyse                      # noqa: E402
from aicio.decisions import generate                    # noqa: E402
from aicio.seed import demo_bundle                      # noqa: E402


@pytest.fixture(scope="session")
def bundle():
    return demo_bundle()


@pytest.fixture(scope="session")
def analysis(bundle):
    # Fewer Monte Carlo trials than production: the seeded simulation is
    # deterministic either way, and the tests are run on every commit.
    return analyse(
        bundle["portfolio"], bundle["profile"], bundle["policy"], bundle["goals"],
        today=bundle["as_of"], quality=bundle["quality"], behaviour=bundle["behaviour"],
        monte_carlo_trials=400,
    )


@pytest.fixture(scope="session")
def recommendations(analysis, bundle):
    return generate(analysis, today=bundle["as_of"], limit=0)


@pytest.fixture
def store(tmp_path):
    from aicio.crypto import SealedBox
    from aicio.store import Store

    box = SealedBox.from_secret("test-secret", salt=b"0123456789abcdef", purpose="documents")
    store = Store(tmp_path / "test.db", actor="test", box=box)
    yield store
    store.close()


@pytest.fixture
def seeded_store(store, bundle):
    store.save_user(bundle["user"])
    store.save_profile(bundle["profile"])
    store.save_policy(bundle["policy"])
    store.save_goals(bundle["goals"])
    store.save_portfolio(bundle["portfolio"])
    return store
