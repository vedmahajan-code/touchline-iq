"""Shared match-event schema and offline data helpers for Touchline IQ.

Coordinates use a 0–100 pitch: x runs from the team's own goal (0) toward
the opposition goal (100), and y runs from the top touchline (0) to the
bottom touchline (100). Synthetic events are explicitly marked in ``source``.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


EVENT_FIELDS = (
    "event_id",
    "minute",
    "second",
    "team",
    "player",
    "event_type",
    "outcome",
    "start_x",
    "start_y",
    "end_x",
    "end_y",
    "description",
    "source",
)

EVENT_TYPES = frozenset({"pass", "recovery", "shot", "turnover", "goal"})
OUTCOMES = frozenset({"successful", "unsuccessful", "scored", "n/a"})
SOURCES = frozenset({"synthetic", "manual"})
SYNTHETIC_MATCH_ID = "synthetic-northbridge-harbour-seed-42"
SYNTHETIC_COMPETITION = "Touchline Demo Cup"
SYNTHETIC_TEAMS = ("Northbridge FC", "Harbour City")
SYNTHETIC_PLAYERS = {
    "Northbridge FC": ("A. Cole", "M. Silva", "J. Reed", "T. Okafor", "L. Byrne", "D. Khan"),
    "Harbour City": ("R. Costa", "E. Ward", "S. Ibrahim", "N. Park", "P. Morgan", "C. Lewis"),
}


class EventValidationError(ValueError):
    """Raised when an event does not conform to the shared event schema."""


def _number(value: Any, field: str, event_id: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EventValidationError(f"{event_id}: {field} must be a number") from exc
    if not 0 <= result <= 100:
        raise EventValidationError(f"{event_id}: {field} must be between 0 and 100")
    return result


def validate_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and normalize events, returning fresh dictionaries.

    Required columns are listed in ``EVENT_FIELDS``. Coordinate fields may be
    blank when not applicable (for example, a goal); all other fields are
    required. This function accepts rows from CSV or manually constructed data.
    """
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for row_number, raw in enumerate(events, start=1):
        event_id = str(raw.get("event_id", "")).strip()
        if not event_id:
            raise EventValidationError(f"row {row_number}: event_id is required")
        if event_id in seen_ids:
            raise EventValidationError(f"{event_id}: duplicate event_id")
        seen_ids.add(event_id)

        missing = [field for field in EVENT_FIELDS if field not in raw]
        if missing:
            raise EventValidationError(f"{event_id}: missing columns: {', '.join(missing)}")

        try:
            minute, second = int(raw["minute"]), int(raw["second"])
        except (TypeError, ValueError) as exc:
            raise EventValidationError(f"{event_id}: minute and second must be integers") from exc
        if minute < 0 or second < 0 or second > 59:
            raise EventValidationError(f"{event_id}: minute must be nonnegative and second 0–59")

        team = str(raw["team"]).strip()
        player = str(raw["player"]).strip()
        event_type = str(raw["event_type"]).strip().lower()
        outcome = str(raw["outcome"]).strip().lower()
        source = str(raw["source"]).strip().lower()
        description = str(raw["description"]).strip()
        if not team or not player or not description:
            raise EventValidationError(f"{event_id}: team, player, and description are required")
        if event_type not in EVENT_TYPES:
            raise EventValidationError(f"{event_id}: event_type must be one of {sorted(EVENT_TYPES)}")
        if outcome not in OUTCOMES:
            raise EventValidationError(f"{event_id}: outcome must be one of {sorted(OUTCOMES)}")
        if source not in SOURCES:
            raise EventValidationError(f"{event_id}: source must be 'synthetic' or 'manual'")

        event: dict[str, Any] = {
            "event_id": event_id,
            "minute": minute,
            "second": second,
            "team": team,
            "player": player,
            "event_type": event_type,
            "outcome": outcome,
        }
        for axis in ("start_x", "start_y", "end_x", "end_y"):
            value = raw[axis]
            event[axis] = None if value is None or str(value).strip() == "" else _number(value, axis, event_id)
        event.update(description=description, source=source)
        validated.append(event)

    return sorted(validated, key=lambda event: (event["minute"], event["second"], event["event_id"]))


def load_manual_events(path: str | Path) -> list[dict[str, Any]]:
    """Load a manually annotated CSV and validate it against the shared schema.

    CSV must have the ``EVENT_FIELDS`` column names. Its source column may be
    omitted or blank; loaded rows are always labelled ``manual``.
    """
    with Path(path).open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise EventValidationError("CSV is empty or has no header row")
        missing = [field for field in EVENT_FIELDS if field != "source" and field not in reader.fieldnames]
        if missing:
            raise EventValidationError(f"CSV missing columns: {', '.join(missing)}")
        rows = []
        for row in reader:
            row["source"] = "manual"
            rows.append(row)
    return validate_events(rows)


def generate_synthetic_match(seed: int = 42) -> list[dict[str, Any]]:
    """Create one deterministic, chronologically scripted 90-minute demo match.

    The seed controls fictional player attribution for non-goal actions. The
    match, team, and event identities and the sequence of football actions are
    stable. Scores are represented by explicit ``goal`` rows, separate from
    their corresponding ``shot`` rows.
    """
    rng = random.Random(seed)
    teams = SYNTHETIC_TEAMS
    players = SYNTHETIC_PLAYERS
    events: list[dict[str, Any]] = []

    def add(minute: int, second: int, team: str, event_type: str, outcome: str,
            start: tuple[float, float] | None, end: tuple[float, float] | None,
            description: str) -> None:
        idx = len(events) + 1
        events.append({
            "event_id": f"SYN-{idx:03d}", "minute": minute, "second": second,
            "team": team, "player": rng.choice(players[team]),
            "event_type": event_type, "outcome": outcome,
            "start_x": start[0] if start else None, "start_y": start[1] if start else None,
            "end_x": end[0] if end else None, "end_y": end[1] if end else None,
            "description": description, "source": "synthetic",
        })

    a, b = teams

    # Connected passages are explicit; the coordinates are normalized pitch
    # locations only and are not converted into physical distances.
    scripted = [
        (1, 10, a, "pass", "successful", (28, 50), (42, 52), "Completed pass into midfield", None),
        (1, 32, a, "pass", "successful", (42, 52), (58, 45), "Completed forward pass", None),
        (2, 5, a, "pass", "successful", (58, 45), (72, 48), "Completed pass into the attacking channel", None),
        (4, 20, a, "shot", "unsuccessful", (83, 48), (100, 50), "Shot saved by the goalkeeper", None),
        (8, 0, b, "recovery", "successful", (37, 55), None, "Harbour City recover possession in midfield", None),
        (8, 12, b, "pass", "successful", (37, 55), (52, 61), "Completed pass after the recovery", None),
        (8, 35, b, "pass", "successful", (52, 61), (70, 54), "Completed pass toward the box", None),
        (9, 5, b, "shot", "unsuccessful", (82, 50), (100, 50), "Shot pushed wide", None),
        (12, 0, b, "turnover", "unsuccessful", (64, 48), None, "Harbour City lose possession under pressure", None),
        (12, 20, a, "recovery", "successful", (61, 48), None, "Northbridge FC recover the loose ball", None),
        (12, 31, a, "pass", "successful", (61, 48), (70, 43), "Completed pass to start a counterattack", None),
        (12, 50, a, "pass", "successful", (70, 43), (82, 48), "Completed pass into the shooting area", None),
        (13, 15, a, "shot", "unsuccessful", (82, 51), (100, 50), "Shot goes narrowly wide", None),
        (18, 10, a, "recovery", "successful", (49, 52), None, "Northbridge FC regain possession", None),
        (18, 20, a, "pass", "successful", (49, 52), (65, 49), "Completed pass through midfield", None),
        (18, 32, a, "pass", "successful", (65, 49), (79, 46), "Completed pass into the penalty area", None),
        (18, 45, a, "shot", "scored", (86, 49), (100, 50), "Low shot finds the net", "A. Cole"),
        (18, 45, a, "goal", "scored", (86, 49), (100, 50), "Goal recorded for Northbridge FC", "A. Cole"),
        (25, 0, b, "recovery", "successful", (35, 48), None, "Harbour City recover possession", None),
        (25, 16, b, "pass", "successful", (35, 48), (50, 44), "Completed pass forward", None),
        (25, 40, b, "pass", "successful", (50, 44), (68, 48), "Completed pass into the right channel", None),
        (27, 5, b, "shot", "unsuccessful", (83, 52), (100, 50), "Shot saved from the edge of the box", None),
        (30, 0, a, "turnover", "unsuccessful", (59, 51), None, "Northbridge FC lose the ball in midfield", None),
        (30, 10, b, "recovery", "successful", (60, 50), None, "Harbour City recover possession after the turnover", None),
        (31, 0, b, "pass", "successful", (60, 50), (73, 46), "Completed pass into the attacking third", None),
        (31, 20, b, "pass", "successful", (73, 46), (84, 49), "Completed pass toward the penalty area", None),
        (32, 0, b, "shot", "scored", (85, 49), (100, 50), "Shot across the goalkeeper and into the net", "R. Costa"),
        (32, 0, b, "goal", "scored", (85, 49), (100, 50), "Goal recorded for Harbour City", "R. Costa"),
        (38, 15, a, "pass", "unsuccessful", (58, 52), (64, 52), "Pass intercepted by the opposition", None),
        (40, 0, a, "shot", "unsuccessful", (84, 47), (100, 50), "Shot goes over the crossbar", None),
        (51, 0, a, "recovery", "successful", (43, 50), None, "Northbridge FC recover possession in the second half", None),
        (52, 5, a, "pass", "successful", (43, 50), (61, 46), "Completed forward pass", None),
        (52, 25, a, "pass", "successful", (61, 46), (76, 48), "Completed pass into the attacking channel", None),
        (53, 10, a, "shot", "unsuccessful", (84, 48), (100, 50), "Shot saved at the near post", None),
        (58, 0, b, "recovery", "successful", (38, 53), None, "Harbour City recover possession", None),
        (59, 10, b, "pass", "successful", (38, 53), (57, 49), "Completed pass forward", None),
        (60, 5, b, "shot", "unsuccessful", (81, 48), (100, 50), "Shot blocked by a defender", None),
        (67, 19, b, "recovery", "successful", (46, 42), None, "Harbour City intercept a pass in midfield", None),
        (67, 25, b, "pass", "successful", (46, 42), (68, 35), "Completed forward pass toward the penalty area", None),
        (67, 34, b, "shot", "unsuccessful", (83, 50), (100, 50), "Shot goes wide", None),
        (74, 0, b, "turnover", "unsuccessful", (63, 47), None, "Harbour City lose possession while building", None),
        (74, 10, a, "recovery", "successful", (64, 47), None, "Northbridge FC recover the ball", None),
        (74, 25, a, "pass", "successful", (64, 47), (73, 43), "Completed pass into the attacking half", None),
        (74, 43, a, "pass", "successful", (73, 43), (84, 47), "Completed pass into the box", None),
        (76, 20, a, "shot", "scored", (86, 47), (100, 50), "Shot placed into the bottom corner", "M. Silva"),
        (76, 20, a, "goal", "scored", (86, 47), (100, 50), "Goal recorded for Northbridge FC", "M. Silva"),
        (80, 0, b, "pass", "unsuccessful", (52, 51), (57, 51), "Forward pass intercepted", None),
        (84, 15, a, "recovery", "successful", (54, 48), None, "Northbridge FC recover possession", None),
        (85, 0, a, "shot", "unsuccessful", (82, 49), (100, 50), "Shot saved by the goalkeeper", None),
        (89, 0, b, "shot", "unsuccessful", (82, 51), (100, 50), "Late shot goes wide", None),
    ]

    for minute, second, team, kind, outcome, start, end, description, player in scripted:
        add(minute, second, team, kind, outcome, start, end, description)
        if player:
            events[-1]["player"] = player

    return validate_events(events)


def iter_synthetic_match(seed: int = 42) -> Iterator[dict[str, Any]]:
    """Yield one reproducible match event at a time in chronological order.

    It delegates to the canonical match generator. Consumers can retain the
    yielded prefix as live state; every subsequent yield belongs to the same
    deterministic match.
    """
    yield from generate_synthetic_match(seed=seed)


if __name__ == "__main__":
    match = generate_synthetic_match()
    counts = {kind: sum(event["event_type"] == kind for event in match) for kind in sorted(EVENT_TYPES)}
    print(f"Generated synthetic match: {len(match)} events")
    print(f"Event counts: {counts}")
    print(f"All events labelled synthetic: {all(event['source'] == 'synthetic' for event in match)}")
