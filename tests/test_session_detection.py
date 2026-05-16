# Author: Nicholas Corrieri

from datetime import datetime, timedelta

from rawdog.session_detection import detect_sessions


def test_detect_sessions_by_time_gap() -> None:
    start = datetime(2026, 5, 16, 8, 0)
    captures = [
        start,
        start + timedelta(minutes=20),
        start + timedelta(hours=4),
        start + timedelta(hours=4, minutes=30),
    ]

    sessions = detect_sessions(captures, gap=timedelta(hours=2))

    assert len(sessions) == 2
    assert sessions[0].file_count == 2
    assert sessions[1].file_count == 2
