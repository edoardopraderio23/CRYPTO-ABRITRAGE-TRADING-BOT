"""Smoke tests for repositories. Full integration tests need a real
Postgres container — those come in a follow-up PR.

DESTINATION: tests/db/test_repositories.py
"""

from __future__ import annotations

import pytest

from src.db import repositories as repos


def test_classes_exist() -> None:
    assert hasattr(repos, "BookSnapshotRepo")
    assert hasattr(repos, "CycleRepo")
    assert hasattr(repos, "TradeRepo")
    assert hasattr(repos, "ModelVersionRepo")


def test_from_env_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        repos.BookSnapshotRepo.from_env()
