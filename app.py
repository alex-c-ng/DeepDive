"""Streamlit interface for the local DeepDive Trainer application."""

import time
from datetime import date

import streamlit as st

from deepdive.engine import (
    IMPORTS_FOLDER,
    STARTER_PACK,
    all_facts,
    choose_question,
    estimate_points,
    load_pack,
    match_answer,
    save_imported_pack,
    seconds_remaining,
)
from deepdive.storage import (
    connect,
    get_due_question_ids,
    get_review_statuses,
    get_stats,
    review_fact,
    record_response,
    weak_categories,
)


st.set_page_config(page_title="DeepDive Trainer", page_icon="🌊", layout="centered")

st.markdown(
    """
    <style>
    .stApp { background: radial-gradient(ellipse at top, #103348 0%, #081923 45%, #06121a 100%); color: #e7f1f5; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    [data-testid="stSidebar"] { background: #0b202c; }
    h1, h2, h3 { color: #e9f7fb; }
    .eyebrow { color: #6ed6c4; text-transform: uppercase; letter-spacing: .13em; font-size: .76rem; font-weight: 700; }
    .fact-card { padding: 1.2rem 1.35rem; margin: .6rem 0 1rem; background: linear-gradient(145deg, #123447, #102936); border: 1px solid #286177; border-radius: 16px; }
    .fact-text { color: #f3fbfd; font-size: 1.3rem; line-height: 1.5; font-weight: 650; }
    .subtle { color: #a8c0ca; }
    [data-testid="stMetric"] { background: #102a37; padding: .8rem; border: 1px solid #204858; border-radius: 12px; }
    div.stButton > button[kind="primary"] { background: #087f83; border-color: #39b8a8; }
    @media (max-width: 640px) { .fact-text { font-size: 1.12rem; } section.main > div { padding-left: 1rem; padding-right: 1rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_questions():
    """Load the starter data and each validated local import pack."""
    questions = list(load_pack(STARTER_PACK)["questions"])
    if IMPORTS_FOLDER.exists():
        for pack_path in sorted(IMPORTS_FOLDER.glob("*.json")):
            questions.extend(load_pack(pack_path)["questions"])
    ids = [question["id"] for question in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Question IDs must be unique across the starter pack and imported packs.")
    return questions


questions = load_questions()
facts = all_facts(questions)
facts_by_id = {fact["fact_id"]: fact for fact in facts}
database = connect()


def next_question(state_key, questions_to_use=questions):
    """Pick a fresh question and remember recent IDs for this play mode."""
    recent = st.session_state.get(f"{state_key}_recent", [])
    selected = choose_question(
        questions_to_use,
        recent_ids=recent[-8:],
        weak_categories=weak_categories(database),
        due_question_ids=get_due_question_ids(database, questions),
    )
    st.session_state[f"{state_key}_recent"] = [*recent, selected["id"]][-12:]
    return selected


def save_attempt(question, submitted, matched):
    """Save an answer and send missed answer facts to spaced review."""
    record_response(database, question, submitted, bool(matched))
    if matched:
        index = question["answers"].index(matched)
        review_fact(database, f"{question['id']}:{index}", "know")
    else:
        for index, _answer in enumerate(question["answers"]):
            review_fact(database, f"{question['id']}:{index}", "study")


def show_feedback(question, submitted, matched, heading="Answer"):
    """Explain the result and reveal several harder valid answers."""
    if matched:
        st.success(f"Correct: **{matched['name']}**")
        st.write(matched["explanation"])
    else:
        st.warning("Not verified in this pack. That does not prove your answer is invalid; it may not be in the offline accepted-answer list.")
        st.caption("Accepted answers below are examples from this pack, not an exhaustive list of every possible correct answer.")
    st.markdown(f"**{heading}: other valid answers to learn**")
    less_obvious = sorted(question["answers"], key=lambda item: item.get("obscurity", 1), reverse=True)
    shown = [item for item in less_obvious if not matched or item["name"] != matched["name"]][:4]
    for answer in shown:
        st.markdown(f"- **{answer['name']}** — {answer['explanation']}")
    if matched and matched.get("source_url"):
        st.markdown(f"[Source]({matched['source_url']})")


def reset_speed_dive():
    """Start a fresh seven-question run."""
    st.session_state["dive_number"] = 0
    st.session_state["dive_correct"] = 0
    st.session_state["dive_points"] = 0
    st.session_state["dive_results"] = []
    st.session_state["dive_recent"] = []
    st.session_state["dive_result"] = None
    st.session_state["dive_started_at"] = time.time()
    st.session_state["dive_timed_out"] = False
    st.session_state["dive_timer_was_enabled"] = False
    st.session_state["dive_question"] = next_question("dive")
    st.session_state["dive_active"] = True


def render_speed_timer():
    """Refresh only the timer display; timeout records a missed attempt once."""
    if not st.session_state.get("dive_active"):
        return
    remaining = seconds_remaining(st.session_state["dive_started_at"])
    st.progress(remaining / 25, text=f"Time left: {remaining} seconds")
    if remaining == 0 and not st.session_state.get("dive_result"):
        question = st.session_state["dive_question"]
        save_attempt(question, "", None)
        st.session_state["dive_result"] = {"submitted": "", "matched": None, "timed_out": True}
        st.session_state["dive_results"].append(
            {"question": question, "answer": "", "correct": False, "matched": None, "points": 0}
        )
        st.session_state["dive_number"] += 1
        st.session_state["dive_timed_out"] = True
        st.rerun(scope="app")


def render_discover():
    """Browse a rotating stack of fact cards and schedule each one."""
    st.title("Discover")
    st.write("Collect a few surprising facts, then turn the ones you miss into future recall practice.")
    review_states = get_review_statuses(database)
    due_ids = {key for key, value in review_states.items() if value["due_on"] <= date.today().isoformat()}
    category_options = ["All categories", *sorted({fact["category"] for fact in facts})]
    selected_category = st.selectbox("Category", category_options)
    candidates = [
        fact for fact in facts
        if selected_category == "All categories" or fact["category"] == selected_category
    ]
    candidates.sort(key=lambda fact: (fact["fact_id"] not in due_ids, fact["fact_id"] in review_states))
    if not candidates:
        st.info("No facts in this category yet.")
        return
    position_key = f"discover_position_{selected_category}"
    index = st.session_state.get(position_key, 0) % len(candidates)
    fact = candidates[index]
    st.markdown(f'<div class="eyebrow">{fact["category"]} · {fact["subcategory"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="fact-card"><div class="fact-text">{fact["fact"]}</div></div>', unsafe_allow_html=True)
    st.write(fact["explanation"])
    st.markdown(f"**Recall prompt:** {fact['recall_question']}")
    status = review_states.get(fact["fact_id"])
    if status:
        st.caption(f"Review status: {status['status']} · next due {status['due_on']}")
    source = fact.get("source_url")
    if source:
        st.markdown(f"[Read the source]({source})")

    col1, col2 = st.columns(2)
    if col1.button("✓  Know it", type="primary", use_container_width=True):
        review_fact(database, fact["fact_id"], "know")
        st.session_state[position_key] = index + 1
        st.rerun()
    if col2.button("↻  Study again", use_container_width=True):
        review_fact(database, fact["fact_id"], "study")
        st.session_state[position_key] = index + 1
        st.rerun()
    if st.button("Next fact", use_container_width=True):
        st.session_state[position_key] = index + 1
        st.rerun()
    st.caption(f"Fact {index + 1} of {len(candidates)} · Your local bank grows when you import more packs.")


def render_recall():
    """Run one open-ended answer attempt."""
    st.title("Recall")
    st.write("Type any answer you can retrieve. No multiple choice, no hints before you answer.")
    if "recall_question" not in st.session_state:
        st.session_state["recall_question"] = next_question("recall")
    question = st.session_state["recall_question"]
    st.markdown(f'<div class="eyebrow">{question["category"]} · {question["subcategory"]}</div>', unsafe_allow_html=True)
    st.markdown(f"## {question['prompt']}")
    st.caption(question["rule"])
    if st.session_state.get("recall_result"):
        result = st.session_state["recall_result"]
        show_feedback(question, result["submitted"], result["matched"])
        if st.button("Next question", type="primary"):
            st.session_state["recall_question"] = next_question("recall")
            st.session_state["recall_result"] = None
            st.rerun()
    else:
        with st.form("recall_form"):
            answer = st.text_input("Your answer", placeholder="Type an answer…")
            submitted = st.form_submit_button("Check answer", type="primary")
        if submitted:
            matched = match_answer(question, answer)
            save_attempt(question, answer, matched)
            st.session_state["recall_result"] = {"submitted": answer, "matched": matched}
            st.rerun()


def render_speed_dive():
    """Play a seven-question set and award transparent practice points."""
    st.title("Speed Dive")
    st.write("Seven mixed questions. Points reward correct answers and pack-estimated obscurity—not Krillion rarity.")
    timer_enabled = st.checkbox("Use a 25-second timer per question", key="dive_timer_enabled")
    if timer_enabled and not st.session_state.get("dive_timer_was_enabled", False):
        st.session_state["dive_started_at"] = time.time()
    st.session_state["dive_timer_was_enabled"] = timer_enabled
    if timer_enabled:
        st.caption("The timer starts when each question appears. Answers are revealed only after submitting or timing out.")
    if not st.session_state.get("dive_active"):
        if st.button("Start a 7-question dive", type="primary"):
            reset_speed_dive()
            st.rerun()
        return
    if st.session_state["dive_number"] >= 7:
        st.markdown("## Dive complete")
        st.metric("Practice points", st.session_state["dive_points"])
        st.write(f"You got **{st.session_state['dive_correct']} of 7** answers accepted.")
        st.markdown("### Useful answers to remember")
        for item in st.session_state["dive_results"]:
            if item["matched"]:
                st.markdown(f"- **{item['matched']['name']}** — {item['matched']['explanation']}")
            elif item["question"]["answers"]:
                uncommon = max(item["question"]["answers"], key=lambda answer: answer.get("obscurity", 1))
                st.markdown(f"- **{uncommon['name']}** — {uncommon['explanation']}")
        if st.button("Play again", type="primary"):
            reset_speed_dive()
            st.rerun()
        st.session_state["dive_active"] = False
        return

    question = st.session_state["dive_question"]
    st.caption(f"Question {st.session_state['dive_number'] + 1} of 7")
    if st.session_state.get("dive_timer_enabled"):
        st.session_state.setdefault("dive_started_at", time.time())
        st.fragment(run_every="1s")(render_speed_timer)()
    st.markdown(f"## {question['prompt']}")
    if st.session_state.get("dive_result"):
        result = st.session_state["dive_result"]
        show_feedback(question, result["submitted"], result["matched"])
        if st.button("Continue", type="primary"):
            st.session_state["dive_result"] = None
            st.session_state["dive_timed_out"] = False
            if st.session_state["dive_number"] < 7:
                st.session_state["dive_question"] = next_question("dive")
                st.session_state["dive_started_at"] = time.time()
            st.rerun()
    else:
        with st.form("dive_form"):
            answer = st.text_input("Your answer", placeholder="One answer is enough…")
            submitted = st.form_submit_button("Submit answer", type="primary")
        if submitted:
            matched = match_answer(question, answer)
            save_attempt(question, answer, matched)
            points = estimate_points(question, matched) if matched else 0
            st.session_state["dive_correct"] += int(bool(matched))
            st.session_state["dive_points"] += points
            st.session_state["dive_results"].append(
                {"question": question, "answer": answer, "correct": bool(matched), "matched": matched, "points": points}
            )
            st.session_state["dive_number"] += 1
            st.session_state["dive_result"] = {"submitted": answer, "matched": matched}
            st.rerun()


def render_smart_review():
    """Prioritize due facts and weaker categories in a repeatable recall loop."""
    st.title("Smart Review")
    stats = get_stats(database)
    a, b, c, d = st.columns(4)
    a.metric("Day streak", f"{stats['streak']} days")
    b.metric("Questions", stats["questions_completed"])
    c.metric("Accuracy", f"{stats['accuracy']}%")
    d.metric("Facts mastered", stats["facts_mastered"])
    statuses = get_review_statuses(database)
    due_facts = [
        facts_by_id[key] for key, value in statuses.items()
        if key in facts_by_id and value["due_on"] <= date.today().isoformat()
    ]
    if due_facts:
        selected_fact = due_facts[0]
        question = next(item for item in questions if item["id"] == selected_fact["question_id"])
        st.info(f"A fact is due for review · {selected_fact['category']}")
    else:
        question = st.session_state.get("review_question")
        if question is None:
            question = next_question("review")
            st.session_state["review_question"] = question
    st.caption(question["rule"])
    st.markdown(f"## {question['prompt']}")
    review_key = question["id"]
    result_key = f"review_result_{review_key}"
    if st.session_state.get(result_key):
        result = st.session_state[result_key]
        show_feedback(question, result["submitted"], result["matched"])
        if st.button("Review another", type="primary"):
            st.session_state[result_key] = None
            st.session_state["review_question"] = next_question("review")
            st.rerun()
    else:
        with st.form(f"review_form_{review_key}"):
            answer = st.text_input("Your answer", placeholder="Recall before you reveal…")
            submitted = st.form_submit_button("Check answer", type="primary")
        if submitted:
            matched = match_answer(question, answer)
            save_attempt(question, answer, matched)
            st.session_state[result_key] = {"submitted": answer, "matched": matched}
            st.rerun()
    st.markdown("### How spaced review works")
    st.caption("Missed answers return sooner. Marking a fact as known schedules it further away after each successful review.")


def render_import():
    """Let users extend their question bank with validated local JSON packs."""
    st.title("Grow your question bank")
    st.write("Import another JSON pack to add prompts and facts. Nothing is uploaded to a service; the file stays on this computer.")
    uploaded = st.file_uploader("Choose a question pack (.json)", type=["json"])
    if uploaded and st.button("Validate and import pack", type="primary"):
        try:
            destination = save_imported_pack(
                uploaded.getvalue(),
                uploaded.name,
                existing_question_ids={question["id"] for question in questions},
            )
            st.success(f"Imported locally as `{destination.name}`. Restarting the app will load the new questions.")
        except (ValueError, OSError) as error:
            st.error(str(error))
    with st.expander("Required JSON shape"):
        st.code(
            """{
  "pack_name": "My pack",
  "questions": [{
    "id": "my-question",
    "category": "Science",
    "subcategory": "Astronomy",
    "prompt": "Name ...",
    "rule": "What counts as a valid answer.",
    "answers": [{
      "name": "Accepted answer",
      "aliases": ["Alternate spelling"],
      "fact": "A memorable fact.",
      "explanation": "Why it is useful or surprising.",
      "obscurity": 3,
      "source_url": "https://example.org/reference"
    }]
  }]
}""",
            language="json",
        )


st.sidebar.markdown("# 🌊 DeepDive")
st.sidebar.caption("Build a deeper well of answers.")
page = st.sidebar.radio(
    "Choose a dive",
    ["Discover", "Recall", "Speed Dive", "Smart Review"],
    label_visibility="collapsed",
)

try:
    if page == "Discover":
        render_discover()
    elif page == "Recall":
        render_recall()
    elif page == "Speed Dive":
        render_speed_dive()
    else:
        render_smart_review()
    st.sidebar.divider()
    if st.sidebar.button("Import a question pack"):
        st.session_state["show_import"] = True
    if st.session_state.get("show_import"):
        render_import()
finally:
    database.close()
