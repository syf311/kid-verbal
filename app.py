import os
import time
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db, get_db
from dictionary import fetch_definition
from test_engine import get_test_words, generate_choices, generate_word_choices, update_progress, record_test_session
from ocr import extract_text

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
    title = data.get("title", "Study Session")
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
    conn.commit()
    conn.close()
    return jsonify({"status": "completed"})


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
    title = data.get("title", "Test")
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

    title = f"Test: {study['title'] or 'Study Session'}"
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
        "INSERT INTO child (name, avatar) VALUES (?, ?)",
        (data["name"], data.get("avatar", "👤"))
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

    recent_sessions = conn.execute(
        """SELECT id, test_type, score, correct_count, total_count, created_at
           FROM test_session WHERE child_id = ?
           ORDER BY created_at DESC LIMIT 5""",
        (child_id,)
    ).fetchall()

    # Get pending study sessions
    study_sessions = conn.execute(
        """SELECT ss.*, a.username as created_by_name,
                  (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
           FROM study_session ss
           JOIN account a ON ss.created_by = a.id
           WHERE ss.child_id = ? AND ss.status != 'completed'
           ORDER BY ss.created_at DESC""",
        (child_id,)
    ).fetchall()

    # Get completed study sessions
    completed_sessions = conn.execute(
        """SELECT ss.*, a.username as created_by_name,
                  (SELECT COUNT(*) FROM study_session_word WHERE session_id = ss.id) as word_count
           FROM study_session ss
           JOIN account a ON ss.created_by = a.id
           WHERE ss.child_id = ? AND ss.status = 'completed'
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

    conn.close()
    return render_template(
        "dashboard.html",
        child=dict(child),
        word_count=word_count,
        recent_sessions=[dict(s) for s in recent_sessions],
        study_sessions=[dict(s) for s in study_sessions],
        completed_sessions=[dict(s) for s in completed_sessions],
        parent_tests=[dict(t) for t in parent_tests],
        role=session.get("role", "parent")
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
        """SELECT w.*, wp.correct_count, wp.wrong_count, wp.difficulty_level
           FROM word w
           LEFT JOIN word_progress wp ON w.id = wp.word_id AND wp.child_id = w.child_id
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
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("test.html", child=dict(child), parent_test_id=parent_test_id)


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

    return render_template(
        "test_detail.html",
        child=dict(child),
        test_session=dict(test_session),
        answers=answers_list
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
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("study.html", child=dict(child), session_id=session_id)


@app.route("/materials")
def materials_list():
    conn = get_db()
    child_filter = request.args.get("child_id", "", type=str)

    if child_filter:
        materials = conn.execute(
            """SELECT rm.*,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = rm.id) as question_count,
                      c.name as child_name
               FROM reading_material rm
               LEFT JOIN child c ON rm.child_id = c.id
               WHERE rm.child_id = ?
               ORDER BY rm.created_at DESC""",
            (child_filter,)
        ).fetchall()
    else:
        materials = conn.execute(
            """SELECT rm.*,
                      (SELECT COUNT(*) FROM material_question WHERE material_id = rm.id) as question_count,
                      c.name as child_name
               FROM reading_material rm
               LEFT JOIN child c ON rm.child_id = c.id
               ORDER BY rm.created_at DESC"""
        ).fetchall()

    children = conn.execute("SELECT id, name FROM child ORDER BY name").fetchall()
    conn.close()
    return render_template(
        "materials.html",
        materials=[dict(m) for m in materials],
        children=[dict(c) for c in children],
        child_filter=child_filter
    )


@app.route("/api/materials", methods=["POST"])
def create_material():
    title = request.form.get("title", "Untitled")
    content = request.form.get("content", "")
    source_url = request.form.get("source_url", "").strip() or None
    child_id = request.form.get("child_id", "").strip() or None
    image_path = None

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
        "INSERT INTO reading_material (title, content, image_path, source_url, child_id) VALUES (?, ?, ?, ?, ?)",
        (title, content, image_path, source_url, child_id)
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

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "iframe", "form", "noscript"]):
        tag.decompose()
    # Remove common ad/navigation classes
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
        # Get text with paragraph breaks
        paragraphs = content_el.find_all("p")
        if paragraphs:
            content = "\n\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())
        else:
            content = content_el.get_text(separator="\n").strip()
    else:
        content = soup.get_text(separator="\n").strip()

    if not content:
        return jsonify({"error": "Could not extract article text"}), 400

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO reading_material (title, content, source_url) VALUES (?, ?, ?)",
        (title, content, url)
    )
    material_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"id": material_id, "title": title, "content_length": len(content)}), 201


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


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5001, debug=False, allow_unsafe_werkzeug=True)
