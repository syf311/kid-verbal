from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from database import init_db, get_db
from dictionary import fetch_definition

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


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
