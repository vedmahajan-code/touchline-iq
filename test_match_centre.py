"""Historical reconstruction tests for the fictional match centre."""

from __future__ import annotations

import unittest

from analytics import (
    MATCH_DURATION_SECONDS,
    calculate_match_metrics,
    calculate_player_stats,
    clamp_viewed_match_time,
    events_through_time,
    generate_match_commentary,
    generate_match_insights,
)
from match_data import (
    SYNTHETIC_MATCH_ID,
    SYNTHETIC_PLAYERS,
    SYNTHETIC_TEAMS,
    generate_synthetic_match,
)


class MatchCentreHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.events = generate_synthetic_match(seed=42)

    def test_deterministic_fictional_identities_and_chronological_history(self) -> None:
        self.assertEqual(self.events, generate_synthetic_match(seed=42))
        self.assertEqual(len(SYNTHETIC_TEAMS), 2)
        known_players = {player for roster in SYNTHETIC_PLAYERS.values() for player in roster}
        self.assertTrue(all(event["team"] in SYNTHETIC_TEAMS for event in self.events))
        self.assertTrue(all(event["player"] in known_players for event in self.events))
        times = [(event["minute"], event["second"], event["event_id"]) for event in self.events]
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(event["source"] == "synthetic" for event in self.events))
        passes = [event for event in self.events if event["event_type"] == "pass"]
        self.assertTrue(any(event["outcome"] == "successful" for event in passes))
        self.assertTrue(any(event["outcome"] == "unsuccessful" for event in passes))
        final_metrics = calculate_match_metrics(self.events)
        self.assertEqual(final_metrics["teams"][SYNTHETIC_TEAMS[0]]["goals"], 2)
        self.assertEqual(final_metrics["teams"][SYNTHETIC_TEAMS[1]]["goals"], 1)

    def test_historical_score_and_team_metrics_use_only_visible_events(self) -> None:
        goal_time = 18 * 60 + 45
        before_goal = events_through_time(self.events, goal_time - 1)
        at_goal = events_through_time(self.events, goal_time)
        before_metrics = calculate_match_metrics(before_goal)
        at_metrics = calculate_match_metrics(at_goal)
        self.assertEqual(before_metrics["goals"], 0)
        self.assertEqual(at_metrics["goals"], 1)
        self.assertEqual(at_metrics["teams"][SYNTHETIC_TEAMS[0]]["goals"], 1)
        self.assertEqual(at_metrics["shots"], sum(event["event_type"] == "shot" for event in at_goal))
        self.assertTrue(all(event["minute"] * 60 + event["second"] <= goal_time for event in at_goal))
        historical_insights = generate_match_insights(before_goal, SYNTHETIC_MATCH_ID, complete=False)
        visible_ids = {event["event_id"] for event in before_goal}
        self.assertTrue(all(
            set(insight["supporting_event_ids"]).issubset(visible_ids)
            for insight in historical_insights
        ))
        self.assertFalse(any(insight["type"] == "goal_highlight" for insight in historical_insights))

    def test_player_stats_are_time_filtered_and_missing_pass_rate_stays_unavailable(self) -> None:
        goal_time = 18 * 60 + 45
        earlier_stats = calculate_player_stats(events_through_time(self.events, goal_time - 1))
        at_goal_stats = calculate_player_stats(events_through_time(self.events, goal_time))
        self.assertEqual(earlier_stats.get("A. Cole", {}).get("goals", 0), 0)
        self.assertEqual(at_goal_stats["A. Cole"]["goals"], 1)
        self.assertEqual(at_goal_stats["A. Cole"]["shots"], 1)
        self.assertIsNone(calculate_player_stats([]).get("A. Cole", {}).get("pass_completion_pct"))

    def test_time_clamp_never_allows_viewing_beyond_latest(self) -> None:
        self.assertEqual(clamp_viewed_match_time(500, 240), 240)
        self.assertEqual(clamp_viewed_match_time(-5, 240), 0)
        self.assertEqual(clamp_viewed_match_time(9000, 9000), MATCH_DURATION_SECONDS)

    def test_commentary_is_time_scoped_and_score_is_correct_at_goal(self) -> None:
        goal_time = 18 * 60 + 45
        earlier = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID, viewed_match_time=goal_time - 1
        )
        self.assertFalse(any(item["type"] == "goal" for item in earlier))
        at_goal = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID, viewed_match_time=goal_time
        )
        goal_line = next(item for item in at_goal if item["type"] == "goal")
        self.assertEqual(goal_line["timestamp"], "18:45")
        self.assertEqual(goal_line["score"][SYNTHETIC_TEAMS[0]], 1)
        self.assertEqual(goal_line["score"][SYNTHETIC_TEAMS[1]], 0)
        self.assertTrue(all(item["match_seconds"] <= goal_time for item in at_goal))
        self.assertTrue(any(item["type"] == "attacking_sequence" for item in at_goal))
        self.assertTrue(any(item["type"] == "defensive_sequence" for item in at_goal))

    def test_half_time_full_time_and_recap_gates(self) -> None:
        before_half = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID, viewed_match_time=44 * 60
        )
        at_half = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID, viewed_match_time=45 * 60
        )
        self.assertFalse(any(item["type"] == "half_time" for item in before_half))
        self.assertTrue(any(item["type"] == "half_time" for item in at_half))

        before_full = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID,
            viewed_match_time=MATCH_DURATION_SECONDS - 1, complete=True,
        )
        at_full = generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID,
            viewed_match_time=MATCH_DURATION_SECONDS, complete=True,
        )
        self.assertFalse(any(item["type"] == "full_time" for item in before_full))
        self.assertTrue(any(item["type"] == "full_time" for item in at_full))
        self.assertFalse(any(item["type"] == "full_time" for item in generate_match_commentary(
            self.events, SYNTHETIC_MATCH_ID,
            viewed_match_time=MATCH_DURATION_SECONDS, complete=False,
        )))

        historical_insights = generate_match_insights(
            events_through_time(self.events, MATCH_DURATION_SECONDS), SYNTHETIC_MATCH_ID, complete=False
        )
        final_insights = generate_match_insights(self.events, SYNTHETIC_MATCH_ID, complete=True)
        self.assertFalse(any(item["type"] == "match_recap" for item in historical_insights))
        self.assertTrue(any(item["type"] == "match_recap" for item in final_insights))


if __name__ == "__main__":
    unittest.main(verbosity=2)
