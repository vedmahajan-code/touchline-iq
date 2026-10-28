"""Deterministic, match-scoped retrieval and response helpers.

This first conversational layer selects evidence from the chosen match and
returns a structured answer. It does not call a language model or any service.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


STAT_LABELS = {
    "possession_pct": ("possession", "%"),
    "xg": ("expected goals (xG)", ""),
    "shots": ("shots", ""),
    "shots_on_target": ("shots on target", ""),
    "passes_completed": ("passes completed", ""),
    "passes_attempted": ("passes attempted", ""),
    "touches_in_opposition_box": ("touches in the opposition box", ""),
}

STOP_WORDS = {
    "a", "an", "and", "are", "about", "at", "be", "by", "can", "did", "do",
    "does", "for", "from", "game", "give", "how", "i", "in", "is", "it", "match",
    "me", "of", "on", "or", "please", "show", "tell", "the", "this", "to", "us",
    "was", "were", "what", "when", "where", "which", "who", "with", "would",
    "user", "reported", "report", "notes", "note", "manual", "observation", "observations",
    "observed", "observe", "see", "saw", "according",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _normalise(question: str) -> str:
    return re.sub(r"\s+", " ", question.casefold()).strip()


def _format(value: Any, suffix: str = "") -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value}{suffix}"


def _source_lookup(match: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(source.get("source_id")): dict(source)
        for source in match.get("source_references", [])
        if isinstance(source, Mapping) and source.get("source_id")
    }


def _sources_for(match: Mapping[str, Any], group: str) -> list[dict[str, str]]:
    lookup = _source_lookup(match)
    if group == "statistics":
        ids = (match.get("statistics") or {}).get("source_ids", [])
    elif group == "timeline":
        ids = (match.get("event_timeline") or {}).get("source_ids", [])
    elif group == "identity":
        ids = [
            source_id for source_id, source in lookup.items()
            if set(source.get("used_for", [])) & {"match_identity", "score", "goals"}
        ]
        if not ids:
            ids = list(lookup)
    else:
        ids = list(lookup)

    result = []
    for source_id in ids:
        source = lookup.get(str(source_id))
        if source:
            result.append({
                "source_id": str(source_id),
                "name": _text(source.get("name", source_id)),
                "url": _text(source.get("url", "")),
            })
    return result


def _response(
    answer: str,
    category: str,
    evidence: list[str] | None = None,
    sources: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "category": category,
        "evidence": evidence or [],
        "sources": sources or [],
    }


def _timeline_events(match: Mapping[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    timeline = (match.get("event_timeline") or {}).get("events", [])
    events = [dict(event) for event in timeline if isinstance(event, Mapping)]
    if kind:
        events = [event for event in events if event.get("event_type") == kind]

    def sort_key(event: Mapping[str, Any]) -> tuple[int, int, int]:
        raw_minute = _text(event.get("minute"))
        if "+" in raw_minute:
            base, extra = raw_minute.split("+", 1)
            try:
                return int(base), int(extra), 1
            except ValueError:
                return 10_000, 0, 1
        try:
            return int(raw_minute), 0, 0
        except ValueError:
            return 10_000, 0, 1

    return sorted(events, key=sort_key)


def _event_description(event: Mapping[str, Any]) -> str:
    minute = _text(event.get("minute", "time unavailable"))
    kind = _text(event.get("event_type", "event")).replace("_", " ")
    team = _text(event.get("team", "team unavailable"))
    player = _text(event.get("player", ""))
    if kind == "goal":
        assist = event.get("assist")
        detail = f" (assist: {assist})" if assist else " (assist unavailable)"
        if event.get("detail"):
            detail += f"; {event['detail']}"
        return f"{minute}′ — {team}: {player or 'scorer unavailable'} scored{detail}."
    if kind == "substitution":
        return f"{minute}′ — {team}: {event.get('player_on', 'Player unavailable')} on for {event.get('player_off', 'player unavailable')}."
    return f"{minute}′ — {team}: {player or 'Player unavailable'} ({kind})."


def _manual_entries(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    manual = match.get("manual_observations") or {}
    if not isinstance(manual, Mapping):
        return []
    return [dict(entry) for entry in manual.get("entries", []) if isinstance(entry, Mapping)]


def _manual_matches(entries: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    tokens = {
        token for token in re.findall(r"[\wÀ-ÿ]+", _normalise(question))
        if len(token) > 2 and token not in STOP_WORDS
    }
    if not tokens:
        return entries
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        body = _normalise(" ".join((_text(entry.get("text")), _text(entry.get("category")))))
        overlap = sum(token in body for token in tokens)
        if overlap:
            ranked.append((overlap, -index, entry))
    if not ranked:
        return []
    best = max(score for score, _, _ in ranked)
    # Keep all matching notes for broad questions, but only the closest-ranked
    # notes when a query names a specific player or tactical concept.
    return [entry for score, _, entry in ranked if score == best]


def _answer_manual(match: Mapping[str, Any], question: str, tactical: bool = False) -> dict[str, Any]:
    entries = _manual_entries(match)
    matched = _manual_matches(entries, question)
    if matched:
        lines = [f"User-reported observation — unverified: {entry.get('text', '')}" for entry in matched]
        if tactical:
            lines.append(
                "This is a user observation, not independently sourced tactical evidence. "
                "The stored timeline lacks the event-level positions and actions needed to verify the tactical claim."
            )
        return _response("\n\n".join(lines), "User-reported, unverified observation")
    if tactical:
        return _response(
            "I can’t support that tactical conclusion from this match record. It contains aggregate statistics "
            "and a goals/cards/substitutions timeline, but lacks the relevant event-level shots, turnovers, "
            "recoveries, pressure actions, or coordinates. Manual notes are kept separate and do not verify it.",
            "Evidence unavailable",
        )
    if not entries:
        return _response(
            "No user-reported observations are recorded for this match. I won’t infer them from the sourced statistics.",
            "Evidence unavailable",
        )
    return _response(
        "I couldn’t find a recorded manual observation matching that question. The match has other user-reported "
        "notes, but they are unverified and are not evidence for this specific point.",
        "Evidence unavailable",
    )


def _answer_statistics(match: Mapping[str, Any], question: str) -> dict[str, Any]:
    statistics = match.get("statistics") or {}
    teams = statistics.get("teams") or {}
    home, away = _text(match.get("home_team")), _text(match.get("away_team"))
    home_values, away_values = teams.get(home, {}), teams.get(away, {})
    query = _normalise(question)

    selected_keys: list[str] = []
    asks_pass_rate = any(term in query for term in ("completion", "accuracy", "successful passes"))
    for key, (label, _) in STAT_LABELS.items():
        terms = {
            "possession_pct": ("possession", "possess"),
            "xg": ("xg", "expected goal", "expected goals"),
            "shots": ("shot", "attempt"),
            "shots_on_target": ("on target", "shots on target"),
            "passes_completed": ("pass", "passing", "completed pass", "accurate pass"),
            "passes_attempted": ("attempted pass", "passes attempted"),
            "touches_in_opposition_box": ("touch", "opposition box", "penalty box touch", "box touch"),
        }[key]
        if any(term in query for term in terms) or (asks_pass_rate and key in {"passes_completed", "passes_attempted"}):
            selected_keys.append(key)

    if "shots_on_target" in selected_keys and "shots" in selected_keys:
        # Shots-on-target wording also includes the general token "shots";
        # showing both makes the comparison clearer and avoids double intent.
        pass
    elif "shots_on_target" in selected_keys and "shot" in query:
        selected_keys = [key for key in selected_keys if key != "shots"]

    if "passes_attempted" in selected_keys:
        # Completed passes are useful context for attempted-pass questions.
        if "passes_completed" not in selected_keys:
            selected_keys.append("passes_completed")

    if not selected_keys and any(term in query for term in ("stat", "numbers", "compare", "comparison")):
        selected_keys = [key for key in STAT_LABELS if key in home_values or key in away_values]

    if not selected_keys:
        return _response("", "")

    lines: list[str] = []
    evidence: list[str] = []
    for key in selected_keys:
        label, suffix = STAT_LABELS[key]
        home_value, away_value = home_values.get(key), away_values.get(key)
        if key == "passes_completed":
            label = "passes completed"
        lines.append(f"{label.title()}: {home} {_format(home_value, suffix)}; {away} {_format(away_value, suffix)}.")
        evidence.append(f"Sourced statistic — {label}: {home}={_format(home_value, suffix)}, {away}={_format(away_value, suffix)}.")

    if asks_pass_rate:
        completed_home, attempted_home = home_values.get("passes_completed"), home_values.get("passes_attempted")
        completed_away, attempted_away = away_values.get("passes_completed"), away_values.get("passes_attempted")
        if all(isinstance(value, (int, float)) for value in (completed_home, attempted_home, completed_away, attempted_away)) and attempted_home and attempted_away:
            home_rate = round(100 * completed_home / attempted_home, 1)
            away_rate = round(100 * completed_away / attempted_away, 1)
            lines.append(f"Pass completion rate (calculated from stored totals): {home} {home_rate}%; {away} {away_rate}%. ")
            evidence.append(
                "Calculated from sourced completed/attempted pass totals; this percentage is derived, not separately source-reported."
            )

    if any(term in query for term in ("dominat", "control the game", "who was better", "who controlled")):
        lines.append(
            "Generated interpretation: these are descriptive statistical comparisons only; they do not by themselves "
            "establish tactical control, dominance, or why either team produced those numbers."
        )
        category = "Sourced statistics with cautious interpretation"
    elif any(term in query for term in ("suggest", "mean", "indicate", "tell us")):
        lines.append(
            "Generated interpretation: the listed values describe these measured outputs only; they do not establish "
            "tactical intent, causation, or overall match control."
        )
        category = "Sourced statistics with cautious interpretation"
    else:
        category = "Sourced statistics"
    if asks_pass_rate:
        category = "Sourced statistics with a transparent derived calculation"
    return _response("\n".join(lines), category, evidence, _sources_for(match, "statistics"))


def _answer_quality(match: Mapping[str, Any]) -> dict[str, Any]:
    stats = match.get("statistics") or {}
    discrepancies = stats.get("discrepancies") or []
    quality_notes = match.get("data_quality_notes") or []
    conflicts = match.get("manual_observation_conflicts") or []
    lines: list[str] = []
    evidence: list[str] = []

    for discrepancy in discrepancies:
        if isinstance(discrepancy, Mapping):
            metric = _text(discrepancy.get("metric", "statistic"))
            note = _text(discrepancy.get("note", ""))
            values = discrepancy.get("values")
            lines.append(f"{metric}: {note}" if note else f"{metric}: values differ between providers.")
            if values is not None:
                evidence.append(f"Recorded provider values for {metric}: {values}")
    for note in quality_notes:
        lines.append(str(note))
        evidence.append(f"Recorded data-quality note: {note}")
    for conflict in conflicts:
        if isinstance(conflict, Mapping):
            status = _text(conflict.get("status", "verification note"))
            note = _text(conflict.get("note", ""))
            lines.append(f"Manual-observation conflict ({status}): {note}")
            evidence.append(f"Recorded manual-observation conflict ({status}): {note}")

    if not lines:
        lines.append("No data discrepancies or quality warnings are recorded for this match.")
    lines.append("These notes identify recorded uncertainty; they do not rank the sources or establish which value is correct.")
    return _response("\n".join(lines), "Recorded data-quality information", evidence, _sources_for(match, "all"))


def _answer_events(match: Mapping[str, Any], kind: str) -> dict[str, Any]:
    events = _timeline_events(match, kind)
    label = "goal" if kind == "goal" else "substitution"
    if not events:
        return _response(
            f"No {label} entries are recorded in this match’s sourced timeline. That means the current dataset "
            "has no such entries; it does not prove none occurred in the match.",
            "Sourced timeline lookup",
            sources=_sources_for(match, "timeline"),
        )
    descriptions = [_event_description(event) for event in events]
    evidence = [f"Sourced timeline event: {_event_description(event)}" for event in events]
    return _response("\n".join(descriptions), "Sourced timeline events", evidence, _sources_for(match, "timeline"))


def _answer_score(match: Mapping[str, Any]) -> dict[str, Any]:
    score = match.get("final_score") or {}
    home, away = _text(match.get("home_team", "Home")), _text(match.get("away_team", "Away"))
    home_score, away_score = score.get("home"), score.get("away")
    date = _text(match.get("date", "Date unavailable"))
    competition = _text(match.get("competition", "Competition unavailable"))
    answer = f"{home} {home_score}–{away_score} {away} ({competition}, {date})."
    evidence = [f"Sourced match result: {home} {home_score}–{away_score} {away}."]
    return _response(answer, "Sourced match fact", evidence, _sources_for(match, "identity"))


def _manual_question(question: str) -> bool:
    return any(term in question for term in (
        "manual observation", "user observation", "user-reported", "what did i observe",
        "user reported", "did the user observe", "what did the user observe", "what did i report",
        "what did i see", "my notes", "observation", "what did we notice", "observed",
    ))


def _tactical_question(question: str) -> bool:
    return any(term in question for term in (
        "tactic", "tactical", "formation", "shape", "press", "pressing", "block",
        "counter", "defend", "defensive", "attack pattern", "space", "why did", "why was",
        "cause", "caused", "create space", "wing", "overlap", "build-up", "build up",
    ))


def _answer_interpretation(match: Mapping[str, Any], question: str) -> dict[str, Any]:
    stats = match.get("statistics") or {}
    teams = stats.get("teams") or {}
    home, away = _text(match.get("home_team")), _text(match.get("away_team"))
    home_stats, away_stats = teams.get(home, {}), teams.get(away, {})
    comparable = [key for key in ("possession_pct", "shots", "shots_on_target", "touches_in_opposition_box")
                  if isinstance(home_stats.get(key), (int, float)) and isinstance(away_stats.get(key), (int, float))]
    if not comparable:
        return _response(
            "I can’t make a data-based comparison because this match has no comparable sourced statistics available.",
            "Evidence unavailable",
        )

    comparisons = []
    evidence = []
    for key in comparable:
        label, suffix = STAT_LABELS[key]
        h, a = home_stats[key], away_stats[key]
        if h == a:
            comparison = f"{home} and {away} were level on {label} ({_format(h, suffix)})"
        else:
            leader, other = (home, away) if h > a else (away, home)
            comparison = f"{leader} recorded more {label} ({_format(h if leader == home else a, suffix)} vs {_format(a if leader == home else h, suffix)})"
        comparisons.append(comparison)
        evidence.append(f"Sourced statistic — {label}: {home}={_format(h, suffix)}, {away}={_format(a, suffix)}.")

    answer = (
        "Generated interpretation: " + "; ".join(comparisons) + ". These recorded metrics describe selected "
        "outputs only; they do not establish overall dominance, tactical intent, or causation."
    )
    return _response(answer, "Generated interpretation, grounded in sourced statistics", evidence, _sources_for(match, "statistics"))


def answer_question(match: Mapping[str, Any], question: str) -> dict[str, Any]:
    """Answer a question using only the selected match's stored evidence.

    The output has ``answer``, ``category``, ``evidence``, and ``sources``.
    No model is called. Manual notes are accessed only as observations and are
    never converted to event records or passed to the tactical-pattern engine.
    """
    if not isinstance(match, Mapping):
        raise TypeError("match must be a mapping")
    if not isinstance(question, str) or not question.strip():
        return _response("Ask a question about the selected match.", "No question")

    query = _normalise(question)
    if _manual_question(query):
        return _answer_manual(match, question)
    if any(term in query for term in ("discrepanc", "data quality", "quality warning", "source", "reliab", "reliable", "trust", "conflict note")):
        return _answer_quality(match)
    if _tactical_question(query):
        # If the user asks about an actual manual observation, preserve that
        # provenance and still explain that it is not independently verified.
        manual_result = _answer_manual(match, question, tactical=True)
        if manual_result["category"] != "Evidence unavailable":
            return manual_result
        return manual_result
    if any(term in query for term in ("substitution", "substitutions", "subs", "who came on", "who went off", "changes")):
        return _answer_events(match, "substitution")
    asks_goal_events = any(term in query for term in (
        "scorer", "scorers", "who scored", "goal timeline", "goals scored", "assist", "goal at",
    )) or (
        any(term in query for term in ("goal", "goals"))
        and not any(term in query for term in ("expected goal", "xg"))
    )
    if asks_goal_events:
        return _answer_events(match, "goal")

    statistics = _answer_statistics(match, question)
    if statistics["answer"]:
        return statistics

    if any(term in query for term in ("dominat", "what does the data suggest", "what can you conclude", "controlled the match")):
        return _answer_interpretation(match, question)
    if any(term in query for term in ("score", "result", "who won", "winner", "final score")):
        return _answer_score(match)

    if any(term in query for term in ("event", "timeline", "card", "booking")):
        events = _timeline_events(match)
        if not events:
            return _response("No sourced timeline events are recorded for this match.", "Evidence unavailable")
        evidence = [f"Sourced timeline event: {_event_description(event)}" for event in events]
        answer = "Recorded sourced timeline entries:\n" + "\n".join(_event_description(event) for event in events)
        return _response(answer, "Sourced timeline events", evidence, _sources_for(match, "timeline"))

    return _response(
        "I couldn’t find enough relevant evidence to answer that. Try asking about the result, a stored statistic, "
        "a goal or substitution in the sourced timeline, a recorded discrepancy, or a user-reported observation.",
        "Evidence unavailable",
    )


def match_scoped_history(session_state: Any, match_id: str) -> list[dict[str, Any]]:
    """Return this match's chat history, isolated from other match sessions."""
    conversations = session_state.setdefault("touchline_iq_conversations", {})
    if not isinstance(conversations, dict):
        conversations = {}
        session_state["touchline_iq_conversations"] = conversations
    history = conversations.setdefault(match_id, [])
    if not isinstance(history, list):
        history = []
        conversations[match_id] = history
    return history
