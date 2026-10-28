"""Touchline IQ local match-intelligence dashboard."""

from __future__ import annotations

import html
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import (
    MATCH_DURATION_SECONDS,
    calculate_match_metrics,
    calculate_player_stats,
    clamp_viewed_match_time,
    events_through_time,
    generate_match_commentary,
    generate_match_insights,
)
from assistant import answer_question, match_scoped_history
from match_data import (
    SYNTHETIC_MATCH_ID,
    SYNTHETIC_COMPETITION,
    SYNTHETIC_PLAYERS,
    SYNTHETIC_TEAMS,
    iter_synthetic_match,
    validate_events,
)
from real_data import get_match_by_id, load_real_matches


DATA_PATH = Path(__file__).with_name("real_matches.json")

# Every fixture is generated once per Streamlit session from the existing
# deterministic event generator. Team/player aliases keep each fictional
# match distinct without changing the shared event contract.
LIVE_FIXTURES = (
    ("live-northbridge-harbour", 42, "Northbridge FC", "Harbour City"),
    ("live-ashford-riverside", 137, "Ashford Athletic", "Riverside United"),
)
HIGHLIGHT_FIXTURES = (
    ("completed-01", 201, "Northbridge FC", "Harbour City"),
    ("completed-02", 202, "Ashford Athletic", "Riverside United"),
    ("completed-03", 203, "Kingsport Town", "Westhaven Rovers"),
    ("completed-04", 204, "Redmere City", "Eastvale FC"),
    ("completed-05", 205, "Stonebridge United", "Lakeside Athletic"),
    ("completed-06", 206, "Pineford FC", "Southbank Town"),
    ("completed-07", 207, "Highmoor Rovers", "Fairview City"),
    ("completed-08", 208, "Oakwell Athletic", "Brookfield United"),
    ("completed-09", 209, "Cedarvale Town", "Summit FC"),
    ("completed-10", 210, "Meadow Park", "Harbourview City"),
)
_COMPLETED_PROFILES = {
    201: {"goals": [(6, 0), (18, 1), (37, 0), (54, 1), (73, 0), (86, 0)], "actions": 32, "home_share": .56, "shot_rate": .28, "recovery_rate": .14},
    202: {"goals": [(82, 0)], "actions": 34, "home_share": .50, "shot_rate": .12, "recovery_rate": .23},
    203: {"goals": [(12, 1), (49, 0), (88, 0)], "actions": 36, "home_share": .49, "shot_rate": .24, "recovery_rate": .17},
    204: {"goals": [(25, 0), (89, 1)], "actions": 34, "home_share": .50, "shot_rate": .18, "recovery_rate": .22},
    205: {"goals": [], "actions": 46, "home_share": .48, "shot_rate": .08, "recovery_rate": .35},
    206: {"goals": [(22, 0), (61, 0), (78, 1)], "actions": 48, "home_share": .52, "shot_rate": .34, "recovery_rate": .13},
    207: {"goals": [(3, 0), (66, 1), (84, 1)], "actions": 39, "home_share": .42, "shot_rate": .25, "recovery_rate": .18},
    208: {"goals": [(15, 0), (33, 1), (57, 1), (76, 0)], "actions": 41, "home_share": .50, "shot_rate": .26, "recovery_rate": .18},
    209: {"goals": [(9, 0), (31, 0), (52, 0), (81, 0)], "actions": 35, "home_share": .68, "shot_rate": .22, "recovery_rate": .16},
    210: {"goals": [(68, 0)], "actions": 50, "home_share": .55, "shot_rate": .17, "recovery_rate": .21},
}
_ROSTER_NAMES = ("A. Cole", "M. Silva", "J. Reed", "T. Okafor", "L. Byrne", "D. Khan",
                 "R. Costa", "E. Ward", "S. Ibrahim", "N. Park", "P. Morgan", "C. Lewis")
_PURPLE_LIME_CSS = """
<style>
  .stApp {background:#170f26;color:#f7f3ff}
  [data-testid="stHeader"] {background:rgba(23,15,38,.92)}
  [data-testid="stSidebar"] {background:#211536;border-right:1px solid #44345c}
  .block-container {max-width:1440px}
  h1,h2,h3 {color:#fff}
  .hero,.panel,.metric-card,div[data-testid="stMetric"] {background:#261a3b;border-color:#49365f}
  .hero {background:linear-gradient(115deg,#2c1c45,#211532 65%,#30203a)}
  .eyebrow,.section-kicker {color:#c7f36b}
  .score {color:#d3fb73}
  .badge {color:#ddff98;background:#34421d;border-color:#637a31}
  .tagline,.subtle,.hero-meta,.metric-label {color:#c1b4d4}
  div[data-testid="stButton"]>button {border-color:#625080;background:#2b1d40;color:#fff}
  div[data-testid="stButton"]>button:hover {border-color:#d0f878;background:#3b2855;color:#fff}
  div[data-testid="stButton"]>button[kind="primary"] {background:#7651a5;border-color:#a17dcc}
  div[data-testid="stButton"]>button:focus-visible {outline:3px solid #d0f878}
  .manual-box {background:#271f37}
  .warning-box {background:#302818}
</style>
"""

st.set_page_config(
    page_title="Touchline IQ | Match Intelligence",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { color-scheme: dark; }
      .stApp { background: #0b1117; color: #edf3f5; }
      [data-testid="stHeader"] { background: rgba(11,17,23,.92); }
      [data-testid="stSidebar"] { background: #101a22; border-right: 1px solid #24333c; }
      .block-container { max-width: 1420px; padding-top: 1.4rem; padding-bottom: 3rem; }
      h1, h2, h3 { color: #f5f8f8; letter-spacing: -.02em; }
      .brand-row { display:flex; align-items:center; gap:.85rem; margin-bottom:.25rem; }
      .brand-mark { width:42px; height:42px; display:grid; place-items:center; border-radius:13px;
        background:linear-gradient(145deg,#b9ef63,#74b834); color:#122014; font-size:23px; }
      .brand-name { font-size:1.35rem; font-weight:800; letter-spacing:.04em; color:#f4f7f6; }
      .tagline { margin:.15rem 0 1.15rem 3.35rem; color:#94a6ac; font-size:.88rem; letter-spacing:.08em; text-transform:uppercase; }
      .eyebrow { font-size:.7rem; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#a9ca72; }
      .hero { border:1px solid #283a41; border-radius:18px; padding:1.25rem 1.5rem;
        background:linear-gradient(115deg,#142129 0%,#111b22 62%,#19281e 100%); margin:.5rem 0 1.3rem; }
      .hero-meta { color:#a8b8bd; margin-top:.35rem; font-size:.92rem; }
      .scoreline { display:flex; align-items:center; justify-content:center; gap:1.2rem; padding:.4rem .2rem .1rem; }
      .score-team { font-size:1.22rem; font-weight:700; flex:1; }
      .score-team.right { text-align:right; }
      .score { font-size:2rem; font-weight:850; letter-spacing:.06em; color:#d7f7a1; white-space:nowrap; }
      .panel { border:1px solid #24343d; border-radius:15px; padding:1rem 1.05rem; background:#111a21; margin:.35rem 0 .8rem; }
      .metric-card { border:1px solid #293a42; background:#111a21; border-radius:14px; padding:.85rem .9rem; min-height:112px; }
      .metric-label { color:#9bafb4; font-size:.73rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
      .metric-pair { display:flex; justify-content:space-between; align-items:baseline; gap:.5rem; margin-top:.45rem; }
      .metric-value { color:#eff5ee; font-size:1.25rem; font-weight:750; }
      .metric-team { color:#789096; font-size:.72rem; margin-top:.25rem; }
      .badge { display:inline-block; padding:.3rem .62rem; border-radius:99px; font-size:.72rem; font-weight:800;
        letter-spacing:.04em; color:#d7f7a1; background:#26371e; border:1px solid #405830; }
      .warning-box { border-left:3px solid #e6b95b; padding:.65rem .8rem; background:#211e17; border-radius:0 9px 9px 0; color:#e4d8b7; margin:.4rem 0; }
      .manual-box { border-left:3px solid #75a9d3; padding:.7rem .85rem; background:#14202a; border-radius:0 9px 9px 0; margin:.45rem 0; }
      .subtle { color:#93a5ab; }
      .section-kicker { margin:.2rem 0 .65rem; color:#a9ca72; text-transform:uppercase; letter-spacing:.12em; font-weight:800; font-size:.7rem; }
      div[data-testid="stMetric"] { background:#111a21; border:1px solid #293a42; padding:.75rem .9rem; border-radius:13px; }
      div[data-testid="stMetricLabel"] { color:#9bafb4; }
      div[data-testid="stMetricValue"] { color:#eff5ee; }
      div[data-testid="stButton"] > button { min-height:3rem; border-color:#435b4a; transition:background .15s ease,border-color .15s ease; }
      div[data-testid="stButton"] > button:hover { border-color:#b9ef63; background:#1b2a22; }
      div[data-testid="stButton"] > button:focus-visible { outline:3px solid #b9ef63; outline-offset:2px; }
      div[data-testid="stButton"] > button[kind="secondary"] { text-align:left; }
      @media (max-width: 700px) { .score-team {font-size:1rem;} .score {font-size:1.55rem;} .hero {padding:1rem;} }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(_PURPLE_LIME_CSS, unsafe_allow_html=True)


def _fixture_events(fixture: tuple[str, int, str, str]) -> tuple[list[dict[str, Any]], tuple[str, str], dict[str, tuple[str, ...]]]:
    fixture_id, seed, home, away = fixture
    source_events = list(iter_synthetic_match(seed=seed))
    source_teams = SYNTHETIC_TEAMS
    teams = (home, away)
    roster_map = {
        source_teams[0]: tuple(f"{name} · {home.split()[0]}" for name in _ROSTER_NAMES[:6]),
        source_teams[1]: tuple(f"{name} · {away.split()[0]}" for name in _ROSTER_NAMES[6:]),
    }
    mapped: list[dict[str, Any]] = []
    for index, original in enumerate(source_events):
        event = dict(original)
        old_team = event["team"]
        event["team"] = home if old_team == source_teams[0] else away
        player_index = _ROSTER_NAMES.index(event["player"])
        event["player"] = roster_map[old_team][player_index % 6]
        if fixture_id != "live-northbridge-harbour":
            event["event_id"] = f"{fixture_id}-{index + 1:03d}"
        mapped.append(event)
    mapped = validate_events(mapped)
    return mapped, teams, {home: roster_map[source_teams[0]], away: roster_map[source_teams[1]]}


def _completed_fixture_events(
    fixture: tuple[str, int, str, str],
) -> tuple[list[dict[str, Any]], tuple[str, str], dict[str, tuple[str, ...]]]:
    """Generate a unique, reproducible completed event history for one profile."""
    fixture_id, seed, home, away = fixture
    profile = _COMPLETED_PROFILES[seed]
    rng = random.Random(seed)
    teams = (home, away)
    rosters = {
        home: tuple(f"{name} · {home.split()[0]}" for name in _ROSTER_NAMES[:6]),
        away: tuple(f"{name} · {away.split()[0]}" for name in _ROSTER_NAMES[6:]),
    }
    events: list[dict[str, Any]] = []

    def add(minute: int, second: int, side: int, kind: str, outcome: str,
            start: tuple[float, float] | None, end: tuple[float, float] | None,
            description: str, player_index: int | None = None) -> dict[str, Any]:
        event_id = f"{fixture_id}-evt-{len(events) + 1:03d}"
        player = rosters[teams[side]][player_index if player_index is not None else rng.randrange(6)]
        event = {
            "event_id": event_id, "minute": minute, "second": second,
            "team": teams[side], "player": player, "event_type": kind,
            "outcome": outcome,
            "start_x": start[0] if start else None, "start_y": start[1] if start else None,
            "end_x": end[0] if end else None, "end_y": end[1] if end else None,
            "description": description, "source": "synthetic",
        }
        events.append(event)
        return event

    goal_windows: list[tuple[int, int]] = []
    for goal_index, (minute, side) in enumerate(profile["goals"]):
        goal_windows.append((minute, minute - 1))
        scorer_index = (goal_index * 2 + seed) % 6
        # These explicitly recorded passes are the only events described as a
        # goal build-up; background actions are kept outside this short window.
        for pass_index, (start_x, end_x) in enumerate(((54.0, 68.0), (68.0, 83.0))):
            add(max(0, minute - 1), 10 + pass_index * 20, side, "pass", "successful",
                (start_x - 10, round(rng.uniform(35, 65), 1)),
                (end_x, round(rng.uniform(35, 65), 1)),
                "Completed pass in the recorded scoring sequence", (scorer_index + pass_index + 1) % 6)
        shot = add(minute, 20, side, "shot", "scored", (88.0, 50.0), (100.0, 50.0),
                   "Recorded shot resulted in a goal", scorer_index)
        add(minute, 21, side, "goal", "scored", (88.0, 50.0), (100.0, 50.0),
            "Explicit synthetic goal event", scorer_index)
        # Keep the explicit shot ID with the generated scoring pair for
        # diagnostics/tests; no score is inferred from the shot alone.
        shot["description"] = "Recorded shot resulted in a goal"

    for _ in range(int(profile["actions"])):
        minute = rng.randint(1, 90)
        second = rng.randint(0, 59)
        if any(abs(minute - goal_minute) <= 2 or abs(minute - pass_minute) <= 1
               for goal_minute, pass_minute in goal_windows):
            continue
        side = 0 if rng.random() < float(profile["home_share"]) else 1
        kind = rng.choices(
            ["pass", "recovery", "turnover", "shot"],
            weights=[54, 100 * float(profile["recovery_rate"]), 12, 100 * float(profile["shot_rate"])],
            k=1,
        )[0]
        x = round(rng.uniform(12, 88), 1)
        y = round(rng.uniform(8, 92), 1)
        if kind == "pass":
            successful = rng.random() < .82
            end = (round(max(0, min(100, x + rng.uniform(-7, 18))), 1),
                   round(max(0, min(100, y + rng.uniform(-16, 16))), 1))
            add(minute, second, side, kind, "successful" if successful else "unsuccessful",
                (x, y), end, "Completed pass" if successful else "Pass not completed")
        elif kind == "recovery":
            add(minute, second, side, kind, "successful", (x, y), None,
                "Possession recovered in the recorded match")
        elif kind == "turnover":
            add(minute, second, side, kind, "unsuccessful", (x, y), None,
                "Possession lost in the recorded match")
        else:
            on_target = rng.random() < .28
            add(minute, second, side, kind, "successful" if on_target else "unsuccessful",
                (round(rng.uniform(70, 94), 1), y), (100.0, 50.0),
                "Shot on target" if on_target else "Shot attempt recorded")

    return validate_events(events), teams, rosters


def _catalogue() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return session-cached, independent live and completed synthetic matches."""
    cache_key = "touchline_iq_fixture_catalogue_v1"
    if cache_key not in st.session_state:
        live: dict[str, dict[str, Any]] = {}
        for fixture_id, seed, home, away in LIVE_FIXTURES:
            events, teams, rosters = _fixture_events((fixture_id, seed, home, away))
            live[fixture_id] = {"id": fixture_id, "teams": teams, "rosters": rosters, "events": events}
        completed: dict[str, dict[str, Any]] = {}
        for fixture_id, seed, home, away in HIGHLIGHT_FIXTURES:
            events, teams, rosters = _completed_fixture_events((fixture_id, seed, home, away))
            metrics = calculate_match_metrics(events)
            completed[fixture_id] = {
                "id": fixture_id, "teams": teams, "rosters": rosters, "events": events,
                "final_score": {team: metrics["teams"].get(team, {}).get("goals", 0) for team in teams},
            }
        st.session_state[cache_key] = (live, completed)
    return st.session_state[cache_key]


def _match_state_key(match_id: str) -> str:
    return f"touchline_iq_playback_{match_id}"


def _restore_match_state(match: Mapping[str, Any]) -> None:
    """Load one fixture's independent clock into the established match-centre keys."""
    state = st.session_state.setdefault(_match_state_key(str(match["id"])), {
        "latest": 0, "viewed": 0, "playing": False, "step": 5, "next_tick": None,
    })
    st.session_state[_LATEST_TIME_KEY] = state["latest"]
    st.session_state[_VIEWED_TIME_KEY] = state["viewed"]
    st.session_state["match_simulation_playing"] = state["playing"]
    st.session_state["match_simulation_step_minutes"] = state["step"]
    st.session_state["match_next_tick_at"] = state["next_tick"]
    st.session_state[_SLIDER_KEY] = state["viewed"]


def _save_match_state(match_id: str) -> None:
    st.session_state[_match_state_key(match_id)] = {
        "latest": int(st.session_state.get(_LATEST_TIME_KEY, 0)),
        "viewed": int(st.session_state.get(_VIEWED_TIME_KEY, 0)),
        "playing": bool(st.session_state.get("match_simulation_playing", False)),
        "step": int(st.session_state.get("match_simulation_step_minutes", 5)),
        "next_tick": st.session_state.get("match_next_tick_at"),
    }


def _safe(value: Any) -> str:
    return html.escape(str(value))


def _number(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        rendered = f"{value:g}" if isinstance(value, float) else str(value)
        return f"{rendered}{suffix}"
    return f"{value}{suffix}"


def _metric_card(label: str, home: str, away: str, home_team: str, away_team: str) -> None:
    st.markdown(
        f"""<div class="metric-card">
        <div class="metric-label">{_safe(label)}</div>
        <div class="metric-pair"><span class="metric-value">{_safe(home)}</span><span class="subtle">vs</span><span class="metric-value">{_safe(away)}</span></div>
        <div class="metric-pair"><span class="metric-team">{_safe(home_team)}</span><span class="metric-team">{_safe(away_team)}</span></div>
        </div>""",
        unsafe_allow_html=True,
    )


def _timeline_frame(events: list[Mapping[str, Any]]) -> pd.DataFrame:
    def time_key(event: Mapping[str, Any]) -> tuple[int, int, int]:
        raw = str(event.get("minute", ""))
        if "+" in raw:
            base, extra = raw.split("+", 1)
            try:
                return int(base), int(extra), 1
            except ValueError:
                return 999, 999, 1
        try:
            return int(raw), 0, 0
        except ValueError:
            return 999, 999, 1

    ordered = sorted(events, key=time_key)
    rows = []
    for event in ordered:
        event_type = str(event.get("event_type", "event"))
        detail_parts = []
        assist = event.get("assist")
        if assist:
            detail_parts.append(f"Assist: {assist}")
        if event.get("detail"):
            detail_parts.append(str(event["detail"]))
        player_on, player_off = event.get("player_on"), event.get("player_off")
        if player_on or player_off:
            detail_parts.append(f"{player_on or '—'} for {player_off or '—'}")
        rows.append({
            "Time": str(event.get("minute", "—")),
            "Event": event_type.replace("_", " ").title(),
            "Team": event.get("team", "—"),
            "Player": event.get("player", player_on or "—"),
            "Details": " · ".join(detail_parts) if detail_parts else "—",
        })
    return pd.DataFrame(rows, columns=["Time", "Event", "Team", "Player", "Details"])


def _show_brand() -> None:
    st.markdown(
        '<div class="brand-row"><div class="brand-mark">⚽</div><div class="brand-name">TOUCHLINE IQ</div></div>'
        '<div class="tagline">Beyond the Score. Into the Game.</div>',
        unsafe_allow_html=True,
    )


def _show_real_match(match: Mapping[str, Any]) -> None:
    home, away = match.get("home_team", "Home"), match.get("away_team", "Away")
    score = match.get("final_score") or {}
    st.markdown(
        f"""<div class="hero">
          <div class="eyebrow">Sourced match data</div>
          <div class="scoreline"><div class="score-team">{_safe(home)}</div>
          <div class="score">{_safe(score.get('home', '—'))} : {_safe(score.get('away', '—'))}</div>
          <div class="score-team right">{_safe(away)}</div></div>
          <div class="hero-meta" style="text-align:center">{_safe(match.get('competition', 'Competition unavailable'))} &nbsp;·&nbsp; {_safe(match.get('date', 'Date unavailable'))}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    stats = (match.get("statistics") or {}).get("teams") or {}
    home_stats = stats.get(home) or {}
    away_stats = stats.get(away) or {}
    stat_specs = [
        ("Possession", "possession_pct", "%"),
        ("Expected goals · sourced", "xg", ""),
        ("Shots", "shots", ""),
        ("Shots on target", "shots_on_target", ""),
        ("Passes completed / attempted", "passes", ""),
        ("Touches in opposition box", "touches_in_opposition_box", ""),
    ]
    st.markdown('<div class="section-kicker">Match statistics · sourced values</div>', unsafe_allow_html=True)
    columns = st.columns(3)
    for index, (label, key, suffix) in enumerate(stat_specs):
        if key == "passes":
            home_value = f"{_number(home_stats.get('passes_completed'))} / {_number(home_stats.get('passes_attempted'))}"
            away_value = f"{_number(away_stats.get('passes_completed'))} / {_number(away_stats.get('passes_attempted'))}"
        else:
            home_value = _number(home_stats.get(key), suffix)
            away_value = _number(away_stats.get(key), suffix)
        with columns[index % 3]:
            _metric_card(label, home_value, away_value, home, away)

    timeline = (match.get("event_timeline") or {}).get("events") or []
    timeline_types = sorted({str(event.get("event_type", "")) for event in timeline if isinstance(event, Mapping)})
    st.markdown('<div class="section-kicker" style="margin-top:1.35rem">Match timeline · sourced events</div>', unsafe_allow_html=True)
    st.caption(f"{len(timeline)} sourced timeline entries · event types: {', '.join(timeline_types) if timeline_types else 'not available'}")
    if timeline:
        st.dataframe(_timeline_frame(timeline), hide_index=True, width="stretch")
    else:
        st.info("No sourced timeline events are available for this match.")

    # The current sourced timelines contain result events, cards and substitutions,
    # but do not contain the event coordinates or event types used by analytics.py.
    st.markdown('<div class="section-kicker" style="margin-top:1.35rem">Tactical analysis</div>', unsafe_allow_html=True)
    st.info(
        "Event-level tactical analysis is unavailable for this match. The sourced timeline does not provide "
        "the shot, turnover, recovery, and coordinate evidence required by the current rule-based analytics. "
        "Aggregate statistics and manual observations are not converted into events."
    )

    with st.expander("Sources & data quality", expanded=False):
        references = match.get("source_references") or []
        if references:
            for reference in references:
                name = _safe(reference.get("name", "Source"))
                url = _safe(reference.get("url", ""))
                source_id = _safe(reference.get("source_id", ""))
                used_for = reference.get("used_for") or []
                st.markdown(f"- **{name}** · `{source_id}` · [Open source]({url})")
                if used_for:
                    st.caption("Used for: " + ", ".join(str(item) for item in used_for))
        else:
            st.caption("No source references are recorded.")

        warnings = list(match.get("data_quality_notes") or [])
        discrepancies = (match.get("statistics") or {}).get("discrepancies") or []
        for discrepancy in discrepancies:
            note = discrepancy.get("note") if isinstance(discrepancy, Mapping) else None
            if note:
                warnings.append(str(note))
        if warnings:
            st.markdown("**Recorded warnings and discrepancies**")
            for warning in dict.fromkeys(warnings):
                st.markdown(f'<div class="warning-box">{_safe(warning)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No data-quality warnings are recorded.")

    manual = match.get("manual_observations") or {}
    entries = manual.get("entries") or [] if isinstance(manual, Mapping) else []
    st.markdown('<div class="section-kicker" style="margin-top:1rem">Manual observations</div>', unsafe_allow_html=True)
    st.markdown('<span class="badge">User-reported observation — unverified</span>', unsafe_allow_html=True)
    if entries:
        st.caption("These notes are presented separately and are not treated as sourced timeline events or analytics input.")
        for entry in entries:
            text = entry.get("text", "") if isinstance(entry, Mapping) else str(entry)
            category = entry.get("category", "observation") if isinstance(entry, Mapping) else "observation"
            st.markdown(
                f'<div class="manual-box"><span class="eyebrow">{_safe(category.replace("_", " "))}</span><br>{_safe(text)}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No user-reported manual observations are recorded for this match.")

    conflicts = match.get("manual_observation_conflicts") or []
    if conflicts:
        with st.expander("Manual-observation conflict notes", expanded=False):
            st.caption("For later verification; these notes do not alter the sourced match record.")
            for conflict in conflicts:
                note = conflict.get("note", "") if isinstance(conflict, Mapping) else str(conflict)
                status = conflict.get("status", "") if isinstance(conflict, Mapping) else ""
                st.markdown(f'<div class="warning-box"><b>{_safe(status)}</b><br>{_safe(note)}</div>', unsafe_allow_html=True)


def _synthetic_events() -> list[dict[str, Any]]:
    seed = 42
    stream_key = f"touchline_iq_synthetic_stream_{seed}"
    count_key = f"touchline_iq_synthetic_revealed_{seed}"
    if stream_key not in st.session_state:
        st.session_state[stream_key] = list(iter_synthetic_match(seed=seed))
        st.session_state[count_key] = 0
    return st.session_state[stream_key]


def _synthetic_revealed_events(all_events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    count_key = "touchline_iq_synthetic_revealed_42"
    count = min(int(st.session_state.get(count_key, 0)), len(all_events))
    return all_events[:count], count == len(all_events)


def _sourced_highlights(match: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Adapt only the sourced timeline's recorded events into display moments."""
    events = (match.get("event_timeline") or {}).get("events") or []
    highlights: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        kind = str(event.get("event_type", "event"))
        player = event.get("player")
        if kind == "goal":
            title = f"Goal — {player}" if player else "Goal recorded"
        elif kind == "yellow_card":
            title = f"Yellow card — {player}" if player else "Yellow card recorded"
        elif kind == "substitution":
            on, off = event.get("player_on"), event.get("player_off")
            title = f"Substitution — {on or 'Unknown'} for {off or 'Unknown'}"
        else:
            title = kind.replace("_", " ").title()
        details = []
        if event.get("assist"):
            details.append(f"Assist recorded: {event['assist']}")
        if event.get("detail"):
            details.append(str(event["detail"]))
        highlights.append({
            "title": title,
            "minute": event.get("minute"),
            "team": event.get("team"),
            "explanation": "; ".join(details) or "Recorded sourced timeline event.",
            "event_type": kind,
        })
    return highlights


def _match_score(match: Mapping[str, Any]) -> str:
    score = match.get("final_score") or {}
    home, away = score.get("home"), score.get("away")
    return f"{home}–{away}" if home is not None and away is not None else "—"


def _sourced_player_involvements(match: Mapping[str, Any]) -> pd.DataFrame:
    involvements: dict[str, Counter[str]] = defaultdict(Counter)
    events = (match.get("event_timeline") or {}).get("events") or []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        kind = str(event.get("event_type", "event"))
        if event.get("player"):
            involvements[str(event["player"])][kind] += 1
        if event.get("assist"):
            involvements[str(event["assist"])]["assist"] += 1
        if event.get("player_on"):
            involvements[str(event["player_on"])]["substitution_on"] += 1
        if event.get("player_off"):
            involvements[str(event["player_off"])]["substitution_off"] += 1
    rows = [
        {"Player": player, "Recorded timeline involvements": sum(counts.values()),
         **{label.replace("_", " ").title(): count for label, count in sorted(counts.items())}}
        for player, counts in sorted(involvements.items())
    ]
    return pd.DataFrame(rows)


def _synthetic_player_stats(events: list[Mapping[str, Any]]) -> pd.DataFrame:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        player = event.get("player")
        if player:
            counts[str(player)][str(event.get("event_type", "event"))] += 1
    columns = ["Player", "Events", "Passes", "Shots", "Goals", "Recoveries", "Turnovers"]
    rows = []
    for player, values in sorted(counts.items()):
        rows.append({
            "Player": player,
            "Events": sum(values.values()),
            "Passes": values["pass"],
            "Shots": values["shot"],
            "Goals": values["goal"],
            "Recoveries": values["recovery"],
            "Turnovers": values["turnover"],
        })
    return pd.DataFrame(rows, columns=columns)


def _render_synthetic_highlights(insights: list[Mapping[str, Any]]) -> None:
    available = [item for item in insights if item.get("type") != "match_recap"]
    if not available:
        st.info("No supported highlights are available in the revealed synthetic events yet.")
        return
    for insight in available:
        when = insight.get("match_timestamp") or {}
        timestamp = f"{when.get('minute')}:{int(when.get('second', 0)):02d}" if when else "Time unavailable"
        with st.container(border=True):
            st.markdown(f"**{timestamp} · {insight.get('title', 'Match insight')}**")
            st.write(insight.get("explanation", ""))
            st.caption(
                f"{insight.get('status', 'provisional').title()} · Supporting synthetic events: "
                + ", ".join(insight.get("supporting_event_ids", []))
            )
            quality = insight.get("evidence_quality") or {}
            st.caption(
                f"Evidence strength: {quality.get('strength', 'Unavailable')} (descriptive, not a probability). "
                + "; ".join(quality.get("limitations", []))
            )


def _show_synthetic_detail() -> None:
    all_events = _synthetic_events()
    events, complete = _synthetic_revealed_events(all_events)
    metrics = calculate_match_metrics(events)
    insights = generate_match_insights(events, SYNTHETIC_MATCH_ID, complete=complete)
    overview, highlights, player_stats, outro = st.tabs(["Overview", "Highlights", "Player Stats", "Outro"])

    with overview:
        st.markdown(
            '<div class="hero"><div class="eyebrow">Synthetic demonstration · not a real fixture</div>'
            '<div style="font-size:1.5rem;font-weight:800;margin-top:.3rem">Northbridge FC vs Harbour City</div>'
            '<div class="hero-meta">Seed 42 · one persistent match event stream</div></div>',
            unsafe_allow_html=True,
        )
        home, away = SYNTHETIC_TEAMS
        score = f"{metrics['teams'].get(home, {}).get('goals', 0)}–{metrics['teams'].get(away, {}).get('goals', 0)}"
        score_col, event_col, shots_col, passes_col = st.columns(4)
        score_col.metric("Score so far", score)
        event_col.metric("Events revealed", f"{len(events)} / {len(all_events)}")
        shots_col.metric("Explicit shots", metrics["shots"])
        passes_col.metric("Pass completion", _number(metrics["pass_completion_pct"], "%"))
        st.caption("All figures use only the revealed synthetic event prefix; goals and shots count explicit records separately.")
        if not complete and st.button("Reveal next 10 synthetic events", type="primary", key="detail-reveal-next"):
            st.session_state["touchline_iq_synthetic_revealed_42"] = min(len(events) + 10, len(all_events))
            st.rerun()
        st.markdown("**Fictional player pools**")
        for team in SYNTHETIC_TEAMS:
            st.write(f"{team}: {', '.join(SYNTHETIC_PLAYERS[team])}")
        st.caption("These are player pools, not a separately modelled starting lineup.")

    with highlights:
        st.subheader("Synthetic highlights and rule-based insights")
        st.caption("Generated only from the events revealed for this match; provisional until the stream is complete.")
        _render_synthetic_highlights(insights)
        if events:
            st.markdown("**Revealed event timeline**")
            timeline = _timeline_frame(events)
            timeline.insert(0, "Provenance", "Synthetic demonstration data")
            st.dataframe(timeline, hide_index=True, width="stretch")

    with player_stats:
        st.subheader("Recorded synthetic player events")
        st.caption("Event counts only; these are not physical or performance measurements.")
        frame = _synthetic_player_stats(events)
        if frame.empty:
            st.info("No player events have been revealed yet.")
        else:
            st.dataframe(frame, hide_index=True, width="stretch")

    with outro:
        st.subheader("Outro · synthetic match recap")
        if not complete:
            st.info("The final recap is unavailable until the synthetic event stream is complete.")
            if st.button("Complete synthetic match", type="primary", key="detail-complete-match"):
                st.session_state["touchline_iq_synthetic_revealed_42"] = len(all_events)
                st.rerun()
        else:
            recap = next((item for item in insights if item.get("type") == "match_recap"), None)
            if recap:
                st.success("Final recap · based on the completed synthetic event stream.")
                st.markdown(f"**{recap['title']}**")
                st.write(recap["explanation"])
                st.json(recap["metrics"])
            _render_synthetic_highlights(insights)


def _render_source_highlights(match: Mapping[str, Any]) -> None:
    highlights = _sourced_highlights(match)
    if not highlights:
        st.info("No sourced timeline moments are available for this match.")
        return
    timeline = match.get("event_timeline") or {}
    source_ids = timeline.get("source_ids") or []
    references = {item.get("source_id"): item for item in match.get("source_references", [])}
    st.caption("Sourced timeline moments only; no additional tactical events have been inferred.")
    for highlight in highlights:
        with st.container(border=True):
            st.markdown(f"**{highlight['minute'] or '—'}′ · {highlight['title']}**")
            team = highlight.get("team")
            st.write((f"{team} · " if team else "") + highlight["explanation"])
            st.caption("Provenance: Sourced match data · " + ", ".join(source_ids or ["source unavailable"]))
    for source_id in source_ids:
        reference = references.get(source_id)
        if reference:
            st.markdown(f"Source: [{reference.get('name', source_id)}]({reference.get('url', '')})")


def _show_sourced_detail(match: Mapping[str, Any]) -> None:
    overview, highlights, player_stats, outro = st.tabs(["Overview", "Highlights", "Player Stats", "Outro"])
    with overview:
        _show_chat(match)
        _show_real_match(match)
    with highlights:
        st.subheader("Sourced match highlights")
        _render_source_highlights(match)
    with player_stats:
        st.subheader("Player stats · sourced timeline evidence")
        frame = _sourced_player_involvements(match)
        if frame.empty:
            st.info("Player-level statistics are unavailable in this match record.")
        else:
            st.caption("Only player involvements explicitly recorded in the sourced event timeline are shown; team aggregates are not distributed to players.")
            st.dataframe(frame, hide_index=True, width="stretch")
    with outro:
        st.subheader("Outro · sourced match record")
        st.markdown(
            f"**{match.get('home_team', 'Home')} {_match_score(match)} {match.get('away_team', 'Away')}**"
        )
        st.caption(
            f"{match.get('competition', 'Competition unavailable')} · {match.get('date', 'Date unavailable')} · Sourced match data"
        )
        st.write(
            f"The record contains {len(_sourced_highlights(match))} sourced timeline moments. "
            "This is a summary of the stored record, not a newly inferred tactical recap."
        )
        _render_source_highlights(match)

def _render_chat_item(item: Mapping[str, Any]) -> None:
    role = item.get("role", "assistant")
    with st.chat_message(role):
        if role == "user":
            st.write(item.get("content", ""))
            return

        response = item.get("response") or {}
        st.markdown(response.get("answer", ""))
        category = response.get("category")
        if category:
            st.caption(f"Evidence type: {category}")

        evidence = response.get("evidence") or []
        if evidence:
            with st.expander("Evidence used", expanded=False):
                for item_text in evidence:
                    st.markdown(f"- {item_text}")

        sources = response.get("sources") or []
        if sources:
            source_links = []
            for source in sources:
                name = source.get("name") or source.get("source_id") or "Source"
                url = source.get("url")
                source_links.append(f"[{name}]({url})" if url else str(name))
            st.markdown("Sources: " + " · ".join(source_links))
        elif category == "User-reported, unverified observation":
            st.caption("This is user-reported material; no external source is attached as verification.")


def _show_chat(match: Mapping[str, Any]) -> None:
    match_id = str(match.get("match_id", "selected-match"))
    history = match_scoped_history(st.session_state, match_id)
    st.markdown('<div class="section-kicker" style="margin-top:.7rem">Ask Touchline IQ</div>', unsafe_allow_html=True)
    st.caption("Local evidence retrieval · deterministic responses · no language model or external service")

    if not history:
        with st.chat_message("assistant"):
            st.write("Ask about this match’s result, statistics, goals, substitutions, sources, or recorded observations.")
            st.caption("Answers use only the selected match. Unsupported tactical claims are reported as unavailable.")
    else:
        for item in history:
            _render_chat_item(item)

    home = str(match.get("home_team", "Home"))
    away = str(match.get("away_team", "Away"))
    prompt = st.chat_input(
        f"Ask about {home} vs {away}",
        key=f"touchline-chat-input-{match_id}",
    )
    if prompt and prompt.strip():
        history.append({"role": "user", "content": prompt.strip()})
        history.append({"role": "assistant", "response": answer_question(match, prompt.strip())})
        st.rerun()


def _match_browser_rows(
    section: str,
    matches: list[Mapping[str, Any]],
    all_synthetic_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    is_highlights = section == "HIGHLIGHTS"
    for match in matches:
        moments = _sourced_highlights(match)
        if is_highlights and not moments:
            continue
        key_moment = next((item for item in moments if item["event_type"] == "goal"), None)
        key_moment = key_moment or (moments[0] if moments else None)
        score = _match_score(match)
        rows.append({
            "match_ref": f"sourced:{match.get('match_id')}",
            "match_label": f"{match.get('home_team', 'Home')} {score} {match.get('away_team', 'Away')}",
            "Status": "Recorded · not live" if not is_highlights else "Sourced",
            "Home team": match.get("home_team", "—"),
            "Score": score,
            "Away team": match.get("away_team", "—"),
            "Competition": match.get("competition") or "—",
            "Available highlights": len(moments),
            "Key moment": (
                f"{key_moment['minute']}′ · {key_moment['title']}" if key_moment else "—"
            ),
            "Provenance": "Sourced match data",
            "Action": "Choose below",
        })

    if is_highlights:
        demo_events = all_synthetic_events
        demo_metrics = calculate_match_metrics(demo_events)
        demo_insights = generate_match_insights(demo_events, SYNTHETIC_MATCH_ID, complete=True)
        demo_highlights = [item for item in demo_insights if item.get("type") != "match_recap"]
        first_moment = next(
            (item for item in demo_highlights if item.get("type") == "goal_highlight"),
            demo_highlights[0] if demo_highlights else None,
        )
        teams = SYNTHETIC_TEAMS
        score = f"{demo_metrics['teams'].get(teams[0], {}).get('goals', 0)}–{demo_metrics['teams'].get(teams[1], {}).get('goals', 0)}"
        timestamp = (first_moment or {}).get("match_timestamp") or {}
        moment_label = (
            f"{timestamp.get('minute')}′ · {first_moment.get('title')}" if first_moment else "—"
        )
        rows.append({
            "match_ref": f"synthetic:{SYNTHETIC_MATCH_ID}",
            "match_label": f"{teams[0]} {score} {teams[1]} · Demo",
            "Status": "Demo",
            "Home team": teams[0],
            "Score": score,
            "Away team": teams[1],
            "Competition": "Synthetic demonstration",
            "Available highlights": len(demo_highlights),
            "Key moment": moment_label,
            "Provenance": "Synthetic demonstration data",
            "Action": "Choose below",
        })
    else:
        current_events, _ = _synthetic_revealed_events(all_synthetic_events)
        metrics = calculate_match_metrics(current_events)
        home, away = SYNTHETIC_TEAMS
        demo_score = f"{metrics['teams'].get(home, {}).get('goals', 0)}–{metrics['teams'].get(away, {}).get('goals', 0)}"
        rows.append({
            "match_ref": f"synthetic:{SYNTHETIC_MATCH_ID}",
            "match_label": f"{home} {demo_score} {away} · Demo",
            "Status": "Demo",
            "Home team": home,
            "Score": demo_score,
            "Away team": away,
            "Competition": "Synthetic demonstration",
            "Available highlights": "—",
            "Key moment": "—",
            "Provenance": "Synthetic demonstration data",
            "Action": "Choose below",
        })
    return rows


def _show_match_browser(section: str, matches: list[Mapping[str, Any]], synthetic_events: list[dict[str, Any]]) -> None:
    if section == "LIVE":
        st.info("Real-time match coverage is not connected. Recorded sourced matches are not live fixtures; the synthetic entry is labelled Demo.")
    else:
        st.caption("Sourced timeline moments and synthetic insights are kept separate and labelled by provenance.")

    query = st.text_input("Search teams or competition", key=f"match-search-{section}").strip().casefold()
    rows = _match_browser_rows(section, matches, synthetic_events)
    if query:
        rows = [row for row in rows if query in " ".join(str(value) for value in row.values()).casefold()]
    if not rows:
        st.info("No matches are available for this search.")
        return

    if section == "LIVE":
        columns = ["Status", "Home team", "Score", "Away team", "Competition", "Provenance", "Action"]
    else:
        columns = ["Status", "Home team", "Score", "Away team", "Available highlights", "Key moment", "Provenance", "Action"]
    st.dataframe(pd.DataFrame(rows)[columns], hide_index=True, width="stretch")
    st.caption("Select a match, then use View match to open its analysis tabs.")
    selected_ref = st.selectbox(
        "Select match",
        options=[row["match_ref"] for row in rows],
        format_func=lambda ref: next((row["match_label"] for row in rows if row["match_ref"] == ref), ref),
        key=f"match-choice-{section}",
    )
    if st.button("View match", type="primary", key=f"view-match-{section}"):
        st.session_state["touchline_iq_selected_match_ref"] = selected_ref
        st.session_state["touchline_iq_match_origin"] = section
        if selected_ref == f"synthetic:{SYNTHETIC_MATCH_ID}" and section == "HIGHLIGHTS":
            st.session_state["touchline_iq_synthetic_revealed_42"] = len(synthetic_events)
        st.rerun()


_MATCH_EVENTS_KEY = "touchline_iq_match_centre_events_v2"
_MATCH_ID_KEY = "touchline_iq_match_centre_selected_v2"
_LATEST_TIME_KEY = "current_match_time"
_VIEWED_TIME_KEY = "viewed_match_time"
_SLIDER_KEY = "match_timeline_slider_v2"


def _ensure_demo_session() -> list[dict[str, Any]]:
    """Initialize one match history and its clock once per Streamlit session."""
    if _MATCH_EVENTS_KEY not in st.session_state:
        st.session_state[_MATCH_EVENTS_KEY] = list(iter_synthetic_match(seed=42))
    st.session_state.setdefault(_MATCH_ID_KEY, None)
    st.session_state.setdefault(_LATEST_TIME_KEY, 0)
    st.session_state.setdefault(_VIEWED_TIME_KEY, 0)
    st.session_state.setdefault("follow_match_latest", True)
    st.session_state.setdefault("match_simulation_playing", False)
    st.session_state.setdefault("match_simulation_step_minutes", 5)
    st.session_state.setdefault("match_next_tick_at", None)
    st.session_state.setdefault(_SLIDER_KEY, 0)
    return st.session_state[_MATCH_EVENTS_KEY]


def _format_match_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _set_viewed_time(seconds: int) -> None:
    latest = int(st.session_state.get(_LATEST_TIME_KEY, 0))
    viewed = clamp_viewed_match_time(seconds, latest)
    st.session_state[_VIEWED_TIME_KEY] = viewed
    st.session_state[_SLIDER_KEY] = viewed
    st.session_state["follow_match_latest"] = viewed == latest
    active_id = st.session_state.get("touchline_iq_current_live_id")
    if active_id:
        _save_match_state(active_id)


def _on_timeline_slider_change() -> None:
    _set_viewed_time(int(st.session_state[_SLIDER_KEY]))


def _scoreline(metrics: Mapping[str, Any], teams: tuple[str, str] = SYNTHETIC_TEAMS) -> str:
    home, away = teams
    teams = metrics.get("teams") or {}
    return f"{teams.get(home, {}).get('goals', 0)}–{teams.get(away, {}).get('goals', 0)}"


def _match_highlights(
    events: list[dict[str, Any]], insights: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    highlights: list[dict[str, Any]] = []
    for insight in insights:
        if insight.get("type") == "match_recap":
            continue
        timestamp = insight.get("match_timestamp") or {}
        minute = int(timestamp.get("minute", 0))
        second = int(timestamp.get("second", 0))
        highlights.append({
            "time": minute * 60 + second,
            "title": insight.get("title", "Match insight"),
            "explanation": insight.get("explanation", ""),
            "supporting_event_ids": list(insight.get("supporting_event_ids", [])),
            "strength": (insight.get("evidence_quality") or {}).get("strength"),
            "kind": insight.get("type", "insight"),
        })
    represented = {event_id for item in highlights for event_id in item["supporting_event_ids"]}
    for event in events:
        if event["event_type"] != "shot" or event["outcome"] == "scored" or event["event_id"] in represented:
            continue
        highlights.append({
            "time": int(event["minute"]) * 60 + int(event["second"]),
            "title": f"Shot attempt · {event['player']} ({event['team']})",
            "explanation": event["description"],
            "supporting_event_ids": [event["event_id"]],
            "strength": "Recorded event",
            "kind": "shot",
        })
    return sorted(highlights, key=lambda item: (item["time"], item["title"]))


@st.fragment(run_every=1.0)
def _show_match_centre(
    all_events: list[dict[str, Any]], match_id: str = SYNTHETIC_MATCH_ID,
    teams: tuple[str, str] = SYNTHETIC_TEAMS,
    rosters: Mapping[str, tuple[str, ...]] = SYNTHETIC_PLAYERS,
) -> None:
    now = time.monotonic()
    latest = min(int(st.session_state.get(_LATEST_TIME_KEY, 0)), MATCH_DURATION_SECONDS)
    if st.session_state.get("match_simulation_playing"):
        deadline = st.session_state.get("match_next_tick_at")
        if deadline is not None and now >= deadline:
            step = int(st.session_state.get("match_simulation_step_minutes", 5)) * 60
            latest = min(latest + step, MATCH_DURATION_SECONDS)
            st.session_state[_LATEST_TIME_KEY] = latest
            st.session_state["match_next_tick_at"] = now + 1.0
            if st.session_state.get("follow_match_latest", True):
                st.session_state[_VIEWED_TIME_KEY] = latest
                st.session_state[_SLIDER_KEY] = latest
            if latest >= MATCH_DURATION_SECONDS:
                st.session_state["match_simulation_playing"] = False
                st.session_state["match_next_tick_at"] = None

    latest = min(int(st.session_state.get(_LATEST_TIME_KEY, 0)), MATCH_DURATION_SECONDS)
    viewed = clamp_viewed_match_time(int(st.session_state.get(_VIEWED_TIME_KEY, 0)), latest)
    st.session_state[_VIEWED_TIME_KEY] = viewed
    if int(st.session_state.get(_SLIDER_KEY, 0)) > latest:
        st.session_state[_SLIDER_KEY] = viewed

    header_col, control_col = st.columns([3, 2])
    with header_col:
        status = (
            "Full Time · Demo" if latest >= MATCH_DURATION_SECONDS
            else "Simulating · Demo" if st.session_state.get("match_simulation_playing")
            else "Ready · Demo" if latest == 0
            else "Paused · Demo"
        )
        st.markdown(
            f'<div class="hero"><div class="eyebrow">Simulated match · not a real fixture</div>'
            f'<div class="scoreline"><div class="score-team">{_safe(teams[0])}</div>'
            f'<div class="score">{_scoreline(calculate_match_metrics(events_through_time(all_events, viewed)), teams)}</div>'
            f'<div class="score-team right">{_safe(teams[1])}</div></div>'
            f'<div class="hero-meta" style="text-align:center">{_safe(SYNTHETIC_COMPETITION)} · {status} · '
            f'Viewed {_format_match_time(viewed)} · Latest {_format_match_time(latest)}</div></div>',
            unsafe_allow_html=True,
        )
    with control_col:
        st.markdown("**Manual simulation clock**")
        step = st.selectbox(
            "Match minutes per second",
            options=[1, 2, 5, 10],
            key="match_simulation_step_minutes",
            format_func=lambda value: f"{value} match minute{'s' if value != 1 else ''} / second",
        )
        buttons = st.columns(3)
        with buttons[0]:
            if not st.session_state.get("match_simulation_playing"):
                if st.button("▶ Play", key="match-play", disabled=latest >= MATCH_DURATION_SECONDS):
                    st.session_state["match_simulation_playing"] = True
                    st.session_state["match_next_tick_at"] = time.monotonic() + 1.0
            elif st.button("⏸ Pause", key="match-pause"):
                st.session_state["match_simulation_playing"] = False
                st.session_state["match_next_tick_at"] = None
        with buttons[1]:
            if st.button("Jump to Latest", key="match-jump-latest"):
                _set_viewed_time(latest)
        with buttons[2]:
            st.caption("Playing" if st.session_state.get("match_simulation_playing") else "Paused")
        st.caption(f"Current simulation time (latest reached): {_format_match_time(latest)}")
        st.caption(f"Viewing match history at: {_format_match_time(viewed)}")

    if latest > 0:
        st.session_state[_SLIDER_KEY] = clamp_viewed_match_time(
            int(st.session_state.get(_SLIDER_KEY, viewed)), latest
        )
        st.slider(
            "Match timeline · drag backward to inspect history",
            min_value=0,
            max_value=latest,
            step=1,
            key=_SLIDER_KEY,
            on_change=_on_timeline_slider_change,
            format="%d seconds",
        )
        viewed = clamp_viewed_match_time(int(st.session_state[_SLIDER_KEY]), latest)
        st.session_state[_VIEWED_TIME_KEY] = viewed
    else:
        st.info("The match is paused at 00:00. Press Play to start; the historical timeline unlocks as the clock advances.")

    goal_markers = [
        _format_match_time(int(event["minute"]) * 60 + int(event["second"]))
        for event in all_events
        if event["event_type"] == "goal"
        and int(event["minute"]) * 60 + int(event["second"]) <= viewed
    ]
    st.caption("Goal markers visible at this historical point: " + (" · ".join(goal_markers) if goal_markers else "none"))

    viewed = clamp_viewed_match_time(int(st.session_state[_VIEWED_TIME_KEY]), latest)
    visible_events = events_through_time(all_events, viewed)
    metrics = calculate_match_metrics(visible_events)
    full_time_view = latest >= MATCH_DURATION_SECONDS and viewed >= MATCH_DURATION_SECONDS
    insights = generate_match_insights(visible_events, match_id, complete=full_time_view)
    commentary = generate_match_commentary(
        all_events, match_id, viewed_match_time=viewed,
        complete=latest >= MATCH_DURATION_SECONDS,
    )
    overview, highlights_tab, player_stats_tab, commentary_tab = st.tabs(
        ["Overview", "Highlights", "Player Stats", "Commentary"]
    )

    with overview:
        st.subheader("Overview")
        st.caption(f"{SYNTHETIC_COMPETITION} · Fictional teams and players · Synthetic demonstration data")
        stat_columns = st.columns(5)
        metric_specs = [
            ("Goals", metrics["goals"]),
            ("Shots", metrics["shots"]),
            ("Passes", metrics["passes"]),
            ("Recoveries", metrics["recoveries"]),
            ("Turnovers", metrics["turnovers"]),
        ]
        for column, (label, value) in zip(stat_columns, metric_specs):
            column.metric(label, value)
        st.metric("Pass completion from recorded pass outcomes", _number(metrics["pass_completion_pct"], "%"))
        st.caption("Statistics and score are reconstructed only from events at or before the viewed time. No possession, xG, assists, or tracking measurements are inferred.")
        recent = [item for item in commentary if item["type"] not in {"half_time", "full_time"}][-3:]
        st.markdown("**Recent commentary at this time**")
        if recent:
            for item in recent:
                st.write(f"{item['timestamp']} · {item['text']}")
        else:
            st.caption("No event commentary is available at this viewed time.")
        tactical = [item for item in insights if item["type"] in {"tactical_pattern", "shot_area"}]
        if tactical:
            st.markdown("**Evidence-backed tactical observations**")
            for item in tactical[:3]:
                st.markdown(f"- **{item['title']}** — {item['explanation']}")
                st.caption(f"Supporting event IDs: {', '.join(item['supporting_event_ids'])} · {item['evidence_quality']['strength']} descriptive evidence")

    with highlights_tab:
        st.subheader("Highlights")
        highlights = _match_highlights(visible_events, insights)
        if not highlights:
            st.info("No highlights have occurred by the viewed time.")
        for index, item in enumerate(highlights):
            with st.container(border=True):
                st.markdown(f"**{_format_match_time(item['time'])} · {item['title']}**")
                st.write(item["explanation"])
                st.caption("Supporting event IDs: " + (", ".join(item["supporting_event_ids"]) or "none recorded"))
                if item.get("strength"):
                    st.caption(f"Evidence strength: {item['strength']} · descriptive, not a model probability")
                st.button(
                    f"View at {_format_match_time(item['time'])}",
                    key=f"highlight-jump-{index}-{item['kind']}",
                    on_click=_set_viewed_time,
                    args=(item["time"],),
                )

    with player_stats_tab:
        st.subheader("Player Stats")
        st.caption("Event-derived counts for the selected player, limited to the viewed time. No ratings or physical metrics are available.")
        player_stats = calculate_player_stats(visible_events)
        all_players = sorted({player for roster in rosters.values() for player in roster})
        selected_player = st.selectbox("Select a player", all_players, key=f"match-centre-player-select-{match_id}")
        selected_stats = player_stats.get(selected_player, {})
        st.caption(f"Team: {selected_stats.get('team', next((team for team, roster in rosters.items() if selected_player in roster), 'Unavailable'))}")
        player_columns = st.columns(4)
        player_specs = [
            ("Goals", selected_stats.get("goals", 0)),
            ("Shots", selected_stats.get("shots", 0)),
            ("Pass attempts", selected_stats.get("pass_attempts", 0)),
            ("Successful passes", selected_stats.get("successful_passes", 0)),
            ("Pass completion", _number(selected_stats.get("pass_completion_pct"), "%")),
            ("Recoveries", selected_stats.get("recoveries", 0)),
            ("Turnovers", selected_stats.get("turnovers", 0)),
        ]
        for column, (label, value) in zip((player_columns * 2), player_specs):
            column.metric(label, value)
        contributions = [event for event in visible_events if event["player"] == selected_player]
        if contributions:
            st.markdown("**Recorded contributions**")
            st.dataframe(_timeline_frame(contributions), hide_index=True, width="stretch")
        else:
            st.info("No events attributed to this player have occurred by the viewed time.")

    with commentary_tab:
        st.subheader("Commentary")
        st.caption("Deterministic text commentary generated from this match's recorded synthetic events and supported rules.")
        if not commentary:
            st.info("Commentary will appear as the simulation clock advances.")
        for item in commentary:
            st.markdown(f"**{item['timestamp']} · {item['type'].replace('_', ' ').title()} · {item['score'][teams[0]]}–{item['score'][teams[1]]}**")
            st.write(item["text"])
            if item["supporting_event_ids"]:
                st.caption("Evidence event IDs: " + ", ".join(item["supporting_event_ids"]))
        if full_time_view:
            recap = next((item for item in insights if item["type"] == "match_recap"), None)
            if recap:
                st.divider()
                st.markdown("### Final recap")
                st.write(recap["explanation"])
                st.caption("Generated from the completed event history and final supported event metrics.")
                st.json(recap["metrics"])
                goals = [event for event in visible_events if event["event_type"] == "goal"]
                st.markdown("**Recorded goals**")
                for event in goals:
                    st.write(f"{_format_match_time(int(event['minute']) * 60 + int(event['second']))} · {event['player']} ({event['team']})")
        elif latest >= MATCH_DURATION_SECONDS:
            st.info("The final recap is hidden while viewing a historical point before full time.")
        else:
            st.info("The final recap becomes available only after the simulation reaches full time.")

    _save_match_state(match_id)


def _set_page(page: str) -> None:
    st.session_state["touchline_iq_page"] = page


def _top_navigation() -> None:
    columns = st.columns([1, 1, 1, 1])
    for column, label, target in zip(
        columns, ("Home", "Live Matches", "Highlight Matches"),
        ("home", "live", "highlights"),
    ):
        with column:
            if st.button(label, key=f"nav-{target}", use_container_width=True):
                _set_page(target)
                st.rerun()


def _fixture_stats(match: Mapping[str, Any]) -> dict[str, Any]:
    return calculate_match_metrics(match["events"])


def _fixture_score(match: Mapping[str, Any]) -> str:
    home, away = match["teams"]
    score = match.get("final_score") or {}
    return f"{score.get(home, 0)}–{score.get(away, 0)}"


def _fixture_summary(match: Mapping[str, Any]) -> str:
    metrics = _fixture_stats(match)
    home, away = match["teams"]
    team_metrics = metrics["teams"]
    home_goals = team_metrics.get(home, {}).get("goals", 0)
    away_goals = team_metrics.get(away, {}).get("goals", 0)
    goal_events = [event for event in match["events"] if event["event_type"] == "goal"]
    total_goals = home_goals + away_goals
    if not goal_events:
        lead = "No goals were recorded. "
    else:
        first = goal_events[0]
        winner = home if home_goals > away_goals else away if away_goals > home_goals else None
        last = goal_events[-1]
        last_minute = int(last["minute"])
        if winner and first["team"] != winner:
            lead = f"{winner} came from behind to win {home_goals}–{away_goals}. "
        elif winner and last["team"] == winner and last_minute >= 80:
            lead = f"{winner} recorded a late winning goal at {last_minute}′. "
        elif total_goals >= 4:
            lead = f"A high-scoring match with {total_goals} recorded goals. "
        elif winner:
            lead = f"{winner} won {home_goals}–{away_goals}. "
        else:
            lead = f"The match finished level at {home_goals}–{away_goals}. "
    return (f"{lead}{metrics['shots']} shots, {metrics['recoveries']} recoveries, "
            f"and {metrics['turnovers']} turnovers are recorded in the event history.")


def _score_at_events(events: list[Mapping[str, Any]], teams: tuple[str, str]) -> dict[str, dict[str, int]]:
    score = {team: 0 for team in teams}
    result: dict[str, dict[str, int]] = {}
    for event in events:
        if event.get("event_type") == "goal" and event.get("team") in score:
            score[str(event["team"])] += 1
        result[str(event.get("event_id"))] = dict(score)
    return result


def _highlight_groups(match: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build completed-match moments only from this fixture's event history."""
    events = list(match["events"])
    teams = tuple(match["teams"])
    match_id = str(match["id"])
    insights = generate_match_insights(events, match_id, complete=True)
    scores = _score_at_events(events, teams)
    groups: dict[str, list[dict[str, Any]]] = {
        "Goals": [], "Attacking Moments": [], "Defensive Moments": [], "Tactical Insights": [],
    }

    def add(category: str, title: str, explanation: str, support: list[str], anchor_id: str,
            strength: str | None = None) -> None:
        anchor = next((event for event in events if event["event_id"] == anchor_id), None)
        if anchor is None:
            return
        groups[category].append({
            "category": category,
            "time": int(anchor["minute"]) * 60 + int(anchor["second"]),
            "timestamp": _format_match_time(int(anchor["minute"]) * 60 + int(anchor["second"])),
            "title": title,
            "explanation": explanation,
            "supporting_event_ids": support,
            "score": scores.get(anchor_id, {team: 0 for team in teams}),
            "strength": strength,
            "details": [event for event in events if event["event_id"] in support],
        })

    for event in events:
        if event["event_type"] == "goal":
            goal_time = int(event["minute"]) * 60 + int(event["second"])
            shot = next((item for item in events if item["event_type"] == "shot"
                         and item["team"] == event["team"] and item["player"] == event["player"]
                         and int(item["minute"]) * 60 + int(item["second"]) <= goal_time
                         and goal_time - (int(item["minute"]) * 60 + int(item["second"])) <= 2), None)
            build_up: list[Mapping[str, Any]] = []
            if shot:
                shot_time = int(shot["minute"]) * 60 + int(shot["second"])
                build_up = [item for item in events if item["event_type"] == "pass"
                            and item["team"] == event["team"] and item["outcome"] == "successful"
                            and 0 <= shot_time - (int(item["minute"]) * 60 + int(item["second"])) <= 90]
                build_up = build_up[-2:]
            support = [item["event_id"] for item in build_up]
            if shot:
                support.append(str(shot["event_id"]))
            support.append(str(event["event_id"]))
            explanation = ("The event log records completed passes before the shot and explicit goal; sequence timing is shown as evidence, not proof of causation."
                          if build_up and shot else str(event["description"]))
            add("Goals", f"Goal · {event['player']} ({event['team']})", explanation,
                support, event["event_id"], "Recorded events")
        elif event["event_type"] == "shot" and event["outcome"] != "scored":
            add("Attacking Moments", f"Shot attempt · {event['player']} ({event['team']})",
                event["description"], [event["event_id"]], event["event_id"], "Recorded event")

    for insight in insights:
        if insight.get("type") not in {"tactical_pattern", "shot_area"}:
            continue
        support = list(insight.get("supporting_event_ids", []))
        if not support:
            continue
        category = "Tactical Insights"
        if "recovery" in str(insight.get("title", "")).casefold():
            category = "Defensive Moments"
        anchor_id = support[-1]
        # Only distinct multi-event sequences qualify here; single events already
        # appear in their event category and should not be duplicated.
        if len(support) < 2:
            continue
        quality = insight.get("evidence_quality") or {}
        add(category, str(insight.get("title", "Recorded pattern")),
            str(insight.get("explanation", "")), support, anchor_id,
            quality.get("strength"))

    for values in groups.values():
        values.sort(key=lambda item: (item["time"], item["title"]))
    return groups


def _highlight_count(match: Mapping[str, Any]) -> int:
    return sum(len(items) for items in _highlight_groups(match).values())


def _home_page() -> None:
    st.markdown('<div class="hero"><div class="eyebrow">Synthetic football intelligence</div>'
                '<h1 style="margin:.35rem 0">Welcome to Touchline IQ</h1>'
                '<div class="hero-meta">Beyond the Score. Into the Game.</div></div>',
                unsafe_allow_html=True)
    live_col, highlight_col = st.columns(2, gap="large")
    with live_col, st.container(border=True):
        st.markdown("### Live Matches")
        st.write("Follow the action as it unfolds.")
        st.markdown('<span class="badge">2 matches available</span>', unsafe_allow_html=True)
        st.write("")
        if st.button("View Live Matches", type="primary", key="home-live", use_container_width=True):
            _set_page("live")
            st.rerun()
    with highlight_col, st.container(border=True):
        st.markdown("### Highlight Matches")
        st.write("Relive the moments that matter.")
        st.markdown('<span class="badge">10 matches available</span>', unsafe_allow_html=True)
        st.write("")
        if st.button("Explore Highlights", type="primary", key="home-highlights", use_container_width=True):
            _set_page("highlights")
            st.rerun()
    st.caption("All teams, players and match events are fictional synthetic demonstrations.")


def _live_matches_page(live: Mapping[str, Mapping[str, Any]]) -> None:
    st.title("Live Matches")
    st.caption("Fictional live simulations · each match has its own event history and clock.")
    columns = st.columns(2, gap="large")
    for column, fixture in zip(columns, live.values()):
        state = st.session_state.get(_match_state_key(str(fixture["id"])), {"latest": 0, "playing": False})
        latest = int(state.get("latest", 0))
        prefix = events_through_time(fixture["events"], latest)
        score = _scoreline(calculate_match_metrics(prefix), tuple(fixture["teams"]))
        status = "LIVE" if state.get("playing") else "LIVE · PAUSED"
        with column, st.container(border=True):
            st.markdown(f'<span class="badge">● {status}</span>', unsafe_allow_html=True)
            st.markdown(f"### {fixture['teams'][0]}  **{score}**  {fixture['teams'][1]}")
            st.caption(f"{SYNTHETIC_COMPETITION} · {_format_match_time(latest)} · Fictional fixture")
            if st.button("Open Match Centre", key=f"open-live-{fixture['id']}", type="primary", use_container_width=True):
                st.session_state["touchline_iq_current_live_id"] = fixture["id"]
                _restore_match_state(fixture)
                _set_page("live_detail")
                st.rerun()


def _highlights_page(completed: Mapping[str, Mapping[str, Any]]) -> None:
    st.title("Highlight Matches")
    st.caption("Completed synthetic fixtures · moments are derived from recorded event histories.")
    left, right = st.columns([2, 1])
    with left:
        query = st.text_input("Search fictional teams", key="highlight-search").strip().casefold()
    with right:
        filter_name = st.selectbox("Filter", ["All Matches", "High-Scoring Matches", "Close Matches"], key="highlight-filter")
    matches = list(completed.values())
    if filter_name == "High-Scoring Matches":
        matches = [match for match in matches if _fixture_stats(match)["goals"] >= 4]
    elif filter_name == "Close Matches":
        matches = [match for match in matches if abs(
            _fixture_stats(match)["teams"].get(match["teams"][0], {}).get("goals", 0)
            - _fixture_stats(match)["teams"].get(match["teams"][1], {}).get("goals", 0)
        ) <= 1]
    if query:
        matches = [match for match in matches if query in " ".join(match["teams"]).casefold()]
    st.caption("High-scoring: 4+ total goals · Close: goal difference of 1 or less.")
    if not matches:
        st.info("No completed matches match that search and filter.")
        return
    for offset in range(0, len(matches), 2):
        columns = st.columns(2, gap="large")
        for column, match in zip(columns, matches[offset:offset + 2]):
            with column, st.container(border=True):
                st.markdown('<span class="badge">COMPLETED</span>', unsafe_allow_html=True)
                st.markdown(f"### {match['teams'][0]}  **{_fixture_score(match)}**  {match['teams'][1]}")
                st.write(_fixture_summary(match))
                st.caption(f"{_highlight_count(match)} qualifying moments · Synthetic demonstration data")
                if st.button("View Highlights", key=f"open-highlight-{match['id']}", type="primary", use_container_width=True):
                    st.session_state["touchline_iq_selected_highlight_id"] = match["id"]
                    _set_page("highlight_detail")
                    st.rerun()


def _highlight_detail_page(match: Mapping[str, Any]) -> None:
    if st.button("← Back to Highlights", key="back-highlights"):
        _set_page("highlights")
        st.rerun()
    if st.button("⌂ Home", key="highlight-home"):
        _set_page("home")
        st.rerun()
    home, away = match["teams"]
    events = list(match["events"])
    match_id = str(match["id"])
    rosters = match["rosters"]
    metrics = calculate_match_metrics(events)
    score = match.get("final_score") or {
        team: metrics["teams"].get(team, {}).get("goals", 0) for team in (home, away)
    }
    st.markdown(f'<div class="hero"><div class="eyebrow">COMPLETED · Synthetic demonstration data</div>'
                f'<div class="scoreline"><div class="score-team">{_safe(home)}</div>'
                f'<div class="score">{score.get(home, 0)} : {score.get(away, 0)}</div>'
                f'<div class="score-team right">{_safe(away)}</div></div>'
                f'<div class="hero-meta" style="text-align:center">{_safe(SYNTHETIC_COMPETITION)}</div></div>',
                unsafe_allow_html=True)
    groups = _highlight_groups(match)
    insights = generate_match_insights(events, match_id, complete=True)
    commentary = generate_match_commentary(
        events, match_id, viewed_match_time=MATCH_DURATION_SECONDS, complete=True,
    )
    overview_tab, highlights_tab, player_stats_tab, commentary_tab = st.tabs(
        ["Overview", "Highlights", "Player Stats", "Commentary"]
    )

    with overview_tab:
        st.markdown("### Match narrative")
        st.write(_fixture_summary(match))
        st.markdown("### Full-match statistics · event-derived")
        metric_cols = st.columns(5)
        for col, (label, key) in zip(metric_cols, [("Goals", "goals"), ("Shots", "shots"), ("Passes", "passes"), ("Recoveries", "recoveries"), ("Turnovers", "turnovers")]):
            col.metric(label, metrics[key])
        st.metric("Pass completion from recorded pass outcomes", _number(metrics["pass_completion_pct"], "%"))
        st.caption("All values use this completed match's full synthetic event history.")
        st.markdown("### Supported insights")
        supported = [item for item in insights if item.get("type") in {"goal_highlight", "tactical_pattern", "shot_area", "match_recap"}]
        if not supported:
            st.info("No additional insights are supported by the recorded events.")
        for item in supported:
            st.markdown(f"**{item['title']}**")
            st.write(item["explanation"])
            st.caption("Supporting event IDs: " + (", ".join(item.get("supporting_event_ids", [])) or "none recorded"))
            quality = item.get("evidence_quality") or {}
            if quality.get("strength"):
                st.caption(f"Evidence strength: {quality['strength']} · descriptive, not a probability")

    with highlights_tab:
        st.caption("Prioritised completed-match moments · synthetic event evidence")
        for category in ("Goals", "Attacking Moments", "Defensive Moments", "Tactical Insights"):
            st.markdown(f"### {category}")
            items = groups[category]
            if not items:
                st.info(f"No qualifying {category.casefold()} are supported by this match's recorded events.")
                continue
            for index, item in enumerate(items):
                with st.container(border=True):
                    st.markdown(f"**{item['timestamp']} · {item['title']}**")
                    st.write(item["explanation"])
                    st.caption(f"Score at event: {item['score'].get(home, 0)}–{item['score'].get(away, 0)} · Evidence IDs: {', '.join(item['supporting_event_ids'])}")
                    if item.get("strength"):
                        st.caption(f"Evidence strength: {item['strength']} · descriptive, not a probability")
                    with st.expander(f"Supporting event details · {category} {index + 1}"):
                        for event in item["details"]:
                            st.write(f"{_format_match_time(int(event['minute']) * 60 + int(event['second']))} · {event['team']} · {event['player']} · {event['event_type'].title()} · {event['description']}")

    with player_stats_tab:
        st.caption("Full-match player event counts · no ratings or physical tracking values are inferred.")
        player_stats = calculate_player_stats(events)
        all_players = sorted({player for roster in rosters.values() for player in roster})
        selected_player = st.selectbox("Select a player", all_players, key=f"completed-player-{match_id}")
        selected_stats = player_stats.get(selected_player, {})
        st.caption(f"Team: {selected_stats.get('team', next((team for team, roster in rosters.items() if selected_player in roster), 'Unavailable'))}")
        player_cols = st.columns(4)
        player_specs = [
            ("Goals", selected_stats.get("goals", 0)),
            ("Shots", selected_stats.get("shots", 0)),
            ("Pass attempts", selected_stats.get("pass_attempts", 0)),
            ("Successful passes", selected_stats.get("successful_passes", 0)),
            ("Pass completion", _number(selected_stats.get("pass_completion_pct"), "%")),
            ("Recoveries", selected_stats.get("recoveries", 0)),
            ("Turnovers", selected_stats.get("turnovers", 0)),
        ]
        for column, (label, value) in zip(player_cols * 2, player_specs):
            column.metric(label, value)
        contributions = [event for event in events if event["player"] == selected_player]
        if contributions:
            st.markdown("**Recorded contributions across the completed match**")
            st.dataframe(_timeline_frame(contributions), hide_index=True, width="stretch")
        else:
            st.info("No events are attributed to this player in the completed match.")

    with commentary_tab:
        st.caption("Deterministic commentary generated from this completed match's event history.")
        if not commentary:
            st.info("No commentary events are available.")
        for item in commentary:
            st.markdown(f"**{item['timestamp']} · {item['type'].replace('_', ' ').title()} · {item['score'].get(home, 0)}–{item['score'].get(away, 0)}**")
            st.write(item["text"])
            if item["supporting_event_ids"]:
                st.caption("Evidence event IDs: " + ", ".join(item["supporting_event_ids"]))


def main() -> None:
    _show_brand()
    live, completed = _catalogue()
    page = st.session_state.setdefault("touchline_iq_page", "home")
    _top_navigation()
    if page == "home":
        _home_page()
    elif page == "live":
        _live_matches_page(live)
    elif page == "live_detail":
        match_id = st.session_state.get("touchline_iq_current_live_id")
        match = live.get(match_id)
        if match is None:
            _set_page("live")
            st.rerun()
        if st.button("← Back to Matches", key="match-centre-back"):
            _save_match_state(str(match["id"]))
            state = st.session_state[_match_state_key(str(match["id"]))]
            state["playing"] = False
            state["next_tick"] = None
            _set_page("live")
            st.rerun()
        if st.button("⌂ Home", key="live-home"):
            _save_match_state(str(match["id"]))
            state = st.session_state[_match_state_key(str(match["id"]))]
            state["playing"] = False
            state["next_tick"] = None
            _set_page("home")
            st.rerun()
        st.markdown('<div class="section-kicker">LIVE MATCH CENTRE · SYNTHETIC DEMO</div>', unsafe_allow_html=True)
        _restore_match_state(match)
        _show_match_centre(match["events"], str(match["id"]), tuple(match["teams"]), match["rosters"])
    elif page == "highlights":
        _highlights_page(completed)
    elif page == "highlight_detail":
        match = completed.get(st.session_state.get("touchline_iq_selected_highlight_id"))
        if match is None:
            _set_page("highlights")
            st.rerun()
        _highlight_detail_page(match)
    else:
        _set_page("home")
        st.rerun()


if __name__ == "__main__":
    main()
