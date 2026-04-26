from datetime import datetime, timedelta, timezone

from resonant_ouroboros.dashboard import HzHistory


def test_hz_history_keeps_only_last_60_seconds():
    history = HzHistory(window_seconds=60)
    start = datetime.now(timezone.utc)
    history.add(418.0, sampled_at=start)
    history.add(426.0, sampled_at=start + timedelta(seconds=30))
    history.add(432.0, sampled_at=start + timedelta(seconds=70))
    rows = history.rows(now=start + timedelta(seconds=70))
    assert len(rows) == 2
    assert rows[0]["hz"] == 426.0
    assert rows[1]["hz"] == 432.0
