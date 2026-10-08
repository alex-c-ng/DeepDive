# DeepDive Trainer

DeepDive Trainer is a local trivia practice app built with Python, Streamlit, JSON, and SQLite. It is designed for short daily recall sessions, with an ocean-depth theme and no login or paid API.

## Run it

Use Python 3.10 or newer. In the VS Code terminal, from this project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

Then open the local address Streamlit prints (usually `http://localhost:8501`). On Windows, if PowerShell blocks environment activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal and activate again. You can also install packages with `py -m pip install -r requirements.txt` without activating the environment.

Run the automated checks with:

```powershell
py -m unittest discover -s tests -v
```

## Modes

- **Discover:** browse facts, open their references, then mark each as known or due for review.
- **Recall:** answer a prompt in your own words and see accepted examples, explanations, and source links.
- **Speed Dive:** answer seven questions with optional 25-second turns. Practice points combine correctness with this pack's 1–5 obscurity estimate. They are not Krillion scores or live rarity data.
- **Smart Review:** see local streak, accuracy, question count, mastered facts, and missed facts that are due. Review intervals grow for facts marked known and reset to one day when studied again.

## Project map

```text
app.py                    Streamlit pages, forms, navigation, and simple styling
deepdive/engine.py        JSON validation, matching, fact lists, question selection
deepdive/storage.py       SQLite setup, answer history, streaks, and review dates
data/starter_pack.json    Offline questions and their accepted answers/facts
data/imported_packs/      Locally imported JSON packs (created on first import)
data/progress.db          Local learning data (created when the app first runs)
tests/                    Focused matching and persistence tests
```

Question content stays in JSON. Each question declares its answer rule and has answer entries with aliases, a fact, an explanation, a source URL, and an approximate obscurity rating. SQLite stores your practice responses and review dates, not the bank.

The starter pack contains more than 150 fact cards. Accepted answers are curated and finite: an answer not in the offline pack is shown as **not verified**, not declared universally wrong. A prompt's accepted list is not a claim that it is exhaustive. Where possible, each fact links to an encyclopedia, official organization, or relevant reference page. Check the linked source before relying on a fact in a high-stakes context.

To add content, use **Import a question pack** in the sidebar. Imported packs must follow the example schema in the app and use question IDs unique across all packs. Files are saved locally under `data/imported_packs/`; they are loaded at the next app start.

## Five Python concepts to notice

1. **Modules and imports:** `app.py`, `deepdive/engine.py`, and `deepdive/storage.py` split responsibilities. `from deepdive.engine import ...` makes reusable functions available to the interface.
2. **Lists and dictionaries:** JSON becomes Python lists and dictionaries. A question dictionary has keys such as `prompt` and `answers`; a list stores multiple questions or accepted answers.
3. **Functions and parameters:** functions such as `match_answer(question, submitted)` name a job, accept the information it needs, and return a result. This makes the logic testable without opening the app.
4. **Loops and conditionals:** `for` loops visit each question or accepted answer, while `if` statements choose a matching answer, a due review, or a feedback message.
5. **Persistence with SQLite:** rows in the `responses` and `fact_reviews` tables survive app restarts. Parameterized SQL (`?`) safely inserts values without building SQL by joining strings.

## Notes and limitations

- Matching ignores capitalization, accents, and punctuation, and checks the explicit aliases. It does not use fuzzy matching, an LLM, or an online answer service.
- The starter bank is a growing offline collection, not an infinite source of unique trivia. Add validated JSON packs to expand it.
- Obscurity ratings are editorial practice hints, not measured answer rarity. Speed points are for practice only.
- SQLite data and imports are local to this folder. Back up `data/progress.db` and `data/imported_packs/` if you want to preserve them.
