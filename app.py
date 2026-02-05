from flask import Flask, render_template
from flask_socketio import SocketIO
from database import init_db

app = Flask(__name__)
app.config["SECRET_KEY"] = "REDACTED-SECRET"
socketio = SocketIO(app, cors_allowed_origins="*")


@app.route("/")
def home():
    return render_template("home.html")


if __name__ == "__main__":
    init_db()
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
