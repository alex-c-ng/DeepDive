import json
import tempfile
import unittest
from pathlib import Path

from deepdive.engine import (
    STARTER_PACK,
    all_facts,
    estimate_points,
    load_pack,
    match_answer,
    normalize_answer,
    seconds_remaining,
    validate_pack,
)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = load_pack(STARTER_PACK)
        cls.questions = cls.pack["questions"]

    def test_starter_pack_has_at_least_150_facts(self):
        self.assertGreaterEqual(len(all_facts(self.questions)), 150)

    def test_matching_ignores_case_accents_and_punctuation(self):
        question = next(item for item in self.questions if item["id"] == "world-islands")
        self.assertEqual(match_answer(question, "  SARDÉGNA! ")["name"], "Sardinia")
        self.assertEqual(normalize_answer("São Tomé"), "saotome")

    def test_known_alias_is_accepted(self):
        question = next(item for item in self.questions if item["id"] == "african-countries")
        self.assertEqual(match_answer(question, "SWAZILAND")["name"], "Eswatini")

    def test_unverified_answer_is_not_called_correct(self):
        question = next(item for item in self.questions if item["id"] == "african-countries")
        self.assertIsNone(match_answer(question, "Atlantis"))

    def test_obscurity_points_are_bounded_practice_points(self):
        self.assertEqual(estimate_points({}, {"obscurity": 5}), 20)
        self.assertEqual(estimate_points({}, {"obscurity": 1}), 12)

    def test_timer_counts_down_and_stops_at_zero(self):
        self.assertEqual(seconds_remaining(100, duration=25, now=108), 17)
        self.assertEqual(seconds_remaining(100, duration=25, now=130), 0)

    def test_invalid_pack_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_pack({"questions": [{"id": "broken"}]})

    def test_imported_pack_cannot_reuse_a_loaded_question_id(self):
        question = self.questions[0]
        pack = {"questions": [question]}
        with self.assertRaisesRegex(ValueError, "Duplicate question id"):
            validate_pack(pack, {question["id"]})


if __name__ == "__main__":
    unittest.main()
