import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from deepdive.storage import (
    connect,
    get_due_question_ids,
    get_stats,
    record_response,
    review_fact,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temp_dir.name) / "test.db")
        self.question = {
            "id": "test-question",
            "category": "Science",
            "answers": [{"name": "Example"}, {"name": "Other"}],
        }

    def tearDown(self):
        self.connection.close()
        self.temp_dir.cleanup()

    def test_response_updates_totals_accuracy_and_streak(self):
        today = date(2025, 1, 10)
        record_response(self.connection, self.question, "Example", True, today)
        record_response(self.connection, self.question, "Nope", False, today)
        stats = get_stats(self.connection, today)
        self.assertEqual(stats["questions_completed"], 2)
        self.assertEqual(stats["accuracy"], 50)
        self.assertEqual(stats["streak"], 1)

    def test_study_review_is_due_next_day_and_maps_to_question(self):
        today = date(2025, 1, 10)
        review_fact(self.connection, "test-question:0", "study", today)
        due = get_due_question_ids(self.connection, [self.question], today + timedelta(days=1))
        self.assertIn("test-question", due)

    def test_known_fact_waits_longer_after_repeat_review(self):
        today = date(2025, 1, 10)
        review_fact(self.connection, "test-question:0", "know", today)
        review_fact(self.connection, "test-question:0", "know", today + timedelta(days=2))
        row = self.connection.execute(
            "SELECT due_on, streak FROM fact_reviews WHERE fact_id = 'test-question:0'"
        ).fetchone()
        self.assertEqual(row["streak"], 2)
        self.assertEqual(row["due_on"], "2025-01-16")


if __name__ == "__main__":
    unittest.main()
