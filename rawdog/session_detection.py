# Author: Nicholas Corrieri

from __future__ import annotations

from datetime import datetime, timedelta

from rawdog.models import SessionCandidate


def detect_sessions(
    capture_times: list[datetime],
    gap: timedelta = timedelta(hours=2),
) -> list[SessionCandidate]:
    if not capture_times:
        return []

    ordered = sorted(capture_times)
    sessions: list[list[datetime]] = [[ordered[0]]]
    for captured_at in ordered[1:]:
        if captured_at - sessions[-1][-1] >= gap:
            sessions.append([captured_at])
        else:
            sessions[-1].append(captured_at)

    return [
        SessionCandidate(
            start_at=session[0],
            end_at=session[-1],
            file_count=len(session),
        )
        for session in sessions
    ]
