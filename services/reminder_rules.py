"""Pure scheduling rules for the daily attendance reminder (no DB / UI imports).

Kept dependency-free so the "should a reminder be generated right now?"
decision can be unit-tested on its own. Weekdays follow Python's
datetime.weekday(): Monday=0 ... Sunday=6.
"""
from __future__ import annotations
from datetime import datetime, time

DEFAULT_ENABLED = True
DEFAULT_TIME = "09:00"
# Default: every day except Friday (weekly day off in Egypt). Configurable in Settings.
DEFAULT_WORKING_DAYS = [0, 1, 2, 3, 5, 6]

WEEKDAY_NAMES_AR = {
    0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس",
    4: "الجمعة", 5: "السبت", 6: "الأحد",
}


def parse_time(value: str) -> time:
    """'HH:MM' -> datetime.time; falls back to 09:00 on bad input."""
    try:
        h, m = str(value).strip().split(":")[:2]
        return time(int(h), int(m))
    except Exception:
        return time(9, 0)


def parse_days(value) -> list[int]:
    """'0,1,2' (or a list) -> sorted unique weekday ints in 0..6."""
    if isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = str(value or "").split(",")
    days = set()
    for d in raw:
        try:
            n = int(str(d).strip())
        except ValueError:
            continue
        if 0 <= n <= 6:
            days.add(n)
    return sorted(days)


def should_generate(now: datetime, enabled: bool, time_str: str, working_days) -> bool:
    """True when reminders are enabled, today is a working day, and the
    configured time has been reached (so a late app start still catches up
    the same day). Whether a given project was already reminded today is a
    separate check (DB unique constraint)."""
    if not enabled:
        return False
    if now.weekday() not in set(parse_days(working_days)):
        return False
    return now.time() >= parse_time(time_str)
