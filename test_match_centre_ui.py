"""Streamlit interaction checks for Touchline IQ's match library navigation."""

from __future__ import annotations

import time
import unittest
from pathlib import Path

from analytics import calculate_match_metrics, calculate_player_stats, events_through_time, generate_match_insights

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Streamlit AppTest is unavailable in this interpreter")
class MatchCentreUITests(unittest.TestCase):
    app_path = Path(__file__).with_name("app.py")

    def test_landing_routes_to_exactly_two_live_matches(self) -> None:
        app = AppTest.from_file(str(self.app_path)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Welcome to Touchline IQ" in item.value for item in app.markdown))
        app.button(key="home-live").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len([button for button in app.button if button.label == "Open Match Centre"]), 2)

    def test_two_live_matches_keep_independent_events_and_clock(self) -> None:
        app = AppTest.from_file(str(self.app_path)).run()
        app.button(key="home-live").click().run()
        app.button(key="open-live-live-northbridge-harbour").click().run()
        self.assertEqual([tab.label for tab in app.tabs], ["Overview", "Highlights", "Player Stats", "Commentary"])
        self.assertIn("match-centre-player-select-live-northbridge-harbour", [item.key for item in app.selectbox])
        first_key = "touchline_iq_playback_live-northbridge-harbour"
        first_events = app.session_state["touchline_iq_fixture_catalogue_v1"][0]["live-northbridge-harbour"]["events"]
        app.button(key="match-play").click().run()
        time.sleep(1.05)
        app.run()
        app.button(key="match-pause").click().run()
        first_time = app.session_state[first_key]["latest"]
        self.assertGreater(first_time, 0)
        self.assertLessEqual(app.slider[0].max, first_time)
        historical = max(0, first_time - 30)
        app.slider[0].set_value(historical).run()
        self.assertEqual(app.session_state["viewed_match_time"], historical)
        self.assertTrue(any("Goal markers visible at this historical point: none" in item.value for item in app.caption))
        future_ids = {event["event_id"] for event in first_events
                      if event["minute"] * 60 + event["second"] > historical}
        rendered = " ".join(item.value for item in (*app.markdown, *app.caption))
        self.assertFalse(any(event_id in rendered for event_id in future_ids))
        live_goal_metrics = [item for item in app.metric if item.label == "Goals"]
        expected_live_goals = calculate_match_metrics(events_through_time(first_events, historical))["goals"]
        self.assertEqual(int(live_goal_metrics[0].value), expected_live_goals)
        app.button(key="match-jump-latest").click().run()
        self.assertEqual(app.session_state["viewed_match_time"], first_time)

        app.button(key="match-centre-back").click().run()
        app.button(key="open-live-live-ashford-riverside").click().run()
        second_key = "touchline_iq_playback_live-ashford-riverside"
        second_events = app.session_state["touchline_iq_fixture_catalogue_v1"][0]["live-ashford-riverside"]["events"]
        self.assertNotEqual([e["event_id"] for e in first_events], [e["event_id"] for e in second_events])
        self.assertEqual(app.session_state[second_key]["latest"], 0)
        self.assertNotEqual(first_key, second_key)
        self.assertTrue(any("Ashford Athletic" in item.value for item in app.markdown))

    def test_highlight_library_has_ten_and_detail_has_no_playback_controls(self) -> None:
        app = AppTest.from_file(str(self.app_path)).run()
        app.button(key="home-highlights").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 10)
        self.assertFalse(app.slider)
        app.button(key="open-highlight-completed-01").click().run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Overview", "Highlights", "Player Stats", "Commentary"])
        self.assertIn("completed-player-completed-01", [item.key for item in app.selectbox])
        self.assertFalse(app.slider)
        labels = [button.label for button in app.button]
        self.assertFalse(any(label in {"▶ Play", "⏸ Pause", "Jump to Latest"} for label in labels))
        rendered = " ".join(item.value for item in app.markdown)
        for category in ("Goals", "Attacking Moments", "Defensive Moments", "Tactical Insights"):
            self.assertIn(category, rendered)
        self.assertTrue(any("completed match's event history" in item.value for item in app.caption))
        completed = app.session_state["touchline_iq_fixture_catalogue_v1"][1]["completed-01"]
        selected_player = app.selectbox(key="completed-player-completed-01").value
        expected_player_stats = calculate_player_stats(completed["events"])[selected_player]
        player_goal_metrics = [item for item in app.metric if item.label == "Goals"]
        self.assertEqual(int(player_goal_metrics[-1].value), expected_player_stats["goals"])
        goal_ids = [event["event_id"] for event in completed["events"] if event["event_type"] == "goal"]
        commentary_evidence = " ".join(item.value for item in app.caption)
        self.assertTrue(all(goal_id in commentary_evidence for goal_id in goal_ids))

    def test_highlight_search_and_filters_use_the_existing_library(self) -> None:
        app = AppTest.from_file(str(self.app_path)).run()
        app.button(key="home-highlights").click().run()
        app.text_input(key="highlight-search").set_value("Ashford").run()
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 1)
        app.selectbox(key="highlight-filter").select("High-Scoring Matches").run()
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 0)
        app.text_input(key="highlight-search").set_value("").run()
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 3)
        app.selectbox(key="highlight-filter").select("Close Matches").run()
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 8)
        app.selectbox(key="highlight-filter").select("All Matches").run()
        self.assertEqual(len([button for button in app.button if button.label == "View Highlights"]), 10)

    def test_completed_histories_are_unique_deterministic_and_score_consistent(self) -> None:
        app = AppTest.from_file(str(self.app_path)).run()
        import app as touchline_app

        live, completed = app.session_state["touchline_iq_fixture_catalogue_v1"]
        self.assertEqual(len(live), 2)
        self.assertEqual(len(completed), 10)
        self.assertEqual(len({match["id"] for match in completed.values()}), 10)
        for fixture in touchline_app.HIGHLIGHT_FIXTURES:
            regenerated, teams, _ = touchline_app._completed_fixture_events(fixture)
            cached = completed[fixture[0]]
            self.assertEqual(regenerated, cached["events"])
            self.assertEqual(teams, cached["teams"])

        def signature(match: dict) -> tuple:
            return tuple((event["minute"], event["second"], event["event_type"], event["outcome"],
                          event["start_x"], event["start_y"], event["end_x"], event["end_y"])
                         for event in match["events"])

        completed_signatures = [signature(match) for match in completed.values()]
        live_signatures = [signature(match) for match in live.values()]
        self.assertEqual(len(set(completed_signatures)), 10)
        self.assertFalse(set(completed_signatures) & set(live_signatures))

        first_snapshot = {key: [dict(event) for event in match["events"]]
                          for key, match in completed.items()}
        app.run()
        _, rerun_completed = app.session_state["touchline_iq_fixture_catalogue_v1"]
        self.assertEqual(first_snapshot, {key: match["events"] for key, match in rerun_completed.items()})

        for match in completed.values():
            events = match["events"]
            teams = match["teams"]
            metrics = calculate_match_metrics(events)
            goals = [event for event in events if event["event_type"] == "goal"]
            self.assertEqual(metrics["goals"], len(goals))
            for team in teams:
                expected = sum(event["team"] == team for event in goals)
                self.assertEqual(metrics["teams"].get(team, {}).get("goals", 0), expected)
                self.assertEqual(match["final_score"][team], expected)
            for goal in goals:
                self.assertTrue(any(
                    event["event_type"] == "shot" and event["team"] == goal["team"]
                    and event["player"] == goal["player"] and event["outcome"] == "scored"
                    and 0 <= (goal["minute"] * 60 + goal["second"])
                    - (event["minute"] * 60 + event["second"]) <= 2
                    for event in events
                ))
            event_ids = {event["event_id"] for event in events}
            insights = generate_match_insights(events, match["id"], complete=True)
            self.assertTrue(all(set(item["supporting_event_ids"]) <= event_ids for item in insights))
            groups = touchline_app._highlight_groups(match)
            self.assertTrue(all(
                set(item["supporting_event_ids"]) <= event_ids
                for group in groups.values() for item in group
            ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
