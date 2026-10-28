"""Transparent, deterministic match metrics and tactical pattern rules.

All functions consume and validate the shared event schema from ``match_data``.
Evidence-strength labels describe the amount of supporting event evidence;
they are not probabilities or outputs from a trained model.
"""

from __future__ import annotations

from collections import Counter
from math import hypot
from typing import Any, Iterable, Mapping

from match_data import (
    SYNTHETIC_TEAMS,
    generate_synthetic_match,
    validate_events,
)


SEQUENCE_WINDOW_SECONDS = 5 * 60
SHOT_AREA_RADIUS = 12.0
MIN_SHOTS_FOR_REPEATED_AREA = 3
MATCH_DURATION_SECONDS = 90 * 60


def _metrics_for(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(event["event_type"] for event in events)
    passes = [event for event in events if event["event_type"] == "pass"]
    known_outcome_passes = [event for event in passes if event["outcome"] in {"successful", "unsuccessful"}]
    completed_passes = sum(event["outcome"] == "successful" for event in known_outcome_passes)
    return {
        "event_count": len(events),
        "goals": counts["goal"],
        "shots": counts["shot"],
        "recoveries": counts["recovery"],
        "turnovers": counts["turnover"],
        "passes": len(passes),
        "successful_passes": completed_passes,
        "unsuccessful_passes": sum(event["outcome"] == "unsuccessful" for event in known_outcome_passes),
        "pass_completion_pct": round(100 * completed_passes / len(known_outcome_passes), 1)
        if known_outcome_passes else None,
    }


def calculate_match_metrics(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate event counts and pass completion overall and for each team.

    Goal totals count explicit ``goal`` events; shot totals count explicit
    ``shot`` events. No possession or other unobserved metrics are estimated.
    An empty input returns zero counts and ``None`` for undefined pass rate.
    Input is validated by ``match_data.validate_events``.
    """
    clean_events = validate_events(events)
    by_team: dict[str, list[dict[str, Any]]] = {}
    for event in clean_events:
        by_team.setdefault(event["team"], []).append(event)
    return {
        **_metrics_for(clean_events),
        "teams": {team: _metrics_for(by_team[team]) for team in sorted(by_team)},
    }


def clamp_viewed_match_time(viewed_match_time: int, current_match_time: int) -> int:
    """Clamp historical inspection to the latest simulated point and match end."""
    current = max(0, min(int(current_match_time), MATCH_DURATION_SECONDS))
    return max(0, min(int(viewed_match_time), current))


def events_through_time(
    events: Iterable[Mapping[str, Any]], through_seconds: int
) -> list[dict[str, Any]]:
    """Return validated events at or before an absolute match-time second."""
    cutoff = max(0, min(int(through_seconds), MATCH_DURATION_SECONDS))
    return [event for event in validate_events(events) if _seconds(event) <= cutoff]


def calculate_player_stats(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Calculate player event counts from recorded actions only."""
    by_player: dict[str, list[dict[str, Any]]] = {}
    for event in validate_events(events):
        by_player.setdefault(event["player"], []).append(event)

    stats: dict[str, dict[str, Any]] = {}
    for player, player_events in sorted(by_player.items()):
        counts = Counter(event["event_type"] for event in player_events)
        passes = [event for event in player_events if event["event_type"] == "pass"]
        known_passes = [event for event in passes if event["outcome"] in {"successful", "unsuccessful"}]
        completed = sum(event["outcome"] == "successful" for event in known_passes)
        teams = sorted({event["team"] for event in player_events})
        stats[player] = {
            "team": teams[0] if len(teams) == 1 else teams,
            "events": len(player_events),
            "goals": counts["goal"],
            "shots": counts["shot"],
            "pass_attempts": len(passes),
            "successful_passes": completed,
            "pass_completion_pct": round(100 * completed / len(known_passes), 1) if known_passes else None,
            "recoveries": counts["recovery"],
            "turnovers": counts["turnover"],
        }
    return stats


def _seconds(event: Mapping[str, Any]) -> int:
    return int(event["minute"]) * 60 + int(event["second"])


def _timestamp(event: Mapping[str, Any]) -> str:
    return f"{event['minute']}:{event['second']:02d}"


def _support(event: Mapping[str, Any]) -> dict[str, str]:
    return {
        "event_id": event["event_id"],
        "timestamp": _timestamp(event),
        "team": event["team"],
        "event_type": event["event_type"],
    }


def _strength(event_count: int) -> str:
    """Label evidence volume, not statistical or model confidence."""
    if event_count >= 5:
        return "High"
    if event_count >= 4:
        return "Medium"
    return "Low"


def _evidence_fields(event_count: int) -> dict[str, str]:
    return {
        "evidence_strength": _strength(event_count),
        "evidence_strength_note": "Descriptive evidence volume; not a trained-model probability.",
    }


def _cluster_shots(shots: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Deterministically merge shot clusters while keeping every shot in range.

    A cluster's representative centre is the arithmetic mean of its shot start
    coordinates. At each step, merge the closest pair whose merged members
    would all remain within SHOT_AREA_RADIUS of the new centre. Ties are broken
    by event IDs. Each input shot belongs to exactly one resulting cluster.
    """
    clusters = [[shot] for shot in shots]

    def centre(cluster: list[dict[str, Any]]) -> tuple[float, float]:
        return (
            sum(float(shot["start_x"]) for shot in cluster) / len(cluster),
            sum(float(shot["start_y"]) for shot in cluster) / len(cluster),
        )

    while True:
        choices: list[tuple[float, tuple[str, ...], int, int, list[dict[str, Any]]]] = []
        for left in range(len(clusters)):
            for right in range(left + 1, len(clusters)):
                merged = sorted(
                    clusters[left] + clusters[right],
                    key=lambda shot: (shot["minute"], shot["second"], shot["event_id"]),
                )
                cx, cy = centre(merged)
                if any(hypot(float(shot["start_x"]) - cx, float(shot["start_y"]) - cy)
                       > SHOT_AREA_RADIUS + 1e-9 for shot in merged):
                    continue
                lx, ly = centre(clusters[left])
                rx, ry = centre(clusters[right])
                separation = hypot(lx - rx, ly - ry)
                choices.append((separation, tuple(shot["event_id"] for shot in merged), left, right, merged))
        if not choices:
            break

        _, _, left, right, merged = min(choices, key=lambda choice: (choice[0], choice[1]))
        clusters = [cluster for index, cluster in enumerate(clusters) if index not in {left, right}]
        clusters.append(merged)
        clusters.sort(key=lambda cluster: min(shot["event_id"] for shot in cluster))

    return sorted(clusters, key=lambda cluster: min(shot["event_id"] for shot in cluster))


def detect_tactical_patterns(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Find rule-based sequences and repeated shot areas in validated events.

    Sequence rule: a qualifying shot or goal occurs within five minutes after
    the initiating event. Turnover-to-opponent patterns are considered only
    when exactly two team names occur in the supplied match.

    Repeated-area rule: at least three shots by one team have complete start
    coordinates within 12 pitch units of their cluster's representative centre.
    Only shots are used, so a separate goal row does not double-count a shot.
    """
    clean_events = validate_events(events)
    if not clean_events:
        return []

    teams = {event["team"] for event in clean_events}
    patterns: list[dict[str, Any]] = []

    def add_sequence_pattern(title: str, rule: str, first: Mapping[str, Any],
                             outcome: Mapping[str, Any], explanation: str,
                             pattern_number: int) -> None:
        patterns.append({
            "pattern_id": f"sequence-{pattern_number:03d}",
            "title": title,
            "rule": rule,
            "supporting_events": [_support(first), _support(outcome)],
            "explanation": explanation,
            **_evidence_fields(2),
        })

    sequence_number = 0
    for index, event in enumerate(clean_events):
        event_type = event["event_type"]
        if event_type not in {"turnover", "recovery"}:
            continue
        for later in clean_events[index + 1:]:
            elapsed = _seconds(later) - _seconds(event)
            if elapsed > SEQUENCE_WINDOW_SECONDS:
                break
            if elapsed < 0 or later["event_type"] not in {"shot", "goal"}:
                continue

            if event_type == "turnover":
                if len(teams) != 2 or later["team"] == event["team"]:
                    continue
                title = "Opponent shot soon after a turnover"
                rule = "A shot or goal by the other of the match's two observed teams occurs within 5 minutes after a turnover."
                explanation = (
                    f"{event['team']} recorded a turnover at {_timestamp(event)}, followed by a "
                    f"{later['team']} {later['event_type']} at {_timestamp(later)} "
                    f"({elapsed} seconds later). The event sequence is consistent with an immediate counter opportunity; "
                    "these events alone do not establish the cause of the shot."
                )
            else:
                if later["team"] != event["team"]:
                    continue
                title = "Shot soon after a recovery"
                rule = "A shot or goal by the same team occurs within 5 minutes after a recovery."
                explanation = (
                    f"{event['team']} recorded a recovery at {_timestamp(event)}, followed by a "
                    f"{later['event_type']} at {_timestamp(later)} ({elapsed} seconds later). "
                    "This shows a recovery-to-attempt sequence; it does not by itself prove the recovery caused the attempt."
                )

            sequence_number += 1
            add_sequence_pattern(title, rule, event, later, explanation, sequence_number)
            break  # Report the first qualifying attempt after each initiating event.

    for team in sorted(teams):
        shots = [
            event for event in clean_events
            if event["team"] == team
            and event["event_type"] == "shot"
            and event["start_x"] is not None
            and event["start_y"] is not None
        ]
        area_number = 0
        for group in _cluster_shots(shots):
            if len(group) < MIN_SHOTS_FOR_REPEATED_AREA:
                continue

            area_number += 1
            xs = [float(shot["start_x"]) for shot in group]
            ys = [float(shot["start_y"]) for shot in group]
            center_x, center_y = sum(xs) / len(xs), sum(ys) / len(ys)
            safe_team = "".join(character.lower() if character.isalnum() else "-" for character in team).strip("-")
            patterns.append({
                "pattern_id": f"shot-area-{safe_team}-{area_number:02d}",
                "title": f"Repeated shots from a similar area: {team}",
                "rule": (
                    f"At least {MIN_SHOTS_FOR_REPEATED_AREA} shots by the same team have start coordinates "
                    f"within {SHOT_AREA_RADIUS:g} pitch units of the cluster's representative centre."
                ),
                "supporting_events": [
                    _support(shot)
                    for shot in sorted(group, key=lambda shot: (shot["minute"], shot["second"], shot["event_id"]))
                ],
                "explanation": (
                    f"{team} recorded {len(group)} shots from a similar area, centered near "
                    f"({center_x:.1f}, {center_y:.1f}) on the 0–100 pitch. This establishes repeated shot locations "
                    "in the supplied data, but not why the team attacked from there."
                ),
                **_evidence_fields(len(group)),
            })

    return patterns


def generate_match_insights(
    events: Iterable[Mapping[str, Any]], match_id: str, *, complete: bool = False
) -> list[dict[str, Any]]:
    """Wrap supported rules and explicit goals in a small serializable contract.

    Insights are derived only from the validated event prefix supplied here.
    Their IDs are deterministic for a fixed match ID and event sequence. A
    final recap is emitted only when ``complete`` is true.
    """
    clean_events = validate_events(events)
    if not match_id:
        raise ValueError("match_id is required")
    if any(event["source"] != "synthetic" for event in clean_events):
        raise ValueError("generate_match_insights currently accepts synthetic events only")
    status = "final" if complete else "provisional"
    by_id = {event["event_id"]: event for event in clean_events}
    insights: list[dict[str, Any]] = []

    def timestamp(event: Mapping[str, Any]) -> dict[str, int]:
        return {"minute": int(event["minute"]), "second": int(event["second"])}

    def base(insight_id: str, insight_type: str, stage: str, title: str,
             explanation: str, support_ids: list[str], anchor: Mapping[str, Any] | None,
             metrics: Mapping[str, Any], limitations: list[str],
             evidence_strength: str | None = None) -> dict[str, Any]:
        return {
            "insight_id": insight_id,
            "match_id": match_id,
            "type": insight_type,
            "stage": stage,
            "match_timestamp": timestamp(anchor) if anchor else None,
            "title": title,
            "explanation": explanation,
            "supporting_event_ids": support_ids,
            "metrics": dict(metrics),
            "provenance": {"source": "synthetic", "label": "Synthetic demonstration data"},
            "evidence_quality": {
                "strength": evidence_strength,
                "limitations": limitations,
                "strength_is_probability": False,
            },
            "status": status,
        }

    for event in clean_events:
        if event["event_type"] != "goal":
            continue
        score_for_team = sum(
            other["event_type"] == "goal" and other["team"] == event["team"]
            for other in clean_events
        )
        insights.append(base(
            f"{match_id}:goal:{event['event_id']}", "goal_highlight", "highlights",
            f"Goal recorded for {event['team']}",
            event["description"], [event["event_id"]], event,
            {"explicit_goal_events_for_team": score_for_team},
            ["Synthetic event record; not a real fixture."], "Low",
        ))

    for pattern in detect_tactical_patterns(clean_events):
        support = pattern["supporting_events"]
        support_ids = [item["event_id"] for item in support]
        # A pattern is not observable until its final supporting event occurs.
        anchor = by_id.get(support_ids[-1]) if support_ids else None
        kind = "tactical_pattern" if not pattern["pattern_id"].startswith("shot-area-") else "shot_area"
        insights.append(base(
            f"{match_id}:pattern:{'|'.join(support_ids)}", kind, "live",
            pattern["title"],
            f"{pattern['explanation']} Rule: {pattern['rule']}",
            support_ids, anchor, {"supporting_event_count": len(support_ids)},
            ["Rule-based observation; descriptive evidence strength is not a probability."],
            pattern.get("evidence_strength"),
        ))

    if complete and clean_events:
        metrics = calculate_match_metrics(clean_events)
        all_ids = [event["event_id"] for event in clean_events]
        insights.append(base(
            f"{match_id}:final-recap", "match_recap", "outro",
            "Synthetic match recap",
            f"The completed event stream contains {metrics['event_count']} events, "
            f"including {metrics['goals']} explicit goal events and {metrics['shots']} explicit shot events.",
            all_ids, clean_events[-1] if clean_events else None,
            {key: metrics[key] for key in (
                "event_count", "goals", "shots", "recoveries", "turnovers", "passes",
                "successful_passes", "unsuccessful_passes", "pass_completion_pct",
            )},
            ["Summary is limited to recorded synthetic events; unavailable measures are omitted."],
            "Descriptive summary",
        ))
    return insights


def generate_match_commentary(
    events: Iterable[Mapping[str, Any]],
    match_id: str,
    *,
    viewed_match_time: int,
    complete: bool = False,
) -> list[dict[str, Any]]:
    """Create deterministic event and rule commentary available by a time.

    Period-boundary lines are generated from the simulated match clock. All
    other lines link to recorded event IDs or an existing tactical pattern.
    Scores count explicit goal events only.
    """
    if not match_id:
        raise ValueError("match_id is required")
    all_clean = validate_events(events)
    visible = events_through_time(all_clean, viewed_match_time)
    if any(event["source"] != "synthetic" for event in visible):
        raise ValueError("generate_match_commentary currently accepts synthetic events only")

    observed_teams = list(dict.fromkeys(event["team"] for event in all_clean))
    teams = (list(SYNTHETIC_TEAMS) if set(observed_teams).issubset(SYNTHETIC_TEAMS)
             else observed_teams[:2] or list(SYNTHETIC_TEAMS))
    scores = {team: 0 for team in teams}
    commentary: list[dict[str, Any]] = []
    score_at_event: dict[str, dict[str, int]] = {}

    def add(commentary_id: str, kind: str, seconds: int, text: str,
            supporting_ids: list[str], score: Mapping[str, int]) -> None:
        commentary.append({
            "commentary_id": commentary_id,
            "match_id": match_id,
            "type": kind,
            "match_seconds": seconds,
            "timestamp": f"{seconds // 60}:{seconds % 60:02d}",
            "text": text,
            "score": {team: int(score.get(team, 0)) for team in teams},
            "supporting_event_ids": supporting_ids,
            "provenance": "Synthetic demonstration data",
        })

    def variant(event: Mapping[str, Any], count: int) -> int:
        try:
            return int(str(event["event_id"]).rsplit("-", 1)[-1]) % count
        except (ValueError, IndexError):
            return 0

    for event in visible:
        seconds = _seconds(event)
        if event["event_type"] == "goal" and event["team"] in scores:
            scores[event["team"]] += 1
        score_at_event[event["event_id"]] = dict(scores)
        player, team = event["player"], event["team"]
        description = event["description"]
        if event["event_type"] == "goal":
            scoreline = f"{scores.get(teams[0], 0)}–{scores.get(teams[1], 0)}"
            goal_templates = (
                f"Goal for {team}: {player} scores. The score is {scoreline}.",
                f"{player} finds the net for {team}; the score moves to {scoreline}.",
                f"{team} add a goal through {player}. It is now {scoreline}.",
            )
            text = goal_templates[variant(event, len(goal_templates))]
            add(f"{match_id}:commentary:{event['event_id']}", "goal", seconds, text,
                [event["event_id"]], scores)
        elif event["event_type"] == "shot":
            shot_templates = (
                f"{team}: {player} attempts a shot. {description}",
                f"{player} takes an attempt for {team}. {description}",
                f"A shot is recorded for {team} by {player}. {description}",
            )
            add(f"{match_id}:commentary:{event['event_id']}", "shot", seconds,
                shot_templates[variant(event, len(shot_templates))], [event["event_id"]], scores)
        elif event["event_type"] == "recovery":
            recovery_templates = (
                f"{team} recover possession through {player}. {description}",
                f"Possession is recorded with {team} after {player}'s recovery. {description}",
                f"{player} is credited with a recovery for {team}. {description}",
            )
            add(f"{match_id}:commentary:{event['event_id']}", "recovery", seconds,
                recovery_templates[variant(event, len(recovery_templates))], [event["event_id"]], scores)
        elif event["event_type"] == "turnover":
            turnover_templates = (
                f"{team} lose possession after {player}'s action. {description}",
                f"A turnover is recorded against {team} after {player}'s action. {description}",
            )
            add(f"{match_id}:commentary:{event['event_id']}", "turnover", seconds,
                turnover_templates[variant(event, len(turnover_templates))], [event["event_id"]], scores)
        elif event["event_type"] == "pass" and event["outcome"] == "unsuccessful":
            pass_templates = (
                f"An unsuccessful pass by {player} for {team}.",
                f"{team}'s pass from {player} is recorded as unsuccessful.",
            )
            add(f"{match_id}:commentary:{event['event_id']}", "pass", seconds,
                pass_templates[variant(event, len(pass_templates))],
                [event["event_id"]], scores)

    # Call out a connected completed-pass sequence only when it leads directly
    # into a recorded shot. The pass and shot IDs make the claim auditable.
    for index, event in enumerate(visible):
        if event["event_type"] != "shot":
            continue
        chain: list[dict[str, Any]] = []
        cursor = index - 1
        while cursor >= 0:
            previous = visible[cursor]
            if (
                previous["event_type"] != "pass"
                or previous["outcome"] != "successful"
                or previous["team"] != event["team"]
                or _seconds(event) - _seconds(previous) > 180
            ):
                break
            chain.append(previous)
            cursor -= 1
        if len(chain) >= 2:
            chain.reverse()
            supporting_ids = [item["event_id"] for item in chain] + [event["event_id"]]
            add(
                f"{match_id}:attack-sequence:{event['event_id']}", "attacking_sequence",
                _seconds(event),
                f"{event['team']} completed {len(chain)} consecutive passes before {event['player']} took this shot.",
                supporting_ids, score_at_event[event["event_id"]],
            )

    # A turnover followed immediately by the opponent's recorded recovery is
    # a defensible defensive sequence; no unrecorded tackle is implied.
    for index, event in enumerate(visible):
        if event["event_type"] != "turnover":
            continue
        for later in visible[index + 1:]:
            elapsed = _seconds(later) - _seconds(event)
            if elapsed > 30:
                break
            if later["event_type"] == "recovery" and later["team"] != event["team"]:
                add(
                    f"{match_id}:defensive-sequence:{event['event_id']}:{later['event_id']}",
                    "defensive_sequence", _seconds(later),
                    f"{later['team']} recorded a recovery {elapsed} seconds after {event['team']}'s turnover.",
                    [event["event_id"], later["event_id"]], score_at_event[later["event_id"]],
                )
                break

    for pattern in detect_tactical_patterns(visible):
        support = pattern.get("supporting_events", [])
        supporting_ids = [item["event_id"] for item in support]
        if not supporting_ids:
            continue
        anchor_id = supporting_ids[-1]
        anchor = next((event for event in visible if event["event_id"] == anchor_id), None)
        if anchor is None:
            continue
        add(
            f"{match_id}:pattern-commentary:{pattern['pattern_id']}", "tactical_pattern",
            _seconds(anchor), pattern["explanation"], supporting_ids,
            score_at_event[anchor_id],
        )

    halftime = 45 * 60
    if viewed_match_time >= halftime:
        halftime_goals = [event for event in visible if _seconds(event) <= halftime and event["event_type"] == "goal"]
        halftime_score = Counter(event["team"] for event in halftime_goals)
        add(
            f"{match_id}:period:half-time", "half_time", halftime,
            f"Half-time: {halftime_score.get(teams[0], 0)}–{halftime_score.get(teams[1], 0)}.",
            [event["event_id"] for event in halftime_goals], halftime_score,
        )
    if complete and viewed_match_time >= MATCH_DURATION_SECONDS:
        add(
            f"{match_id}:period:full-time", "full_time", MATCH_DURATION_SECONDS,
            f"Full-time: {scores.get(teams[0], 0)}–{scores.get(teams[1], 0)}.",
            [event["event_id"] for event in visible if event["event_type"] == "goal"], scores,
        )

    return sorted(commentary, key=lambda item: (item["match_seconds"], item["commentary_id"]))


def _test_event(event_id: str, minute: int, team: str, event_type: str,
                start: tuple[float, float] | None = None) -> dict[str, Any]:
    outcome = "scored" if event_type == "goal" else "successful" if event_type == "recovery" else "unsuccessful"
    return {
        "event_id": event_id, "minute": minute, "second": 0,
        "team": team, "player": "Test Player", "event_type": event_type,
        "outcome": outcome,
        "start_x": start[0] if start else None, "start_y": start[1] if start else None,
        "end_x": None, "end_y": None, "description": "In-file analytics self-test event",
        "source": "manual",
    }


def _run_self_tests() -> None:
    """Run compact assertions for core analytics behavior without extra files."""
    assert calculate_match_metrics([])["event_count"] == 0
    assert calculate_match_metrics([])["pass_completion_pct"] is None
    assert detect_tactical_patterns([]) == []

    turnover_case = [
        _test_event("T1", 10, "Team A", "turnover"),
        _test_event("T2", 12, "Team B", "shot", (80, 50)),
    ]
    turnover_patterns = detect_tactical_patterns(turnover_case)
    turnover_result = next(pattern for pattern in turnover_patterns if "turnover" in pattern["title"].lower())
    assert [item["event_id"] for item in turnover_result["supporting_events"]] == ["T1", "T2"]
    assert [item["timestamp"] for item in turnover_result["supporting_events"]] == ["10:00", "12:00"]

    recovery_case = [
        _test_event("R1", 20, "Team A", "recovery"),
        _test_event("R2", 22, "Team A", "shot", (75, 48)),
    ]
    recovery_patterns = detect_tactical_patterns(recovery_case)
    recovery_result = next(pattern for pattern in recovery_patterns if "recovery" in pattern["title"].lower())
    assert [item["event_id"] for item in recovery_result["supporting_events"]] == ["R1", "R2"]

    area_case = [
        _test_event("A1", 30, "Team A", "shot", (20, 50)),
        _test_event("A2", 31, "Team A", "shot", (31, 50)),
        _test_event("A3", 32, "Team A", "shot", (40, 50)),
        _test_event("A4", 33, "Team A", "shot"),  # Missing coordinates are safely excluded.
    ]
    area_patterns = [pattern for pattern in detect_tactical_patterns(area_case) if pattern["pattern_id"].startswith("shot-area-")]
    assert len(area_patterns) == 1
    assert {item["event_id"] for item in area_patterns[0]["supporting_events"]} == {"A1", "A2", "A3"}
    assert len({item["event_id"] for item in area_patterns[0]["supporting_events"]}) == 3

    all_test_patterns = turnover_patterns + recovery_patterns + area_patterns
    for pattern in all_test_patterns:
        assert pattern["title"] and pattern["rule"] and pattern["explanation"]
        assert pattern["supporting_events"] and pattern["evidence_strength"] in {"Low", "Medium", "High"}
        assert pattern["evidence_strength_note"].startswith("Descriptive")

    goal_only = [_test_event("G1", 40, "Team A", "goal")]
    goal_metrics = calculate_match_metrics(goal_only)
    assert goal_metrics["goals"] == 1 and goal_metrics["shots"] == 0


if __name__ == "__main__":
    _run_self_tests()
    print("Analytics self-tests passed.")
    demo_events = generate_synthetic_match()
    print("Synthetic match metrics:")
    print(calculate_match_metrics(demo_events))
    print("\nRule-based tactical patterns:")
    for detected in detect_tactical_patterns(demo_events):
        print(f"- {detected['title']} [{detected['evidence_strength']} evidence]")
        print(f"  Rule: {detected['rule']}")
        print(f"  Events: {detected['supporting_events']}")
        print(f"  Explanation: {detected['explanation']}")
