"""Focused offline tests for Touchline IQ's deterministic match assistant."""

from __future__ import annotations

import unittest
from pathlib import Path

from assistant import answer_question, match_scoped_history
from real_data import get_match_by_id, load_real_matches


class AssistantRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matches = load_real_matches(Path(__file__).with_name("real_matches.json"))

    def match(self, match_id: str):
        return get_match_by_id(self.matches, match_id)

    def test_result_and_statistics_from_two_matches(self) -> None:
        barcelona = self.match("laliga-2026-10-25-barcelona-real-madrid")
        villa = self.match("premier-league-2026-10-24-aston-villa-manchester-city")

        result = answer_question(barcelona, "What was the result?")
        possession = answer_question(villa, "Compare possession and expected goals")

        self.assertIn("Barcelona 1–2 Real Madrid", result["answer"])
        self.assertIn("Barcelona", result["evidence"][0])
        self.assertTrue(result["sources"])
        self.assertIn("37%", possession["answer"])
        self.assertIn("1.79", possession["answer"])
        self.assertEqual(possession["category"], "Sourced statistics")
        self.assertTrue(possession["sources"])

    def test_goal_and_substitution_timeline_keep_original_minutes(self) -> None:
        como = self.match("uefa-champions-league-2026-10-21-como-manchester-united")
        goals = answer_question(como, "List the goals and scorers")
        substitutions = answer_question(como, "What substitutions are recorded?")

        self.assertIn("90+1′", goals["answer"])
        self.assertIn("Nico Paz", goals["answer"])
        self.assertIn("Amad Diallo on for Matheus Cunha", substitutions["answer"])
        self.assertTrue(goals["sources"])

    def test_unsupported_tactical_claim_explains_missing_evidence(self) -> None:
        barcelona = self.match("laliga-2026-10-25-barcelona-real-madrid")
        result = answer_question(barcelona, "Did Barcelona's press cause Madrid's turnovers?")

        self.assertEqual(result["category"], "Evidence unavailable")
        self.assertIn("lacks", result["answer"])
        self.assertIn("coordinates", result["answer"])

    def test_manual_observation_is_labelled_unverified(self) -> None:
        villa = self.match("premier-league-2026-10-24-aston-villa-manchester-city")
        result = answer_question(villa, "What did I observe about Cherki?")

        self.assertEqual(result["category"], "User-reported, unverified observation")
        self.assertIn("User-reported observation — unverified", result["answer"])
        self.assertIn("Cherki", result["answer"])
        self.assertEqual(result["sources"], [])

    def test_discrepancies_and_manual_conflicts_are_retrieved(self) -> None:
        villa = self.match("premier-league-2026-10-24-aston-villa-manchester-city")
        result = answer_question(villa, "What discrepancies or conflict notes are recorded?")

        self.assertIn("xg", result["answer"].lower())
        self.assertIn("Manual-observation conflict", result["answer"])

    def test_match_history_is_isolated_when_selection_changes(self) -> None:
        session: dict = {}
        barcelona_history = match_scoped_history(session, "laliga-2026-10-25-barcelona-real-madrid")
        barcelona_history.append({"role": "user", "content": "Barcelona question"})

        villa_history = match_scoped_history(session, "premier-league-2026-10-24-aston-villa-manchester-city")

        self.assertEqual(villa_history, [])
        self.assertEqual(len(match_scoped_history(session, "laliga-2026-10-25-barcelona-real-madrid")), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
