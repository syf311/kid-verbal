import json
import math
import os
import re
import time
import threading
import tempfile
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, get_db
from dictionary import fetch_definition
from test_engine import get_test_words, generate_choices, generate_word_choices, update_progress, record_test_session, update_science_progress
from ocr import extract_text
from pdf_parser import parse_answer_pdf, parse_grid_answer_pdf, extract_row_answers, pdf_page_to_png
from science_parser import parse_science_bowl_pdf

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "REDACTED-SECRET"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Store active sessions
active_sessions = {}

# RSS feed sources for browsing articles
RSS_FEEDS = [
    {"name": "Science News for Students", "url": "https://www.sciencenewsforstudents.org/feed", "category": "Science"},
    {"name": "Time for Kids", "url": "https://www.timeforkids.com/feed/", "category": "News"},
    {"name": "Curious Kids", "url": "https://theconversation.com/us/topics/curious-kids-us-74795/articles.atom", "category": "General"},
    {"name": "NYT Education", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Education.xml", "category": "News"},
]

# Cache for RSS feed results: {feed_url: {"articles": [...], "fetched_at": timestamp}}
_feed_cache = {}


# ── Science mastery helper ──

def compute_mastery_status(q_dict, cutoff):
    """Compute mastery status for a science question dict.
    Expects keys: m_last_tested, m_wrong_count, m_correct_count, m_streak, m_difficulty_level, m_last_correct_at.
    cutoff: datetime string for 7-day review window.
    Returns one of: 'never', 'wrong', 'mastered', 'due', 'good'.
    """
    if not q_dict.get("m_last_tested"):
        return "never"
    if q_dict["m_wrong_count"] > q_dict["m_correct_count"]:
        return "wrong"
    if q_dict["m_streak"] == 0 and q_dict["m_last_tested"]:
        return "wrong"
    if q_dict["m_difficulty_level"] >= 4:
        return "mastered"
    if not q_dict.get("m_last_correct_at") or q_dict["m_last_correct_at"] < cutoff:
        return "due"
    return "good"


# ── Auth helpers ──

def get_current_account():
    if "account_id" not in session:
        return None
    conn = get_db()
    account = conn.execute(
        "SELECT * FROM account WHERE id = ?", (session["account_id"],)
    ).fetchone()
    conn.close()
    return dict(account) if account else None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "account_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def parent_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "account_id" not in session:
            return redirect(url_for("login_page"))
        if session.get("role") != "parent":
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated


def check_plan_completion(plan_id, conn):
    """Check if all items in a learning plan are completed; if so, mark the plan completed."""
    items = conn.execute(
        "SELECT item_type, item_id FROM learning_plan_item WHERE plan_id = ?", (plan_id,)
    ).fetchall()
    if not items:
        return
    for item in items:
        if item["item_type"] == "study_session":
            row = conn.execute("SELECT status FROM study_session WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "reading_assignment":
            row = conn.execute("SELECT status FROM reading_assignment WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "math_test":
            row = conn.execute("SELECT status FROM math_test WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "parent_test":
            row = conn.execute("SELECT status FROM parent_test WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "writing_test":
            row = conn.execute("SELECT status FROM writing_test WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "science_study":
            row = conn.execute("SELECT status FROM science_study_session WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "science_test":
            row = conn.execute("SELECT status FROM science_test WHERE id = ?", (item["item_id"],)).fetchone()
        elif item["item_type"] == "math_bank_test":
            row = conn.execute("SELECT status FROM math_bank_test WHERE id = ?", (item["item_id"],)).fetchone()
        else:
            continue
        if not row or row["status"] != "completed":
            return
    conn.execute(
        "UPDATE learning_plan SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'released'",
        (plan_id,)
    )
    conn.commit()


# ── Auth routes ──

@app.route("/login", methods=["GET"])
def login_page():
    if "account_id" in session:
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_submit():
    data = request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")

    conn = get_db()
    account = conn.execute(
        "SELECT * FROM account WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not account or not check_password_hash(account["password_hash"], password):
        return render_template("login.html", error="Invalid username or password")

    session["account_id"] = account["id"]
    session["role"] = account["role"]
    session["username"] = account["username"]
    if account["child_id"]:
        session["child_id"] = account["child_id"]

    return redirect(url_for("home"))


@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def register_submit():
    data = request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "parent")

    if not username or not password:
        return render_template("register.html", error="Username and password required")

    if len(password) < 4:
        return render_template("register.html", error="Password must be at least 4 characters")

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM account WHERE username = ?", (username,)
    ).fetchone()

    if existing:
        conn.close()
        return render_template("register.html", error="Username already taken")

    conn.execute(
        "INSERT INTO account (username, password_hash, role) VALUES (?, ?, ?)",
        (username, generate_password_hash(password, method='pbkdf2:sha256'), role)
    )
    conn.commit()
    conn.close()

    return redirect(url_for("login_page"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Home route ──

@app.route("/")
@login_required
def home():
    if session.get("role") == "parent":
        return redirect(url_for("parent_home"))
    else:
        child_id = session.get("child_id")
        if child_id:
            return redirect(url_for("child_dashboard", child_id=child_id))
        return "No child profile linked", 400


# ── Parent routes ──

@app.route("/parent")
@parent_required
def parent_home():
    conn = get_db()
    children = conn.execute(
        "SELECT * FROM child ORDER BY name"
    ).fetchall()

    # Get child accounts
    child_accounts = conn.execute(
        "SELECT a.id, a.username, a.child_id, c.name as child_name "
        "FROM account a LEFT JOIN child c ON a.child_id = c.id "
        "WHERE a.role = 'child'"
    ).fetchall()

    conn.close()
    return render_template(
        "parent_home.html",
        children=[dict(c) for c in children],
        child_accounts=[dict(a) for a in child_accounts],
        account=get_current_account()
    )


@app.route("/api/children/<int:child_id>/dashboard-summary", methods=["GET"])
@parent_required
def child_dashboard_summary(child_id):
    conn = get_db()

    word_count = conn.execute(
        "SELECT COUNT(*) FROM word WHERE child_id = ?", (child_id,)
    ).fetchone()[0]

    study_sessions = conn.execute(
        """SELECT ss.id, ss.title, ss.status, ss.created_at, ss.learning_plan_id,
                  lp.title as plan_title,
                  (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
           FROM study_session ss
           LEFT JOIN learning_plan lp ON ss.learning_plan_id = lp.id
           WHERE ss.child_id = ?
           ORDER BY ss.created_at DESC
           LIMIT 10""",
        (child_id,)
    ).fetchall()

    parent_tests = conn.execute(
        """SELECT pt.id, pt.title, pt.status, pt.created_at, pt.source_type,
                  (SELECT COUNT(*) FROM parent_test_word WHERE parent_test_id = pt.id) as word_count,
                  (SELECT id FROM test_session WHERE parent_test_id = pt.id LIMIT 1) as test_session_id
           FROM parent_test pt
           WHERE pt.child_id = ?
           ORDER BY pt.created_at DESC
           LIMIT 10""",
        (child_id,)
    ).fetchall()

    pending_assignments = conn.execute(
        """SELECT ra.id, ra.material_id, ra.status, ra.created_at, ra.learning_plan_id,
                  lp.title as plan_title,
                  rm.title as material_title,
                  (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           LEFT JOIN learning_plan lp ON ra.learning_plan_id = lp.id
           WHERE ra.child_id = ? AND ra.status = 'pending'
           ORDER BY ra.created_at DESC""",
        (child_id,)
    ).fetchall()

    completed_assignments = conn.execute(
        """SELECT ra.id, ra.material_id, ra.status, ra.created_at, ra.completed_at, ra.learning_plan_id,
                  lp.title as plan_title,
                  rm.title as material_title,
                  (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count,
                  (SELECT COUNT(*) FROM reading_assignment_answer WHERE assignment_id = ra.id AND is_correct = 1) as correct_count
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           LEFT JOIN learning_plan lp ON ra.learning_plan_id = lp.id
           WHERE ra.child_id = ? AND ra.status = 'completed'
           ORDER BY ra.completed_at DESC
           LIMIT 10""",
        (child_id,)
    ).fetchall()

    math_tests = conn.execute(
        """SELECT mt.id, mt.title, mt.status, mt.total_questions, mt.created_at,
                  mt.timer_mode, mt.time_limit_seconds, mt.learning_plan_id,
                  lp.title as plan_title,
                  (SELECT id FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as submission_id,
                  (SELECT score FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as score,
                  (SELECT correct_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as correct_count,
                  (SELECT total_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as total_count,
                  (SELECT time_taken_seconds FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as time_taken_seconds
           FROM math_test mt
           LEFT JOIN learning_plan lp ON mt.learning_plan_id = lp.id
           WHERE mt.child_id = ?
           ORDER BY mt.created_at DESC
           LIMIT 20""",
        (child_id,)
    ).fetchall()

    writing_tests = conn.execute(
        """SELECT wt.id, wt.topic_text, wt.status, wt.created_at,
                  wt.timer_mode, wt.time_limit_seconds, wt.min_word_count, wt.max_word_count,
                  wt.learning_plan_id,
                  lp.title as plan_title,
                  (SELECT id FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as submission_id,
                  (SELECT word_count FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as word_count,
                  (SELECT score FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as score,
                  (SELECT time_taken_seconds FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as time_taken_seconds
           FROM writing_test wt
           LEFT JOIN learning_plan lp ON wt.learning_plan_id = lp.id
           WHERE wt.child_id = ?
           ORDER BY wt.created_at DESC
           LIMIT 20""",
        (child_id,)
    ).fetchall()

    math_bank_tests = conn.execute(
        """SELECT mbt.id, mbt.title, mbt.status, mbt.created_at,
                  mbt.timer_mode, mbt.time_limit_seconds, mbt.learning_plan_id,
                  lp.title as plan_title,
                  (SELECT COUNT(*) FROM math_bank_test_question WHERE test_id = mbt.id) as question_count,
                  (SELECT score FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as score,
                  (SELECT correct_count FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as correct_count,
                  (SELECT total_count FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as total_count
           FROM math_bank_test mbt
           LEFT JOIN learning_plan lp ON mbt.learning_plan_id = lp.id
           WHERE mbt.child_id = ?
           ORDER BY mbt.created_at DESC
           LIMIT 20""",
        (child_id,)
    ).fetchall()

    learning_plans = conn.execute(
        """SELECT lp.*,
                  (SELECT COUNT(*) FROM learning_plan_item WHERE plan_id = lp.id) as item_count,
                  (SELECT COUNT(*) FROM learning_plan_item lpi
                   WHERE lpi.plan_id = lp.id AND (
                       (lpi.item_type = 'study_session' AND (SELECT status FROM study_session WHERE id = lpi.item_id) = 'completed') OR
                       (lpi.item_type = 'reading_assignment' AND (SELECT status FROM reading_assignment WHERE id = lpi.item_id) = 'completed') OR
                       (lpi.item_type = 'math_test' AND (SELECT status FROM math_test WHERE id = lpi.item_id) = 'completed') OR
                       (lpi.item_type = 'writing_test' AND (SELECT status FROM writing_test WHERE id = lpi.item_id) = 'completed') OR
                       (lpi.item_type = 'math_bank_test' AND (SELECT status FROM math_bank_test WHERE id = lpi.item_id) = 'completed')
                   )) as completed_item_count
           FROM learning_plan lp
           WHERE lp.child_id = ?
           ORDER BY lp.created_at DESC""",
        (child_id,)
    ).fetchall()

    conn.close()
    return jsonify({
        "word_count": word_count,
        "study_sessions": [dict(s) for s in study_sessions],
        "parent_tests": [dict(t) for t in parent_tests],
        "pending_assignments": [dict(a) for a in pending_assignments],
        "completed_assignments": [dict(a) for a in completed_assignments],
        "math_tests": [dict(t) for t in math_tests],
        "math_bank_tests": [dict(t) for t in math_bank_tests],
        "writing_tests": [dict(t) for t in writing_tests],
        "learning_plans": [dict(p) for p in learning_plans],
    })


@app.route("/api/child-accounts", methods=["POST"])
@parent_required
def create_child_account():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    child_id = data.get("child_id")

    if not username or not password or not child_id:
        return jsonify({"error": "Username, password, and child profile required"}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM account WHERE username = ?", (username,)
    ).fetchone()

    if existing:
        conn.close()
        return jsonify({"error": "Username already taken"}), 400

    conn.execute(
        "INSERT INTO account (username, password_hash, role, child_id) VALUES (?, ?, 'child', ?)",
        (username, generate_password_hash(password, method='pbkdf2:sha256'), child_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "created"}), 201


@app.route("/parent/child/<int:child_id>/study/new")
@parent_required
def create_study_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("create_study.html", child=dict(child))


@app.route("/parent/child/<int:child_id>/test/new")
@parent_required
def create_test_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("create_test.html", child=dict(child))


# ── Study session API ──

@app.route("/api/study-sessions", methods=["POST"])
@parent_required
def create_study_session():
    data = request.json
    child_id = data.get("child_id")
    title = data.get("title") or datetime.now().strftime("%m/%d/%Y")
    word_ids = data.get("word_ids", [])

    if not child_id or not word_ids:
        return jsonify({"error": "child_id and word_ids required"}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO study_session (child_id, created_by, title) VALUES (?, ?, ?)",
        (child_id, session["account_id"], title)
    )
    session_id = cursor.lastrowid

    for wid in word_ids:
        conn.execute(
            "INSERT INTO study_session_word (session_id, word_id) VALUES (?, ?)",
            (session_id, wid)
        )

    conn.commit()
    conn.close()

    return jsonify({"id": session_id}), 201


@app.route("/api/children/<int:child_id>/study-sessions", methods=["GET"])
@login_required
def get_study_sessions(child_id):
    conn = get_db()
    sessions = conn.execute(
        """SELECT ss.*, a.username as created_by_name,
                  (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
           FROM study_session ss
           JOIN account a ON ss.created_by = a.id
           WHERE ss.child_id = ?
           ORDER BY ss.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(s) for s in sessions])


@app.route("/api/study-sessions/<int:session_id>/words", methods=["GET"])
@login_required
def get_study_session_words(session_id):
    conn = get_db()
    words = conn.execute(
        """SELECT w.id, w.word, w.definition, w.example_sentence, w.image_path,
                  COALESCE(wp.difficulty_level, 1) as difficulty_level
           FROM study_session_word ssw
           JOIN word w ON ssw.word_id = w.id
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
           WHERE ssw.session_id = ?""",
        (session_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(w) for w in words])


@app.route("/api/study-sessions/<int:session_id>/complete", methods=["POST"])
@login_required
def complete_study_session(session_id):
    conn = get_db()
    conn.execute(
        "UPDATE study_session SET status = 'completed' WHERE id = ?",
        (session_id,)
    )
    # Check if this study session belongs to a learning plan
    ss = conn.execute("SELECT * FROM study_session WHERE id = ?", (session_id,)).fetchone()
    plan_id = ss["learning_plan_id"] if ss else None

    test_id = None
    if plan_id:
        # Auto-create a vocabulary test from this study session's words
        words = conn.execute(
            "SELECT word_id FROM study_session_word WHERE session_id = ?", (session_id,)
        ).fetchall()
        if words:
            title = f"Vocab Test: {ss['title'] or 'Vocabulary'}"
            cursor = conn.execute(
                "INSERT INTO parent_test (child_id, created_by, title, source_type, source_id) VALUES (?, ?, ?, 'study_session', ?)",
                (ss["child_id"], ss["created_by"], title, session_id)
            )
            test_id = cursor.lastrowid
            for w in words:
                conn.execute(
                    "INSERT INTO parent_test_word (parent_test_id, word_id) VALUES (?, ?)",
                    (test_id, w["word_id"])
                )
            # Add the test to the same learning plan
            max_sort = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'parent_test', ?, ?)",
                (plan_id, test_id, max_sort + 1)
            )

        check_plan_completion(plan_id, conn)

    conn.commit()
    conn.close()
    return jsonify({"status": "completed", "test_id": test_id})


@app.route("/api/study-sessions/<int:session_id>", methods=["DELETE"])
@parent_required
def delete_study_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM study_session_word WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM study_session WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return "", 204


# ── Parent test API ──

@app.route("/api/parent-tests", methods=["POST"])
@parent_required
def create_parent_test():
    data = request.json
    child_id = data.get("child_id")
    title = data.get("title") or datetime.now().strftime("%m/%d/%Y")
    word_ids = data.get("word_ids", [])

    if not child_id or not word_ids:
        return jsonify({"error": "child_id and word_ids required"}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO parent_test (child_id, created_by, title, source_type) VALUES (?, ?, ?, 'custom')",
        (child_id, session["account_id"], title)
    )
    pt_id = cursor.lastrowid

    for wid in word_ids:
        conn.execute(
            "INSERT INTO parent_test_word (parent_test_id, word_id) VALUES (?, ?)",
            (pt_id, wid)
        )

    conn.commit()
    conn.close()
    return jsonify({"id": pt_id}), 201


@app.route("/api/parent-tests/from-study/<int:study_id>", methods=["POST"])
@parent_required
def create_parent_test_from_study(study_id):
    conn = get_db()
    study = conn.execute("SELECT * FROM study_session WHERE id = ?", (study_id,)).fetchone()
    if not study:
        conn.close()
        return jsonify({"error": "Study session not found"}), 404

    # Copy words from study session
    words = conn.execute(
        "SELECT word_id FROM study_session_word WHERE session_id = ?", (study_id,)
    ).fetchall()

    if not words:
        conn.close()
        return jsonify({"error": "No words in study session"}), 400

    title = f"Test: {study['title'] or datetime.now().strftime('%m/%d/%Y')}"
    cursor = conn.execute(
        "INSERT INTO parent_test (child_id, created_by, title, source_type, source_id) VALUES (?, ?, ?, 'study_session', ?)",
        (study["child_id"], session["account_id"], title, study_id)
    )
    pt_id = cursor.lastrowid

    for w in words:
        conn.execute(
            "INSERT INTO parent_test_word (parent_test_id, word_id) VALUES (?, ?)",
            (pt_id, w["word_id"])
        )

    conn.commit()
    conn.close()
    return jsonify({"id": pt_id}), 201


@app.route("/api/children/<int:child_id>/parent-tests", methods=["GET"])
@login_required
def get_parent_tests(child_id):
    conn = get_db()
    tests = conn.execute(
        """SELECT pt.*, a.username as created_by_name,
                  (SELECT COUNT(*) FROM parent_test_word WHERE parent_test_id = pt.id) as word_count,
                  (SELECT id FROM test_session WHERE parent_test_id = pt.id LIMIT 1) as test_session_id
           FROM parent_test pt
           JOIN account a ON pt.created_by = a.id
           WHERE pt.child_id = ?
           ORDER BY pt.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tests])


@app.route("/api/parent-tests/<int:pt_id>/words", methods=["GET"])
@login_required
def get_parent_test_words(pt_id):
    conn = get_db()
    words = conn.execute(
        """SELECT w.id, w.word, w.definition, w.example_sentence, w.image_path,
                  COALESCE(wp.difficulty_level, 1) as difficulty_level
           FROM parent_test_word ptw
           JOIN word w ON ptw.word_id = w.id
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
           WHERE ptw.parent_test_id = ?""",
        (pt_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(w) for w in words])


@app.route("/api/parent-tests/<int:pt_id>/complete", methods=["POST"])
@login_required
def complete_parent_test(pt_id):
    conn = get_db()
    conn.execute(
        "UPDATE parent_test SET status = 'completed' WHERE id = ?",
        (pt_id,)
    )
    # Check if this parent test belongs to a learning plan
    plan_item = conn.execute(
        "SELECT plan_id FROM learning_plan_item WHERE item_type = 'parent_test' AND item_id = ?",
        (pt_id,)
    ).fetchone()
    if plan_item:
        check_plan_completion(plan_item["plan_id"], conn)
    conn.commit()
    conn.close()
    return jsonify({"status": "completed"})


@app.route("/api/parent-tests/<int:pt_id>", methods=["DELETE"])
@parent_required
def delete_parent_test(pt_id):
    conn = get_db()
    conn.execute("DELETE FROM parent_test_word WHERE parent_test_id = ?", (pt_id,))
    conn.execute("DELETE FROM parent_test WHERE id = ?", (pt_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/children", methods=["GET"])
def get_children():
    conn = get_db()
    children = conn.execute(
        "SELECT id, name, avatar FROM child ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(c) for c in children])


@app.route("/api/children", methods=["POST"])
def create_child():
    data = request.json
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO child (name, avatar, grade_level) VALUES (?, ?, ?)",
        (data["name"], data.get("avatar", "👤"), data.get("grade_level"))
    )
    child_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": child_id}), 201


@app.route("/api/children/<int:child_id>", methods=["GET"])
def get_child(child_id):
    conn = get_db()
    child = conn.execute(
        "SELECT * FROM child WHERE id = ?", (child_id,)
    ).fetchone()
    conn.close()
    if not child:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(child))


@app.route("/api/children/<int:child_id>", methods=["DELETE"])
@parent_required
def delete_child(child_id):
    conn = get_db()
    # Delete related data
    conn.execute("DELETE FROM learning_plan_item WHERE plan_id IN (SELECT id FROM learning_plan WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM learning_plan WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM math_test_submission WHERE math_test_id IN (SELECT id FROM math_test WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM math_test WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM writing_test_submission WHERE writing_test_id IN (SELECT id FROM writing_test WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM writing_test WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM writing_topic WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM reading_assignment_answer WHERE assignment_id IN (SELECT id FROM reading_assignment WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM reading_assignment WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM parent_test_word WHERE parent_test_id IN (SELECT id FROM parent_test WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM parent_test WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM study_session_word WHERE session_id IN (SELECT id FROM study_session WHERE child_id = ?)", (child_id,))
    conn.execute("DELETE FROM study_session WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM word_progress WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM badge WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM test_session WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM word WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM account WHERE child_id = ?", (child_id,))
    conn.execute("DELETE FROM child WHERE id = ?", (child_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/child/<int:child_id>")
@login_required
def child_dashboard(child_id):
    conn = get_db()
    child = conn.execute(
        "SELECT * FROM child WHERE id = ?", (child_id,)
    ).fetchone()
    if not child:
        return "Child not found", 404

    word_count = conn.execute(
        "SELECT COUNT(*) FROM word WHERE child_id = ?", (child_id,)
    ).fetchone()[0]

    role = session.get("role", "parent")

    recent_sessions = conn.execute(
        """SELECT id, test_type, score, correct_count, total_count, created_at
           FROM test_session WHERE child_id = ?
           ORDER BY created_at DESC LIMIT 5""",
        (child_id,)
    ).fetchall()

    if role == "parent":
        # Get pending study sessions
        study_sessions = conn.execute(
            """SELECT ss.*, a.username as created_by_name,
                      (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
               FROM study_session ss
               JOIN account a ON ss.created_by = a.id
               WHERE ss.child_id = ? AND ss.status != 'completed' AND ss.learning_plan_id IS NULL
               ORDER BY ss.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get completed study sessions
        completed_sessions = conn.execute(
            """SELECT ss.*, a.username as created_by_name,
                      (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
               FROM study_session ss
               JOIN account a ON ss.created_by = a.id
               WHERE ss.child_id = ? AND ss.status = 'completed' AND ss.learning_plan_id IS NULL
               ORDER BY ss.created_at DESC
               LIMIT 20""",
            (child_id,)
        ).fetchall()

        # Get pending parent tests
        parent_tests = conn.execute(
            """SELECT pt.*, a.username as created_by_name,
                      (SELECT COUNT(*) FROM parent_test_word WHERE parent_test_id = pt.id) as word_count
               FROM parent_test pt
               JOIN account a ON pt.created_by = a.id
               WHERE pt.child_id = ? AND pt.status != 'completed'
               ORDER BY pt.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get pending reading assignments
        pending_assignments = conn.execute(
            """SELECT ra.*, rm.title as material_title,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count
               FROM reading_assignment ra
               JOIN reading_material rm ON ra.material_id = rm.id
               WHERE ra.child_id = ? AND ra.status = 'pending' AND ra.learning_plan_id IS NULL
               ORDER BY ra.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get completed reading assignments
        completed_assignments = conn.execute(
            """SELECT ra.*, rm.title as material_title,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count,
                      (SELECT COUNT(*) FROM reading_assignment_answer WHERE assignment_id = ra.id AND is_correct = 1) as correct_count
               FROM reading_assignment ra
               JOIN reading_material rm ON ra.material_id = rm.id
               WHERE ra.child_id = ? AND ra.status = 'completed' AND ra.learning_plan_id IS NULL
               ORDER BY ra.completed_at DESC
               LIMIT 20""",
            (child_id,)
        ).fetchall()

        # Get pending math tests
        math_tests = conn.execute(
            """SELECT mt.id, mt.title, mt.total_questions, mt.status, mt.created_at
               FROM math_test mt
               WHERE mt.child_id = ? AND mt.status = 'pending' AND mt.learning_plan_id IS NULL
               ORDER BY mt.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get completed math tests
        completed_math_tests = conn.execute(
            """SELECT mt.id, mt.title, mt.total_questions, mt.created_at,
                      (SELECT correct_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as correct_count,
                      (SELECT total_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as total_count
               FROM math_test mt
               WHERE mt.child_id = ? AND mt.status = 'completed' AND mt.learning_plan_id IS NULL
               ORDER BY mt.created_at DESC LIMIT 20""",
            (child_id,)
        ).fetchall()

        # Get pending writing tests (including revision)
        writing_tests = conn.execute(
            """SELECT wt.id, wt.topic_text, wt.status, wt.created_at
               FROM writing_test wt
               WHERE wt.child_id = ? AND wt.status IN ('pending', 'revision') AND wt.learning_plan_id IS NULL
               ORDER BY wt.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get completed writing tests
        completed_writing_tests = conn.execute(
            """SELECT wt.id, wt.topic_text, wt.created_at,
                      (SELECT word_count FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as word_count,
                      (SELECT score FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as score
               FROM writing_test wt
               WHERE wt.child_id = ? AND wt.status = 'completed' AND wt.learning_plan_id IS NULL
               ORDER BY wt.created_at DESC LIMIT 20""",
            (child_id,)
        ).fetchall()

        # Get pending science study sessions
        science_study_sessions = conn.execute(
            """SELECT ss.id, ss.title, ss.status, ss.created_at,
                      (SELECT COUNT(*) FROM science_study_session_question WHERE session_id = ss.id) as question_count
               FROM science_study_session ss
               WHERE ss.child_id = ? AND ss.status = 'pending' AND ss.learning_plan_id IS NULL
               ORDER BY ss.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get pending science tests
        science_tests = conn.execute(
            """SELECT st.id, st.title, st.status, st.created_at,
                      (SELECT COUNT(*) FROM science_test_question WHERE test_id = st.id) as question_count
               FROM science_test st
               WHERE st.child_id = ? AND st.status = 'pending' AND st.learning_plan_id IS NULL
               ORDER BY st.created_at DESC""",
            (child_id,)
        ).fetchall()

        # Get completed science tests
        completed_science_tests = conn.execute(
            """SELECT st.id, st.title, st.created_at,
                      (SELECT correct_count FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as correct_count,
                      (SELECT total_count FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as total_count,
                      (SELECT score FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as score
               FROM science_test st
               WHERE st.child_id = ? AND st.status = 'completed' AND st.learning_plan_id IS NULL
               ORDER BY st.created_at DESC LIMIT 20""",
            (child_id,)
        ).fetchall()
    else:
        # Children only see learning plans, not individual items
        study_sessions = []
        completed_sessions = []
        parent_tests = []
        pending_assignments = []
        completed_assignments = []
        math_tests = []
        completed_math_tests = []
        writing_tests = []
        completed_writing_tests = []
        science_study_sessions = []
        science_tests = []
        completed_science_tests = []

    # Get learning plans (released or completed)
    learning_plans = conn.execute(
        """SELECT lp.*,
                  (SELECT COUNT(*) FROM learning_plan_item WHERE plan_id = lp.id) as item_count
           FROM learning_plan lp
           WHERE lp.child_id = ? AND lp.status IN ('released', 'completed', 'reviewed')
           ORDER BY lp.created_at DESC""",
        (child_id,)
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        child=dict(child),
        word_count=word_count,
        recent_sessions=[dict(s) for s in recent_sessions],
        study_sessions=[dict(s) for s in study_sessions],
        completed_sessions=[dict(s) for s in completed_sessions],
        parent_tests=[dict(t) for t in parent_tests],
        pending_assignments=[dict(a) for a in pending_assignments],
        completed_assignments=[dict(a) for a in completed_assignments],
        math_tests=[dict(t) for t in math_tests],
        completed_math_tests=[dict(t) for t in completed_math_tests],
        writing_tests=[dict(t) for t in writing_tests],
        completed_writing_tests=[dict(t) for t in completed_writing_tests],
        science_study_sessions=[dict(s) for s in science_study_sessions],
        science_tests=[dict(t) for t in science_tests],
        completed_science_tests=[dict(t) for t in completed_science_tests],
        learning_plans=[dict(p) for p in learning_plans],
        role=role
    )


@app.route("/child/<int:child_id>/words")
def word_list(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("words.html", child=dict(child))


@app.route("/api/children/<int:child_id>/words", methods=["GET"])
def get_words(child_id):
    conn = get_db()
    words = conn.execute(
        """SELECT w.*, wp.correct_count, wp.wrong_count, wp.difficulty_level,
                  wp.last_tested, wp.last_correct_at,
                  rm.title as source_material_title, rm.source_url as source_material_url
           FROM word w
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
           LEFT JOIN reading_material rm ON w.source_material_id = rm.id
           WHERE w.child_id = ?
           ORDER BY w.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(w) for w in words])


@app.route("/api/children/<int:child_id>/words", methods=["POST"])
def add_word(child_id):
    data = request.json
    word = data["word"].strip().lower()

    # Auto-fetch definition if not provided
    definition = data.get("definition", "")
    example = data.get("example_sentence", "")

    if not definition:
        result = fetch_definition(word)
        if result:
            definition = result["definition"]
            if not example:
                example = result.get("example", "")

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO word (child_id, word, definition, example_sentence)
           VALUES (?, ?, ?, ?)""",
        (child_id, word, definition, example)
    )
    word_id = cursor.lastrowid

    # Create initial progress record
    conn.execute(
        """INSERT INTO word_progress (child_id, word_id, difficulty_level)
           VALUES (?, ?, 1)""",
        (child_id, word_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"id": word_id, "definition": definition, "example": example}), 201


@app.route("/api/words/<int:word_id>", methods=["PUT"])
def update_word(word_id):
    data = request.json
    conn = get_db()
    if "word" in data:
        conn.execute(
            """UPDATE word SET word = ?, definition = ?, example_sentence = ? WHERE id = ?""",
            (data.get("word", "").strip().lower(), data.get("definition", ""), data.get("example_sentence", ""), word_id)
        )
    else:
        conn.execute(
            """UPDATE word SET definition = ?, example_sentence = ? WHERE id = ?""",
            (data.get("definition", ""), data.get("example_sentence", ""), word_id)
        )
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/words/<int:word_id>/refresh", methods=["POST"])
def refresh_word_definition(word_id):
    """Re-fetch definition from dictionary API."""
    conn = get_db()
    word = conn.execute("SELECT word FROM word WHERE id = ?", (word_id,)).fetchone()
    if not word:
        conn.close()
        return jsonify({"error": "Word not found"}), 404

    result = fetch_definition(word["word"])
    if result:
        definition = result["definition"]
        example = result.get("example", "")
        conn.execute(
            "UPDATE word SET definition = ?, example_sentence = ? WHERE id = ?",
            (definition, example, word_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"definition": definition, "example": example})

    conn.close()
    return jsonify({"error": "Definition not found"}), 404


@app.route("/api/words/<int:word_id>/image", methods=["POST"])
def upload_word_image(word_id):
    """Upload an image for a word definition."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    # Save with unique name
    filename = f"word_{word_id}_{secure_filename(file.filename)}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Update database
    conn = get_db()
    conn.execute("UPDATE word SET image_path = ? WHERE id = ?", (filename, word_id))
    conn.commit()
    conn.close()

    return jsonify({"image_path": filename})


@app.route("/api/words/<int:word_id>/image", methods=["DELETE"])
def delete_word_image(word_id):
    """Remove image from a word definition."""
    conn = get_db()
    word = conn.execute("SELECT image_path FROM word WHERE id = ?", (word_id,)).fetchone()
    if word and word["image_path"]:
        # Delete file
        filepath = os.path.join(UPLOAD_FOLDER, word["image_path"])
        if os.path.exists(filepath):
            os.remove(filepath)
        conn.execute("UPDATE word SET image_path = NULL WHERE id = ?", (word_id,))
        conn.commit()
    conn.close()
    return "", 204


@app.route("/uploads/<filename>")
def serve_upload(filename):
    """Serve uploaded files."""
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/words/<int:word_id>", methods=["DELETE"])
def delete_word(word_id):
    conn = get_db()
    conn.execute("DELETE FROM word_progress WHERE word_id = ?", (word_id,))
    conn.execute("DELETE FROM word WHERE id = ?", (word_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/children/<int:child_id>/words/import-pairs", methods=["POST"])
def import_word_pairs(child_id):
    data = request.json
    pairs = data.get("pairs", [])

    if not pairs:
        return jsonify({"error": "No word pairs provided"}), 400

    conn = get_db()
    existing = set(
        row[0] for row in conn.execute(
            "SELECT word FROM word WHERE child_id = ?", (child_id,)
        ).fetchall()
    )

    imported = 0
    skipped = 0
    for pair in pairs:
        word = pair.get("word", "").strip().lower()
        definition = pair.get("definition", "").strip()
        if not word:
            continue
        if word in existing:
            skipped += 1
            continue
        cursor = conn.execute(
            "INSERT INTO word (child_id, word, definition) VALUES (?, ?, ?)",
            (child_id, word, definition)
        )
        conn.execute(
            "INSERT INTO word_progress (child_id, word_id, difficulty_level) VALUES (?, ?, 1)",
            (child_id, cursor.lastrowid)
        )
        existing.add(word)
        imported += 1

    conn.commit()
    conn.close()
    return jsonify({"imported": imported, "skipped": skipped})


@app.route("/api/children/<int:child_id>/words/batch", methods=["POST"])
def batch_import_words(child_id):
    """Import multiple words at once. Accepts JSON with 'words' array."""
    data = request.json
    words_input = data.get("words", [])

    if isinstance(words_input, str):
        # Handle newline-separated string
        words_input = [w.strip() for w in words_input.split("\n") if w.strip()]

    results = []
    conn = get_db()

    for word_text in words_input:
        word = word_text.strip().lower()
        if not word:
            continue

        # Check if word already exists for this child
        existing = conn.execute(
            "SELECT id FROM word WHERE child_id = ? AND word = ?",
            (child_id, word)
        ).fetchone()

        if existing:
            results.append({"word": word, "status": "exists"})
            continue

        # Fetch definition
        result = fetch_definition(word)
        definition = result["definition"] if result else ""
        example = result.get("example", "") if result else ""

        cursor = conn.execute(
            "INSERT INTO word (child_id, word, definition, example_sentence) VALUES (?, ?, ?, ?)",
            (child_id, word, definition, example)
        )
        word_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO word_progress (child_id, word_id, difficulty_level) VALUES (?, ?, 1)",
            (child_id, word_id)
        )

        results.append({
            "word": word,
            "status": "added",
            "id": word_id,
            "definition": definition
        })

    conn.commit()
    conn.close()

    return jsonify({
        "imported": len([r for r in results if r["status"] == "added"]),
        "skipped": len([r for r in results if r["status"] == "exists"]),
        "results": results
    })


@app.route("/api/dictionary/<word>", methods=["GET"])
def lookup_word(word):
    result = fetch_definition(word)
    if result:
        return jsonify(result)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/children/<int:child_id>/test/words", methods=["GET"])
def get_words_for_test(child_id):
    count = request.args.get("count", 25, type=int)
    words = get_test_words(child_id, count)
    return jsonify(words)


@app.route("/api/children/<int:child_id>/test/choices/<int:word_id>", methods=["GET"])
def get_choices(child_id, word_id):
    conn = get_db()
    word = conn.execute("SELECT * FROM word WHERE id = ?", (word_id,)).fetchone()
    all_words = conn.execute(
        "SELECT * FROM word WHERE child_id = ?", (child_id,)
    ).fetchall()
    conn.close()

    if not word:
        return jsonify({"error": "Word not found"}), 404

    mode = request.args.get("mode", "definition")
    word_dict = dict(word)
    all_words_list = [dict(w) for w in all_words]

    if mode == "word":
        choices = generate_word_choices(word_dict, all_words_list)
        return jsonify({"choices": choices, "correct": word["word"]})
    else:
        choices = generate_choices(word_dict, all_words_list)
        return jsonify({"choices": choices, "correct": word["definition"]})


@app.route("/api/children/<int:child_id>/test/answer", methods=["POST"])
def submit_answer(child_id):
    data = request.json
    word_id = data["word_id"]
    correct = data["correct"]

    result = update_progress(child_id, word_id, correct)
    return jsonify(result)


@app.route("/api/children/<int:child_id>/test/session", methods=["POST"])
def save_test_session(child_id):
    data = request.json
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO test_session
           (child_id, test_type, score, correct_count, total_count, time_taken, created_by, parent_test_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (child_id, data["test_type"], data.get("score", 0),
         data["correct_count"], data["total_count"], data["time_taken"],
         data.get("created_by", "child"), data.get("parent_test_id"))
    )
    session_id = cursor.lastrowid

    # Save individual answers if provided
    import json as json_mod
    answers = data.get("answers", [])
    for a in answers:
        choices_json = json_mod.dumps(a.get("choices", [])) if a.get("choices") else None
        conn.execute(
            """INSERT INTO test_session_answer
               (session_id, word_id, word_text, question_type, child_answer, correct_answer, is_correct, choices, question_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, a.get("word_id", 0), a.get("word_text", ""),
             a.get("question_type", ""), a.get("child_answer", ""),
             a.get("correct_answer", ""), a.get("is_correct", False), choices_json,
             a.get("question_text", ""))
        )

    conn.commit()
    conn.close()
    return jsonify({"id": session_id}), 201


@app.route("/child/<int:child_id>/test")
@app.route("/child/<int:child_id>/test/<int:parent_test_id>")
def test_page(child_id, parent_test_id=None):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404
    learning_plan_id = None
    if parent_test_id:
        # Check if this test is in a learning plan
        lpi = conn.execute(
            "SELECT plan_id FROM learning_plan_item WHERE item_type = 'parent_test' AND item_id = ?",
            (parent_test_id,)
        ).fetchone()
        if lpi:
            learning_plan_id = lpi["plan_id"]
    conn.close()
    return render_template("test.html", child=dict(child), parent_test_id=parent_test_id, learning_plan_id=learning_plan_id)


@app.route("/child/<int:child_id>/tests")
@login_required
def test_history(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    sessions = conn.execute(
        """SELECT ts.id, ts.test_type, ts.score, ts.correct_count, ts.total_count,
                  ts.time_taken, ts.created_at, ts.created_by, ts.parent_test_id,
                  pt.title as parent_test_title, pt.source_type as parent_test_source
           FROM test_session ts
           LEFT JOIN parent_test pt ON ts.parent_test_id = pt.id
           WHERE ts.child_id = ?
           ORDER BY ts.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()

    return render_template(
        "test_history.html",
        child=dict(child),
        sessions=[dict(s) for s in sessions]
    )


@app.route("/child/<int:child_id>/tests/<int:session_id>")
@login_required
def test_detail(child_id, session_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    test_session = conn.execute(
        """SELECT ts.*, pt.title as parent_test_title, pt.source_type as parent_test_source
           FROM test_session ts
           LEFT JOIN parent_test pt ON ts.parent_test_id = pt.id
           WHERE ts.id = ? AND ts.child_id = ?""",
        (session_id, child_id)
    ).fetchone()
    if not test_session:
        conn.close()
        return "Test session not found", 404

    answers = conn.execute(
        """SELECT tsa.*, w.image_path as word_image
           FROM test_session_answer tsa
           LEFT JOIN word w ON tsa.word_id = w.id
           WHERE tsa.session_id = ?
           ORDER BY tsa.id""",
        (session_id,)
    ).fetchall()
    conn.close()

    import json as json_mod
    answers_list = []
    for a in answers:
        d = dict(a)
        if d.get("choices"):
            d["choices"] = json_mod.loads(d["choices"])
        else:
            d["choices"] = []
        answers_list.append(d)

    learning_plan_id = request.args.get("plan_id")
    return render_template(
        "test_detail.html",
        child=dict(child),
        test_session=dict(test_session),
        answers=answers_list,
        learning_plan_id=learning_plan_id
    )


@app.route("/api/children/<int:child_id>/test-sessions", methods=["DELETE"])
@parent_required
def clear_test_history(child_id):
    conn = get_db()
    session_ids = conn.execute(
        "SELECT id FROM test_session WHERE child_id = ?", (child_id,)
    ).fetchall()
    for row in session_ids:
        conn.execute("DELETE FROM test_session_answer WHERE session_id = ?", (row["id"],))
    conn.execute("DELETE FROM test_session WHERE child_id = ?", (child_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/child/<int:child_id>/progress")
def progress_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    words = conn.execute(
        """SELECT w.id, w.word, w.definition, w.example_sentence, w.image_path,
                  COALESCE(wp.correct_count, 0) as correct_count,
                  COALESCE(wp.wrong_count, 0) as wrong_count,
                  COALESCE(wp.difficulty_level, 1) as difficulty_level,
                  wp.last_tested, wp.last_correct_at
           FROM word w
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
           WHERE w.child_id = ?
           ORDER BY w.word""",
        (child_id,)
    ).fetchall()
    conn.close()

    words_list = [dict(w) for w in words]

    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # Compute stats
    total = len(words_list)
    never_tested = sum(1 for w in words_list if not w["last_tested"])
    needs_work = sum(1 for w in words_list
                     if w["last_tested"] and (w["wrong_count"] > w["correct_count"]))
    mastered = sum(1 for w in words_list if w["difficulty_level"] >= 4)

    return render_template(
        "progress.html",
        child=dict(child),
        words=words_list,
        total=total,
        never_tested=never_tested,
        needs_work=needs_work,
        mastered=mastered,
        cutoff=cutoff,
        role=session.get("role", "parent")
    )


@app.route("/child/<int:child_id>/study")
@app.route("/child/<int:child_id>/study/<int:session_id>")
@login_required
def study_page(child_id, session_id=None):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404
    learning_plan_id = None
    if session_id:
        ss = conn.execute("SELECT learning_plan_id FROM study_session WHERE id = ?", (session_id,)).fetchone()
        if ss:
            learning_plan_id = ss["learning_plan_id"]
    conn.close()
    return render_template("study.html", child=dict(child), session_id=session_id, learning_plan_id=learning_plan_id)


@app.route("/materials")
def materials_list():
    conn = get_db()
    child_filter = request.args.get("child_id", "", type=str)

    if child_filter:
        materials = conn.execute(
            """SELECT rm.*,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = rm.id) as question_count,
                      (SELECT COUNT(*) FROM material_power_word WHERE material_id = rm.id) as power_word_count,
                      c.name as child_name
               FROM reading_material rm
               LEFT JOIN child c ON rm.child_id = c.id
               WHERE rm.child_id = ?
               ORDER BY rm.created_at DESC""",
            (child_filter,)
        ).fetchall()
        # Compute attempt stats per material for this child
        material_stats = {}
        for m in materials:
            mid = m["id"]
            assignments = conn.execute(
                """SELECT ra.id, ra.completed_at
                   FROM reading_assignment ra
                   WHERE ra.material_id = ? AND ra.child_id = ? AND ra.status = 'completed'
                   ORDER BY ra.completed_at DESC""",
                (mid, child_filter)
            ).fetchall()
            times_tried = len(assignments)
            last_tried_at = None
            last_correct = None
            last_total = None
            if times_tried > 0:
                last_tried_at = assignments[0]["completed_at"]
                latest_id = assignments[0]["id"]
                stats = conn.execute(
                    """SELECT COUNT(*) as total,
                              SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct
                       FROM reading_assignment_answer
                       WHERE assignment_id = ?""",
                    (latest_id,)
                ).fetchone()
                last_total = stats["total"]
                last_correct = stats["correct"] or 0
            material_stats[mid] = {
                "times_tried": times_tried,
                "last_tried_at": last_tried_at,
                "last_correct": last_correct,
                "last_total": last_total,
            }
    else:
        materials = conn.execute(
            """SELECT rm.*,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = rm.id) as question_count,
                      (SELECT COUNT(*) FROM material_power_word WHERE material_id = rm.id) as power_word_count,
                      c.name as child_name
               FROM reading_material rm
               LEFT JOIN child c ON rm.child_id = c.id
               ORDER BY rm.created_at DESC"""
        ).fetchall()
        material_stats = {}

    children = conn.execute("SELECT id, name FROM child ORDER BY name").fetchall()
    conn.close()
    return render_template(
        "materials.html",
        materials=[dict(m) for m in materials],
        children=[dict(c) for c in children],
        child_filter=child_filter,
        material_stats=material_stats
    )


@app.route("/api/materials", methods=["POST"])
def create_material():
    title = request.form.get("title", "Untitled")
    content = request.form.get("content", "")
    source_url = request.form.get("source_url", "").strip() or None
    child_id = request.form.get("child_id", "").strip() or None
    image_path = None
    content_pdf = None

    # Handle PDF upload
    if "content_pdf" in request.files:
        pdf_file = request.files["content_pdf"]
        if pdf_file.filename:
            filename = secure_filename(pdf_file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            pdf_file.save(filepath)
            content_pdf = filename
            if not content:
                content = "[PDF content]"

    if "image" in request.files:
        file = request.files["image"]
        if file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            image_path = filename

            # OCR if no content provided
            if not content:
                content = extract_text(filepath)

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reading_material (title, content, image_path, source_url, child_id, content_pdf) VALUES (?, ?, ?, ?, ?, ?)",
        (title, content, image_path, source_url, child_id, content_pdf)
    )
    material_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"id": material_id, "content": content})


@app.route("/api/materials/ocr", methods=["POST"])
def ocr_image():
    """Extract text from an image using OCR."""
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400

    file = request.files["image"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    text = extract_text(filepath)

    # Clean up temp file
    os.remove(filepath)

    return jsonify({"text": text})


@app.route("/api/materials/<int:material_id>", methods=["GET"])
def get_material(material_id):
    conn = get_db()
    material = conn.execute(
        "SELECT * FROM reading_material WHERE id = ?", (material_id,)
    ).fetchone()
    conn.close()
    if not material:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(material))


@app.route("/api/materials/<int:material_id>", methods=["PUT"])
def update_material(material_id):
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE reading_material SET title = ?, content = ?, source_url = ?, child_id = ? WHERE id = ?",
        (data.get("title"), data.get("content"), data.get("source_url") or None, data.get("child_id") or None, material_id)
    )
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/<int:material_id>", methods=["DELETE"])
def delete_material(material_id):
    conn = get_db()
    conn.execute("DELETE FROM reading_assignment_answer WHERE assignment_id IN (SELECT id FROM reading_assignment WHERE material_id = ?)", (material_id,))
    conn.execute("DELETE FROM reading_assignment WHERE material_id = ?", (material_id,))
    conn.execute("DELETE FROM material_question WHERE material_id = ?", (material_id,))
    conn.execute("DELETE FROM reading_material WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/<int:material_id>/questions", methods=["GET"])
def get_material_questions(material_id):
    conn = get_db()
    questions = conn.execute(
        "SELECT * FROM material_question WHERE material_id = ? ORDER BY created_at",
        (material_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(q) for q in questions])


@app.route("/api/materials/<int:material_id>/questions", methods=["POST"])
def create_material_question(material_id):
    data = request.json
    question_text = data.get("question_text", "").strip()
    answer_text = data.get("answer_text", "").strip() or None

    if not question_text:
        return jsonify({"error": "Question text is required"}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO material_question (material_id, question_text, answer_text) VALUES (?, ?, ?)",
        (material_id, question_text, answer_text)
    )
    qid = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": qid}), 201


@app.route("/api/materials/questions/<int:qid>", methods=["PUT"])
def update_material_question(qid):
    data = request.json
    question_text = data.get("question_text", "").strip()
    answer_text = data.get("answer_text", "").strip() or None

    if not question_text:
        return jsonify({"error": "Question text is required"}), 400

    conn = get_db()
    conn.execute(
        "UPDATE material_question SET question_text = ?, answer_text = ? WHERE id = ?",
        (question_text, answer_text, qid)
    )
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/questions/<int:qid>", methods=["DELETE"])
def delete_material_question(qid):
    conn = get_db()
    conn.execute("DELETE FROM material_question WHERE id = ?", (qid,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/<int:material_id>/questions/batch", methods=["POST"])
def batch_create_material_questions(material_id):
    import re
    data = request.json
    questions_text = data.get("questions", "")
    answers_text = data.get("answers", "")

    # Parse questions: split on numbered lines (e.g. "1.", "2.")
    # Each block is a question + its A/B/C/D choices
    lines = questions_text.strip().split("\n")
    questions = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if line starts a new numbered question
        if re.match(r'^\d+[\.\)]\s', stripped) and current:
            questions.append("\n".join(current))
            current = [stripped]
        else:
            current.append(stripped)
    if current:
        questions.append("\n".join(current))

    # Parse answers (one per line)
    answers = [a.strip() for a in answers_text.strip().split("\n") if a.strip()]

    if not questions:
        return jsonify({"error": "No questions provided"}), 400

    conn = get_db()
    count = 0
    for i, q in enumerate(questions):
        answer = answers[i] if i < len(answers) else None
        conn.execute(
            "INSERT INTO material_question (material_id, question_text, answer_text) VALUES (?, ?, ?)",
            (material_id, q, answer)
        )
        count += 1

    conn.commit()
    conn.close()
    return jsonify({"added": count}), 201


@app.route("/api/materials/<int:material_id>/questions", methods=["DELETE"])
def clear_material_questions(material_id):
    conn = get_db()
    conn.execute("DELETE FROM material_question WHERE material_id = ?", (material_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/browse", methods=["GET"])
def browse_articles():
    """Fetch articles from RSS feeds for browsing/importing."""
    import feedparser
    import requests as req
    from bs4 import BeautifulSoup

    source_filter = request.args.get("source", "")
    cache_ttl = 30 * 60  # 30 minutes

    feeds_to_fetch = RSS_FEEDS
    if source_filter:
        feeds_to_fetch = [f for f in RSS_FEEDS if f["name"] == source_filter]

    all_articles = []
    for feed_info in feeds_to_fetch:
        url = feed_info["url"]
        cached = _feed_cache.get(url)
        if cached and (time.time() - cached["fetched_at"]) < cache_ttl:
            all_articles.extend(cached["articles"])
            continue

        try:
            # Use requests for fetching (better SSL support), then parse with feedparser
            resp = req.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; KidVerbal/1.0)"
            })
            resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            articles = []
            for entry in parsed.entries[:15]:
                summary = entry.get("summary", "")
                # Strip HTML tags from summary
                if summary:
                    summary = BeautifulSoup(summary, "html.parser").get_text()
                    if len(summary) > 300:
                        summary = summary[:300] + "..."

                articles.append({
                    "title": entry.get("title", "Untitled"),
                    "summary": summary,
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": feed_info["name"],
                    "category": feed_info["category"],
                })

            _feed_cache[url] = {"articles": articles, "fetched_at": time.time()}
            all_articles.extend(articles)
        except Exception:
            continue

    # Mark articles already imported by matching title
    conn = get_db()
    existing_titles = set(
        row[0] for row in conn.execute("SELECT title FROM reading_material").fetchall()
    )
    conn.close()
    for article in all_articles:
        article["imported"] = article["title"] in existing_titles

    return jsonify(all_articles)


@app.route("/api/materials/import-article", methods=["POST"])
def import_article():
    """Fetch full article text from URL and save as reading material."""
    import requests as req
    from bs4 import BeautifulSoup

    data = request.json
    url = data.get("url", "")
    title = data.get("title", "Imported Article")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        resp = req.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; KidVerbal/1.0)"
        })
        resp.raise_for_status()
    except Exception as e:
        return jsonify({"error": f"Failed to fetch article: {str(e)}"}), 400

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract Power Words BEFORE removing non-content elements (they live in footer areas)
    power_words = []
    pw_section = soup.find("section", id="power-words") or soup.find("div", class_="power-words-container")
    if not pw_section:
        # Fallback: look for h3 containing "Power Words" and go to grandparent
        for h3 in soup.find_all("h3"):
            if "power words" in (h3.get_text() or "").lower():
                pw_section = h3.parent.parent if h3.parent else h3.parent
                break
    if pw_section:
        for p in pw_section.find_all("p"):
            strong = p.find("strong")
            if not strong:
                continue
            word = strong.get_text().strip().rstrip(":")
            if not word:
                continue
            # Get full paragraph text, remove the word part, strip leading colon
            full_text = p.get_text()
            definition = full_text.replace(strong.get_text(), "", 1).strip()
            if definition.startswith(":"):
                definition = definition[1:].strip()
            if word and definition:
                power_words.append({"word": word.lower(), "definition": definition})

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "iframe", "form", "noscript"]):
        tag.decompose()
    for selector in [".ad", ".ads", ".advertisement", ".sidebar", ".nav",
                     ".menu", ".footer", ".header", ".cookie", ".popup"]:
        for el in soup.select(selector):
            el.decompose()

    # Try to find main content area
    content_el = (
        soup.find("article") or
        soup.find("main") or
        soup.find(class_="content") or
        soup.find(class_="article-body") or
        soup.find(class_="post-content") or
        soup.body
    )

    if content_el:
        paragraphs = content_el.find_all("p")
        if paragraphs:
            content = "\n\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
        else:
            content = content_el.get_text(separator="\n").strip()
    else:
        content = soup.get_text(separator="\n").strip()

    if not content:
        return jsonify({"error": "Could not extract article text"}), 400

    child_id = data.get("child_id") or None

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reading_material (title, content, source_url, child_id) VALUES (?, ?, ?, ?)",
        (title, content, url, child_id)
    )
    material_id = cursor.lastrowid

    # Store power words
    for pw in power_words:
        conn.execute(
            "INSERT INTO material_power_word (material_id, word, definition) VALUES (?, ?, ?)",
            (material_id, pw["word"], pw["definition"])
        )

    conn.commit()
    conn.close()

    return jsonify({"id": material_id, "title": title, "content_length": len(content), "power_word_count": len(power_words)}), 201


@app.route("/api/materials/<int:material_id>/power-words", methods=["GET"])
@login_required
def get_power_words(material_id):
    conn = get_db()
    words = conn.execute(
        "SELECT * FROM material_power_word WHERE material_id = ? ORDER BY id",
        (material_id,)
    ).fetchall()
    child_id = request.args.get("child_id", type=int)
    result = []
    for w in words:
        d = dict(w)
        d["already_added"] = False
        if child_id:
            existing = conn.execute(
                "SELECT id FROM word WHERE child_id = ? AND LOWER(word) = LOWER(?)",
                (child_id, w["word"])
            ).fetchone()
            d["already_added"] = existing is not None
        result.append(d)
    conn.close()
    return jsonify(result)


@app.route("/api/materials/<int:material_id>/power-words/add-to-vocab", methods=["POST"])
@parent_required
def add_power_words_to_vocab(material_id):
    data = request.json
    child_id = data.get("child_id")
    word_ids = data.get("word_ids", [])
    if not child_id or not word_ids:
        return jsonify({"error": "child_id and word_ids required"}), 400

    conn = get_db()
    added = 0
    for wid in word_ids:
        pw = conn.execute(
            "SELECT word, definition FROM material_power_word WHERE id = ? AND material_id = ?",
            (wid, material_id)
        ).fetchone()
        if not pw:
            continue
        existing = conn.execute(
            "SELECT id FROM word WHERE child_id = ? AND LOWER(word) = LOWER(?)",
            (child_id, pw["word"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO word (child_id, word, definition, source_material_id) VALUES (?, ?, ?, ?)",
            (child_id, pw["word"], pw["definition"], material_id)
        )
        added += 1
    conn.commit()
    conn.close()
    return jsonify({"added": added})


@app.route("/api/active-reading-sessions", methods=["GET"])
@login_required
def get_active_reading_sessions():
    if not active_sessions:
        return jsonify([])
    material_ids = list(active_sessions.keys())
    conn = get_db()
    placeholders = ",".join("?" * len(material_ids))
    materials = conn.execute(
        f"SELECT id, title FROM reading_material WHERE id IN ({placeholders})",
        material_ids
    ).fetchall()
    conn.close()
    return jsonify([dict(m) for m in materials])


@app.route("/session/<int:material_id>/parent")
def session_parent(material_id):
    conn = get_db()
    material = conn.execute(
        "SELECT * FROM reading_material WHERE id = ?", (material_id,)
    ).fetchone()
    children = conn.execute("SELECT id, name FROM child ORDER BY name").fetchall()
    conn.close()
    if not material:
        return "Material not found", 404
    return render_template(
        "session_parent.html",
        material=dict(material),
        children=[dict(c) for c in children]
    )


@app.route("/session/<int:material_id>/child")
def session_child(material_id):
    conn = get_db()
    material = conn.execute(
        "SELECT * FROM reading_material WHERE id = ?", (material_id,)
    ).fetchone()
    children = conn.execute("SELECT id, name FROM child ORDER BY name").fetchall()
    conn.close()
    if not material:
        return "Material not found", 404
    return render_template(
        "session_child.html",
        material=dict(material),
        children=[dict(c) for c in children]
    )


@socketio.on("join_session")
def handle_join(data):
    room = f"session_{data['material_id']}"
    join_room(room)
    emit("user_joined", {"role": data["role"]}, room=room)

    # Track active parent sessions
    if data["role"] == "parent":
        active_sessions[data["material_id"]] = {
            "material_id": data["material_id"],
            "sid": request.sid
        }


@socketio.on("disconnect")
def handle_disconnect():
    # Remove any sessions owned by this socket
    to_remove = [mid for mid, info in active_sessions.items() if info.get("sid") == request.sid]
    for mid in to_remove:
        del active_sessions[mid]


@socketio.on("highlight_word")
def handle_highlight(data):
    room = f"session_{data['material_id']}"
    emit("word_highlighted", data, room=room, include_self=False)


@socketio.on("clear_highlight")
def handle_clear(data):
    room = f"session_{data['material_id']}"
    emit("highlight_cleared", {}, room=room, include_self=False)


@socketio.on("ask_question")
def handle_question(data):
    room = f"session_{data['material_id']}"
    emit("question_asked", data, room=room, include_self=False)


@socketio.on("child_response")
def handle_response(data):
    room = f"session_{data['material_id']}"
    emit("response_received", data, room=room, include_self=False)


@socketio.on("scroll_update")
def handle_scroll(data):
    room = f"session_{data['material_id']}"
    emit("scroll_updated", data, room=room, include_self=False)


@socketio.on("add_word")
def handle_add_word(data):
    # Add word to child's vocabulary
    word = data["word"].strip().lower()
    child_id = data["child_id"]
    material_id = data.get("material_id")

    conn = get_db()

    # Check if word already exists for this child
    existing = conn.execute(
        "SELECT id, definition, example_sentence FROM word WHERE child_id = ? AND word = ?",
        (child_id, word)
    ).fetchone()

    if existing:
        conn.close()
        room = f"session_{data['material_id']}"
        emit("word_added", {
            "word": word,
            "word_id": existing["id"],
            "definition": existing["definition"] or "",
            "example": existing["example_sentence"] or "",
            "already_exists": True
        }, room=room)
        return

    result = fetch_definition(word)
    definition = result["definition"] if result else ""
    example = result.get("example", "") if result else ""

    cursor = conn.execute(
        "INSERT INTO word (child_id, word, definition, example_sentence, source_material_id) VALUES (?, ?, ?, ?, ?)",
        (child_id, word, definition, example, material_id)
    )
    word_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO word_progress (child_id, word_id, difficulty_level) VALUES (?, ?, 1)",
        (child_id, word_id)
    )
    conn.commit()
    conn.close()

    room = f"session_{data['material_id']}"
    emit("word_added", {
        "word": word,
        "word_id": word_id,
        "definition": definition,
        "example": example,
        "already_exists": False
    }, room=room)


# ── Reading Assignment API ──

@app.route("/api/reading-assignments", methods=["POST"])
@parent_required
def create_reading_assignment():
    data = request.json
    material_id = data.get("material_id")
    child_id = data.get("child_id")

    if not material_id or not child_id:
        return jsonify({"error": "material_id and child_id required"}), 400

    conn = get_db()

    # Verify material has questions
    qcount = conn.execute(
        "SELECT COUNT(*) FROM material_question WHERE material_id = ?", (material_id,)
    ).fetchone()[0]
    if qcount == 0:
        conn.close()
        return jsonify({"error": "Material has no questions"}), 400

    cursor = conn.execute(
        "INSERT INTO reading_assignment (material_id, child_id) VALUES (?, ?)",
        (material_id, child_id)
    )
    assignment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": assignment_id}), 201


@app.route("/api/children/<int:child_id>/reading-assignments", methods=["GET"])
@login_required
def get_reading_assignments(child_id):
    conn = get_db()
    assignments = conn.execute(
        """SELECT ra.*, rm.title as material_title,
                  (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           WHERE ra.child_id = ?
           ORDER BY ra.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(a) for a in assignments])


@app.route("/api/reading-assignments/<int:assignment_id>", methods=["GET"])
@login_required
def get_reading_assignment(assignment_id):
    conn = get_db()
    assignment = conn.execute(
        """SELECT ra.*, rm.title as material_title, rm.content as material_content,
                  rm.image_path as material_image, c.name as child_name
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           JOIN child c ON ra.child_id = c.id
           WHERE ra.id = ?""",
        (assignment_id,)
    ).fetchone()
    if not assignment:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    questions = conn.execute(
        """SELECT mq.id as question_id, mq.question_text, mq.answer_text,
                  raa.child_answer, raa.evidence_text
           FROM material_question mq
           LEFT JOIN reading_assignment_answer raa
               ON raa.question_id = mq.id AND raa.assignment_id = ?
           WHERE mq.material_id = ?
           ORDER BY mq.id""",
        (assignment_id, assignment["material_id"])
    ).fetchall()
    conn.close()

    result = dict(assignment)
    result["questions"] = [dict(q) for q in questions]
    return jsonify(result)


@app.route("/api/reading-assignments/<int:assignment_id>/submit", methods=["POST"])
@login_required
def submit_reading_assignment(assignment_id):
    data = request.json
    answers = data.get("answers", [])

    conn = get_db()
    assignment = conn.execute(
        "SELECT * FROM reading_assignment WHERE id = ?", (assignment_id,)
    ).fetchone()
    if not assignment:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    for a in answers:
        # Look up the correct answer for this question
        question = conn.execute(
            "SELECT answer_text FROM material_question WHERE id = ?",
            (a["question_id"],)
        ).fetchone()
        child_answer = a.get("child_answer", "").strip().upper()
        correct_answer = (question["answer_text"] or "").strip().upper() if question else ""
        is_correct = child_answer == correct_answer and child_answer != ""
        conn.execute(
            "INSERT INTO reading_assignment_answer (assignment_id, question_id, child_answer, is_correct, evidence_text) VALUES (?, ?, ?, ?, ?)",
            (assignment_id, a["question_id"], a.get("child_answer", ""), is_correct, a.get("evidence_text", ""))
        )

    unknown_words = data.get("unknown_words", [])
    for word in unknown_words:
        w = word.strip()
        if w:
            conn.execute(
                "INSERT INTO reading_assignment_unknown_word (assignment_id, word) VALUES (?, ?)",
                (assignment_id, w)
            )

    conn.execute(
        "UPDATE reading_assignment SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (assignment_id,)
    )
    # Check if this reading assignment belongs to a learning plan
    ra = conn.execute("SELECT learning_plan_id FROM reading_assignment WHERE id = ?", (assignment_id,)).fetchone()
    if ra and ra["learning_plan_id"]:
        check_plan_completion(ra["learning_plan_id"], conn)
    conn.commit()
    conn.close()
    return jsonify({"status": "completed"})


@app.route("/api/reading-assignments/<int:assignment_id>", methods=["DELETE"])
@parent_required
def delete_reading_assignment(assignment_id):
    conn = get_db()
    conn.execute("DELETE FROM reading_assignment_answer WHERE assignment_id = ?", (assignment_id,))
    conn.execute("DELETE FROM reading_assignment_unknown_word WHERE assignment_id = ?", (assignment_id,))
    conn.execute("DELETE FROM reading_assignment WHERE id = ?", (assignment_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/reading-assignments/<int:assignment_id>/add-word", methods=["POST"])
@parent_required
def add_unknown_word_to_vocab(assignment_id):
    data = request.json
    word = data.get("word", "").strip().lower()
    if not word:
        return jsonify({"error": "No word provided"}), 400

    conn = get_db()
    assignment = conn.execute(
        "SELECT child_id FROM reading_assignment WHERE id = ?", (assignment_id,)
    ).fetchone()
    if not assignment:
        conn.close()
        return jsonify({"error": "Assignment not found"}), 404

    child_id = assignment["child_id"]

    # Check if word already exists for this child
    existing = conn.execute(
        "SELECT id FROM word WHERE child_id = ? AND word = ?", (child_id, word)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"status": "exists", "word_id": existing["id"]}), 200

    # Fetch definition (use provided values if given)
    definition = data.get("definition", "").strip()
    example = data.get("example_sentence", "").strip()

    if not definition:
        result = fetch_definition(word)
        if result:
            definition = result["definition"]
            if not example:
                example = result.get("example", "")

    cursor = conn.execute(
        "INSERT INTO word (child_id, word, definition, example_sentence) VALUES (?, ?, ?, ?)",
        (child_id, word, definition, example)
    )
    word_id = cursor.lastrowid
    conn.execute(
        "INSERT INTO word_progress (child_id, word_id, difficulty_level) VALUES (?, ?, 1)",
        (child_id, word_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "added", "word_id": word_id, "definition": definition, "example": example}), 201


@app.route("/api/dictionary/<word>")
@login_required
def dictionary_lookup(word):
    word = word.strip().lower()
    result = fetch_definition(word)
    if result:
        return jsonify({"definition": result["definition"], "example": result.get("example", "")})
    return jsonify({"definition": "", "example": ""})


@app.route("/child/<int:child_id>/reading-assignment/<int:assignment_id>")
@login_required
def reading_assignment_page(child_id, assignment_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    assignment = conn.execute(
        """SELECT ra.*, rm.title, rm.content, rm.image_path, rm.content_pdf, rm.source_url
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           WHERE ra.id = ? AND ra.child_id = ?""",
        (assignment_id, child_id)
    ).fetchone()
    if not assignment:
        conn.close()
        return "Assignment not found", 404

    questions = conn.execute(
        "SELECT * FROM material_question WHERE material_id = ? ORDER BY id",
        (assignment["material_id"],)
    ).fetchall()
    conn.close()

    return render_template(
        "reading_assignment.html",
        child=dict(child),
        assignment=dict(assignment),
        questions=[dict(q) for q in questions],
        learning_plan_id=assignment["learning_plan_id"]
    )


@app.route("/child/<int:child_id>/reading-assignment/<int:assignment_id>/review")
@login_required
def reading_assignment_review_page(child_id, assignment_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    assignment = conn.execute(
        """SELECT ra.*, rm.title, rm.content, rm.content_pdf
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           WHERE ra.id = ? AND ra.child_id = ?""",
        (assignment_id, child_id)
    ).fetchone()
    if not assignment:
        conn.close()
        return "Assignment not found", 404

    questions = conn.execute(
        """SELECT mq.question_text, mq.answer_text,
                  raa.child_answer, raa.is_correct, raa.evidence_text
           FROM material_question mq
           LEFT JOIN reading_assignment_answer raa
               ON raa.question_id = mq.id AND raa.assignment_id = ?
           WHERE mq.material_id = ?
           ORDER BY mq.id""",
        (assignment_id, assignment["material_id"])
    ).fetchall()

    unknown_words = conn.execute(
        "SELECT word FROM reading_assignment_unknown_word WHERE assignment_id = ? ORDER BY id",
        (assignment_id,)
    ).fetchall()

    # Get child's existing vocabulary for checking overlap
    existing_words = conn.execute(
        "SELECT word FROM word WHERE child_id = ?", (child_id,)
    ).fetchall()
    conn.close()

    existing_word_set = {row["word"].lower() for row in existing_words}

    # Compute score
    questions_list = [dict(q) for q in questions]
    total_count = len(questions_list)
    correct_count = sum(1 for q in questions_list if q.get("is_correct"))
    score = round(correct_count / total_count * 100) if total_count > 0 else 0

    return render_template(
        "reading_assignment_review.html",
        child=dict(child),
        assignment=dict(assignment),
        questions=questions_list,
        unknown_words=[row["word"] for row in unknown_words],
        existing_word_set=existing_word_set,
        score=score,
        correct_count=correct_count,
        total_count=total_count,
        role=session.get("role", "parent"),
        learning_plan_id=assignment["learning_plan_id"]
    )


# ── Math Tests ──

@app.route("/parent/child/<int:child_id>/math-test/new")
@parent_required
def create_math_test_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("create_math_test.html", child=dict(child))


@app.route("/api/math-tests/preview-answers", methods=["POST"])
@parent_required
def preview_math_answers():
    if "answer_pdf" not in request.files:
        return jsonify({"error": "No answer PDF uploaded"}), 400
    f = request.files["answer_pdf"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    row = request.form.get("row", "").strip()

    # Save to temp file, parse, then delete
    filename = secure_filename(f.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, "temp_" + filename)
    f.save(temp_path)
    try:
        if row:
            rows_dict, error = parse_grid_answer_pdf(temp_path)
            if error:
                return jsonify({"error": error}), 400
            answers, error = extract_row_answers(rows_dict, row)
        else:
            answers, error = parse_answer_pdf(temp_path)
    finally:
        os.remove(temp_path)

    if error:
        return jsonify({"error": error}), 400
    return jsonify({"answers": answers, "total": len(answers)})


@app.route("/api/math-tests/preview-grid-answers", methods=["POST"])
@parent_required
def preview_grid_answers():
    if "answer_pdf" not in request.files:
        return jsonify({"error": "No answer PDF uploaded"}), 400
    f = request.files["answer_pdf"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(f.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, "temp_" + filename)
    f.save(temp_path)
    try:
        rows_dict, error = parse_grid_answer_pdf(temp_path)
    finally:
        os.remove(temp_path)

    if error == "SCANNED":
        return jsonify({"scanned": True})
    if error:
        return jsonify({"error": error}), 400
    rows_summary = {name: len(answers) for name, answers in rows_dict.items()}
    return jsonify({"rows": rows_summary})


@app.route("/api/math-tests/pdf-preview-image", methods=["POST"])
@parent_required
def pdf_preview_image():
    if "answer_pdf" not in request.files:
        return jsonify({"error": "No answer PDF uploaded"}), 400
    f = request.files["answer_pdf"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(f.filename)
    temp_path = os.path.join(UPLOAD_FOLDER, "temp_" + filename)
    f.save(temp_path)
    try:
        png_bytes, error = pdf_page_to_png(temp_path)
    finally:
        os.remove(temp_path)

    if error:
        return jsonify({"error": error}), 400

    from flask import Response
    return Response(png_bytes, mimetype="image/png")


@app.route("/api/math-tests", methods=["POST"])
@parent_required
def create_math_test():
    title = request.form.get("title", "").strip()
    child_id = request.form.get("child_id", type=int)
    if not title or not child_id:
        return jsonify({"error": "Title and child are required"}), 400

    if "question_pdf" not in request.files or "answer_pdf" not in request.files:
        return jsonify({"error": "Both question and answer PDFs are required"}), 400

    q_file = request.files["question_pdf"]
    a_file = request.files["answer_pdf"]
    if not q_file.filename or not a_file.filename:
        return jsonify({"error": "Both PDF files must be selected"}), 400

    # Save PDFs
    ts = int(time.time())
    q_filename = f"math_q_{child_id}_{ts}_{secure_filename(q_file.filename)}"
    a_filename = f"math_a_{child_id}_{ts}_{secure_filename(a_file.filename)}"
    q_path = os.path.join(UPLOAD_FOLDER, q_filename)
    a_path = os.path.join(UPLOAD_FOLDER, a_filename)
    q_file.save(q_path)
    a_file.save(a_path)

    # Parse answer key
    manual_answers = request.form.get("manual_answers", "").strip()
    row = request.form.get("row", "").strip()
    timer_mode = request.form.get("timer_mode", "none").strip()
    time_limit_seconds = request.form.get("time_limit_seconds", 0, type=int)
    if manual_answers:
        answers = json.loads(manual_answers)
        error = None
    elif row:
        rows_dict, error = parse_grid_answer_pdf(a_path)
        if not error:
            answers, error = extract_row_answers(rows_dict, row)
    else:
        answers, error = parse_answer_pdf(a_path)
    if error:
        os.remove(q_path)
        os.remove(a_path)
        return jsonify({"error": f"Failed to parse answer PDF: {error}"}), 400

    account = get_current_account()
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO math_test (child_id, created_by, title, question_pdf, answer_pdf, answer_key, total_questions, timer_mode, time_limit_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (child_id, account["id"], title, q_filename, a_filename, json.dumps(answers), len(answers), timer_mode, time_limit_seconds)
    )
    test_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": test_id, "total_questions": len(answers)}), 201


@app.route("/api/children/<int:child_id>/math-tests", methods=["GET"])
@login_required
def list_math_tests(child_id):
    conn = get_db()
    tests = conn.execute(
        """SELECT mt.id, mt.title, mt.status, mt.total_questions, mt.created_at,
                  (SELECT id FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as submission_id,
                  (SELECT score FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as score
           FROM math_test mt
           WHERE mt.child_id = ?
           ORDER BY mt.created_at DESC""",
        (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(t) for t in tests])


@app.route("/api/math-tests/<int:test_id>", methods=["GET"])
@login_required
def get_math_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not test:
        return jsonify({"error": "Not found"}), 404
    result = dict(test)
    # Don't expose answer key to child role
    if session.get("role") != "parent":
        result.pop("answer_key", None)
    return jsonify(result)


@app.route("/api/math-tests/<int:test_id>", methods=["DELETE"])
@parent_required
def delete_math_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    # Delete PDF files
    for fname in [test["question_pdf"], test["answer_pdf"]]:
        fpath = os.path.join(UPLOAD_FOLDER, fname)
        if os.path.exists(fpath):
            os.remove(fpath)

    conn.execute("DELETE FROM math_test_submission WHERE math_test_id = ?", (test_id,))
    conn.execute("DELETE FROM math_test WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/math-tests/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_math_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    data = request.json
    child_answers = data.get("answers", {})
    child_explanations = data.get("explanations", {})
    time_taken_seconds = data.get("time_taken_seconds", 0)
    is_retry = data.get("is_retry", False)
    answer_key = json.loads(test["answer_key"])

    # If retry, merge new answers into existing submission
    if is_retry:
        existing_sub = conn.execute(
            "SELECT * FROM math_test_submission WHERE math_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (test_id,)
        ).fetchone()
        if existing_sub:
            merged = json.loads(existing_sub["answers"])
            merged.update(child_answers)
            child_answers = merged
            # Merge explanations
            existing_explanations = json.loads(existing_sub["explanations"] or "{}")
            existing_explanations.update(child_explanations)
            child_explanations = existing_explanations
            # Preserve the original time taken
            time_taken_seconds = existing_sub["time_taken_seconds"]

    correct_count = 0
    total_count = len(answer_key)
    for q_num, correct_ans in answer_key.items():
        if child_answers.get(q_num, "").upper() == correct_ans.upper():
            correct_count += 1

    score = round(correct_count / total_count * 100) if total_count > 0 else 0

    cursor = conn.execute(
        """INSERT INTO math_test_submission (math_test_id, child_id, answers, explanations, score, correct_count, total_count, time_taken_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (test_id, test["child_id"], json.dumps(child_answers), json.dumps(child_explanations), score, correct_count, total_count, time_taken_seconds)
    )
    submission_id = cursor.lastrowid

    # Only update status on first submission, not on retries
    if not is_retry:
        conn.execute("UPDATE math_test SET status = 'completed' WHERE id = ?", (test_id,))
        # Check if this math test belongs to a learning plan
        mt = conn.execute("SELECT learning_plan_id FROM math_test WHERE id = ?", (test_id,)).fetchone()
        if mt and mt["learning_plan_id"]:
            check_plan_completion(mt["learning_plan_id"], conn)
    conn.commit()
    conn.close()
    return jsonify({"submission_id": submission_id, "score": score, "correct_count": correct_count, "total_count": total_count})


@app.route("/api/math-test-submissions/<int:submission_id>", methods=["GET"])
@login_required
def get_math_test_submission(submission_id):
    conn = get_db()
    sub = conn.execute("SELECT * FROM math_test_submission WHERE id = ?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (sub["math_test_id"],)).fetchone()
    conn.close()
    if not test:
        return jsonify({"error": "Test not found"}), 404
    result = dict(sub)
    result["answer_key"] = json.loads(test["answer_key"])
    result["question_pdf"] = test["question_pdf"]
    result["answer_pdf"] = test["answer_pdf"]
    result["title"] = test["title"]
    return jsonify(result)


@app.route("/parent/child/<int:child_id>/math-test/<int:test_id>/manage")
@parent_required
def manage_math_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not child or not test:
        return "Not found", 404
    return render_template("manage_math_test.html", child=dict(child), test=dict(test))


@app.route("/api/math-tests/<int:test_id>/answers", methods=["PUT"])
@parent_required
def update_math_test_answers(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    data = request.json
    answers = data.get("answers", {})
    if not answers:
        conn.close()
        return jsonify({"error": "No answers provided"}), 400
    timer_mode = data.get("timer_mode")
    time_limit_seconds = data.get("time_limit_seconds")
    conn.execute(
        "UPDATE math_test SET answer_key = ?, total_questions = ? WHERE id = ?",
        (json.dumps(answers), len(answers), test_id)
    )
    if timer_mode is not None:
        conn.execute(
            "UPDATE math_test SET timer_mode = ?, time_limit_seconds = ? WHERE id = ?",
            (timer_mode, time_limit_seconds or 0, test_id)
        )
    conn.commit()
    conn.close()
    return jsonify({"total_questions": len(answers)})


@app.route("/child/<int:child_id>/math-test/<int:test_id>")
@login_required
def take_math_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not child or not test:
        return "Not found", 404
    return render_template("math_test.html", child=dict(child), test={
        "id": test["id"], "title": test["title"],
        "question_pdf": test["question_pdf"], "total_questions": test["total_questions"],
        "timer_mode": test["timer_mode"] or "none",
        "time_limit_seconds": test["time_limit_seconds"] or 0
    }, learning_plan_id=test["learning_plan_id"])


@app.route("/child/<int:child_id>/math-test/<int:test_id>/review")
@login_required
def review_math_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not child or not test:
        conn.close()
        return "Not found", 404
    sub = conn.execute(
        "SELECT * FROM math_test_submission WHERE math_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (test_id,)
    ).fetchone()
    if not sub:
        conn.close()
        return "No submission found", 404

    role = session.get("role", "parent")
    test_data = dict(test)

    # Fetch the original (first) submission to compare with retried answers
    original_sub = conn.execute(
        "SELECT * FROM math_test_submission WHERE math_test_id = ? ORDER BY submitted_at ASC LIMIT 1",
        (test_id,)
    ).fetchone()
    original_answers_json = None
    original_score = None
    if original_sub and original_sub["id"] != sub["id"]:
        original_answers_json = original_sub["answers"]
        original_score = original_sub["score"]

    # For child role, compute results server-side and strip answer key
    if role != "parent":
        answer_key = json.loads(test["answer_key"])
        child_answers = json.loads(sub["answers"])
        child_explanations = json.loads(sub["explanations"] or "{}")
        original_answers = json.loads(original_answers_json) if original_answers_json else None
        conn.close()
        results = []
        for i in range(1, len(answer_key) + 1):
            key = str(i)
            child_ans = child_answers.get(key, "-")
            correct_ans = answer_key.get(key, "?")
            original_ans = original_answers.get(key, "-") if original_answers else None
            r = {"q": i, "child_answer": child_ans, "is_correct": child_ans.upper() == correct_ans.upper(), "explanation": child_explanations.get(key, "")}
            # Show original answer if it differs from current (i.e., was retried)
            if original_answers and original_ans.upper() != child_ans.upper():
                r["original_answer"] = original_ans
            results.append(r)
        has_retries = original_answers is not None
        test_data.pop("answer_key", None)
        test_data.pop("answer_pdf", None)
        return render_template("math_test_review.html", child=dict(child), test=test_data, submission=dict(sub), role=role, results=results, has_retries=has_retries, original_score=original_score, learning_plan_id=test["learning_plan_id"])

    conn.close()
    return render_template("math_test_review.html", child=dict(child), test=test_data, submission=dict(sub), role=role, original_answers_json=original_answers_json, original_score=original_score, learning_plan_id=test["learning_plan_id"])


@app.route("/api/math-tests/<int:test_id>/retake", methods=["POST"])
@parent_required
def retake_math_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404
    account = get_current_account()
    cursor = conn.execute(
        """INSERT INTO math_test (child_id, created_by, title, question_pdf, answer_pdf, answer_key, total_questions, timer_mode, time_limit_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (test["child_id"], account["id"], test["title"], test["question_pdf"], test["answer_pdf"],
         test["answer_key"], test["total_questions"], test.get("timer_mode", "none"), test.get("time_limit_seconds", 0))
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({"id": new_id, "child_id": test["child_id"]})


@app.route("/api/math-tests/<int:test_id>/child-retake", methods=["POST"])
@login_required
def child_retake_math_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404

    # Find wrong questions from latest submission
    sub = conn.execute(
        "SELECT * FROM math_test_submission WHERE math_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (test_id,)
    ).fetchone()
    if not sub:
        conn.close()
        return jsonify({"error": "No submission found"}), 404

    answer_key = json.loads(test["answer_key"])
    child_answers = json.loads(sub["answers"])
    wrong_questions = []
    for q_num, correct_ans in answer_key.items():
        if child_answers.get(q_num, "").upper() != correct_ans.upper():
            wrong_questions.append(q_num)

    conn.close()
    return jsonify({"id": test_id, "child_id": test["child_id"], "wrong_questions": wrong_questions})


# ── Writing Topics ──

@app.route("/parent/child/<int:child_id>/writing-topics")
@parent_required
def writing_topics_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("writing_topics.html", child=dict(child))


@app.route("/api/children/<int:child_id>/writing-topics", methods=["GET"])
@login_required
def get_writing_topics(child_id):
    conn = get_db()
    topics = conn.execute(
        "SELECT * FROM writing_topic WHERE child_id = ? ORDER BY created_at DESC", (child_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(t) for t in topics])


@app.route("/api/children/<int:child_id>/writing-topics", methods=["POST"])
@parent_required
def add_writing_topics(child_id):
    data = request.json
    topics = data.get("topics", [])
    if not topics:
        return jsonify({"error": "topics required"}), 400
    account = get_current_account()
    conn = get_db()
    added = []
    for topic_text in topics:
        topic_text = topic_text.strip()
        if not topic_text:
            continue
        cursor = conn.execute(
            "INSERT INTO writing_topic (child_id, topic_text, created_by) VALUES (?, ?, ?)",
            (child_id, topic_text, account["id"])
        )
        added.append({"id": cursor.lastrowid, "topic_text": topic_text})
    conn.commit()
    conn.close()
    return jsonify({"added": added}), 201


@app.route("/api/writing-topics/<int:topic_id>", methods=["DELETE"])
@parent_required
def delete_writing_topic(topic_id):
    conn = get_db()
    conn.execute("DELETE FROM writing_topic WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()
    return "", 204


# ── Writing Tests ──

@app.route("/api/writing-tests", methods=["POST"])
@parent_required
def create_writing_test():
    data = request.json
    child_id = data.get("child_id")
    topic_text = data.get("topic_text", "").strip()
    if not child_id or not topic_text:
        return jsonify({"error": "child_id and topic_text required"}), 400
    account = get_current_account()
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO writing_test (child_id, created_by, topic_text, topic_id, timer_mode, time_limit_seconds, min_word_count, max_word_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (child_id, account["id"], topic_text, data.get("topic_id"),
         data.get("timer_mode", "none"), data.get("time_limit_seconds", 0),
         data.get("min_word_count", 0), data.get("max_word_count", 0))
    )
    test_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": test_id}), 201


@app.route("/api/writing-tests/<int:test_id>", methods=["GET"])
@login_required
def get_writing_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not test:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(test))


@app.route("/api/writing-tests/<int:test_id>", methods=["DELETE"])
@parent_required
def delete_writing_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    conn.execute("DELETE FROM writing_test_submission WHERE writing_test_id = ?", (test_id,))
    conn.execute("DELETE FROM writing_test WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/writing-tests/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_writing_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    data = request.json
    writing_text = data.get("writing_text", "").strip()
    time_taken_seconds = data.get("time_taken_seconds", 0)
    if not writing_text:
        conn.close()
        return jsonify({"error": "writing_text required"}), 400

    word_count = len(writing_text.split())

    cursor = conn.execute(
        """INSERT INTO writing_test_submission (writing_test_id, child_id, writing_text, word_count, time_taken_seconds)
           VALUES (?, ?, ?, ?, ?)""",
        (test_id, test["child_id"], writing_text, word_count, time_taken_seconds)
    )
    submission_id = cursor.lastrowid
    conn.execute("UPDATE writing_test SET status = 'completed' WHERE id = ?", (test_id,))

    if test["learning_plan_id"]:
        check_plan_completion(test["learning_plan_id"], conn)
    conn.commit()
    conn.close()
    return jsonify({"submission_id": submission_id, "word_count": word_count})


@app.route("/api/writing-test-submissions/<int:sub_id>/review", methods=["PUT"])
@parent_required
def review_writing_test_submission(sub_id):
    data = request.json
    score = data.get("score")
    feedback = data.get("feedback", "").strip()
    if score is None:
        return jsonify({"error": "score required"}), 400
    score = max(0, min(100, int(score)))
    conn = get_db()
    conn.execute(
        "UPDATE writing_test_submission SET score = ?, feedback = ? WHERE id = ?",
        (score, feedback, sub_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/writing-test-submissions/<int:sub_id>/annotations", methods=["PUT"])
@parent_required
def update_writing_test_annotations(sub_id):
    data = request.json
    annotations = data.get("annotations", [])
    if not isinstance(annotations, list):
        return jsonify({"error": "annotations must be a list"}), 400
    import json
    conn = get_db()
    conn.execute(
        "UPDATE writing_test_submission SET annotations = ? WHERE id = ?",
        (json.dumps(annotations), sub_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/writing-tests/<int:test_id>/send-back", methods=["POST"])
@parent_required
def send_back_writing_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    if test["status"] != "completed":
        conn.close()
        return jsonify({"error": "Test is not completed"}), 400

    conn.execute("UPDATE writing_test SET status = 'revision' WHERE id = ?", (test_id,))

    # If part of a learning plan that was completed, revert to released
    if test["learning_plan_id"]:
        conn.execute(
            "UPDATE learning_plan SET status = 'released', completed_at = NULL WHERE id = ? AND status = 'completed'",
            (test["learning_plan_id"],)
        )

    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/child/<int:child_id>/writing-test/<int:test_id>")
@login_required
def take_writing_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    if not child or not test:
        conn.close()
        return "Not found", 404

    previous_submission = None
    prev_annotations = []
    if test["status"] == "revision":
        sub = conn.execute(
            "SELECT * FROM writing_test_submission WHERE writing_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (test_id,)
        ).fetchone()
        if sub:
            previous_submission = dict(sub)
            if sub["annotations"]:
                import json
                try:
                    prev_annotations = json.loads(sub["annotations"])
                except (json.JSONDecodeError, TypeError):
                    prev_annotations = []

    conn.close()
    learning_plan_id = request.args.get("plan_id") or test["learning_plan_id"]
    return render_template("writing_test.html", child=dict(child), test=dict(test),
                           learning_plan_id=learning_plan_id,
                           previous_submission=previous_submission,
                           prev_annotations=prev_annotations)


@app.route("/child/<int:child_id>/writing-test/<int:test_id>/review")
@login_required
def review_writing_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM writing_test WHERE id = ?", (test_id,)).fetchone()
    if not child or not test:
        conn.close()
        return "Not found", 404
    submission = conn.execute(
        "SELECT * FROM writing_test_submission WHERE writing_test_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (test_id,)
    ).fetchone()
    conn.close()
    learning_plan_id = request.args.get("plan_id") or test["learning_plan_id"]
    role = session.get("role", "parent")
    import json
    annotations = []
    if submission and submission["annotations"]:
        try:
            annotations = json.loads(submission["annotations"])
        except (json.JSONDecodeError, TypeError):
            annotations = []
    return render_template("writing_test_review.html", child=dict(child), test=dict(test),
                           submission=dict(submission) if submission else None,
                           learning_plan_id=learning_plan_id, role=role,
                           annotations=annotations)


# ── Learning Plan page routes ──

@app.route("/api/children/<int:child_id>/reading-materials", methods=["GET"])
@login_required
def get_child_reading_materials(child_id):
    conn = get_db()
    materials = conn.execute(
        """SELECT rm.id, rm.title,
                  (SELECT COUNT(*) FROM material_question WHERE material_id = rm.id) as question_count
           FROM reading_material rm
           WHERE rm.child_id = ? OR rm.child_id IS NULL
           ORDER BY rm.created_at DESC""",
        (child_id,)
    ).fetchall()
    result = []
    for m in materials:
        if m["question_count"] == 0:
            continue
        d = dict(m)
        assignments = conn.execute(
            """SELECT ra.id, ra.completed_at
               FROM reading_assignment ra
               WHERE ra.material_id = ? AND ra.child_id = ? AND ra.status = 'completed'
               ORDER BY ra.completed_at DESC""",
            (m["id"], child_id)
        ).fetchall()
        d["times_tried"] = len(assignments)
        d["last_tried_at"] = None
        d["last_correct"] = None
        d["last_total"] = None
        if len(assignments) > 0:
            d["last_tried_at"] = assignments[0]["completed_at"]
            stats = conn.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct
                   FROM reading_assignment_answer
                   WHERE assignment_id = ?""",
                (assignments[0]["id"],)
            ).fetchone()
            d["last_total"] = stats["total"]
            d["last_correct"] = stats["correct"] or 0
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route("/parent/child/<int:child_id>/learning-plan/new")
@parent_required
def create_plan_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("manage_plan.html", child=dict(child), plan=None, mode="create")


@app.route("/parent/child/<int:child_id>/learning-plan/<int:plan_id>/manage")
@parent_required
def manage_plan_page(child_id, plan_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ? AND child_id = ?", (plan_id, child_id)).fetchone()
    conn.close()
    if not child or not plan:
        return "Not found", 404
    return render_template("manage_plan.html", child=dict(child), plan=dict(plan), mode="manage")


@app.route("/child/<int:child_id>/learning-plan/<int:plan_id>")
@login_required
def view_plan_page(child_id, plan_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ? AND child_id = ?", (plan_id, child_id)).fetchone()
    conn.close()
    if not child or not plan:
        return "Not found", 404
    if plan["status"] == "draft":
        return "This plan is not yet available", 403
    role = session.get("role", "child")
    return render_template("view_plan.html", child=dict(child), plan=dict(plan), role=role)


# ── Learning Plan APIs ──

@app.route("/api/learning-plans", methods=["POST"])
@parent_required
def create_learning_plan():
    data = request.json
    child_id = data.get("child_id")
    title = data.get("title", "").strip()
    if not child_id or not title:
        return jsonify({"error": "child_id and title required"}), 400
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO learning_plan (child_id, created_by, title) VALUES (?, ?, ?)",
        (child_id, session["account_id"], title)
    )
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": plan_id}), 201


@app.route("/api/learning-plans/<int:plan_id>", methods=["GET"])
@login_required
def get_learning_plan(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    items = conn.execute(
        "SELECT * FROM learning_plan_item WHERE plan_id = ? ORDER BY sort_order, id", (plan_id,)
    ).fetchall()
    item_list = []
    for item in items:
        item_data = dict(item)
        if item["item_type"] == "study_session":
            row = conn.execute(
                """SELECT ss.id, ss.title, ss.status,
                          (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
                   FROM study_session ss WHERE ss.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "reading_assignment":
            row = conn.execute(
                """SELECT ra.id, rm.title, ra.status,
                          (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count,
                          (SELECT COUNT(*) FROM reading_assignment_answer WHERE assignment_id = ra.id AND is_correct = 1) as correct_count
                   FROM reading_assignment ra
                   JOIN reading_material rm ON ra.material_id = rm.id
                   WHERE ra.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "math_test":
            row = conn.execute(
                """SELECT mt.id, mt.title, mt.status, mt.total_questions,
                          (SELECT score FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as score,
                          (SELECT correct_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as correct_count,
                          (SELECT total_count FROM math_test_submission WHERE math_test_id = mt.id LIMIT 1) as total_count
                   FROM math_test mt WHERE mt.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "parent_test":
            row = conn.execute(
                """SELECT pt.id, pt.title, pt.status,
                          (SELECT COUNT(*) FROM parent_test_word WHERE parent_test_id = pt.id) as word_count,
                          (SELECT id FROM test_session WHERE parent_test_id = pt.id ORDER BY created_at DESC LIMIT 1) as test_session_id,
                          (SELECT correct_count FROM test_session WHERE parent_test_id = pt.id ORDER BY created_at DESC LIMIT 1) as correct_count,
                          (SELECT total_count FROM test_session WHERE parent_test_id = pt.id ORDER BY created_at DESC LIMIT 1) as total_count,
                          (SELECT score FROM test_session WHERE parent_test_id = pt.id ORDER BY created_at DESC LIMIT 1) as score
                   FROM parent_test pt WHERE pt.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "writing_test":
            row = conn.execute(
                """SELECT wt.id, wt.topic_text as title, wt.status,
                          (SELECT word_count FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as word_count,
                          (SELECT score FROM writing_test_submission WHERE writing_test_id = wt.id LIMIT 1) as score
                   FROM writing_test wt WHERE wt.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "science_study":
            row = conn.execute(
                """SELECT ss.id, ss.title, ss.status,
                          (SELECT COUNT(*) FROM science_study_session_question WHERE session_id = ss.id) as question_count
                   FROM science_study_session ss WHERE ss.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "science_test":
            row = conn.execute(
                """SELECT st.id, st.title, st.status,
                          (SELECT COUNT(*) FROM science_test_question WHERE test_id = st.id) as question_count,
                          (SELECT score FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as score,
                          (SELECT correct_count FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as correct_count,
                          (SELECT total_count FROM science_test_submission WHERE science_test_id = st.id ORDER BY submitted_at DESC LIMIT 1) as total_count
                   FROM science_test st WHERE st.id = ?""",
                (item["item_id"],)
            ).fetchone()
        elif item["item_type"] == "math_bank_test":
            row = conn.execute(
                """SELECT mbt.id, mbt.title, mbt.status,
                          (SELECT COUNT(*) FROM math_bank_test_question WHERE test_id = mbt.id) as question_count,
                          (SELECT score FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as score,
                          (SELECT correct_count FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as correct_count,
                          (SELECT total_count FROM math_bank_test_submission WHERE test_id = mbt.id ORDER BY submitted_at DESC LIMIT 1) as total_count
                   FROM math_bank_test mbt WHERE mbt.id = ?""",
                (item["item_id"],)
            ).fetchone()
        else:
            row = None
        if row:
            item_data["details"] = dict(row)
        item_list.append(item_data)
    conn.close()
    result = dict(plan)
    result["items"] = item_list
    return jsonify(result)


@app.route("/api/learning-plans/<int:plan_id>", methods=["DELETE"])
@parent_required
def delete_learning_plan(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    # Delete all underlying items
    items = conn.execute("SELECT * FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchall()
    for item in items:
        if item["item_type"] == "study_session":
            conn.execute("DELETE FROM study_session_word WHERE session_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM study_session WHERE id = ?", (item["item_id"],))
        elif item["item_type"] == "reading_assignment":
            conn.execute("DELETE FROM reading_assignment_answer WHERE assignment_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM reading_assignment_unknown_word WHERE assignment_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM reading_assignment WHERE id = ?", (item["item_id"],))
        elif item["item_type"] == "math_test":
            conn.execute("DELETE FROM math_test_submission WHERE math_test_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM math_test WHERE id = ?", (item["item_id"],))
        elif item["item_type"] == "parent_test":
            conn.execute("DELETE FROM parent_test_word WHERE parent_test_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM parent_test WHERE id = ?", (item["item_id"],))
        elif item["item_type"] == "writing_test":
            conn.execute("DELETE FROM writing_test_submission WHERE writing_test_id = ?", (item["item_id"],))
            conn.execute("DELETE FROM writing_test WHERE id = ?", (item["item_id"],))
    conn.execute("DELETE FROM learning_plan_item WHERE plan_id = ?", (plan_id,))
    conn.execute("DELETE FROM learning_plan WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/learning-plans/<int:plan_id>/release", methods=["POST"])
@parent_required
def release_learning_plan(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    if plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan is not in draft status"}), 400
    item_count = conn.execute("SELECT COUNT(*) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    if item_count == 0:
        conn.close()
        return jsonify({"error": "Plan must have at least one item"}), 400
    conn.execute(
        "UPDATE learning_plan SET status = 'released', released_at = CURRENT_TIMESTAMP WHERE id = ?",
        (plan_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "released"})


@app.route("/api/learning-plans/<int:plan_id>/items/study-session", methods=["POST"])
@parent_required
def add_plan_study_session(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    title = data.get("title") or datetime.now().strftime("%m/%d/%Y")
    word_ids = data.get("word_ids", [])
    if not word_ids:
        conn.close()
        return jsonify({"error": "word_ids required"}), 400
    cursor = conn.execute(
        "INSERT INTO study_session (child_id, created_by, title, learning_plan_id) VALUES (?, ?, ?, ?)",
        (plan["child_id"], session["account_id"], title, plan_id)
    )
    ss_id = cursor.lastrowid
    for wid in word_ids:
        conn.execute("INSERT INTO study_session_word (session_id, word_id) VALUES (?, ?)", (ss_id, wid))
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'study_session', ?, ?)",
        (plan_id, ss_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": ss_id}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/reading-assignment", methods=["POST"])
@parent_required
def add_plan_reading_assignment(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    material_id = data.get("material_id")
    if not material_id:
        conn.close()
        return jsonify({"error": "material_id required"}), 400
    qcount = conn.execute("SELECT COUNT(*) FROM material_question WHERE material_id = ?", (material_id,)).fetchone()[0]
    if qcount == 0:
        conn.close()
        return jsonify({"error": "Material has no questions"}), 400
    cursor = conn.execute(
        "INSERT INTO reading_assignment (material_id, child_id, learning_plan_id) VALUES (?, ?, ?)",
        (material_id, plan["child_id"], plan_id)
    )
    ra_id = cursor.lastrowid
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'reading_assignment', ?, ?)",
        (plan_id, ra_id, max_order + 1)
    )

    # Shared context for auto-created items
    child_id = plan["child_id"]
    material_title = conn.execute("SELECT title FROM reading_material WHERE id = ?", (material_id,)).fetchone()["title"]
    account = get_current_account()

    # Auto-create study session for power words in child's vocab
    power_words = conn.execute(
        "SELECT pw.word FROM material_power_word pw WHERE pw.material_id = ?",
        (material_id,)
    ).fetchall()
    if power_words:
        pw_word_ids = []
        for pw in power_words:
            w = conn.execute(
                "SELECT id FROM word WHERE child_id = ? AND LOWER(word) = LOWER(?)",
                (child_id, pw["word"])
            ).fetchone()
            if w:
                pw_word_ids.append(w["id"])
        if pw_word_ids:
            ss_cursor = conn.execute(
                "INSERT INTO study_session (child_id, created_by, title, learning_plan_id) VALUES (?, ?, ?, ?)",
                (child_id, account["id"], f"Power Words: {material_title}", plan_id)
            )
            ss_id = ss_cursor.lastrowid
            for wid in pw_word_ids:
                conn.execute("INSERT INTO study_session_word (session_id, word_id) VALUES (?, ?)", (ss_id, wid))
            max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'study_session', ?, ?)",
                (plan_id, ss_id, max_order + 1)
            )

    # Auto-create writing assignment for reading summary
    child_row = conn.execute("SELECT grade_level FROM child WHERE id = ?", (child_id,)).fetchone()
    grade = (child_row["grade_level"] or "").lower() if child_row and child_row["grade_level"] else ""

    # Determine word limits by grade level
    if any(g in grade for g in ["2nd", "3rd", "2", "3"]):
        min_words, max_words = 50, 100
    elif any(g in grade for g in ["6th", "7th", "8th", "6", "7", "8"]):
        min_words, max_words = 200, 350
    else:
        min_words, max_words = 100, 200

    topic_text = f'After reading "{material_title}", write a summary in your own words. What is the article about? What is your point of view on this topic?'
    wt_cursor = conn.execute(
        """INSERT INTO writing_test (child_id, created_by, topic_text, timer_mode, time_limit_seconds, min_word_count, max_word_count, learning_plan_id)
           VALUES (?, ?, ?, 'none', 0, ?, ?, ?)""",
        (child_id, account["id"], topic_text, min_words, max_words, plan_id)
    )
    wt_id = wt_cursor.lastrowid
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'writing_test', ?, ?)",
        (plan_id, wt_id, max_order + 1)
    )

    conn.commit()
    conn.close()
    return jsonify({"id": ra_id, "writing_test_created": True, "writing_test_id": wt_id}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/math-test", methods=["POST"])
@parent_required
def add_plan_math_test(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400

    title = request.form.get("title", "").strip()
    if not title:
        conn.close()
        return jsonify({"error": "Title required"}), 400
    if "question_pdf" not in request.files or "answer_pdf" not in request.files:
        conn.close()
        return jsonify({"error": "Both question and answer PDFs are required"}), 400
    q_file = request.files["question_pdf"]
    a_file = request.files["answer_pdf"]
    if not q_file.filename or not a_file.filename:
        conn.close()
        return jsonify({"error": "Both PDF files must be selected"}), 400

    ts = int(time.time())
    q_filename = f"math_q_{plan['child_id']}_{ts}_{secure_filename(q_file.filename)}"
    a_filename = f"math_a_{plan['child_id']}_{ts}_{secure_filename(a_file.filename)}"
    q_path = os.path.join(UPLOAD_FOLDER, q_filename)
    a_path = os.path.join(UPLOAD_FOLDER, a_filename)
    q_file.save(q_path)
    a_file.save(a_path)

    manual_answers = request.form.get("manual_answers", "").strip()
    row = request.form.get("row", "").strip()
    timer_mode = request.form.get("timer_mode", "none").strip()
    time_limit_seconds = request.form.get("time_limit_seconds", 0, type=int)
    if manual_answers:
        answers = json.loads(manual_answers)
        error = None
    elif row:
        rows_dict, error = parse_grid_answer_pdf(a_path)
        if not error:
            answers, error = extract_row_answers(rows_dict, row)
    else:
        answers, error = parse_answer_pdf(a_path)
    if error:
        os.remove(q_path)
        os.remove(a_path)
        conn.close()
        return jsonify({"error": f"Failed to parse answer PDF: {error}"}), 400

    account = get_current_account()
    cursor = conn.execute(
        """INSERT INTO math_test (child_id, created_by, title, question_pdf, answer_pdf, answer_key, total_questions, timer_mode, time_limit_seconds, learning_plan_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (plan["child_id"], account["id"], title, q_filename, a_filename, json.dumps(answers), len(answers), timer_mode, time_limit_seconds, plan_id)
    )
    mt_id = cursor.lastrowid
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'math_test', ?, ?)",
        (plan_id, mt_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": mt_id, "total_questions": len(answers)}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/writing-test", methods=["POST"])
@parent_required
def add_plan_writing_test(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    topic_text = data.get("topic_text", "").strip()
    if not topic_text:
        conn.close()
        return jsonify({"error": "topic_text required"}), 400
    account = get_current_account()
    cursor = conn.execute(
        """INSERT INTO writing_test (child_id, created_by, topic_text, topic_id, timer_mode, time_limit_seconds, min_word_count, max_word_count, learning_plan_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (plan["child_id"], account["id"], topic_text, data.get("topic_id"),
         data.get("timer_mode", "none"), data.get("time_limit_seconds", 0),
         data.get("min_word_count", 0), data.get("max_word_count", 0), plan_id)
    )
    wt_id = cursor.lastrowid
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'writing_test', ?, ?)",
        (plan_id, wt_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": wt_id}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/<int:item_id>", methods=["DELETE"])
@parent_required
def delete_plan_item(plan_id, item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM learning_plan_item WHERE id = ? AND plan_id = ?", (item_id, plan_id)).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Item not found"}), 404
    # Delete the underlying entity
    if item["item_type"] == "study_session":
        conn.execute("DELETE FROM study_session_word WHERE session_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM study_session WHERE id = ?", (item["item_id"],))
    elif item["item_type"] == "reading_assignment":
        conn.execute("DELETE FROM reading_assignment_answer WHERE assignment_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM reading_assignment_unknown_word WHERE assignment_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM reading_assignment WHERE id = ?", (item["item_id"],))
    elif item["item_type"] == "math_test":
        conn.execute("DELETE FROM math_test_submission WHERE math_test_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM math_test WHERE id = ?", (item["item_id"],))
    elif item["item_type"] == "parent_test":
        conn.execute("DELETE FROM parent_test_word WHERE parent_test_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM parent_test WHERE id = ?", (item["item_id"],))
    elif item["item_type"] == "writing_test":
        conn.execute("DELETE FROM writing_test_submission WHERE writing_test_id = ?", (item["item_id"],))
        conn.execute("DELETE FROM writing_test WHERE id = ?", (item["item_id"],))
    conn.execute("DELETE FROM learning_plan_item WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/learning-plans/<int:plan_id>/items/<int:item_id>/review", methods=["POST"])
@parent_required
def toggle_plan_item_review(plan_id, item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM learning_plan_item WHERE id = ? AND plan_id = ?", (item_id, plan_id)).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Item not found"}), 404

    new_val = 0 if item["parent_reviewed"] else 1
    conn.execute("UPDATE learning_plan_item SET parent_reviewed = ? WHERE id = ?", (new_val, item_id))

    # Check if all items are now reviewed
    items = conn.execute(
        "SELECT parent_reviewed FROM learning_plan_item WHERE plan_id = ?", (plan_id,)
    ).fetchall()
    all_reviewed = all(i["parent_reviewed"] for i in items) and len(items) > 0

    if all_reviewed:
        conn.execute(
            "UPDATE learning_plan SET status = 'reviewed' WHERE id = ? AND status = 'completed'",
            (plan_id,)
        )
    else:
        # If un-reviewing an item, revert from reviewed back to completed
        conn.execute(
            "UPDATE learning_plan SET status = 'completed' WHERE id = ? AND status = 'reviewed'",
            (plan_id,)
        )

    conn.commit()
    conn.close()
    return jsonify({"parent_reviewed": bool(new_val), "all_reviewed": all_reviewed})


@app.route("/api/learning-plans/<int:plan_id>/items/review-all", methods=["POST"])
@parent_required
def review_all_plan_items(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    conn.execute("UPDATE learning_plan_item SET parent_reviewed = 1 WHERE plan_id = ?", (plan_id,))
    conn.execute(
        "UPDATE learning_plan SET status = 'reviewed' WHERE id = ? AND status = 'completed'",
        (plan_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/children/<int:child_id>/unassigned-items", methods=["GET"])
@parent_required
def get_unassigned_items(child_id):
    conn = get_db()
    study_sessions = conn.execute(
        """SELECT ss.id, ss.title, ss.status, ss.created_at,
                  (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
           FROM study_session ss
           WHERE ss.child_id = ? AND ss.learning_plan_id IS NULL
           ORDER BY ss.created_at DESC""",
        (child_id,)
    ).fetchall()

    reading_assignments = conn.execute(
        """SELECT ra.id, rm.title as material_title, ra.status, ra.created_at,
                  (SELECT COUNT(*) FROM material_question WHERE material_id = ra.material_id) as question_count
           FROM reading_assignment ra
           JOIN reading_material rm ON ra.material_id = rm.id
           WHERE ra.child_id = ? AND ra.learning_plan_id IS NULL
           ORDER BY ra.created_at DESC""",
        (child_id,)
    ).fetchall()

    math_tests = conn.execute(
        """SELECT mt.id, mt.title, mt.status, mt.total_questions, mt.created_at
           FROM math_test mt
           WHERE mt.child_id = ? AND mt.learning_plan_id IS NULL
           ORDER BY mt.created_at DESC""",
        (child_id,)
    ).fetchall()

    writing_tests = conn.execute(
        """SELECT wt.id, wt.topic_text, wt.status, wt.created_at
           FROM writing_test wt
           WHERE wt.child_id = ? AND wt.learning_plan_id IS NULL
           ORDER BY wt.created_at DESC""",
        (child_id,)
    ).fetchall()

    science_study_sessions = conn.execute(
        """SELECT ss.id, ss.title, ss.status, ss.created_at,
                  (SELECT COUNT(*) FROM science_study_session_question WHERE session_id = ss.id) as question_count
           FROM science_study_session ss
           WHERE ss.child_id = ? AND ss.learning_plan_id IS NULL
           ORDER BY ss.created_at DESC""",
        (child_id,)
    ).fetchall()

    science_tests = conn.execute(
        """SELECT st.id, st.title, st.status, st.created_at,
                  (SELECT COUNT(*) FROM science_test_question WHERE test_id = st.id) as question_count
           FROM science_test st
           WHERE st.child_id = ? AND st.learning_plan_id IS NULL
           ORDER BY st.created_at DESC""",
        (child_id,)
    ).fetchall()

    conn.close()
    return jsonify({
        "study_sessions": [dict(s) for s in study_sessions],
        "reading_assignments": [dict(a) for a in reading_assignments],
        "math_tests": [dict(t) for t in math_tests],
        "writing_tests": [dict(t) for t in writing_tests],
        "science_study_sessions": [dict(s) for s in science_study_sessions],
        "science_tests": [dict(t) for t in science_tests],
    })


@app.route("/api/learning-plans/<int:plan_id>/items/link", methods=["POST"])
@parent_required
def link_item_to_plan(plan_id):
    data = request.json
    item_type = data.get("item_type")
    item_id = data.get("item_id")

    if item_type not in ("study_session", "reading_assignment", "math_test", "writing_test", "science_study_session", "science_test"):
        return jsonify({"error": "Invalid item_type"}), 400
    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan:
        conn.close()
        return jsonify({"error": "Plan not found"}), 404
    if plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan is not in draft status"}), 400

    # Verify item exists, belongs to same child, and is unassigned
    table = item_type  # study_session, reading_assignment, math_test, science_study_session, science_test
    # Map item_type to learning_plan_item type
    plan_item_type = item_type
    if item_type == "science_study_session":
        plan_item_type = "science_study"
    item = conn.execute(
        f"SELECT id, child_id, learning_plan_id FROM {table} WHERE id = ?", (item_id,)
    ).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Item not found"}), 404
    if item["child_id"] != plan["child_id"]:
        conn.close()
        return jsonify({"error": "Item belongs to a different child"}), 400
    if item["learning_plan_id"] is not None:
        conn.close()
        return jsonify({"error": "Item is already in a plan"}), 400

    # Get next sort order
    max_sort = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)
    ).fetchone()[0]

    # Link the item
    conn.execute(
        f"UPDATE {table} SET learning_plan_id = ? WHERE id = ?", (plan_id, item_id)
    )
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, ?, ?, ?)",
        (plan_id, plan_item_type, item_id, max_sort + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True}), 200


# ── Science Bowl routes ──

@app.route("/api/science/upload", methods=["POST"])
@parent_required
def upload_science_pdf():
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


# ── NSB Bulk Import ──

_bulk_import_progress = {}

NSB_BASE_URL = "https://science.osti.gov"
NSB_PAGE_URL = NSB_BASE_URL + "/wdts/nsb/Regional-Competitions/Resources/MS-Sample-Questions"


def _do_bulk_import(child_id, job_id):
    """Background worker: download all NSB PDFs, parse, deduplicate, save."""
    import requests as req_lib

    progress = _bulk_import_progress[job_id]
    progress["status"] = "fetching_links"

    try:
        # Step 1: Fetch the page and extract PDF links
        resp = req_lib.get(NSB_PAGE_URL, timeout=30)
        resp.raise_for_status()
        pdf_paths = re.findall(r'href="(/-/media/wdts/nsb/pdf/MS-Sample-Questions/[^"]+\.pdf)"', resp.text)
        pdf_paths = list(dict.fromkeys(pdf_paths))  # dedupe, preserve order

        progress["total_pdfs"] = len(pdf_paths)
        progress["status"] = "downloading"

        # Step 2: Load existing question texts for dedup (with ids for updating source_pdf)
        conn = get_db()
        existing = conn.execute(
            "SELECT id, question_text, source_pdf FROM science_question WHERE child_id = ?", (child_id,)
        ).fetchall()
        existing_map = {}  # norm_text -> {id, source_pdf}
        for row in existing:
            norm = row["question_text"].strip().lower()
            existing_map[norm] = {"id": row["id"], "source_pdf": row["source_pdf"] or ""}
        conn.close()

        total_new = 0
        total_skipped = 0
        total_updated = 0
        total_failed = 0
        errors = []

        # Step 3: Process each PDF
        for i, pdf_path in enumerate(pdf_paths):
            progress["current_pdf"] = i + 1
            progress["current_file"] = pdf_path.split("/")[-1]

            url = NSB_BASE_URL + pdf_path

            try:
                pdf_resp = req_lib.get(url, timeout=30)
                pdf_resp.raise_for_status()

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(pdf_resp.content)
                    tmp_path = tmp.name

                questions, error = parse_science_bowl_pdf(tmp_path)
                os.unlink(tmp_path)

                if error or not questions:
                    total_failed += 1
                    errors.append({"file": pdf_path.split("/")[-1], "url": url, "error": error or "No questions found"})
                    continue

                # Save new questions (dedup by question_text)
                conn = get_db()
                pdf_new = 0
                pdf_skip = 0
                pdf_updated = 0
                for q in questions:
                    norm_text = q["question_text"].strip().lower()
                    if norm_text in existing_map:
                        # Question exists - update source_pdf if it doesn't have a URL
                        ex = existing_map[norm_text]
                        if not ex["source_pdf"].startswith("http"):
                            conn.execute(
                                "UPDATE science_question SET source_pdf = ? WHERE id = ?",
                                (url, ex["id"])
                            )
                            ex["source_pdf"] = url
                            pdf_updated += 1
                        pdf_skip += 1
                        continue

                    round_name = q.get("round_name", "")

                    conn.execute(
                        """INSERT INTO science_question
                           (child_id, category, question_type, answer_format, question_text, choices, correct_answer, explanation, source_pdf, round_name)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (child_id, q["category"], q["question_type"], q["answer_format"],
                         q["question_text"], json.dumps(q.get("choices")) if q.get("choices") else None,
                         q["correct_answer"], q.get("explanation", ""), url, round_name)
                    )
                    existing_map[norm_text] = {"id": 0, "source_pdf": url}
                    pdf_new += 1

                conn.commit()
                conn.close()
                total_new += pdf_new
                total_skipped += pdf_skip
                total_updated += pdf_updated

            except Exception as e:
                total_failed += 1
                errors.append({"file": pdf_path.split("/")[-1], "url": url, "error": str(e)})

        progress["status"] = "done"
        progress["total_new"] = total_new
        progress["total_skipped"] = total_skipped
        progress["total_updated"] = total_updated
        progress["total_failed"] = total_failed
        progress["errors"] = errors[:20]  # cap error list

    except Exception as e:
        progress["status"] = "error"
        progress["error"] = str(e)


@app.route("/api/science/bulk-import-nsb", methods=["POST"])
@parent_required
def bulk_import_nsb():
    data = request.json
    child_id = data.get("child_id")
    if not child_id:
        return jsonify({"error": "child_id required"}), 400

    job_id = f"nsb_{child_id}_{int(time.time())}"
    _bulk_import_progress[job_id] = {
        "status": "starting",
        "total_pdfs": 0,
        "current_pdf": 0,
        "current_file": "",
        "total_new": 0,
        "total_skipped": 0,
        "total_updated": 0,
        "total_failed": 0,
    }

    t = threading.Thread(target=_do_bulk_import, args=(child_id, job_id), daemon=True)
    t.start()
    return jsonify({"job_id": job_id}), 200


@app.route("/api/science/bulk-import-status/<job_id>", methods=["GET"])
@parent_required
def bulk_import_status(job_id):
    progress = _bulk_import_progress.get(job_id)
    if not progress:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(progress), 200


@app.route("/api/children/<int:child_id>/science-questions", methods=["GET"])
@login_required
def list_science_questions(child_id):
    from datetime import datetime, timedelta
    category = request.args.get("category")
    status_filter = request.args.get("status")  # comma-separated: never,wrong,due,good,mastered
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(per_page, 200)

    conn = get_db()

    # Fetch all questions with mastery data
    sql = """SELECT sq.*, COALESCE(sp.correct_count, 0) as m_correct_count,
                    COALESCE(sp.wrong_count, 0) as m_wrong_count,
                    COALESCE(sp.streak, 0) as m_streak,
                    COALESCE(sp.difficulty_level, 1) as m_difficulty_level,
                    sp.last_tested as m_last_tested, sp.last_correct_at as m_last_correct_at
             FROM science_question sq
             LEFT JOIN science_question_progress sp ON sq.id = sp.question_id AND sp.child_id = sq.child_id
             WHERE sq.child_id = ?"""
    params = [child_id]
    if category:
        sql += " AND sq.category = ?"
        params.append(category)
    sql += " ORDER BY sq.round_name, sq.question_type, sq.id"
    questions = conn.execute(sql, params).fetchall()

    # All distinct categories for this child (unaffected by filters)
    all_categories = [r[0] for r in conn.execute(
        "SELECT DISTINCT category FROM science_question WHERE child_id = ? ORDER BY category",
        (child_id,)
    ).fetchall()]
    conn.close()

    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    result = []
    status_counts = {"never": 0, "wrong": 0, "due": 0, "good": 0, "mastered": 0}
    for q in questions:
        d = dict(q)
        if d["choices"]:
            d["choices"] = json.loads(d["choices"])
        # Compute mastery status
        d["mastery_status"] = compute_mastery_status(d, cutoff)
        status_counts[d["mastery_status"]] += 1
        # Clean up internal mastery fields
        for k in ("m_correct_count", "m_wrong_count", "m_streak", "m_difficulty_level", "m_last_tested", "m_last_correct_at"):
            del d[k]
        result.append(d)

    # Apply status filter
    if status_filter:
        statuses = set(status_filter.split(","))
        result = [q for q in result if q["mastery_status"] in statuses]

    # Non-paginated mode (backward compat)
    if page is None:
        return jsonify(result)

    # Paginated mode
    total = len(result)
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = result[start:start + per_page]

    return jsonify({
        "questions": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "categories": all_categories,
        "status_counts": status_counts
    })


@app.route("/api/science-questions/<int:question_id>", methods=["PUT"])
@parent_required
def update_science_question(question_id):
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


# ── Math Question Bank ──

@app.route("/parent/child/<int:child_id>/math-questions")
@parent_required
def math_question_bank_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("math_questions.html", child=dict(child))

@app.route("/api/children/<int:child_id>/math-questions", methods=["GET"])
@login_required
def list_math_questions(child_id):
    from datetime import datetime, timedelta
    concept_filter = request.args.get("concept")
    difficulty_filter = request.args.get("difficulty", type=int)
    status_filter = request.args.get("status")
    search = request.args.get("search", "").strip().lower()
    page = request.args.get("page", type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(per_page, 200)

    conn = get_db()

    sql = """SELECT mq.*, COALESCE(mp.correct_count, 0) as m_correct_count,
                    COALESCE(mp.wrong_count, 0) as m_wrong_count,
                    COALESCE(mp.streak, 0) as m_streak,
                    COALESCE(mp.difficulty_level, 1) as m_difficulty_level,
                    mp.last_tested as m_last_tested, mp.last_correct_at as m_last_correct_at
             FROM math_question mq
             LEFT JOIN math_question_progress mp ON mq.id = mp.question_id AND mp.child_id = mq.child_id
             WHERE mq.child_id = ?"""
    params = [child_id]
    if difficulty_filter:
        sql += " AND mq.difficulty = ?"
        params.append(difficulty_filter)
    sql += " ORDER BY mq.created_at DESC"
    questions = conn.execute(sql, params).fetchall()

    # All distinct concepts for this child
    all_concepts_raw = conn.execute(
        "SELECT DISTINCT concepts FROM math_question WHERE child_id = ? AND concepts IS NOT NULL",
        (child_id,)
    ).fetchall()
    all_concepts = set()
    for row in all_concepts_raw:
        try:
            for c in json.loads(row["concepts"]):
                all_concepts.add(c)
        except (json.JSONDecodeError, TypeError):
            pass

    unverified_count = conn.execute(
        "SELECT COUNT(*) FROM math_question WHERE child_id = ? AND verified = 0",
        (child_id,)
    ).fetchone()[0]
    conn.close()

    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    result = []
    status_counts = {"never": 0, "wrong": 0, "due": 0, "good": 0, "mastered": 0}
    for q in questions:
        d = dict(q)
        if d["choices"]:
            try:
                d["choices"] = json.loads(d["choices"])
            except (json.JSONDecodeError, TypeError):
                pass
        if d["concepts"]:
            try:
                d["concepts"] = json.loads(d["concepts"])
            except (json.JSONDecodeError, TypeError):
                d["concepts"] = []
        else:
            d["concepts"] = []

        d["mastery_status"] = compute_mastery_status(d, cutoff)
        status_counts[d["mastery_status"]] += 1

        # Apply concept filter
        if concept_filter and concept_filter not in d["concepts"]:
            for k in ("m_correct_count", "m_wrong_count", "m_streak", "m_difficulty_level", "m_last_tested", "m_last_correct_at"):
                del d[k]
            continue

        # Apply search filter
        if search and search not in d["question_text"].lower():
            for k in ("m_correct_count", "m_wrong_count", "m_streak", "m_difficulty_level", "m_last_tested", "m_last_correct_at"):
                del d[k]
            continue

        for k in ("m_correct_count", "m_wrong_count", "m_streak", "m_difficulty_level", "m_last_tested", "m_last_correct_at"):
            del d[k]
        result.append(d)

    # Apply status filter
    if status_filter:
        statuses = set(status_filter.split(","))
        result = [q for q in result if q["mastery_status"] in statuses]

    if page is None:
        return jsonify(result)

    total = len(result)
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = result[start:start + per_page]

    return jsonify({
        "questions": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "concepts": sorted(all_concepts),
        "status_counts": status_counts,
        "unverified_count": unverified_count
    })


@app.route("/api/children/<int:child_id>/math-questions", methods=["POST"])
@parent_required
def add_math_question(child_id):
    data = request.json
    question_text = data.get("question_text", "").strip()
    choices = data.get("choices", {})
    correct_answer = data.get("correct_answer", "").strip().upper()
    if not question_text or not choices or not correct_answer:
        return jsonify({"error": "question_text, choices, and correct_answer required"}), 400

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO math_question (child_id, question_text, choices, correct_answer, solution_steps, concepts, grade_level, difficulty, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (child_id, question_text, json.dumps(choices), correct_answer,
         data.get("solution_steps", ""), json.dumps(data.get("concepts", [])),
         data.get("grade_level", ""), data.get("difficulty", 3), data.get("source", "manual"))
    )
    conn.commit()
    conn.close()
    return jsonify({"id": cursor.lastrowid}), 201


@app.route("/api/math-questions/<int:question_id>", methods=["PUT"])
@parent_required
def update_math_question(question_id):
    data = request.json
    conn = get_db()
    q = conn.execute("SELECT * FROM math_question WHERE id = ?", (question_id,)).fetchone()
    if not q:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    conn.execute(
        """UPDATE math_question SET question_text = ?, choices = ?, correct_answer = ?,
           solution_steps = ?, concepts = ?, grade_level = ?, difficulty = ?, source = ?,
           verified = 1
           WHERE id = ?""",
        (data.get("question_text", q["question_text"]),
         json.dumps(data.get("choices", json.loads(q["choices"]))),
         data.get("correct_answer", q["correct_answer"]).upper(),
         data.get("solution_steps", q["solution_steps"]),
         json.dumps(data.get("concepts", json.loads(q["concepts"] or "[]"))),
         data.get("grade_level", q["grade_level"]),
         data.get("difficulty", q["difficulty"]),
         data.get("source", q["source"]),
         question_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/math-questions/<int:question_id>", methods=["DELETE"])
@parent_required
def delete_math_question(question_id):
    conn = get_db()
    conn.execute("DELETE FROM math_question WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/children/<int:child_id>/math-questions/generate-ai", methods=["POST"])
@parent_required
def generate_math_questions_ai(child_id):
    api_key = get_config("openai_api_key")
    if not api_key:
        return jsonify({"error": "OpenAI API key not configured. Go to Settings to add it."}), 400

    data = request.json
    count = data.get("count", 10)
    style = data.get("style", "Mixed")
    grade_level = data.get("grade_level", "4th grade")
    difficulty = data.get("difficulty", "mixed")

    if difficulty == "mixed":
        diff_instruction = (
            "- Rate each problem's difficulty from 1 to 5 (1=easiest, 5=hardest) relative to the grade level\n"
            "- Provide a balanced mix of difficulties: include problems at levels 1, 2, 3, 4, and 5\n"
        )
    else:
        diff_instruction = f"- All problems should be at difficulty level {difficulty} out of 5 (1=easiest, 5=hardest) relative to the grade level\n"

    prompt = (
        f"Generate {count} {style} multiple choice math problems for {grade_level} level.\n\n"
        "Requirements:\n"
        f"- Each problem should be appropriately challenging for {grade_level}\n"
        "- Each problem has 5 choices labeled A through E\n"
        "- Use plain text only. Do NOT use LaTeX, MathJax, or any math formatting markup. Write expressions inline like 48 ÷ 6 × 3.\n"
        "- Tag each problem with math concepts it covers (e.g., Fractions, Geometry, Number Theory, Algebra, Combinatorics, Ratios, Percentages, Arithmetic, Measurement, Probability)\n"
        f"{diff_instruction}"
        "- Correct answers MUST be randomized across A-E. No letter should appear more than 3 times.\n\n"
        "Output format:\n\n"
        "PROBLEMS\n"
        "1. [problem text]\n"
        "A. [choice]\n"
        "B. [choice]\n"
        "C. [choice]\n"
        "D. [choice]\n"
        "E. [choice]\n"
        "Concepts: [comma-separated tags]\n"
        "Difficulty: [1-5]\n\n"
        "ANSWERS\n"
        "1. Answer: [letter]\n"
        "Steps: [step-by-step solution]\n\n"
        "2. Answer: [letter]\n"
        "Steps: [step-by-step solution]\n"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000,
        )
        result = response.choices[0].message.content.strip()
        return jsonify({"raw_response": result, "prompt": prompt})
    except Exception as e:
        return jsonify({"error": f"AI generation failed: {str(e)}"}), 500


@app.route("/api/children/<int:child_id>/math-questions/verify", methods=["POST"])
@parent_required
def verify_math_questions(child_id):
    api_key = get_config("openai_api_key")
    if not api_key:
        return jsonify({"error": "OpenAI API key not configured. Go to Settings to add it."}), 400

    data = request.json
    question_ids = data.get("question_ids", [])

    conn = get_db()
    if question_ids:
        placeholders = ",".join("?" for _ in question_ids)
        questions = conn.execute(
            f"SELECT * FROM math_question WHERE child_id = ? AND verified = 0 AND id IN ({placeholders})",
            [child_id] + question_ids
        ).fetchall()
    else:
        questions = conn.execute(
            "SELECT * FROM math_question WHERE child_id = ? AND verified = 0", (child_id,)
        ).fetchall()

    if not questions:
        conn.close()
        return jsonify({"flagged": [], "total_checked": 0})

    batch_size = 20
    all_flagged = []
    correct_ids = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i:i + batch_size]
        prompt_lines = [
            "For each math problem below, verify if the marked correct answer is actually correct.",
            "Check the solution steps and the choices. Report any discrepancies.",
            ""
        ]
        for idx, q in enumerate(batch):
            choices = {}
            try:
                choices = json.loads(q["choices"]) if q["choices"] else {}
            except (json.JSONDecodeError, TypeError):
                pass
            choices_str = " ".join(f'{k}. {v}' for k, v in sorted(choices.items()))
            prompt_lines.append(f"Question {idx + 1}: {q['question_text']}")
            prompt_lines.append(f"Choices: {choices_str}")
            prompt_lines.append(f"Marked Answer: {q['correct_answer']}")
            prompt_lines.append(f"Solution: {q['solution_steps'] or 'N/A'}")
            prompt_lines.append("")

        prompt_lines.append("Output format (one entry per question, no extra text):")
        prompt_lines.append("1. Status: CORRECT | WRONG")
        prompt_lines.append("   Issue: [if wrong, explain what the correct answer should be]")
        prompt_lines.append("   Suggested Answer: [letter or NONE if no choice matches]")

        prompt = "\n".join(prompt_lines)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=4000,
            )
            result_text = response.choices[0].message.content.strip()
        except Exception as e:
            conn.close()
            return jsonify({"error": f"AI verification failed: {str(e)}"}), 500

        entries = re.split(r'\n(?=\d+\.)', result_text)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            num_match = re.match(r'^(\d+)\.', entry)
            if not num_match:
                continue
            num = int(num_match.group(1)) - 1
            if num < 0 or num >= len(batch):
                continue

            if "WRONG" not in entry.upper():
                correct_ids.append(batch[num]["id"])
                continue

            q = batch[num]
            choices = {}
            try:
                choices = json.loads(q["choices"]) if q["choices"] else {}
            except (json.JSONDecodeError, TypeError):
                pass
            concepts = []
            try:
                concepts = json.loads(q["concepts"]) if q["concepts"] else []
            except (json.JSONDecodeError, TypeError):
                pass

            issue_match = re.search(r'Issue:\s*(.+?)(?:\n|$)', entry, re.IGNORECASE)
            suggested_match = re.search(r'Suggested Answer:\s*(\S+)', entry, re.IGNORECASE)

            # Skip false positive: suggested answer matches current answer
            if suggested_match:
                suggested = suggested_match.group(1).strip().rstrip('.').upper()
                if suggested == q["correct_answer"].strip().upper():
                    correct_ids.append(q["id"])
                    continue

            all_flagged.append({
                "id": q["id"],
                "question_text": q["question_text"],
                "choices": choices,
                "correct_answer": q["correct_answer"],
                "solution_steps": q["solution_steps"],
                "concepts": concepts,
                "difficulty": q["difficulty"],
                "grade_level": q["grade_level"],
                "source": q["source"],
                "issue": issue_match.group(1).strip() if issue_match else "Answer may be incorrect",
                "suggested_answer": suggested_match.group(1).strip() if suggested_match else ""
            })

    if correct_ids:
        placeholders = ",".join("?" for _ in correct_ids)
        conn.execute(
            f"UPDATE math_question SET verified = 1 WHERE id IN ({placeholders})",
            correct_ids
        )
        conn.commit()
    conn.close()

    return jsonify({"flagged": all_flagged, "total_checked": len(questions)})


@app.route("/api/children/<int:child_id>/math-questions/import-ai", methods=["POST"])
@parent_required
def import_math_questions_ai(child_id):
    data = request.json
    raw_text = data.get("text", "")
    grade_level = data.get("grade_level", "")
    if not raw_text:
        return jsonify({"error": "No text provided"}), 400

    # Parse the AI response
    parts = re.split(r'\n\s*ANSWERS\s*\n', raw_text, maxsplit=1)
    problems_text = parts[0].strip()
    answers_text = parts[1].strip() if len(parts) > 1 else ""

    # Remove leading "PROBLEMS" header if present
    problems_text = re.sub(r'^\s*PROBLEMS\s*\n', '', problems_text, flags=re.IGNORECASE)

    # Parse problems
    problem_blocks = re.split(r'\n(?=\d+\.)', problems_text)
    problems = []
    for block in problem_blocks:
        block = block.strip()
        if not block:
            continue
        # Extract question number and text
        m = re.match(r'(\d+)\.\s*(.*?)(?=\nA\.)', block, re.DOTALL)
        if not m:
            continue
        q_num = int(m.group(1))
        q_text = re.sub(r'\s+', ' ', m.group(2)).strip()

        # Extract choices
        choices = {}
        for letter in ['A', 'B', 'C', 'D', 'E']:
            cm = re.search(rf'{letter}\.\s*(.*?)(?=\n[A-E]\.|(?:\nConcepts:)|\nDifficulty:|\Z)', block, re.DOTALL)
            if cm:
                choices[letter] = cm.group(1).strip()

        # Extract concepts
        concepts = []
        cm = re.search(r'Concepts:\s*(.*?)(?=\nDifficulty:|\Z)', block, re.DOTALL)
        if cm:
            concepts = [c.strip() for c in cm.group(1).split(",") if c.strip()]

        # Extract difficulty
        difficulty = 3
        dm = re.search(r'Difficulty:\s*(\d)', block)
        if dm:
            difficulty = int(dm.group(1))

        problems.append({
            "num": q_num,
            "question_text": q_text,
            "choices": choices,
            "concepts": concepts,
            "difficulty": difficulty
        })

    # Parse answers
    answers = {}
    if answers_text:
        answer_blocks = re.split(r'\n(?=\d+\.)', answers_text)
        for block in answer_blocks:
            block = block.strip()
            am = re.match(r'(\d+)\.\s*Answer:\s*([A-E])', block)
            if am:
                num = int(am.group(1))
                letter = am.group(2)
                steps = ""
                sm = re.search(r'Steps:\s*(.*?)(?=\n\d+\.|$)', block, re.DOTALL)
                if sm:
                    steps = sm.group(1).strip()
                answers[num] = {"answer": letter, "steps": steps}

    # Store in database, skipping duplicates
    conn = get_db()
    added = 0
    skipped = 0
    for p in problems:
        ans_data = answers.get(p["num"], {})
        correct_answer = ans_data.get("answer", "")
        solution_steps = ans_data.get("steps", "")
        if not correct_answer or not p["choices"]:
            continue
        existing = conn.execute(
            "SELECT id FROM math_question WHERE child_id = ? AND LOWER(TRIM(question_text)) = LOWER(TRIM(?))",
            (child_id, p["question_text"])
        ).fetchone()
        if existing:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO math_question (child_id, question_text, choices, correct_answer, solution_steps, concepts, grade_level, difficulty, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (child_id, p["question_text"], json.dumps(p["choices"]), correct_answer,
             solution_steps, json.dumps(p["concepts"]), grade_level, p["difficulty"], "AI generated")
        )
        added += 1
    conn.commit()
    conn.close()
    return jsonify({"added": added, "skipped": skipped})


# ── Math Bank Tests ──

@app.route("/parent/child/<int:child_id>/math-bank-test/new")
@parent_required
def create_math_bank_test_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("math_bank_test_create.html", child=dict(child))


@app.route("/child/<int:child_id>/math-bank-test/<int:test_id>")
@login_required
def take_math_bank_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM math_bank_test WHERE id = ?", (test_id,)).fetchone()
    conn.close()
    if not child or not test:
        return "Not found", 404
    learning_plan_id = request.args.get("plan_id") or test["learning_plan_id"]
    return render_template("math_bank_test.html", child=dict(child), test=dict(test), learning_plan_id=learning_plan_id)


@app.route("/child/<int:child_id>/math-bank-test/<int:test_id>/review")
@login_required
def review_math_bank_test(child_id, test_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    test = conn.execute("SELECT * FROM math_bank_test WHERE id = ?", (test_id,)).fetchone()
    if not child or not test:
        conn.close()
        return "Not found", 404
    sub = conn.execute(
        "SELECT * FROM math_bank_test_submission WHERE test_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (test_id,)
    ).fetchone()
    questions = conn.execute(
        """SELECT q.* FROM math_question q
           JOIN math_bank_test_question btq ON q.id = btq.question_id
           WHERE btq.test_id = ? ORDER BY q.id""",
        (test_id,)
    ).fetchall()
    conn.close()
    learning_plan_id = request.args.get("plan_id") or test["learning_plan_id"]
    qs = []
    for q in questions:
        d = dict(q)
        if d["choices"]:
            d["choices"] = json.loads(d["choices"])
        if d["concepts"]:
            try:
                d["concepts"] = json.loads(d["concepts"])
            except (json.JSONDecodeError, TypeError):
                d["concepts"] = []
        qs.append(d)
    answers = json.loads(sub["answers"]) if sub else {}
    return render_template("math_bank_test_review.html", child=dict(child), test=dict(test),
                           submission=dict(sub) if sub else None, questions=qs, answers=answers,
                           learning_plan_id=learning_plan_id)


@app.route("/api/math-bank-tests", methods=["POST"])
@parent_required
def create_math_bank_test():
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
        """INSERT INTO math_bank_test (child_id, created_by, title, timer_mode, time_limit_seconds)
           VALUES (?, ?, ?, ?, ?)""",
        (child_id, account["id"], title or "Math Test", timer_mode, time_limit_seconds)
    )
    test_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute("INSERT INTO math_bank_test_question (test_id, question_id) VALUES (?, ?)", (test_id, qid))
    conn.commit()
    conn.close()
    return jsonify({"id": test_id, "total_questions": len(question_ids)}), 201


@app.route("/api/children/<int:child_id>/math-bank-tests", methods=["GET"])
@login_required
def list_math_bank_tests(child_id):
    conn = get_db()
    tests = conn.execute("SELECT * FROM math_bank_test WHERE child_id = ? ORDER BY created_at DESC", (child_id,)).fetchall()
    result = []
    for t in tests:
        count = conn.execute("SELECT COUNT(*) FROM math_bank_test_question WHERE test_id = ?", (t["id"],)).fetchone()[0]
        sub = conn.execute(
            "SELECT * FROM math_bank_test_submission WHERE test_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (t["id"],)
        ).fetchone()
        d = dict(t)
        d["question_count"] = count
        d["latest_submission"] = dict(sub) if sub else None
        result.append(d)
    conn.close()
    return jsonify(result)


@app.route("/api/math-bank-tests/<int:test_id>", methods=["GET"])
@login_required
def get_math_bank_test(test_id):
    conn = get_db()
    test = conn.execute("SELECT * FROM math_bank_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404
    questions = conn.execute(
        """SELECT q.* FROM math_question q
           JOIN math_bank_test_question btq ON q.id = btq.question_id
           WHERE btq.test_id = ? ORDER BY q.id""",
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


@app.route("/api/math-bank-tests/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_math_bank_test(test_id):
    data = request.json
    answers = data.get("answers", {})
    time_taken = data.get("time_taken_seconds", 0)

    conn = get_db()
    test = conn.execute("SELECT * FROM math_bank_test WHERE id = ?", (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({"error": "Test not found"}), 404

    questions = conn.execute(
        """SELECT q.* FROM math_question q
           JOIN math_bank_test_question btq ON q.id = btq.question_id
           WHERE btq.test_id = ?""",
        (test_id,)
    ).fetchall()

    correct_count = 0
    total_count = len(questions)
    graded_answers = {}

    for q in questions:
        qid_str = str(q["id"])
        child_answer = answers.get(qid_str, "").strip().upper()
        correct = q["correct_answer"].strip().upper()
        is_correct = child_answer == correct

        if is_correct:
            correct_count += 1

        graded_answers[qid_str] = {
            "child_answer": child_answer,
            "correct_answer": correct,
            "is_correct": is_correct
        }

    score = round(correct_count / total_count * 100) if total_count > 0 else 0

    account = get_current_account()
    progress_child_id = account.get("child_id") or test["child_id"]

    # Update per-question mastery tracking
    for q in questions:
        ga = graded_answers.get(str(q["id"]))
        if ga:
            update_math_question_progress(conn, progress_child_id, q["id"], ga["is_correct"])

    conn.execute(
        """INSERT INTO math_bank_test_submission (test_id, child_id, answers, score, correct_count, total_count, time_taken_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (test_id, progress_child_id, json.dumps(graded_answers), score, correct_count, total_count, time_taken)
    )
    conn.execute("UPDATE math_bank_test SET status = 'completed' WHERE id = ?", (test_id,))
    conn.commit()

    if test["learning_plan_id"]:
        check_plan_completion(test["learning_plan_id"], conn)
    conn.close()

    return jsonify({"score": score, "correct_count": correct_count, "total_count": total_count, "answers": graded_answers})


@app.route("/api/math-bank-tests/<int:test_id>", methods=["DELETE"])
@parent_required
def delete_math_bank_test(test_id):
    conn = get_db()
    conn.execute("DELETE FROM math_bank_test WHERE id = ?", (test_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


def update_math_question_progress(conn, child_id, question_id, correct):
    from datetime import datetime
    progress = conn.execute(
        "SELECT * FROM math_question_progress WHERE child_id = ? AND question_id = ?",
        (child_id, question_id)
    ).fetchone()
    if not progress:
        conn.execute(
            "INSERT INTO math_question_progress (child_id, question_id, difficulty_level) VALUES (?, ?, 1)",
            (child_id, question_id)
        )
        progress = {"correct_count": 0, "wrong_count": 0, "streak": 0, "difficulty_level": 1}
    else:
        progress = dict(progress)

    now = datetime.now()
    if correct:
        conn.execute(
            """UPDATE math_question_progress
               SET correct_count = ?, wrong_count = ?, streak = ?, difficulty_level = ?, last_tested = ?, last_correct_at = ?
               WHERE child_id = ? AND question_id = ?""",
            (progress["correct_count"] + 1, progress["wrong_count"], progress["streak"] + 1,
             min(5, progress["difficulty_level"] + 1), now, now, child_id, question_id)
        )
    else:
        conn.execute(
            """UPDATE math_question_progress
               SET correct_count = ?, wrong_count = ?, streak = 0, difficulty_level = ?, last_tested = ?
               WHERE child_id = ? AND question_id = ?""",
            (progress["correct_count"], progress["wrong_count"] + 1,
             max(1, progress["difficulty_level"] - 1), now, child_id, question_id)
        )


# ── Science Study Sessions ──

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
           ORDER BY q.question_type DESC, q.id""",
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

    plan_id = session_row["learning_plan_id"]
    test_id = None

    if plan_id:
        # Auto-create a science test from the same questions
        questions = conn.execute(
            "SELECT question_id FROM science_study_session_question WHERE session_id = ?", (session_id,)
        ).fetchall()
        if questions:
            title = f"Science Test: {session_row['title'] or 'Science'}"
            cursor = conn.execute(
                """INSERT INTO science_test (child_id, created_by, title, timer_mode, time_limit_seconds, learning_plan_id)
                   VALUES (?, ?, ?, 'none', 0, ?)""",
                (session_row["child_id"], session_row["created_by"], title, plan_id)
            )
            test_id = cursor.lastrowid
            for q in questions:
                conn.execute(
                    "INSERT INTO science_test_question (test_id, question_id) VALUES (?, ?)",
                    (test_id, q["question_id"])
                )
            # Add the test to the same learning plan
            max_sort = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'science_test', ?, ?)",
                (plan_id, test_id, max_sort + 1)
            )

        check_plan_completion(plan_id, conn)

    conn.commit()
    conn.close()
    return jsonify({"success": True, "test_id": test_id})


@app.route("/api/science-study-sessions/<int:session_id>", methods=["DELETE"])
@parent_required
def delete_science_study_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM science_study_session WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ── Science Tests ──

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
            # Short answer: check main answer and ACCEPT alternatives
            main_answer = re.split(r'\s*\(', correct)[0].strip()
            is_correct = child_answer.upper() == main_answer.upper()
            if not is_correct and "ACCEPT:" in correct.upper():
                accepts = re.findall(r'ACCEPT:\s*([^)]+)', correct, re.IGNORECASE)
                for acc in accepts:
                    for alt in acc.split(';'):
                        if child_answer.upper().strip() == alt.strip().upper():
                            is_correct = True
                            break

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
    progress_child_id = account.get("child_id") or test["child_id"]

    # Update per-question mastery tracking
    for q in questions:
        ga = graded_answers.get(str(q["id"]))
        if ga:
            update_science_progress(progress_child_id, q["id"], ga["is_correct"])

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


# ── Science Page Routes ──

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


# ── Science Learning Plan Integration ──

@app.route("/api/learning-plans/<int:plan_id>/items/math-bank-test", methods=["POST"])
@parent_required
def add_plan_math_bank_test(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    title = data.get("title", "").strip() or "Math Practice"
    question_ids = data.get("question_ids", [])
    if not question_ids:
        conn.close()
        return jsonify({"error": "question_ids required"}), 400
    timer_mode = data.get("timer_mode", "none")
    time_limit_seconds = data.get("time_limit_seconds", 0)
    account = get_current_account()
    cursor = conn.execute(
        """INSERT INTO math_bank_test (child_id, created_by, title, timer_mode, time_limit_seconds, learning_plan_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (plan["child_id"], account["id"], title, timer_mode, time_limit_seconds, plan_id)
    )
    test_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute("INSERT INTO math_bank_test_question (test_id, question_id) VALUES (?, ?)", (test_id, qid))
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'math_bank_test', ?, ?)",
        (plan_id, test_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": test_id}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/science-study", methods=["POST"])
@parent_required
def add_plan_science_study(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    title = data.get("title", "Science Study").strip()
    question_ids = data.get("question_ids", [])
    if not question_ids:
        conn.close()
        return jsonify({"error": "question_ids required"}), 400
    account = get_current_account()
    cursor = conn.execute(
        "INSERT INTO science_study_session (child_id, created_by, title, learning_plan_id) VALUES (?, ?, ?, ?)",
        (plan["child_id"], account["id"], title, plan_id)
    )
    ss_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute("INSERT INTO science_study_session_question (session_id, question_id) VALUES (?, ?)", (ss_id, qid))
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'science_study', ?, ?)",
        (plan_id, ss_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": ss_id}), 201


@app.route("/api/learning-plans/<int:plan_id>/items/science-test", methods=["POST"])
@parent_required
def add_plan_science_test(plan_id):
    conn = get_db()
    plan = conn.execute("SELECT * FROM learning_plan WHERE id = ?", (plan_id,)).fetchone()
    if not plan or plan["status"] != "draft":
        conn.close()
        return jsonify({"error": "Plan not found or not in draft"}), 400
    data = request.json
    title = data.get("title", "Science Test").strip()
    question_ids = data.get("question_ids", [])
    timer_mode = data.get("timer_mode", "none")
    time_limit_seconds = data.get("time_limit_seconds", 0)
    if not question_ids:
        conn.close()
        return jsonify({"error": "question_ids required"}), 400
    account = get_current_account()
    cursor = conn.execute(
        """INSERT INTO science_test (child_id, created_by, title, timer_mode, time_limit_seconds, learning_plan_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (plan["child_id"], account["id"], title, timer_mode, time_limit_seconds, plan_id)
    )
    st_id = cursor.lastrowid
    for qid in question_ids:
        conn.execute("INSERT INTO science_test_question (test_id, question_id) VALUES (?, ?)", (st_id, qid))
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM learning_plan_item WHERE plan_id = ?", (plan_id,)).fetchone()[0]
    conn.execute(
        "INSERT INTO learning_plan_item (plan_id, item_type, item_id, sort_order) VALUES (?, 'science_test', ?, ?)",
        (plan_id, st_id, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": st_id, "total_questions": len(question_ids)}), 201


@app.route("/child/<int:child_id>/science-progress")
def science_progress_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        conn.close()
        return "Child not found", 404

    questions = conn.execute(
        """SELECT sq.id, sq.question_text, sq.category, sq.question_type, sq.answer_format,
                  COALESCE(sp.correct_count, 0) as correct_count,
                  COALESCE(sp.wrong_count, 0) as wrong_count,
                  COALESCE(sp.streak, 0) as streak,
                  COALESCE(sp.difficulty_level, 1) as difficulty_level,
                  sp.last_tested, sp.last_correct_at,
                  COALESCE(sp.correct_count, 0) as m_correct_count,
                  COALESCE(sp.wrong_count, 0) as m_wrong_count,
                  COALESCE(sp.streak, 0) as m_streak,
                  COALESCE(sp.difficulty_level, 1) as m_difficulty_level,
                  sp.last_tested as m_last_tested, sp.last_correct_at as m_last_correct_at
           FROM science_question sq
           LEFT JOIN science_question_progress sp ON sq.id = sp.question_id AND sp.child_id = sq.child_id
           WHERE sq.child_id = ?
           ORDER BY sq.category, sq.id""",
        (child_id,)
    ).fetchall()
    conn.close()

    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    q_list = []
    for q in questions:
        q = dict(q)
        q["status"] = compute_mastery_status(q, cutoff)
        q_list.append(q)

    # Stats
    total = len(q_list)
    never_tested = sum(1 for q in q_list if q["status"] == "never")
    needs_work = sum(1 for q in q_list if q["status"] == "wrong")
    mastered = sum(1 for q in q_list if q["status"] == "mastered")

    # Category rollups
    cat_data = {}
    for q in q_list:
        cat = q["category"]
        if cat not in cat_data:
            cat_data[cat] = {"total": 0, "mastered": 0}
        cat_data[cat]["total"] += 1
        if q["status"] == "mastered":
            cat_data[cat]["mastered"] += 1

    categories = []
    for name in sorted(cat_data.keys()):
        d = cat_data[name]
        pct = round(d["mastered"] * 100 / d["total"]) if d["total"] else 0
        categories.append({"name": name, "total": d["total"], "mastered": d["mastered"], "pct": pct})

    # Fastest mastered: questions with difficulty_level >= 4, fewest total attempts
    fastest = []
    for q in q_list:
        if q["difficulty_level"] >= 4:
            total_attempts = q["correct_count"] + q["wrong_count"]
            fastest.append({
                "question_text": q["question_text"],
                "category": q["category"],
                "total_attempts": total_attempts,
            })
    fastest.sort(key=lambda x: x["total_attempts"])
    fastest = fastest[:10]

    return render_template(
        "science_progress.html",
        child=dict(child),
        questions=q_list,
        total=total,
        never_tested=never_tested,
        needs_work=needs_work,
        mastered=mastered,
        categories=categories,
        fastest=fastest,
        cutoff=cutoff,
        role=session.get("role", "parent")
    )


@app.route("/api/children/<int:child_id>/science-progress")
@login_required
def api_science_progress(child_id):
    conn = get_db()
    questions = conn.execute(
        """SELECT sq.category,
                  COALESCE(sp.correct_count, 0) as correct_count,
                  COALESCE(sp.wrong_count, 0) as wrong_count,
                  COALESCE(sp.streak, 0) as streak,
                  COALESCE(sp.difficulty_level, 1) as difficulty_level,
                  sp.last_tested, sp.last_correct_at
           FROM science_question sq
           LEFT JOIN science_question_progress sp ON sq.id = sp.question_id AND sp.child_id = sq.child_id
           WHERE sq.child_id = ?""",
        (child_id,)
    ).fetchall()
    conn.close()

    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    cat_data = {}
    total = 0
    never_tested = 0
    needs_work = 0
    mastered_count = 0

    for q in questions:
        q = dict(q)
        total += 1
        cat = q["category"]
        if cat not in cat_data:
            cat_data[cat] = {"total": 0, "mastered": 0}
        cat_data[cat]["total"] += 1

        if not q["last_tested"]:
            status = "never"
        elif q["wrong_count"] > q["correct_count"]:
            status = "wrong"
        elif q["streak"] == 0 and q["last_tested"]:
            status = "wrong"
        elif q["difficulty_level"] >= 4:
            status = "mastered"
        elif not q["last_correct_at"] or q["last_correct_at"] < cutoff:
            status = "due"
        else:
            status = "good"

        if status == "never":
            never_tested += 1
        elif status == "wrong":
            needs_work += 1
        elif status == "mastered":
            mastered_count += 1
            cat_data[cat]["mastered"] += 1

    categories = []
    for name in sorted(cat_data.keys()):
        d = cat_data[name]
        pct = round(d["mastered"] * 100 / d["total"]) if d["total"] else 0
        categories.append({"name": name, "total": d["total"], "mastered": d["mastered"], "pct": pct})

    return jsonify({
        "total": total,
        "never_tested": never_tested,
        "needs_work": needs_work,
        "mastered": mastered_count,
        "categories": categories,
    })


# ── Reading Web Proxy ──

@app.route("/api/reading-proxy")
@login_required
def reading_proxy():
    """Fetch a web page, sanitize it (strip links, scripts, nav), and serve it for safe reading."""
    import requests as req
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    url = request.args.get("url", "")
    if not url:
        return "No URL provided", 400

    # Verify this URL belongs to an actual reading material
    conn = get_db()
    material = conn.execute("SELECT id FROM reading_material WHERE source_url = ?", (url,)).fetchone()
    conn.close()
    if not material:
        return "URL not authorized", 403

    try:
        resp = req.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; KidVerbal/1.0)"
        })
        resp.raise_for_status()
    except Exception as e:
        return f"Failed to fetch page: {str(e)}", 502

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "noscript", "nav", "footer", "header",
                              "aside", "iframe", "form"]):
        tag.decompose()
    for selector in [".ad", ".ads", ".advertisement", ".sidebar", ".nav",
                     ".menu", ".footer", ".header", ".cookie", ".popup",
                     ".social", ".share", ".comments", ".related"]:
        for el in soup.select(selector):
            el.decompose()

    # Convert all relative image/media URLs to absolute
    for tag in soup.find_all(["img", "source", "video", "audio"]):
        for attr in ["src", "srcset"]:
            val = tag.get(attr)
            if val:
                if attr == "srcset":
                    parts = []
                    for entry in val.split(","):
                        entry = entry.strip()
                        if entry:
                            pieces = entry.split()
                            pieces[0] = urljoin(url, pieces[0])
                            parts.append(" ".join(pieces))
                    tag[attr] = ", ".join(parts)
                else:
                    tag[attr] = urljoin(url, val)

    # Convert relative CSS URLs to absolute
    for tag in soup.find_all("link", rel="stylesheet"):
        href = tag.get("href")
        if href:
            tag["href"] = urljoin(url, href)

    # Disable all links: remove href, make non-clickable
    for a_tag in soup.find_all("a"):
        a_tag["href"] = "javascript:void(0)"
        a_tag["onclick"] = "return false"
        a_tag["style"] = (a_tag.get("style", "") + "; cursor: default; text-decoration: none; color: inherit;").strip("; ")

    # Inject a style block to disable link behavior and hide any remaining nav
    block_style = soup.new_tag("style")
    block_style.string = (
        "a { pointer-events: none !important; cursor: default !important; "
        "text-decoration: none !important; color: inherit !important; } "
        "nav, .nav, .menu, .sidebar, .footer, .header, .ad, .ads, .social, "
        ".share, .comments, .related { display: none !important; }"
    )
    if soup.head:
        soup.head.append(block_style)
    elif soup.html:
        soup.html.insert(0, block_style)

    return str(soup), 200, {"Content-Type": "text/html; charset=utf-8"}


# ── Site Configuration ──

@app.route("/settings")
@parent_required
def settings_page():
    conn = get_db()
    config_rows = conn.execute("SELECT key, value FROM site_config").fetchall()
    config = {r["key"]: r["value"] for r in config_rows}
    children = conn.execute("SELECT id, name, grade_level FROM child ORDER BY name").fetchall()
    conn.close()
    # Mask the API key for display
    api_key = config.get("openai_api_key", "")
    masked_key = ""
    if api_key:
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
    return render_template(
        "settings.html",
        masked_key=masked_key,
        has_key=bool(api_key),
        children=[dict(c) for c in children],
    )


@app.route("/api/config", methods=["POST"])
@parent_required
def save_config():
    data = request.json
    key = data.get("key")
    value = data.get("value")
    if not key or not value:
        return jsonify({"error": "Key and value required"}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO site_config (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (key, value),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


def get_config(key):
    conn = get_db()
    row = conn.execute("SELECT value FROM site_config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


# ── Child grade level ──

@app.route("/api/children/<int:child_id>/grade", methods=["PUT"])
@parent_required
def update_child_grade(child_id):
    data = request.json
    grade_level = data.get("grade_level", "")
    conn = get_db()
    conn.execute("UPDATE child SET grade_level = ? WHERE id = ?", (grade_level, child_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── AI Question Generation ──

@app.route("/api/materials/<int:material_id>/questions/generate-ai", methods=["POST"])
@parent_required
def generate_ai_questions(material_id):
    api_key = get_config("openai_api_key")
    if not api_key:
        return jsonify({"error": "OpenAI API key not configured. Go to Settings to add it."}), 400

    conn = get_db()
    material = conn.execute("SELECT * FROM reading_material WHERE id = ?", (material_id,)).fetchone()
    if not material:
        conn.close()
        return jsonify({"error": "Material not found"}), 404

    # Determine grade level from associated child
    grade_level = "5th grade"
    if material["child_id"]:
        child = conn.execute("SELECT grade_level FROM child WHERE id = ?", (material["child_id"],)).fetchone()
        if child and child["grade_level"]:
            grade_level = child["grade_level"]
    conn.close()

    # Build the article context
    article_context = ""
    if material["source_url"]:
        article_context = f"the article at this URL: {material['source_url']}"
    if material["content"] and material["content"].strip():
        text = material["content"][:8000]
        if article_context:
            article_context += f"\n\nHere is the article text for reference:\n{text}"
        else:
            article_context = f"the following article:\n{text}"

    if not article_context:
        return jsonify({"error": "Material has no content or source URL to generate questions from."}), 400

    prompt = (
        f"Please build 10 multiple choice questions and answers for {article_context} "
        f"for {grade_level} level.\n\n"
        "IMPORTANT FORMAT RULES:\n"
        "1. Output a QUESTIONS section first, then an ANSWERS section separated by a line that says exactly 'ANSWERS'\n"
        "2. Questions should be numbered (1. 2. 3. etc.) with choices A. B. C. D. on separate lines\n"
        "3. Answers should be one letter per line (e.g. B) with NO numbering, NO periods, just the letter\n"
        "4. The correct answer position MUST be randomized across A, B, C, D. Do NOT put the correct answer in the same position repeatedly. "
        "Each letter should appear roughly 2-3 times among the 10 answers. No letter should appear more than 4 times.\n\n"
        "Example format:\n"
        "1. What is the main idea?\n"
        "A. Option one\n"
        "B. Option two\n"
        "C. Option three\n"
        "D. Option four\n\n"
        "2. What does the word X mean?\n"
        "A. ...\n"
        "B. ...\n"
        "C. ...\n"
        "D. ...\n\n"
        "ANSWERS\n"
        "C\n"
        "A\n"
        "D\n"
        "B\n"
        "A\n"
        "C\n"
        "D\n"
        "B\n"
        "A\n"
        "D\n"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=3000,
        )
        result = response.choices[0].message.content.strip()

        # Split into questions and answers sections
        parts = re.split(r'\n\s*ANSWERS\s*\n', result, maxsplit=1)
        questions_text = parts[0].strip()
        answers_text = parts[1].strip() if len(parts) > 1 else ""

        return jsonify({"questions": questions_text, "answers": answers_text})
    except Exception as e:
        return jsonify({"error": f"AI generation failed: {str(e)}"}), 500


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5001, debug=False, allow_unsafe_werkzeug=True)
