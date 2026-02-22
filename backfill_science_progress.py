#!/usr/bin/env python3
"""One-time backfill of science_question_progress from existing submissions."""
import json
from database import get_db, init_db
from test_engine import update_science_progress


def backfill():
    init_db()  # Ensure the new table exists
    conn = get_db()

    submissions = conn.execute(
        """SELECT sts.child_id, sts.answers
           FROM science_test_submission sts
           ORDER BY sts.submitted_at ASC"""
    ).fetchall()
    conn.close()

    count = 0
    for sub in submissions:
        answers = json.loads(sub["answers"])
        for qid_str, answer_data in answers.items():
            is_correct = answer_data.get("is_correct", False)
            update_science_progress(
                child_id=sub["child_id"],
                question_id=int(qid_str),
                correct=is_correct
            )
            count += 1

    print(f"Backfilled {count} question progress records from {len(submissions)} submissions.")


if __name__ == "__main__":
    backfill()
