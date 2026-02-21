# Science Bowl Study & Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use 10x-engineer:executing-plans to implement this plan task-by-task.

**Goal:** Add Science Bowl question import, study (flashcards), and testing to the Science tab.

**Architecture:** PDF upload parses Science Bowl format into individual questions stored in DB. Parent previews/edits parsed questions, then creates study sessions (flashcard review) or tests (answer-all, auto-grade) from them. Follows existing patterns from math test and vocab study flows.

**Tech Stack:** Flask, SQLite (raw SQL), pdfplumber, Jinja2 templates, vanilla JS

---

### Task 1: Database Schema — Add Science Bowl Tables

**Files:**
- Modify: `database.py:272` (inside `init_db()`, after existing CREATE TABLE block)

**Step 1: Add the new tables to the CREATE TABLE block in `init_db()`**

Add these tables inside the `conn.executescript("""...""")` block, before the closing `""")`:

```python
        CREATE TABLE IF NOT EXISTS science_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            question_type TEXT NOT NULL,
            answer_format TEXT NOT NULL,
            question_text TEXT NOT NULL,
            choices TEXT,
            correct_answer TEXT NOT NULL,
            explanation TEXT,
            source_pdf TEXT,
            round_name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS science_study_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'pending',
            learning_plan_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS science_study_session_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES science_study_session(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES science_question(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS science_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            timer_mode TEXT DEFAULT 'none',
            time_limit_seconds INTEGER DEFAULT 0,
            learning_plan_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS science_test_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            FOREIGN KEY (test_id) REFERENCES science_test(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES science_question(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS science_test_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            science_test_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            answers TEXT NOT NULL,
            score INTEGER NOT NULL,
            correct_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            time_taken_seconds INTEGER DEFAULT 0,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (science_test_id) REFERENCES science_test(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );
```

Column notes:
- `science_question.category`: "LIFE SCIENCE", "PHYSICAL SCIENCE", "EARTH SCIENCE", "MATH", "GENERAL SCIENCE", "ENERGY"
- `science_question.question_type`: "toss_up" or "bonus"
- `science_question.answer_format`: "multiple_choice" or "short_answer"
- `science_question.choices`: JSON string like `{"W": "stationary", "X": "low", "Y": "constant", "Z": "used"}` or null for short answer
- `science_question.explanation`: brief concept explanation for study mode

**Step 2: Verify the app starts without error**

```bash
cd /Users/yfshao/kid-verbal && python3 -c "from database import init_db; init_db(); print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add database.py && git commit -m "feat: add science bowl database tables"
```

---

### Task 2: PDF Parser — Parse Science Bowl Question Format

**Files:**
- Create: `science_parser.py`

**Step 1: Create `science_parser.py`**

The parser must handle the exact format found in the sample PDF (`m_round01.pdf`):

```
TOSS-UP
1) LIFE SCIENCE Short Answer What organelle functions to isolate...
ANSWER: NUCLEUS

BONUS
1) LIFE SCIENCE Short Answer What is the primary oxygen-carrying protein...
ANSWER: HEMOGLOBIN

TOSS-UP
2) PHYSICAL SCIENCE Multiple Choice Which of the following BEST describes...:
W) stationary
X) low
Y) constant
Z) used
ANSWER: W) STATIONARY
```

Key patterns:
- `TOSS-UP` or `BONUS` on its own line marks question type
- Next line: `N) CATEGORY (Short Answer|Multiple Choice) question text`
- For MC: choice lines follow with `W)`, `X)`, `Y)`, `Z)` (or sometimes `A)`, `B)`, `C)`, `D)`)
- `ANSWER:` line has the correct answer
- Footer lines like "Middle School Round 1 Page N" should be ignored
- Some answers have parenthetical accepts like `(ACCEPT: PLASTID)`

```python
import re
import pdfplumber


def parse_science_bowl_pdf(pdf_path):
    """Parse a Science Bowl PDF into structured questions.

    Returns (questions_list, error_string).
        questions_list: list of dicts on success
        error_string: None on success, descriptive message on failure
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            return None, "Could not extract any text from the PDF."

        # Extract round name from text (e.g., "ROUND 1")
        round_match = re.search(r'ROUND\s+(\d+)', text, re.IGNORECASE)
        round_name = f"Round {round_match.group(1)}" if round_match else ""

        # Remove footer lines like "Middle School Round 1 Page 1"
        text = re.sub(r'(?:Middle|High)\s+School\s+Round\s+\d+\s+Page\s+\d+', '', text)

        questions = []

        # Split into blocks by TOSS-UP / BONUS markers
        # Pattern: find TOSS-UP or BONUS followed by content until next TOSS-UP/BONUS or end
        blocks = re.split(r'\n(?=(?:TOSS-UP|BONUS)\s*\n)', text)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Determine question type
            if block.startswith('TOSS-UP'):
                q_type = 'toss_up'
                block = block[len('TOSS-UP'):].strip()
            elif block.startswith('BONUS'):
                q_type = 'bonus'
                block = block[len('BONUS'):].strip()
            else:
                continue

            # Parse the question line: N) CATEGORY (Short Answer|Multiple Choice) question text
            q_match = re.match(
                r'(\d+)\)\s+'
                r'(LIFE SCIENCE|PHYSICAL SCIENCE|EARTH SCIENCE|EARTH AND SPACE|GENERAL SCIENCE|MATH|ENERGY|BIOLOGY|CHEMISTRY|PHYSICS)\s+'
                r'(Short Answer|Multiple Choice)\s+'
                r'(.+?)(?=\nANSWER:|\n[WXYZABCD]\))',
                block, re.DOTALL | re.IGNORECASE
            )

            if not q_match:
                continue

            q_num = int(q_match.group(1))
            category = q_match.group(2).upper()
            answer_format = 'short_answer' if 'short' in q_match.group(3).lower() else 'multiple_choice'
            question_text = re.sub(r'\s+', ' ', q_match.group(4)).strip()
            # Remove trailing colon from MC questions
            if question_text.endswith(':'):
                question_text = question_text[:-1].strip()

            choices = None
            correct_answer = ""
            explanation = ""

            if answer_format == 'multiple_choice':
                # Extract choices - try W/X/Y/Z first, then A/B/C/D
                choice_pattern = re.findall(r'([WXYZABCD])\)\s*(.+?)(?=\n[WXYZABCD]\)|\nANSWER:)', block, re.DOTALL)
                if choice_pattern:
                    choices = {}
                    for letter, text_val in choice_pattern:
                        choices[letter.upper()] = re.sub(r'\s+', ' ', text_val).strip()

                # Extract answer
                ans_match = re.search(r'ANSWER:\s*([WXYZABCD])\)', block, re.IGNORECASE)
                if ans_match:
                    correct_answer = ans_match.group(1).upper()
                    # Build explanation from the answer text
                    full_ans = re.search(r'ANSWER:\s*[WXYZABCD]\)\s*(.+)', block, re.IGNORECASE)
                    if full_ans and choices:
                        explanation = f"The answer is {correct_answer}) {choices.get(correct_answer, full_ans.group(1).strip())}"
            else:
                # Short answer
                ans_match = re.search(r'ANSWER:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
                if ans_match:
                    correct_answer = ans_match.group(1).strip()
                    explanation = f"Answer: {correct_answer}"

            # Normalize category names
            category_map = {
                'BIOLOGY': 'LIFE SCIENCE',
                'CHEMISTRY': 'PHYSICAL SCIENCE',
                'PHYSICS': 'PHYSICAL SCIENCE',
                'EARTH AND SPACE': 'EARTH SCIENCE',
            }
            category = category_map.get(category, category)

            questions.append({
                'number': q_num,
                'question_type': q_type,
                'category': category,
                'answer_format': answer_format,
                'question_text': question_text,
                'choices': choices,
                'correct_answer': correct_answer,
                'explanation': explanation,
                'round_name': round_name,
            })

        if not questions:
            return None, "No Science Bowl questions found in the PDF. Expected format: TOSS-UP/BONUS markers with numbered questions."

        return questions, None

    except Exception as e:
        return None, f"Error reading PDF: {str(e)}"
```

**Step 2: Test the parser against the sample PDF**

```bash
cd /Users/yfshao/kid-verbal && python3 -c "
from science_parser import parse_science_bowl_pdf
qs, err = parse_science_bowl_pdf('m_round01.pdf')
if err:
    print('ERROR:', err)
else:
    print(f'Parsed {len(qs)} questions')
    for q in qs[:4]:
        print(f\"  #{q['number']} {q['question_type']} | {q['category']} | {q['answer_format']} | {q['correct_answer']}\")
        print(f\"    Q: {q['question_text'][:80]}...\")
        if q['choices']:
            print(f\"    Choices: {q['choices']}\")
    print('...')
    # Count by type
    tossups = [q for q in qs if q['question_type'] == 'toss_up']
    bonuses = [q for q in qs if q['question_type'] == 'bonus']
    mc = [q for q in qs if q['answer_format'] == 'multiple_choice']
    sa = [q for q in qs if q['answer_format'] == 'short_answer']
    print(f'Toss-ups: {len(tossups)}, Bonuses: {len(bonuses)}')
    print(f'MC: {len(mc)}, Short Answer: {len(sa)}')
"
```

Expected: Should parse 50 questions (25 toss-ups + 25 bonuses). Iterate on the regex patterns until all questions are parsed correctly.

**Step 3: Commit**

```bash
git add science_parser.py && git commit -m "feat: add Science Bowl PDF parser"
```

---

### Task 3: Backend API — Question Import & Management

**Files:**
- Modify: `app.py:14` (add import)
- Modify: `app.py` (add routes before `if __name__` block at line 3393)

**Step 1: Add import at top of `app.py`**

At line 14, after the `pdf_parser` import, add:

```python
from science_parser import parse_science_bowl_pdf
```

**Step 2: Add API routes for science questions**

Add these routes before the `if __name__` block (line 3393 of `app.py`):

```python
# ── Science Bowl routes ──

@app.route("/api/science/upload", methods=["POST"])
@parent_required
def upload_science_pdf():
    """Upload and parse a Science Bowl PDF. Returns parsed questions for preview."""
    if "pdf" not in request.files:
        return jsonify({"error": "PDF file required"}), 400
    pdf_file = request.files["pdf"]
    if not pdf_file.filename:
        return jsonify({"error": "No file selected"}), 400

    ts = int(time.time())
    filename = f"science_{ts}_{secure_filename(pdf_file.filename)}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    pdf_file.save(filepath)

    questions, error = parse_science_bowl_pdf(filepath)
    if error:
        os.remove(filepath)
        return jsonify({"error": error}), 400

    return jsonify({"questions": questions, "source_pdf": filename}), 200


@app.route("/api/science/questions", methods=["POST"])
@parent_required
def save_science_questions():
    """Save parsed (and possibly edited) questions to DB for a child."""
    data = request.json
    child_id = data.get("child_id")
    questions = data.get("questions", [])
    source_pdf = data.get("source_pdf", "")
    if not child_id or not questions:
        return jsonify({"error": "child_id and questions required"}), 400

    conn = get_db()
    saved_ids = []
    for q in questions:
        cursor = conn.execute(
            """INSERT INTO science_question
               (child_id, category, question_type, answer_format, question_text, choices, correct_answer, explanation, source_pdf, round_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (child_id, q["category"], q["question_type"], q["answer_format"],
             q["question_text"], json.dumps(q.get("choices")) if q.get("choices") else None,
             q["correct_answer"], q.get("explanation", ""), source_pdf, q.get("round_name", ""))
        )
        saved_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    return jsonify({"saved": len(saved_ids), "ids": saved_ids}), 201


@app.route("/api/children/<int:child_id>/science-questions", methods=["GET"])
@login_required
def list_science_questions(child_id):
    """List all science questions for a child, optionally filtered by category."""
    category = request.args.get("category")
    conn = get_db()
    if category:
        questions = conn.execute(
            "SELECT * FROM science_question WHERE child_id = ? AND category = ? ORDER BY round_name, question_type, id",
            (child_id, category)
        ).fetchall()
    else:
        questions = conn.execute(
            "SELECT * FROM science_question WHERE child_id = ? ORDER BY round_name, question_type, id",
            (child_id,)
        ).fetchall()
    conn.close()
    return jsonify([dict(q) for q in questions])


@app.route("/api/science-questions/<int:question_id>", methods=["PUT"])
@parent_required
def update_science_question(question_id):
    """Edit a science question."""
    data = request.json
    conn = get_db()
    q = conn.execute("SELECT * FROM science_question WHERE id = ?", (question_id,)).fetchone()
    if not q:
        conn.close()
        return jsonify({"error": "Question not found"}), 404
    conn.execute(
        """UPDATE science_question SET category=?, question_type=?, answer_format=?,
           question_text=?, choices=?, correct_answer=?, explanation=? WHERE id=?""",
        (data.get("category", q["category"]), data.get("question_type", q["question_type"]),
         data.get("answer_format", q["answer_format"]), data.get("question_text", q["question_text"]),
         json.dumps(data["choices"]) if "choices" in data and data["choices"] else q["choices"],
         data.get("correct_answer", q["correct_answer"]),
         data.get("explanation", q["explanation"]), question_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/science-questions/<int:question_id>", methods=["DELETE"])
@parent_required
def delete_science_question(question_id):
    conn = get_db()
    conn.execute("DELETE FROM science_question WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
```

**Step 3: Verify app starts**

```bash
cd /Users/yfshao/kid-verbal && python3 -c "from app import app; print('OK')"
```

**Step 4: Commit**

```bash
git add app.py && git commit -m "feat: add science question import and management APIs"
```

---

### Task 4: Backend API — Science Study Sessions

**Files:**
- Modify: `app.py` (add routes before `if __name__` block)

**Step 1: Add study session routes**

```python
@app.route("/api/science-study-sessions", methods=["POST"])
@parent_required
def create_science_study_session():
    data = request.json
    child_id = data.get("child_id")
    title = data.get("title", "").strip()
    question_ids = data.get("question_ids", [])
    if not child_id or not question_ids:
        return jsonify({"error": "child_id and question_ids required"}), 400

    account = get_current_account()
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO science_study_session (child_id, created_by, title) VALUES (?, ?, ?)",
        (child_id, account["id"], title or "Science Study")
    )
    session_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute(
            "INSERT INTO science_study_session_question (session_id, question_id) VALUES (?, ?)",
            (session_id, qid)
        )
    conn.commit()
    conn.close()
    return jsonify({"id": session_id}), 201


@app.route("/api/children/<int:child_id>/science-study-sessions", methods=["GET"])
@login_required
def list_science_study_sessions(child_id):
    conn = get_db()
    sessions = conn.execute(
        "SELECT * FROM science_study_session WHERE child_id = ? ORDER BY created_at DESC",
        (child_id,)
    ).fetchall()
    result = []
    for s in sessions:
        count = conn.execute(
            "SELECT COUNT(*) FROM science_study_session_question WHERE session_id = ?", (s["id"],)
        ).fetchone()[0]
        d = dict(s)
        d["question_count"] = count
        result.append(d)
    conn.close()
    return jsonify(result)


@app.route("/api/science-study-sessions/<int:session_id>/questions", methods=["GET"])
@login_required
def get_science_study_session_questions(session_id):
    conn = get_db()
    questions = conn.execute(
        """SELECT q.* FROM science_question q
           JOIN science_study_session_question ssq ON q.id = ssq.question_id
           WHERE ssq.session_id = ?
           ORDER BY q.question_type, q.id""",
        (session_id,)
    ).fetchall()
    conn.close()
    result = []
    for q in questions:
        d = dict(q)
        if d["choices"]:
            d["choices"] = json.loads(d["choices"])
        result.append(d)
    return jsonify(result)


@app.route("/api/science-study-sessions/<int:session_id>/complete", methods=["POST"])
@login_required
def complete_science_study_session(session_id):
    conn = get_db()
    session_row = conn.execute("SELECT * FROM science_study_session WHERE id = ?", (session_id,)).fetchone()
    if not session_row:
        conn.close()
        return jsonify({"error": "Session not found"}), 404
    conn.execute("UPDATE science_study_session SET status = 'completed' WHERE id = ?", (session_id,))
    conn.commit()
    if session_row["learning_plan_id"]:
        check_plan_completion(session_row["learning_plan_id"], conn)
    conn.close()
    return jsonify({"success": True})


@app.route("/api/science-study-sessions/<int:session_id>", methods=["DELETE"])
@parent_required
def delete_science_study_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM science_study_session WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})
```

**Step 2: Commit**

```bash
git add app.py && git commit -m "feat: add science study session APIs"
```

---

### Task 5: Backend API — Science Tests

**Files:**
- Modify: `app.py` (add routes before `if __name__` block)

**Step 1: Add test routes**

```python
@app.route("/api/science-tests", methods=["POST"])
@parent_required
def create_science_test():
    data = request.json
    child_id = data.get("child_id")
    title = data.get("title", "").strip()
    question_ids = data.get("question_ids", [])
    timer_mode = data.get("timer_mode", "none")
    time_limit_seconds = data.get("time_limit_seconds", 0)
    if not child_id or not question_ids:
        return jsonify({"error": "child_id and question_ids required"}), 400

    account = get_current_account()
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO science_test (child_id, created_by, title, timer_mode, time_limit_seconds)
           VALUES (?, ?, ?, ?, ?)""",
        (child_id, account["id"], title or "Science Test", timer_mode, time_limit_seconds)
    )
    test_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute(
            "INSERT INTO science_test_question (test_id, question_id) VALUES (?, ?)",
            (test_id, qid)
        )
    conn.commit()
    conn.close()
    return jsonify({"id": test_id, "total_questions": len(question_ids)}), 201


@app.route("/api/children/<int:child_id>/science-tests", methods=["GET"])
@login_required
def list_science_tests(child_id):
    conn = get_db()
    tests = conn.execute(
        "SELECT * FROM science_test WHERE child_id = ? ORDER BY created_at DESC",
        (child_id,)
    ).fetchall()
    result = []
    for t in tests:
        count = conn.execute(
            "SELECT COUNT(*) FROM science_test_question WHERE test_id = ?", (t["id"],)
        ).fetchone()[0]
        sub = conn.execute(
            "SELECT * FROM science_test_submission WHERE science_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (t["id"],)
        ).fetchone()
        d = dict(t)
        d["question_count"] = count
        d["latest_submission"] = dict(sub) if sub else None
        result.append(d)
    conn.close()
    return jsonify(result)


@app.route("/api/science-tests/<int:test_id>", methods=["GET"])
@login_required
def get_science_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM science_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404
    questions = conn.execute(
        """SELECT q.* FROM science_question q
           JOIN science_test_question stq ON q.id = stq.question_id
           WHERE stq.test_id = ?
           ORDER BY q.question_type DESC, q.id""",
        (test_id,)
    ).fetchall()
    result = dict(test)
    qs = []
    for q in questions:
        d = dict(q)
        if d["choices"]:
            d["choices"] = json.loads(d["choices"])
        qs.append(d)
    result["questions"] = qs
    conn.close()
    return jsonify(result)


@app.route("/api/science-tests/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_science_test(test_id):
    data = request.json
    answers = data.get("answers", {})
    time_taken = data.get("time_taken_seconds", 0)

    conn = get_db()
    test = conn.execute("SELECT * FROM science_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404

    # Get questions for this test
    questions = conn.execute(
        """SELECT q.* FROM science_question q
           JOIN science_test_question stq ON q.id = stq.question_id
           WHERE stq.test_id = ?""",
        (test_id,)
    ).fetchall()

    correct_count = 0
    total_count = len(questions)
    graded_answers = {}

    for q in questions:
        qid_str = str(q["id"])
        child_answer = answers.get(qid_str, "").strip()
        correct = q["correct_answer"].strip()

        if q["answer_format"] == "multiple_choice":
            is_correct = child_answer.upper() == correct.upper()
        else:
            # Short answer: case-insensitive, strip whitespace
            is_correct = child_answer.upper() == correct.upper()
            # Also check if the answer appears in an ACCEPT pattern
            if not is_correct and "ACCEPT:" in correct.upper():
                # e.g., "NUCLEUS (ACCEPT: CELL NUCLEUS)"
                accepts = re.findall(r'ACCEPT:\s*([^)]+)', correct, re.IGNORECASE)
                for acc in accepts:
                    for alt in acc.split(';'):
                        if child_answer.upper().strip() == alt.strip().upper():
                            is_correct = True
                            break
            # Check main answer before any parenthetical
            if not is_correct:
                main_answer = re.split(r'\s*\(', correct)[0].strip()
                is_correct = child_answer.upper() == main_answer.upper()

        if is_correct:
            correct_count += 1

        graded_answers[qid_str] = {
            "child_answer": child_answer,
            "correct_answer": correct,
            "is_correct": is_correct,
            "needs_review": q["answer_format"] == "short_answer" and not is_correct
        }

    score = round(correct_count / total_count * 100) if total_count > 0 else 0

    account = get_current_account()
    conn.execute(
        """INSERT INTO science_test_submission
           (science_test_id, child_id, answers, score, correct_count, total_count, time_taken_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (test_id, account.get("child_id") or test["child_id"],
         json.dumps(graded_answers), score, correct_count, total_count, time_taken)
    )
    conn.execute("UPDATE science_test SET status = 'completed' WHERE id = ?", (test_id,))
    conn.commit()

    if test["learning_plan_id"]:
        check_plan_completion(test["learning_plan_id"], conn)
    conn.close()

    return jsonify({
        "score": score,
        "correct_count": correct_count,
        "total_count": total_count,
        "answers": graded_answers
    })


@app.route("/api/science-tests/<int:test_id>", methods=["DELETE"])
@parent_required
def delete_science_test(test_id):
    conn = get_db()
    conn.execute("DELETE FROM science_test WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/science-test-submissions/<int:submission_id>", methods=["GET"])
@login_required
def get_science_test_submission(submission_id):
    conn = get_db()
    sub = conn.execute("SELECT * FROM science_test_submission WHERE id = ?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return jsonify({"error": "Submission not found"}), 404
    result = dict(sub)
    result["answers"] = json.loads(result["answers"])
    conn.close()
    return jsonify(result)
```

**Step 2: Update `check_plan_completion` to handle science types**

In the `check_plan_completion` function (line 71-97 of `app.py`), add handling for science_study and science_test after the writing_test elif:

```python
        elif item["item_type"] == "science_study":
            row = conn.execute("SELECT status FROM science_study_session WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "science_test":
            row = conn.execute("SELECT status FROM science_test WHERE id = ?", (item["item_id"],)).fetchone()
```

**Step 3: Commit**

```bash
git add app.py && git commit -m "feat: add science test APIs and plan completion support"
```

---

### Task 6: Page Routes — Science Study & Test Pages

**Files:**
- Modify: `app.py` (add page routes before `if __name__` block)

**Step 1: Add page routes**

```python
@app.route("/child/<int:child_id>/science-study/<int:session_id>")
@login_required
def take_science_study(child_id, session_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    session_row = conn.execute("SELECT * FROM science_study_session WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not child or not session_row:
        return "Not found", 404
    return render_template("science_study.html", child=dict(child), session=dict(session_row),
                           learning_plan_id=session_row["learning_plan_id"])


@app.route("/child/<int:child_id>/science-test/<int:test_id>")
@login_required
def take_science_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM science_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not child or not test:
        return "Not found", 404
    return render_template("science_test.html", child=dict(child), test=dict(test),
                           learning_plan_id=test["learning_plan_id"])


@app.route("/child/<int:child_id>/science-test/<int:test_id>/review")
@login_required
def review_science_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM science_test WHERE id = ?", (test_id,)).fetchone()
    if not child or not test:
        conn.close()
        return "Not found", 404
    questions = conn.execute(
        """SELECT q.* FROM science_question q
           JOIN science_test_question stq ON q.id = stq.question_id
           WHERE stq.test_id = ? ORDER BY q.question_type DESC, q.id""",
        (test_id,)
    ).fetchall()
    submissions = conn.execute(
        "SELECT * FROM science_test_submission WHERE science_test_id = ? ORDER BY submitted_at DESC",
        (test_id,)
    ).fetchall()
    conn.close()
    qs = []
    for q in questions:
        d = dict(q)
        if d["choices"]:
            d["choices"] = json.loads(d["choices"])
        qs.append(d)
    return render_template("science_test_review.html", child=dict(child), test=dict(test),
                           questions=qs, submissions=[dict(s) for s in submissions],
                           learning_plan_id=test["learning_plan_id"])
```

**Step 2: Commit**

```bash
git add app.py && git commit -m "feat: add science study and test page routes"
```

---

### Task 7: Template — Science Study (Flashcards)

**Files:**
- Create: `templates/science_study.html`

**Step 1: Create the flashcard study template**

This template shows science questions in flashcard format. Front: question text + choices (if MC). Back: correct answer + explanation + "Search Online" link.

The template follows the same pattern as `study.html` but adapted for science questions:
- No word selection screen (questions come from session)
- Front of card: category badge + question type badge + question text + choices (for MC)
- Back of card: correct answer + explanation + "Search Online" button
- Progress bar + navigation
- "Mark Complete" at the end

Key elements:
- Load questions via `fetch('/api/science-study-sessions/${sessionId}/questions')`
- Card front: show question with category/type badges, MC choices listed (not clickable during study)
- Card back: show answer, explanation, and a "Search Online" link that opens `https://www.google.com/search?q=${encodeURIComponent(searchTerm)}` in new tab
- The search term should be the category + key concept from the question
- Navigation: Previous / Next buttons, progress bar
- On viewing all cards: show "Complete Study" button
- Complete button calls `POST /api/science-study-sessions/${sessionId}/complete`

The template should extend `base.html`, use the same CSS patterns (`.flashcard`, `.nav-btns`, `.progress-bar-bg`) as `study.html`.

**Step 2: Verify template renders**

Start the app and navigate to a science study session page.

**Step 3: Commit**

```bash
git add templates/science_study.html && git commit -m "feat: add science study flashcard template"
```

---

### Task 8: Template — Science Test

**Files:**
- Create: `templates/science_test.html`

**Step 1: Create the science test template**

This template shows all questions at once (like the math test but without PDF viewer). Child answers all questions and submits.

Layout:
- Header: test title, timer (if enabled), back link
- Progress bar showing answered/total
- Question list, each showing:
  - Category badge + question type badge (toss-up/bonus)
  - Question number and text
  - For MC: radio buttons for each choice (W/X/Y/Z or A/B/C/D)
  - For short answer: text input field
- Submit button (enabled when all answered, or allow partial submit)

Data flow:
- Load questions via `fetch('/api/science-tests/${testId}')`
- On submit: `POST /api/science-tests/${testId}/submit` with `{answers: {"question_id": "answer"}, time_taken_seconds: N}`
- On success: redirect to review page

Timer: reuse same timer pattern from `math_test.html` (stopwatch/countdown).

**Step 2: Commit**

```bash
git add templates/science_test.html && git commit -m "feat: add science test template"
```

---

### Task 9: Template — Science Test Review

**Files:**
- Create: `templates/science_test_review.html`

**Step 1: Create the review template**

Shows test results after submission. For each question:
- Question text with category/type badges
- Child's answer vs correct answer
- Green check or red X
- Explanation text
- "Search Online" link for questions they got wrong

Overall score display at top. Follows pattern of `math_test_review.html`.

Data: questions and submissions are passed from the page route (server-side rendered).

**Step 2: Commit**

```bash
git add templates/science_test_review.html && git commit -m "feat: add science test review template"
```

---

### Task 10: Parent Dashboard — Wire Up Science Tab

**Files:**
- Modify: `templates/parent_home.html:413-420` (replace placeholder)
- Modify: `templates/parent_home.html` (add JS functions in script block)

**Step 1: Replace the science tab placeholder**

Replace lines 413-420 (the placeholder panel) with actual science content:

```html
        <!-- Science tab -->
        <div class="tab-panel" data-panel="science" id="panel-science">
            <div class="quick-links" id="science-links"></div>
            <div class="dash-card">
                <h3>Question Bank</h3>
                <div id="science-question-stats"><span class="empty-msg">Loading...</span></div>
            </div>
            <div class="dash-card">
                <h3>Pending Study Sessions</h3>
                <div id="science-study-list"><span class="empty-msg">Loading...</span></div>
            </div>
            <div class="dash-card">
                <h3>Pending Tests</h3>
                <div id="science-test-pending-list"><span class="empty-msg">Loading...</span></div>
            </div>
            <div class="dash-card">
                <h3>Completed Tests</h3>
                <div id="science-test-completed-list"><span class="empty-msg">Loading...</span></div>
            </div>
        </div>
```

**Step 2: Add JS to load science data and handle uploads**

In the `<script>` block of `parent_home.html`, add a `loadScienceTab(childId)` function that:
- Fetches `GET /api/children/${childId}/science-questions` and shows category breakdown
- Fetches `GET /api/children/${childId}/science-study-sessions` and lists them
- Fetches `GET /api/children/${childId}/science-tests` and lists pending/completed
- Renders quick-links: "Import Questions" (opens modal with PDF upload), "Create Study Session" (opens modal to select questions), "Create Test" (opens modal to select questions + timer)
- Wire up the "Import Questions" flow: upload PDF -> show preview table -> allow editing -> save

**Step 3: Add modals for import/create**

Add modal HTML for:
1. **Import modal**: PDF file input + upload button -> shows parsed questions table with edit/delete per row -> "Save All" button
2. **Create study session modal**: question list with checkboxes (filterable by category), title input, create button
3. **Create test modal**: question list with checkboxes (filterable by category), title input, timer options, create button

**Step 4: Wire `switchTab` to call `loadScienceTab`**

In the existing `switchTab()` JS function, add a case for `'science'` that calls `loadScienceTab(currentChildId)`.

**Step 5: Commit**

```bash
git add templates/parent_home.html && git commit -m "feat: wire up science tab in parent dashboard"
```

---

### Task 11: Child Dashboard — Add Science Section

**Files:**
- Modify: `templates/dashboard.html` (add science study sessions and tests to child view)

**Step 1: Add science sections to child dashboard**

Look at how math tests and study sessions are displayed in the child dashboard. Add similar sections for:
- Pending science study sessions (link to `/child/{id}/science-study/{session_id}`)
- Pending science tests (link to `/child/{id}/science-test/{test_id}`)

**Step 2: Add backend data**

Modify the home route in `app.py` that renders `dashboard.html` to also fetch science study sessions and tests for the child.

**Step 3: Commit**

```bash
git add templates/dashboard.html app.py && git commit -m "feat: add science section to child dashboard"
```

---

### Task 12: Learning Plan Integration

**Files:**
- Modify: `app.py` (add learning plan item routes for science)
- Modify: `templates/manage_plan.html` (add science options)
- Modify: `templates/view_plan.html` (show science items)

**Step 1: Add learning plan routes for science**

Follow the pattern of `add_plan_math_test` and `add_plan_writing_test`:

```python
@app.route("/api/learning-plans/<int:plan_id>/items/science-study", methods=["POST"])
@parent_required
def add_plan_science_study(plan_id):
    # Create science study session linked to plan
    # Follow pattern of add_plan_writing_test
    ...

@app.route("/api/learning-plans/<int:plan_id>/items/science-test", methods=["POST"])
@parent_required
def add_plan_science_test(plan_id):
    # Create science test linked to plan
    # Follow pattern of add_plan_math_test
    ...
```

**Step 2: Update plan management template**

Add science study and science test as options when adding items to a learning plan.

**Step 3: Update plan view template**

Show science study sessions and tests in the plan item list with links to the correct pages.

**Step 4: Commit**

```bash
git add app.py templates/manage_plan.html templates/view_plan.html && git commit -m "feat: integrate science into learning plans"
```

---

### Task 13: End-to-End Testing

**Step 1: Manual test the full flow**

1. Start the app: `python3 app.py`
2. Log in as parent
3. Go to Science tab
4. Upload `m_round01.pdf`
5. Verify all 50 questions parsed correctly
6. Edit a question, delete a question
7. Save questions
8. Create a study session with a subset of questions
9. Switch to child account
10. Open the study session, flip through flashcards, click "Search Online"
11. Complete the study session
12. Switch back to parent
13. Create a test from some questions
14. Switch to child, take the test
15. Submit and review results
16. Verify learning plan integration works

**Step 2: Fix any issues found**

**Step 3: Final commit**

```bash
git add -A && git commit -m "feat: complete science bowl study and test feature"
```
