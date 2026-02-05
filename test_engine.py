import random
from datetime import datetime
from database import get_db


def get_test_words(child_id: int, count: int = 10) -> list:
    """
    Get words for testing, weighted by difficulty (lower difficulty = more likely).
    """
    conn = get_db()
    words = conn.execute(
        """SELECT w.id, w.word, w.definition, w.example_sentence,
                  COALESCE(wp.difficulty_level, 1) as difficulty_level
           FROM word w
           LEFT JOIN word_progress wp ON w.id = wp.word_id
           WHERE w.child_id = ?""",
        (child_id,)
    ).fetchall()
    conn.close()

    if not words:
        return []

    words = [dict(w) for w in words]

    # Weight by inverse difficulty (level 1 = weight 5, level 5 = weight 1)
    weighted = []
    for w in words:
        weight = 6 - w["difficulty_level"]
        weighted.extend([w] * weight)

    random.shuffle(weighted)

    # Get unique words up to count
    selected = []
    seen = set()
    for w in weighted:
        if w["id"] not in seen:
            selected.append(w)
            seen.add(w["id"])
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


def update_progress(child_id: int, word_id: int, correct: bool) -> dict:
    """
    Update word progress after an answer.
    Returns points earned and new difficulty.
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

    # Calculate new values
    if correct:
        new_correct = progress["correct_count"] + 1
        new_wrong = progress["wrong_count"]
        new_streak = progress["streak"] + 1
        new_difficulty = min(5, progress["difficulty_level"] + 1)

        # Points: base + streak bonus + difficulty bonus
        points = 10 + (new_streak - 1) * 5 + (progress["difficulty_level"] - 1) * 5
    else:
        new_correct = progress["correct_count"]
        new_wrong = progress["wrong_count"] + 1
        new_streak = 0
        new_difficulty = max(1, progress["difficulty_level"] - 1)
        points = 0

    conn.execute(
        """UPDATE word_progress
           SET correct_count = ?, wrong_count = ?, streak = ?,
               difficulty_level = ?, last_tested = ?
           WHERE child_id = ? AND word_id = ?""",
        (new_correct, new_wrong, new_streak, new_difficulty,
         datetime.now(), child_id, word_id)
    )

    # Update child total points
    if points > 0:
        conn.execute(
            """UPDATE child SET total_points = total_points + ? WHERE id = ?""",
            (points, child_id)
        )

        # Check for level up (every 100 points)
        child = conn.execute(
            "SELECT total_points, level FROM child WHERE id = ?", (child_id,)
        ).fetchone()
        new_level = child["total_points"] // 100 + 1
        if new_level > child["level"]:
            conn.execute(
                "UPDATE child SET level = ? WHERE id = ?", (new_level, child_id)
            )

    conn.commit()
    conn.close()

    return {
        "points": points,
        "streak": new_streak,
        "difficulty": new_difficulty,
        "correct": correct
    }


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
