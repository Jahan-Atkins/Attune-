"""
Pure scheduling-matching logic — no database, no FastAPI — so it can be
unit tested directly (see tests/test_matching.py) before it's ever wired
into a route.

Overlap rule (decided explicitly, per SCHEDULING-ROADMAP.md Part E): a
match exists only if a full `duration_minutes` slot fits inside the
*intersection* of the customer's requested window and the instructor's
availability block on that day — not just "the windows touch at all".
The matched slot starts at the earliest point both windows agree on
(max of the two start times), so the customer gets the soonest lesson
that satisfies what they asked for.
"""
from typing import List, Optional, Tuple

# (day_of_week, start_time "HH:MM", end_time "HH:MM")
AvailabilityTuple = Tuple[int, str, str]


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def has_overlap(
    requested_day: int,
    requested_start: str,
    requested_end: str,
    duration_minutes: int,
    availability_blocks: List[AvailabilityTuple],
) -> Optional[Tuple[str, str]]:
    """
    Returns the (matched_start, matched_end) "HH:MM" pair for the first
    availability block on `requested_day` that has room for a
    `duration_minutes` slot inside the overlap with the customer's
    requested window — or None if no block qualifies.
    """
    requested_start_min = _to_minutes(requested_start)
    requested_end_min = _to_minutes(requested_end)

    for day_of_week, block_start, block_end in availability_blocks:
        if day_of_week != requested_day:
            continue
        block_start_min = _to_minutes(block_start)
        block_end_min = _to_minutes(block_end)

        overlap_start = max(requested_start_min, block_start_min)
        overlap_end = min(requested_end_min, block_end_min)

        if overlap_end - overlap_start >= duration_minutes:
            matched_start_min = overlap_start
            matched_end_min = matched_start_min + duration_minutes
            return _to_hhmm(matched_start_min), _to_hhmm(matched_end_min)

    return None
