import random
from datetime import datetime, timedelta
from database import get_db


REVIEW_WINDOW_DAYS = 7


def get_test_words(child_id: int, count: int = 25) -> list:
    """
    Get words for testing using priority-based selection:
    1. Never tested words (no progress or last_tested IS NULL)
    2. Wrong words (wrong_count > correct_count, or streak=0 and has been tested)
    3. Due for review (last_correct_at older than 7 days)
    4. Recently correct (fill remaining, oldest last_correct_at first)
    """
    conn = get_db()
    words = conn.execute(
        """SELECT w.id, w.word, w.definition, w.example_sentence, w.image_path,
                  wp.correct_count, wp.wrong_count, wp.streak,
                  COALESCE(wp.difficulty_level, 1) as difficulty_level,
                  wp.last_tested, wp.last_correct_at
           FROM word w
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
           WHERE w.child_id = ?""",
        (child_id,)
    ).fetchall()
    conn.close()

    if not words:
        return []

    words = [dict(w) for w in words]
    cutoff = datetime.now() - timedelta(days=REVIEW_WINDOW_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    never_tested = []
    wrong = []
    due_for_review = []
    recently_correct = []

    for w in words:
        if not w["definition"]:
            continue  # skip words without definitions

        if w["last_tested"] is None:
            never_tested.append(w)
        elif w["wrong_count"] and w["wrong_count"] > (w["correct_count"] or 0):
            wrong.append(w)
        elif w["streak"] == 0 and w["last_tested"] is not None:
            wrong.append(w)
        elif w["last_correct_at"] is None or w["last_correct_at"] < cutoff_str:
            due_for_review.append(w)
        else:
            recently_correct.append(w)

    # Shuffle within each group
    random.shuffle(never_tested)
    random.shuffle(wrong)
    random.shuffle(due_for_review)
    # Sort recently correct by oldest last_correct_at first
    recently_correct.sort(key=lambda w: w["last_correct_at"] or "")

    # Combine in priority order
    selected = []
    for group in [never_tested, wrong, due_for_review, recently_correct]:
        for w in group:
            if len(selected) >= count:
                break
            selected.append(w)
        if len(selected) >= count:
            break

    return selected


def generate_choices(correct_word: dict, all_words: list, count: int = 4) -> list:
    """
    Generate multiple choice options including the correct answer.
    """
    choices = [correct_word["definition"]]
    other_defs = [w["definition"] for w in all_words
                  if w["id"] != correct_word["id"] and w["definition"]]

    random.shuffle(other_defs)
    for d in other_defs:
        if d not in choices:
            choices.append(d)
        if len(choices) >= count:
            break

    random.shuffle(choices)
    return choices


def generate_word_choices(correct_word: dict, all_words: list, count: int = 4) -> list:
    """
    Generate multiple choice word options (for reverse quiz and fill-in-blank).
    """
    choices = [correct_word["word"]]
    other_words = [w["word"] for w in all_words
                   if w["id"] != correct_word["id"] and w["word"]]

    random.shuffle(other_words)
    for w in other_words:
        if w not in choices:
            choices.append(w)
        if len(choices) >= count:
            break

    random.shuffle(choices)
    return choices


def update_progress(child_id: int, word_id: int, correct: bool) -> dict:
    """
    Update word progress after an answer.
    """
    conn = get_db()

    # Get current progress
    progress = conn.execute(
        """SELECT * FROM word_progress WHERE child_id = ? AND word_id = ?""",
        (child_id, word_id)
    ).fetchone()

    if not progress:
        conn.execute(
            """INSERT INTO word_progress (child_id, word_id, difficulty_level)
               VALUES (?, ?, 1)""",
            (child_id, word_id)
        )
        progress = {"correct_count": 0, "wrong_count": 0, "streak": 0, "difficulty_level": 1}
    else:
        progress = dict(progress)

    now = datetime.now()

    # Calculate new values
    if correct:
        new_correct = progress["correct_count"] + 1
        new_wrong = progress["wrong_count"]
        new_streak = progress["streak"] + 1
        new_difficulty = min(5, progress["difficulty_level"] + 1)

        conn.execute(
            """UPDATE word_progress
               SET correct_count = ?, wrong_count = ?, streak = ?,
                   difficulty_level = ?, last_tested = ?, last_correct_at = ?
               WHERE child_id = ? AND word_id = ?""",
            (new_correct, new_wrong, new_streak, new_difficulty,
             now, now, child_id, word_id)
        )
    else:
        new_correct = progress["correct_count"]
        new_wrong = progress["wrong_count"] + 1
        new_streak = 0
        new_difficulty = max(1, progress["difficulty_level"] - 1)

        conn.execute(
            """UPDATE word_progress
               SET correct_count = ?, wrong_count = ?, streak = ?,
                   difficulty_level = ?, last_tested = ?
               WHERE child_id = ? AND word_id = ?""",
            (new_correct, new_wrong, new_streak, new_difficulty,
             now, child_id, word_id)
        )

    conn.commit()
    conn.close()

    return {
        "streak": new_streak,
        "correct": correct
    }


def update_science_progress(child_id: int, question_id: int, correct: bool) -> dict:
    """Update science question progress after an answer."""
    conn = get_db()

    progress = conn.execute(
        "SELECT * FROM science_question_progress WHERE child_id = ? AND question_id = ?",
        (child_id, question_id)
    ).fetchone()

    if not progress:
        conn.execute(
            "INSERT INTO science_question_progress (child_id, question_id, difficulty_level) VALUES (?, ?, 1)",
            (child_id, question_id)
        )
        progress = {"correct_count": 0, "wrong_count": 0, "streak": 0, "difficulty_level": 1}
    else:
        progress = dict(progress)

    now = datetime.now()

    if correct:
        new_correct = progress["correct_count"] + 1
        new_wrong = progress["wrong_count"]
        new_streak = progress["streak"] + 1
        new_difficulty = min(5, progress["difficulty_level"] + 1)

        conn.execute(
            """UPDATE science_question_progress
               SET correct_count = ?, wrong_count = ?, streak = ?,
                   difficulty_level = ?, last_tested = ?, last_correct_at = ?
               WHERE child_id = ? AND question_id = ?""",
            (new_correct, new_wrong, new_streak, new_difficulty,
             now, now, child_id, question_id)
        )
    else:
        new_correct = progress["correct_count"]
        new_wrong = progress["wrong_count"] + 1
        new_streak = 0
        new_difficulty = max(1, progress["difficulty_level"] - 1)

        conn.execute(
            """UPDATE science_question_progress
               SET correct_count = ?, wrong_count = ?, streak = ?,
                   difficulty_level = ?, last_tested = ?
               WHERE child_id = ? AND question_id = ?""",
            (new_correct, new_wrong, new_streak, new_difficulty,
             now, child_id, question_id)
        )

    conn.commit()
    conn.close()

    return {"streak": new_streak, "correct": correct}


def record_test_session(child_id: int, test_type: str, score: int,
                        correct_count: int, total_count: int, time_taken: int):
    """Record a completed test session."""
    conn = get_db()
    conn.execute(
        """INSERT INTO test_session
           (child_id, test_type, score, correct_count, total_count, time_taken)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (child_id, test_type, score, correct_count, total_count, time_taken)
    )
    conn.commit()
    conn.close()
