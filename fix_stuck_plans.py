#!/usr/bin/env python3
"""
Fix stuck learning plans where all items are completed but plan status is still 'released'.
Usage: python3 fix_stuck_plans.py [path_to_verbal.db]
"""
import sqlite3
import sys
from pathlib import Path

db_path = sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "verbal.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

plans = conn.execute("SELECT id, title, child_id FROM learning_plan WHERE status = 'released'").fetchall()

if not plans:
    print("No in-progress plans found.")
    conn.close()
    sys.exit(0)

fixed = 0
for plan in plans:
    items = conn.execute(
        "SELECT item_type, item_id FROM learning_plan_item WHERE plan_id = ?", (plan["id"],)
    ).fetchall()

    if not items:
        continue

    all_done = True
    for item in items:
        if item["item_type"] == "study_session":
            row = conn.execute("SELECT status FROM study_session WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "reading_assignment":
            row = conn.execute("SELECT status FROM reading_assignment WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "math_test":
            row = conn.execute("SELECT status FROM math_test WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "parent_test":
            row = conn.execute("SELECT status FROM parent_test WHERE id = ?", (item["item_id"],)).fetchone()
        else:
            continue
        if not row or row["status"] != "completed":
            all_done = False
            print(f"  Plan {plan['id']} ({plan['title']}): {item['item_type']} #{item['item_id']} is {row['status'] if row else 'missing'}")
            break

    if all_done:
        conn.execute(
            "UPDATE learning_plan SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (plan["id"],)
        )
        fixed += 1
        print(f"  Fixed plan {plan['id']} ({plan['title']}) -> completed")
    else:
        print(f"  Plan {plan['id']} ({plan['title']}): not all items done, skipping")

conn.commit()
conn.close()
print(f"\nDone. Fixed {fixed} plan(s).")
