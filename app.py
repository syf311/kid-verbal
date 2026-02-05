from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from database import init_db, get_db

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


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
