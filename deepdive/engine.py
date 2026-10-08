"""Question-bank loading, answer matching, and practice selection."""

import json
import random
import unicodedata
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STARTER_PACK = ROOT / "data" / "starter_pack.json"
IMPORTS_FOLDER = ROOT / "data" / "imported_packs"


def load_pack(path):
    """Load and validate one JSON question pack."""
    with Path(path).open(encoding="utf-8") as pack_file:
        pack = json.load(pack_file)
    validate_pack(pack)
    return pack


def validate_pack(pack, existing_question_ids=()):
    """Reject incomplete packs instead of quietly loading bad questions."""
    if not isinstance(pack, dict) or not isinstance(pack.get("questions"), list):
        raise ValueError("A question pack must contain a 'questions' list.")
    if not pack["questions"]:
        raise ValueError("A question pack must contain at least one question.")

    seen_ids = set(existing_question_ids)
    for question in pack["questions"]:
        required = ("id", "category", "subcategory", "prompt", "rule", "answers")
        if not isinstance(question, dict) or any(not question.get(key) for key in required):
            raise ValueError("Every question needs an id, category, subcategory, prompt, rule, and answers.")
        if question["id"] in seen_ids:
            raise ValueError(f"Duplicate question id across loaded packs: {question['id']}")
        seen_ids.add(question["id"])
        if not isinstance(question["answers"], list) or not question["answers"]:
            raise ValueError(f"Question {question['id']} needs accepted answers.")
        answer_names = set()
        for answer in question["answers"]:
            if not all(answer.get(key) for key in ("name", "explanation", "fact")) or "aliases" not in answer:
                raise ValueError(f"Every answer in {question['id']} needs a name, aliases, fact, and explanation.")
            if not isinstance(answer["aliases"], list):
                raise ValueError(f"Aliases in {question['id']} must be a list.")
            normalized = normalize_answer(answer["name"])
            if normalized in answer_names:
                raise ValueError(f"Duplicate accepted answer in {question['id']}: {answer['name']}")
            answer_names.add(normalized)


def normalize_answer(answer):
    """Make matching tolerant of accents, case, and punctuation."""
    text = unicodedata.normalize("NFKD", str(answer).strip().casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return "".join(character for character in text if character.isalnum())


def match_answer(question, submitted):
    """Return the matched entry, or None when this pack cannot verify it."""
    normalized = normalize_answer(submitted)
    if not normalized:
        return None
    for answer in question["answers"]:
        accepted_names = [answer["name"], *answer["aliases"]]
        if any(normalize_answer(name) == normalized for name in accepted_names):
            return answer
    return None


def all_facts(questions):
    """Flatten answer facts so Discover and Smart Review share the same data."""
    facts = []
    for question in questions:
        for index, answer in enumerate(question["answers"]):
            facts.append(
                {
                    **answer,
                    "fact_id": f"{question['id']}:{index}",
                    "question_id": question["id"],
                    "category": question["category"],
                    "subcategory": question["subcategory"],
                    "recall_question": question["prompt"],
                    "rule": question["rule"],
                }
            )
    return facts


def choose_question(questions, recent_ids=(), weak_categories=(), due_question_ids=()):
    """Choose a due/weak-topic question while avoiding immediate repeats."""
    available = [item for item in questions if item["id"] not in recent_ids]
    if not available:
        available = list(questions)
    due = [item for item in available if item["id"] in due_question_ids]
    if due:
        available = due
    weak = [item for item in available if item["category"] in weak_categories]
    if weak and random.random() < 0.7:
        available = weak
    return random.choice(available)


def estimate_points(question, accepted_answer):
    """Award practice points using pack difficulty, never a claimed rarity score."""
    rating = max(1, min(5, int(accepted_answer.get("obscurity", 1))))
    return 10 + rating * 2


def seconds_remaining(started_at, duration=25, now=None):
    """Return whole seconds left for a timed question."""
    current_time = time.time() if now is None else now
    return max(0, duration - int(current_time - started_at))


def save_imported_pack(uploaded_bytes, filename, existing_question_ids=()):
    """Validate and save a user-supplied JSON pack in the local import folder."""
    try:
        pack = json.loads(uploaded_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The uploaded file must be valid UTF-8 JSON.") from error
    validate_pack(pack, existing_question_ids)
    IMPORTS_FOLDER.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).stem.replace(" ", "_")
    if not safe_name or safe_name in (".", ".."):
        raise ValueError("Choose a filename for the question pack.")
    destination = IMPORTS_FOLDER / f"{safe_name}.json"
    if destination.exists():
        raise ValueError(f"A pack named {destination.name} already exists. Choose a different filename.")
    destination.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination
