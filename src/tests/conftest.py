"""Test setup: put src/ on sys.path and give every test a fresh seeded database file."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.seed import reset_demo_data  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """A file (not :memory:) so the concurrency test can open several connections."""
    monkeypatch.setenv("CAMPUS_FOOD_DB", str(tmp_path / "test.db"))
    reset_demo_data()
