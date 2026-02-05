import os
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
from database import init_db, get_db
from dictionary import fetch_definition
from test_engine import get_test_words, generate_choices, update_progress, record_test_session
from ocr import extract_text

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "REDACTED-SECRET"
socketio = SocketIO(app, cors_allowed_origins="*")


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/api/children", methods=["GET"])
def get_children():
    conn = get_db()
    children = conn.execute(
        "SELECT id, name, avatar, total_points, level FROM child ORDER BY name"
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
def delete_child(child_id):
    conn = get_db()
    conn.execute("DELETE FROM child WHERE id = ?", (child_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/child/<int:child_id>")
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
        """SELECT test_type, score, correct_count, total_count, created_at
           FROM test_session WHERE child_id = ?
           ORDER BY created_at DESC LIMIT 5""",
        (child_id,)
    ).fetchall()

    badges = conn.execute(
        "SELECT badge_type, earned_at FROM badge WHERE child_id = ?",
        (child_id,)
    ).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        child=dict(child),
        word_count=word_count,
        recent_sessions=[dict(s) for s in recent_sessions],
        badges=[dict(b) for b in badges]
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
    conn.execute(
        """UPDATE word SET definition = ?, example_sentence = ? WHERE id = ?""",
        (data.get("definition", ""), data.get("example_sentence", ""), word_id)
    )
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/words/<int:word_id>", methods=["DELETE"])
def delete_word(word_id):
    conn = get_db()
    conn.execute("DELETE FROM word_progress WHERE word_id = ?", (word_id,))
    conn.execute("DELETE FROM word WHERE id = ?", (word_id,))
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/dictionary/<word>", methods=["GET"])
def lookup_word(word):
    result = fetch_definition(word)
    if result:
        return jsonify(result)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/children/<int:child_id>/test/words", methods=["GET"])
def get_words_for_test(child_id):
    count = request.args.get("count", 10, type=int)
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

    choices = generate_choices(dict(word), [dict(w) for w in all_words])
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
    record_test_session(
        child_id,
        data["test_type"],
        data["score"],
        data["correct_count"],
        data["total_count"],
        data["time_taken"]
    )
    return "", 201


@app.route("/child/<int:child_id>/test")
def test_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("test.html", child=dict(child))


@app.route("/materials")
def materials_list():
    conn = get_db()
    materials = conn.execute(
        "SELECT * FROM reading_material ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("materials.html", materials=[dict(m) for m in materials])


@app.route("/api/materials", methods=["POST"])
def create_material():
    title = request.form.get("title", "Untitled")
    content = request.form.get("content", "")
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
        "INSERT INTO reading_material (title, content, image_path) VALUES (?, ?, ?)",
        (title, content, image_path)
    )
    material_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"id": material_id, "content": content})


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
        "UPDATE reading_material SET title = ?, content = ? WHERE id = ?",
        (data.get("title"), data.get("content"), material_id)
    )
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/materials/<int:material_id>", methods=["DELETE"])
def delete_material(material_id):
    conn = get_db()
    conn.execute("DELETE FROM reading_material WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return "", 204


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
