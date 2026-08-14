from datetime import UTC, datetime, timedelta

from gamecrafter.infrastructure.database import models


def test_utc_now_advances_when_wall_clock_value_repeats(monkeypatch) -> None:
    frozen = datetime(2026, 8, 15, 7, 0, tzinfo=UTC)

    class FrozenDateTime:
        @classmethod
        def now(cls, timezone):
            assert timezone is UTC
            return frozen

    monkeypatch.setattr(models, "datetime", FrozenDateTime)
    monkeypatch.setattr(models, "_last_timestamp", frozen)

    first = models.utc_now()
    second = models.utc_now()

    assert first == frozen + timedelta(microseconds=1)
    assert second == frozen + timedelta(microseconds=2)
