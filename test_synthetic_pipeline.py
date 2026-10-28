"""Focused regression tests for Touchline IQ's progressive synthetic demo."""

from __future__ import annotations

import json
import unittest

from analytics import calculate_match_metrics, generate_match_insights
from match_data import (
    SYNTHETIC_MATCH_ID,
    generate_synthetic_match,
    iter_synthetic_match,
)


class SyntheticPipelineTests(unittest.TestCase):
    def test_v1_generator_is_reproducible_and_iterator_preserves_it(self) -> None:
        first = generate_synthetic_match(seed=42)
        second = generate_synthetic_match(seed=42)
        self.assertEqual(first, second)
        self.assertEqual(first, list(iter_synthetic_match(seed=42)))
        self.assertTrue(all(event["source"] == "synthetic" for event in first))
        self.assertEqual(
            [(event["minute"], event["second"], event["event_id"]) for event in first],
            sorted((event["minute"], event["second"], event["event_id"]) for event in first),
        )

    def test_prefix_metrics_use_only_revealed_events(self) -> None:
        stream = iter_synthetic_match(seed=42)
        prefix = [next(stream) for _ in range(4)]
        metrics = calculate_match_metrics(prefix)
        self.assertEqual(metrics["event_count"], 4)
        self.assertEqual(metrics["goals"], sum(event["event_type"] == "goal" for event in prefix))
        self.assertEqual(metrics["shots"], sum(event["event_type"] == "shot" for event in prefix))

    def test_insights_reference_match_events_and_serialize(self) -> None:
        events = generate_synthetic_match(seed=42)
        event_ids = {event["event_id"] for event in events}
        insights = generate_match_insights(events[:20], SYNTHETIC_MATCH_ID, complete=False)
        self.assertTrue(insights)
        self.assertTrue(all(item["status"] == "provisional" for item in insights))
        for insight in insights:
            self.assertEqual(insight["match_id"], SYNTHETIC_MATCH_ID)
            self.assertLessEqual(set(insight["supporting_event_ids"]), {event["event_id"] for event in events[:20]})
            self.assertEqual(insight["provenance"]["source"], "synthetic")
        self.assertFalse(any(item["type"] == "match_recap" for item in insights))
        json.dumps(insights)

    def test_final_recap_only_appears_for_complete_stream(self) -> None:
        insights = generate_match_insights(generate_synthetic_match(), SYNTHETIC_MATCH_ID, complete=True)
        recap = next(item for item in insights if item["type"] == "match_recap")
        self.assertEqual(recap["status"], "final")
        self.assertTrue(recap["supporting_event_ids"])
        self.assertEqual(recap["metrics"]["goals"], calculate_match_metrics(generate_synthetic_match())["goals"])
        self.assertEqual(generate_match_insights([], SYNTHETIC_MATCH_ID, complete=True), [])

    def test_manual_events_cannot_be_mislabeled_as_synthetic_insights(self) -> None:
        manual_event = dict(generate_synthetic_match()[0], source="manual")
        with self.assertRaisesRegex(ValueError, "synthetic events only"):
            generate_match_insights([manual_event], SYNTHETIC_MATCH_ID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
