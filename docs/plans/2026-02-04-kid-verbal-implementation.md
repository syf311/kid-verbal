# Kid Verbal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use 10x-engineer:executing-plans to implement this plan task-by-task.

**Goal:** Build a web app to help kids improve verbal skills through vocabulary management, gamified testing, and interactive reading sessions.

**Architecture:** Flask backend with SQLite database, vanilla JS frontend, WebSocket for real-time reading sessions. OCR via Tesseract, definitions from Free Dictionary API, pronunciation via browser TTS.

**Tech Stack:** Python 3.11+, Flask, Flask-SocketIO, SQLite, pytesseract, Pillow, requests

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `app.py`
- Create: `database.py`
- Create: `templates/base.html`

**Step 1: Create requirements.txt**

```txt
flask==3.0.0
flask-socketio==5.3.6
python-socketio==5.10.0
pytesseract==0.3.10
Pillow==10.2.0
requests==2.31.0
eventlet==0.34.2
```

**Step 2: Create database.py with schema**

```python
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "verbal.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS child (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            avatar TEXT,
            total_points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS word (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            definition TEXT,
            example_sentence TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS word_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            difficulty_level INTEGER DEFAULT 1,
            last_tested DATETIME,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE,
            UNIQUE(child_id, word_id)
        );

        CREATE TABLE IF NOT EXISTS reading_material (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            image_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS test_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            test_type TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            total_count INTEGER DEFAULT 0,
            time_taken INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS badge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            badge_type TEXT NOT NULL,
            earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            UNIQUE(child_id, badge_type)
        );
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
```

**Step 3: Create minimal app.py**

```python
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
```

**Step 4: Create base template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Kid Verbal{% endblock %}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        h1, h2 { color: #333; margin-bottom: 20px; }
        .btn {
            display: inline-block;
            padding: 15px 30px;
            font-size: 18px;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            text-decoration: none;
            margin: 5px;
            transition: transform 0.2s;
        }
        .btn:hover { transform: scale(1.05); }
        .btn-primary { background: #667eea; color: white; }
        .btn-success { background: #48bb78; color: white; }
        .btn-warning { background: #ed8936; color: white; }
        .btn-danger { background: #f56565; color: white; }
        input, textarea {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 8px;
            margin-bottom: 15px;
        }
        input:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        .card {
            background: #f7fafc;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
    </style>
    {% block extra_css %}{% endblock %}
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
    {% block scripts %}{% endblock %}
</body>
</html>
```

**Step 5: Create home template**

Create `templates/home.html`:

```html
{% extends "base.html" %}

{% block title %}Kid Verbal - Home{% endblock %}

{% block content %}
<h1>Kid Verbal</h1>
<p style="margin-bottom: 30px; color: #666;">Choose a profile to get started!</p>

<div id="profiles" class="grid">
    <!-- Profiles loaded via JS -->
</div>

<div style="margin-top: 30px;">
    <h2>Add New Profile</h2>
    <form id="add-profile-form">
        <input type="text" id="child-name" placeholder="Enter name..." required>
        <button type="submit" class="btn btn-success">Add Profile</button>
    </form>
</div>

<div style="margin-top: 30px;">
    <a href="/materials" class="btn btn-warning">Reading Materials</a>
</div>
{% endblock %}

{% block scripts %}
<script>
async function loadProfiles() {
    const res = await fetch('/api/children');
    const children = await res.json();
    const container = document.getElementById('profiles');

    if (children.length === 0) {
        container.innerHTML = '<p style="color: #666;">No profiles yet. Add one below!</p>';
        return;
    }

    container.innerHTML = children.map(child => `
        <a href="/child/${child.id}" class="card" style="text-decoration: none; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 10px;">
                ${child.avatar || '👤'}
            </div>
            <div style="font-size: 20px; font-weight: bold; color: #333;">
                ${child.name}
            </div>
            <div style="color: #666; margin-top: 5px;">
                Level ${child.level} • ${child.total_points} pts
            </div>
        </a>
    `).join('');
}

document.getElementById('add-profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('child-name').value;
    await fetch('/api/children', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    document.getElementById('child-name').value = '';
    loadProfiles();
});

loadProfiles();
</script>
{% endblock %}
```

**Step 6: Install dependencies and test**

```bash
pip install -r requirements.txt
python database.py
python app.py
```

Open http://localhost:5000 - should see home page.

**Step 7: Commit**

```bash
git init
echo "verbal.db" >> .gitignore
echo "uploads/" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
git add .
git commit -m "feat: initial project setup with Flask, SQLite schema, base templates"
```

---

## Task 2: Child Profile CRUD API

**Files:**
- Modify: `app.py`

**Step 1: Add child API endpoints to app.py**

Add after the home route:

```python
from flask import request, jsonify
from database import get_db


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
```

**Step 2: Test manually**

```bash
python app.py
# In another terminal:
curl http://localhost:5000/api/children
curl -X POST -H "Content-Type: application/json" -d '{"name":"Alice"}' http://localhost:5000/api/children
curl http://localhost:5000/api/children
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: add child profile CRUD API"
```

---

## Task 3: Child Dashboard Page

**Files:**
- Modify: `app.py`
- Create: `templates/dashboard.html`

**Step 1: Add dashboard route to app.py**

```python
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
```

**Step 2: Create dashboard template**

Create `templates/dashboard.html`:

```html
{% extends "base.html" %}

{% block title %}{{ child.name }} - Dashboard{% endblock %}

{% block content %}
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
    <div>
        <a href="/" style="color: #667eea; text-decoration: none;">&larr; Back</a>
        <h1 style="margin-top: 10px;">{{ child.name }}</h1>
    </div>
    <div style="text-align: right;">
        <div style="font-size: 48px;">{{ child.avatar or '👤' }}</div>
        <div style="font-size: 24px; font-weight: bold; color: #667eea;">Level {{ child.level }}</div>
        <div style="color: #666;">{{ child.total_points }} points</div>
    </div>
</div>

<div class="grid" style="grid-template-columns: repeat(3, 1fr); margin-bottom: 30px;">
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #667eea;">{{ word_count }}</div>
        <div style="color: #666;">Words</div>
    </div>
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #48bb78;">{{ badges|length }}</div>
        <div style="color: #666;">Badges</div>
    </div>
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #ed8936;">{{ recent_sessions|length }}</div>
        <div style="color: #666;">Recent Tests</div>
    </div>
</div>

<div class="grid" style="grid-template-columns: repeat(2, 1fr);">
    <a href="/child/{{ child.id }}/words" class="btn btn-primary" style="text-align: center;">
        📚 My Words
    </a>
    <a href="/child/{{ child.id }}/test" class="btn btn-success" style="text-align: center;">
        🎯 Start Test
    </a>
    <a href="/child/{{ child.id }}/stats" class="btn btn-warning" style="text-align: center;">
        📊 Stats & Badges
    </a>
    <a href="/materials" class="btn btn-primary" style="text-align: center;">
        📖 Reading
    </a>
</div>

{% if badges %}
<div style="margin-top: 30px;">
    <h2>Badges</h2>
    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
        {% for badge in badges %}
        <div class="card" style="padding: 10px 15px;">
            {{ badge.badge_type }}
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}

{% if recent_sessions %}
<div style="margin-top: 30px;">
    <h2>Recent Tests</h2>
    {% for session in recent_sessions %}
    <div class="card">
        <strong>{{ session.test_type }}</strong> -
        {{ session.correct_count }}/{{ session.total_count }} correct,
        {{ session.score }} pts
    </div>
    {% endfor %}
</div>
{% endif %}
{% endblock %}
```

**Step 3: Test manually**

```bash
python app.py
```

Create a profile, click on it - should see dashboard.

**Step 4: Commit**

```bash
git add .
git commit -m "feat: add child dashboard page with stats"
```

---

## Task 4: Dictionary API Client

**Files:**
- Create: `dictionary.py`

**Step 1: Create dictionary.py**

```python
import requests
from typing import Optional


def fetch_definition(word: str) -> Optional[dict]:
    """
    Fetch word definition from Free Dictionary API.
    Returns dict with 'definition' and 'example' or None if not found.
    """
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            return None

        data = response.json()
        if not data or not isinstance(data, list):
            return None

        # Get first definition
        meanings = data[0].get("meanings", [])
        if not meanings:
            return None

        definitions = meanings[0].get("definitions", [])
        if not definitions:
            return None

        first_def = definitions[0]
        return {
            "definition": first_def.get("definition", ""),
            "example": first_def.get("example", "")
        }
    except Exception:
        return None


if __name__ == "__main__":
    # Quick test
    result = fetch_definition("happy")
    print(result)
```

**Step 2: Test**

```bash
python dictionary.py
```

Should print definition of "happy".

**Step 3: Commit**

```bash
git add .
git commit -m "feat: add dictionary API client"
```

---

## Task 5: Word Management API

**Files:**
- Modify: `app.py`

**Step 1: Add word API endpoints**

Add to app.py:

```python
from dictionary import fetch_definition


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
```

**Step 2: Test**

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"word":"happy"}' \
  http://localhost:5000/api/children/1/words

curl http://localhost:5000/api/children/1/words
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: add word management API with dictionary lookup"
```

---

## Task 6: Word List Page

**Files:**
- Modify: `app.py`
- Create: `templates/words.html`

**Step 1: Add route**

```python
@app.route("/child/<int:child_id>/words")
def word_list(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("words.html", child=dict(child))
```

**Step 2: Create words template**

Create `templates/words.html`:

```html
{% extends "base.html" %}

{% block title %}{{ child.name }} - Words{% endblock %}

{% block content %}
<a href="/child/{{ child.id }}" style="color: #667eea; text-decoration: none;">&larr; Back to Dashboard</a>
<h1 style="margin-top: 10px;">{{ child.name }}'s Words</h1>

<div style="margin: 20px 0;">
    <form id="add-word-form" style="display: flex; gap: 10px;">
        <input type="text" id="new-word" placeholder="Enter a word..." style="flex: 1;" required>
        <button type="submit" class="btn btn-success">Add Word</button>
    </form>
</div>

<div id="words-list">
    <!-- Words loaded via JS -->
</div>

<div id="edit-modal" style="display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100;">
    <div style="background: white; max-width: 500px; margin: 50px auto; padding: 30px; border-radius: 20px;">
        <h2>Edit Word</h2>
        <input type="hidden" id="edit-word-id">
        <label>Word:</label>
        <input type="text" id="edit-word-text" readonly style="background: #f0f0f0;">
        <label>Definition:</label>
        <textarea id="edit-definition" rows="3"></textarea>
        <label>Example Sentence:</label>
        <textarea id="edit-example" rows="2"></textarea>
        <div style="margin-top: 15px;">
            <button class="btn btn-primary" onclick="saveEdit()">Save</button>
            <button class="btn btn-danger" onclick="closeModal()">Cancel</button>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const childId = {{ child.id }};

async function loadWords() {
    const res = await fetch(`/api/children/${childId}/words`);
    const words = await res.json();
    const container = document.getElementById('words-list');

    if (words.length === 0) {
        container.innerHTML = '<p style="color: #666;">No words yet. Add your first word above!</p>';
        return;
    }

    container.innerHTML = words.map(word => `
        <div class="card" style="display: flex; justify-content: space-between; align-items: start;">
            <div style="flex: 1;">
                <div style="font-size: 20px; font-weight: bold; color: #333;">${word.word}</div>
                <div style="color: #666; margin-top: 5px;">${word.definition || 'No definition'}</div>
                ${word.example_sentence ? `<div style="color: #888; font-style: italic; margin-top: 5px;">"${word.example_sentence}"</div>` : ''}
                <div style="margin-top: 8px; font-size: 12px; color: #999;">
                    ✓ ${word.correct_count || 0} | ✗ ${word.wrong_count || 0} | Level ${word.difficulty_level || 1}
                </div>
            </div>
            <div>
                <button class="btn btn-primary" style="padding: 8px 12px; font-size: 14px;" onclick="speak('${word.word}')">🔊</button>
                <button class="btn btn-warning" style="padding: 8px 12px; font-size: 14px;" onclick="editWord(${word.id}, '${word.word}', '${(word.definition || '').replace(/'/g, "\\'")}', '${(word.example_sentence || '').replace(/'/g, "\\'")}')">✏️</button>
                <button class="btn btn-danger" style="padding: 8px 12px; font-size: 14px;" onclick="deleteWord(${word.id})">🗑️</button>
            </div>
        </div>
    `).join('');
}

function speak(word) {
    const utterance = new SpeechSynthesisUtterance(word);
    speechSynthesis.speak(utterance);
}

document.getElementById('add-word-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const word = document.getElementById('new-word').value;
    await fetch(`/api/children/${childId}/words`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word })
    });
    document.getElementById('new-word').value = '';
    loadWords();
});

function editWord(id, word, definition, example) {
    document.getElementById('edit-word-id').value = id;
    document.getElementById('edit-word-text').value = word;
    document.getElementById('edit-definition').value = definition;
    document.getElementById('edit-example').value = example;
    document.getElementById('edit-modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('edit-modal').style.display = 'none';
}

async function saveEdit() {
    const id = document.getElementById('edit-word-id').value;
    await fetch(`/api/words/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            definition: document.getElementById('edit-definition').value,
            example_sentence: document.getElementById('edit-example').value
        })
    });
    closeModal();
    loadWords();
}

async function deleteWord(id) {
    if (!confirm('Delete this word?')) return;
    await fetch(`/api/words/${id}`, { method: 'DELETE' });
    loadWords();
}

loadWords();
</script>
{% endblock %}
```

**Step 3: Test**

Navigate to `/child/1/words`, add words, edit, delete.

**Step 4: Commit**

```bash
git add .
git commit -m "feat: add word list page with CRUD and TTS"
```

---

## Task 7: Test Engine - Core Logic

**Files:**
- Create: `test_engine.py`

**Step 1: Create test_engine.py**

```python
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
```

**Step 2: Test**

```bash
python -c "from test_engine import *; print(get_test_words(1))"
```

**Step 3: Commit**

```bash
git add .
git commit -m "feat: add test engine with weighted word selection and progress tracking"
```

---

## Task 8: Test API Endpoints

**Files:**
- Modify: `app.py`

**Step 1: Add test endpoints**

Add to app.py:

```python
from test_engine import get_test_words, generate_choices, update_progress, record_test_session


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
```

**Step 2: Commit**

```bash
git add .
git commit -m "feat: add test API endpoints"
```

---

## Task 9: Test Page - Definition Quiz

**Files:**
- Modify: `app.py`
- Create: `templates/test.html`

**Step 1: Add test route**

```python
@app.route("/child/<int:child_id>/test")
def test_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    conn.close()
    if not child:
        return "Child not found", 404
    return render_template("test.html", child=dict(child))
```

**Step 2: Create test template**

Create `templates/test.html`:

```html
{% extends "base.html" %}

{% block title %}{{ child.name }} - Test{% endblock %}

{% block extra_css %}
<style>
    .test-type-btn {
        display: block;
        width: 100%;
        padding: 20px;
        margin-bottom: 10px;
        font-size: 20px;
        text-align: left;
        border: 3px solid #ddd;
        border-radius: 15px;
        background: white;
        cursor: pointer;
        transition: all 0.2s;
    }
    .test-type-btn:hover {
        border-color: #667eea;
        transform: scale(1.02);
    }
    .choice-btn {
        display: block;
        width: 100%;
        padding: 15px 20px;
        margin: 10px 0;
        font-size: 18px;
        text-align: left;
        border: 2px solid #ddd;
        border-radius: 10px;
        background: white;
        cursor: pointer;
        transition: all 0.2s;
    }
    .choice-btn:hover { border-color: #667eea; background: #f7fafc; }
    .choice-btn.correct { border-color: #48bb78; background: #c6f6d5; }
    .choice-btn.wrong { border-color: #f56565; background: #fed7d7; }
    .timer { font-size: 24px; font-weight: bold; color: #667eea; }
    .streak { font-size: 18px; color: #ed8936; }
    .score { font-size: 24px; color: #48bb78; }
    #confetti { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1000; }
</style>
{% endblock %}

{% block content %}
<canvas id="confetti"></canvas>

<div id="menu-screen">
    <a href="/child/{{ child.id }}" style="color: #667eea; text-decoration: none;">&larr; Back</a>
    <h1 style="margin-top: 10px;">Choose a Test</h1>

    <button class="test-type-btn" onclick="startTest('definition')">
        📖 Definition Quiz
        <div style="font-size: 14px; color: #666;">See a word, pick the correct definition</div>
    </button>

    <button class="test-type-btn" onclick="startTest('reverse')">
        🔄 Reverse Quiz
        <div style="font-size: 14px; color: #666;">See a definition, pick the correct word</div>
    </button>

    <button class="test-type-btn" onclick="startTest('spelling')">
        ✏️ Spelling Bee
        <div style="font-size: 14px; color: #666;">Hear a word, type the spelling</div>
    </button>

    <button class="test-type-btn" onclick="startTest('fillblank')">
        📝 Fill in the Blank
        <div style="font-size: 14px; color: #666;">Complete the sentence with the right word</div>
    </button>
</div>

<div id="test-screen" style="display: none;">
    <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
        <div class="timer">⏱️ <span id="timer">15</span>s</div>
        <div class="streak">🔥 <span id="streak">0</span> streak</div>
        <div class="score">⭐ <span id="score">0</span> pts</div>
    </div>

    <div style="margin-bottom: 10px; color: #666;">
        Question <span id="current-q">1</span> of <span id="total-q">10</span>
    </div>

    <div id="question-area" class="card">
        <!-- Question content -->
    </div>

    <div id="answer-area">
        <!-- Answer options -->
    </div>

    <div id="feedback" style="display: none; margin-top: 20px; padding: 15px; border-radius: 10px;">
    </div>
</div>

<div id="results-screen" style="display: none; text-align: center;">
    <h1>🎉 Test Complete!</h1>
    <div style="font-size: 48px; margin: 30px 0;">
        <span id="final-score">0</span> points
    </div>
    <div style="font-size: 24px; color: #666; margin-bottom: 30px;">
        <span id="final-correct">0</span>/<span id="final-total">10</span> correct
    </div>
    <button class="btn btn-primary" onclick="location.reload()">Try Again</button>
    <a href="/child/{{ child.id }}" class="btn btn-success">Back to Dashboard</a>
</div>
{% endblock %}

{% block scripts %}
<script>
const childId = {{ child.id }};
let testType = '';
let words = [];
let currentIndex = 0;
let score = 0;
let streak = 0;
let correctCount = 0;
let timer = null;
let timeLeft = 15;
let startTime = null;

async function startTest(type) {
    testType = type;
    const res = await fetch(`/api/children/${childId}/test/words?count=10`);
    words = await res.json();

    if (words.length < 4) {
        alert('You need at least 4 words to start a test!');
        return;
    }

    document.getElementById('menu-screen').style.display = 'none';
    document.getElementById('test-screen').style.display = 'block';
    document.getElementById('total-q').textContent = words.length;

    startTime = Date.now();
    showQuestion();
}

async function showQuestion() {
    if (currentIndex >= words.length) {
        endTest();
        return;
    }

    const word = words[currentIndex];
    document.getElementById('current-q').textContent = currentIndex + 1;
    document.getElementById('feedback').style.display = 'none';

    const questionArea = document.getElementById('question-area');
    const answerArea = document.getElementById('answer-area');

    // Reset timer
    clearInterval(timer);
    timeLeft = 15 + (5 - word.difficulty_level) * 3; // More time for harder words (wait, lower difficulty = more time)
    document.getElementById('timer').textContent = timeLeft;
    timer = setInterval(() => {
        timeLeft--;
        document.getElementById('timer').textContent = timeLeft;
        if (timeLeft <= 0) {
            clearInterval(timer);
            handleAnswer(false, null);
        }
    }, 1000);

    if (testType === 'definition') {
        questionArea.innerHTML = `
            <div style="font-size: 36px; font-weight: bold; text-align: center;">${word.word}</div>
            <div style="text-align: center; margin-top: 10px;">
                <button class="btn btn-primary" style="padding: 8px 15px;" onclick="speak('${word.word}')">🔊 Listen</button>
            </div>
        `;

        const choicesRes = await fetch(`/api/children/${childId}/test/choices/${word.id}`);
        const { choices, correct } = await choicesRes.json();

        answerArea.innerHTML = choices.map((c, i) => `
            <button class="choice-btn" onclick="checkAnswer(this, '${c.replace(/'/g, "\\'")}', '${correct.replace(/'/g, "\\'")}')">
                ${c}
            </button>
        `).join('');

    } else if (testType === 'reverse') {
        questionArea.innerHTML = `
            <div style="font-size: 20px; text-align: center;">${word.definition}</div>
        `;

        // Get word choices
        const otherWords = words.filter(w => w.id !== word.id).slice(0, 3).map(w => w.word);
        const choices = [word.word, ...otherWords].sort(() => Math.random() - 0.5);

        answerArea.innerHTML = choices.map(c => `
            <button class="choice-btn" onclick="checkAnswer(this, '${c}', '${word.word}')">
                ${c}
            </button>
        `).join('');

    } else if (testType === 'spelling') {
        questionArea.innerHTML = `
            <div style="text-align: center;">
                <button class="btn btn-primary" style="font-size: 24px; padding: 20px 40px;" onclick="speak('${word.word}')">
                    🔊 Hear the Word
                </button>
                <div style="margin-top: 15px; color: #666;">Hint: ${word.definition || 'No definition'}</div>
            </div>
        `;
        speak(word.word);

        answerArea.innerHTML = `
            <input type="text" id="spelling-input" placeholder="Type the spelling..."
                   style="font-size: 24px; text-align: center;" autocomplete="off">
            <button class="btn btn-success" style="width: 100%;" onclick="checkSpelling('${word.word}')">
                Check Answer
            </button>
        `;
        document.getElementById('spelling-input').focus();
        document.getElementById('spelling-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') checkSpelling(word.word);
        });

    } else if (testType === 'fillblank') {
        if (!word.example_sentence) {
            // Skip words without examples
            currentIndex++;
            showQuestion();
            return;
        }

        const sentence = word.example_sentence.replace(
            new RegExp(word.word, 'gi'),
            '_____'
        );

        questionArea.innerHTML = `
            <div style="font-size: 20px; text-align: center;">"${sentence}"</div>
        `;

        const otherWords = words.filter(w => w.id !== word.id).slice(0, 3).map(w => w.word);
        const choices = [word.word, ...otherWords].sort(() => Math.random() - 0.5);

        answerArea.innerHTML = choices.map(c => `
            <button class="choice-btn" onclick="checkAnswer(this, '${c}', '${word.word}')">
                ${c}
            </button>
        `).join('');
    }
}

function speak(word) {
    const utterance = new SpeechSynthesisUtterance(word);
    speechSynthesis.speak(utterance);
}

function checkAnswer(btn, selected, correct) {
    clearInterval(timer);
    const isCorrect = selected.toLowerCase() === correct.toLowerCase();

    document.querySelectorAll('.choice-btn').forEach(b => {
        b.disabled = true;
        if (b.textContent.trim().toLowerCase() === correct.toLowerCase()) {
            b.classList.add('correct');
        } else if (b === btn && !isCorrect) {
            b.classList.add('wrong');
        }
    });

    handleAnswer(isCorrect, correct);
}

function checkSpelling(correct) {
    clearInterval(timer);
    const input = document.getElementById('spelling-input');
    const answer = input.value.trim().toLowerCase();
    const isCorrect = answer === correct.toLowerCase();

    input.disabled = true;
    input.style.borderColor = isCorrect ? '#48bb78' : '#f56565';
    input.style.background = isCorrect ? '#c6f6d5' : '#fed7d7';

    handleAnswer(isCorrect, correct);
}

async function handleAnswer(isCorrect, correct) {
    const word = words[currentIndex];

    // Update server
    const res = await fetch(`/api/children/${childId}/test/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word_id: word.id, correct: isCorrect })
    });
    const result = await res.json();

    if (isCorrect) {
        correctCount++;
        score += result.points;
        streak = result.streak;

        if (streak >= 3) {
            showConfetti();
        }
    } else {
        streak = 0;
    }

    document.getElementById('score').textContent = score;
    document.getElementById('streak').textContent = streak;

    // Show feedback
    const feedback = document.getElementById('feedback');
    feedback.style.display = 'block';
    feedback.style.background = isCorrect ? '#c6f6d5' : '#fed7d7';
    feedback.innerHTML = isCorrect
        ? `✓ Correct! +${result.points} points`
        : `✗ The answer was: <strong>${correct}</strong>`;

    // Next question after delay
    setTimeout(() => {
        currentIndex++;
        showQuestion();
    }, 1500);
}

function endTest() {
    clearInterval(timer);
    const timeTaken = Math.round((Date.now() - startTime) / 1000);

    // Save session
    fetch(`/api/children/${childId}/test/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            test_type: testType,
            score: score,
            correct_count: correctCount,
            total_count: words.length,
            time_taken: timeTaken
        })
    });

    document.getElementById('test-screen').style.display = 'none';
    document.getElementById('results-screen').style.display = 'block';
    document.getElementById('final-score').textContent = score;
    document.getElementById('final-correct').textContent = correctCount;
    document.getElementById('final-total').textContent = words.length;

    showConfetti();
}

function showConfetti() {
    const canvas = document.getElementById('confetti');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const pieces = [];
    const colors = ['#667eea', '#48bb78', '#ed8936', '#f56565', '#9f7aea'];

    for (let i = 0; i < 100; i++) {
        pieces.push({
            x: Math.random() * canvas.width,
            y: -20,
            size: Math.random() * 10 + 5,
            color: colors[Math.floor(Math.random() * colors.length)],
            speed: Math.random() * 3 + 2,
            angle: Math.random() * Math.PI * 2
        });
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        let active = false;

        pieces.forEach(p => {
            if (p.y < canvas.height) {
                active = true;
                p.y += p.speed;
                p.x += Math.sin(p.angle) * 2;
                p.angle += 0.1;

                ctx.fillStyle = p.color;
                ctx.fillRect(p.x, p.y, p.size, p.size);
            }
        });

        if (active) requestAnimationFrame(animate);
    }

    animate();
}
</script>
{% endblock %}
```

**Step 3: Test**

Add at least 4 words, then go to test page and try all test types.

**Step 4: Commit**

```bash
git add .
git commit -m "feat: add test page with all quiz types, timer, scoring, confetti"
```

---

## Task 10: OCR Module

**Files:**
- Create: `ocr.py`
- Create: `uploads/` directory

**Step 1: Create uploads directory**

```bash
mkdir -p uploads
```

**Step 2: Create ocr.py**

```python
import pytesseract
from PIL import Image
from pathlib import Path


def extract_text(image_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Returns extracted text or empty string on failure.
    """
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        print(f"OCR error: {e}")
        return ""


if __name__ == "__main__":
    # Test with a sample image if available
    import sys
    if len(sys.argv) > 1:
        text = extract_text(sys.argv[1])
        print(text)
    else:
        print("Usage: python ocr.py <image_path>")
```

**Step 3: Test (if you have an image)**

```bash
python ocr.py /path/to/test/image.png
```

**Step 4: Commit**

```bash
git add .
git commit -m "feat: add OCR module for text extraction"
```

---

## Task 11: Reading Materials Management

**Files:**
- Modify: `app.py`
- Create: `templates/materials.html`

**Step 1: Add material routes**

Add to app.py:

```python
import os
from werkzeug.utils import secure_filename
from ocr import extract_text

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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
```

**Step 2: Create materials template**

Create `templates/materials.html`:

```html
{% extends "base.html" %}

{% block title %}Reading Materials{% endblock %}

{% block content %}
<a href="/" style="color: #667eea; text-decoration: none;">&larr; Home</a>
<h1 style="margin-top: 10px;">Reading Materials</h1>

<div class="card" style="margin: 20px 0;">
    <h2>Add New Material</h2>
    <form id="upload-form" enctype="multipart/form-data">
        <input type="text" name="title" placeholder="Title..." required>

        <div style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px;">Upload Image (optional - will OCR text):</label>
            <input type="file" name="image" accept="image/*" id="image-input">
        </div>

        <div style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px;">Or paste/type text directly:</label>
            <textarea name="content" id="content-input" rows="6" placeholder="Paste or type reading material here..."></textarea>
        </div>

        <button type="submit" class="btn btn-success">Add Material</button>
    </form>
</div>

<h2>Materials</h2>
<div id="materials-list">
    {% for material in materials %}
    <div class="card" style="margin-bottom: 15px;">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div>
                <h3 style="margin: 0;">{{ material.title }}</h3>
                <p style="color: #666; margin-top: 5px;">
                    {{ material.content[:100] }}{% if material.content|length > 100 %}...{% endif %}
                </p>
            </div>
            <div>
                <a href="/session/{{ material.id }}/parent" class="btn btn-primary" style="padding: 8px 15px;">
                    Start Session
                </a>
                <button class="btn btn-danger" style="padding: 8px 15px;" onclick="deleteMaterial({{ material.id }})">
                    Delete
                </button>
            </div>
        </div>
    </div>
    {% else %}
    <p style="color: #666;">No materials yet. Add one above!</p>
    {% endfor %}
</div>
{% endblock %}

{% block scripts %}
<script>
document.getElementById('upload-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    const res = await fetch('/api/materials', {
        method: 'POST',
        body: formData
    });

    if (res.ok) {
        location.reload();
    } else {
        alert('Error creating material');
    }
});

async function deleteMaterial(id) {
    if (!confirm('Delete this material?')) return;
    await fetch(`/api/materials/${id}`, { method: 'DELETE' });
    location.reload();
}
</script>
{% endblock %}
```

**Step 3: Test**

Upload an image or paste text, see it in the list.

**Step 4: Commit**

```bash
git add .
git commit -m "feat: add reading materials management with OCR upload"
```

---

## Task 12: Interactive Reading Session - WebSocket

**Files:**
- Modify: `app.py`
- Create: `templates/session_parent.html`
- Create: `templates/session_child.html`

**Step 1: Add WebSocket events and routes**

Add to app.py:

```python
from flask_socketio import emit, join_room, leave_room

# Store active sessions
active_sessions = {}


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

    result = fetch_definition(word)
    definition = result["definition"] if result else ""
    example = result.get("example", "") if result else ""

    conn = get_db()
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

    room = f"session_{data['material_id']}"
    emit("word_added", {"word": word, "definition": definition}, room=room)
```

**Step 2: Create parent session template**

Create `templates/session_parent.html`:

```html
{% extends "base.html" %}

{% block title %}Reading Session - Parent{% endblock %}

{% block extra_css %}
<style>
    .reading-content {
        font-size: 20px;
        line-height: 1.8;
        white-space: pre-wrap;
    }
    .reading-content span {
        cursor: pointer;
        padding: 2px;
        border-radius: 3px;
    }
    .reading-content span:hover {
        background: #e2e8f0;
    }
    .reading-content span.highlighted {
        background: #faf089;
        font-weight: bold;
    }
    .control-panel {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        background: white;
        padding: 15px;
        box-shadow: 0 -5px 20px rgba(0,0,0,0.1);
    }
    .progress-bar {
        height: 10px;
        background: #e2e8f0;
        border-radius: 5px;
        margin-bottom: 10px;
    }
    .progress-fill {
        height: 100%;
        background: #667eea;
        border-radius: 5px;
        transition: width 0.3s;
    }
</style>
{% endblock %}

{% block content %}
<div style="margin-bottom: 100px;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <div>
            <a href="/materials" style="color: #667eea; text-decoration: none;">&larr; Back</a>
            <h1 style="margin-top: 10px;">{{ material.title }}</h1>
        </div>
        <div>
            <label>Child: </label>
            <select id="child-select" style="padding: 8px; font-size: 16px;">
                {% for child in children %}
                <option value="{{ child.id }}">{{ child.name }}</option>
                {% endfor %}
            </select>
        </div>
    </div>

    <div style="background: #f0f0f0; padding: 10px; border-radius: 8px; margin-bottom: 20px;">
        <span style="color: #666;">Child's view: </span>
        <a href="/session/{{ material.id }}/child" target="_blank" style="color: #667eea;">
            Open in new tab →
        </a>
        <span style="margin-left: 20px; color: #888;" id="connection-status">Waiting for child to connect...</span>
    </div>

    <div class="reading-content" id="content">
        <!-- Words will be wrapped in spans -->
    </div>
</div>

<div class="control-panel">
    <div class="progress-bar">
        <div class="progress-fill" id="progress-fill" style="width: 0%;"></div>
    </div>
    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
        <span id="selected-word" style="font-weight: bold; min-width: 100px;"></span>
        <button class="btn btn-primary" id="ask-meaning-btn" style="display: none;" onclick="askMeaning()">
            What does this mean?
        </button>
        <button class="btn btn-success" id="add-word-btn" style="display: none;" onclick="addWord()">
            Add to Words
        </button>
        <button class="btn btn-warning" id="clear-btn" style="display: none;" onclick="clearHighlight()">
            Clear
        </button>
        <input type="text" id="custom-question" placeholder="Type a question..." style="flex: 1; min-width: 200px;">
        <button class="btn btn-primary" onclick="askCustom()">Ask</button>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
<script>
const materialId = {{ material.id }};
const socket = io();
let selectedWord = null;

// Wrap each word in a span
const content = `{{ material.content | e }}`;
const contentEl = document.getElementById('content');
contentEl.innerHTML = content.split(/(\s+)/).map((part, i) => {
    if (part.trim()) {
        return `<span onclick="selectWord(this, '${part.replace(/[^a-zA-Z]/g, '')}')">${part}</span>`;
    }
    return part;
}).join('');

socket.emit('join_session', { material_id: materialId, role: 'parent' });

socket.on('user_joined', (data) => {
    if (data.role === 'child') {
        document.getElementById('connection-status').textContent = 'Child connected!';
        document.getElementById('connection-status').style.color = '#48bb78';
    }
});

socket.on('scroll_updated', (data) => {
    document.getElementById('progress-fill').style.width = data.percent + '%';
});

socket.on('response_received', (data) => {
    alert(`Child responded: ${data.response}`);
});

socket.on('word_added', (data) => {
    alert(`Added "${data.word}" to vocabulary!\nDefinition: ${data.definition}`);
});

function selectWord(el, word) {
    // Clear previous highlight
    document.querySelectorAll('.highlighted').forEach(e => e.classList.remove('highlighted'));

    // Highlight new word
    el.classList.add('highlighted');
    selectedWord = word;

    document.getElementById('selected-word').textContent = word;
    document.getElementById('ask-meaning-btn').style.display = 'inline-block';
    document.getElementById('add-word-btn').style.display = 'inline-block';
    document.getElementById('clear-btn').style.display = 'inline-block';

    socket.emit('highlight_word', {
        material_id: materialId,
        word: word,
        index: Array.from(el.parentNode.children).indexOf(el)
    });
}

function clearHighlight() {
    document.querySelectorAll('.highlighted').forEach(e => e.classList.remove('highlighted'));
    selectedWord = null;
    document.getElementById('selected-word').textContent = '';
    document.getElementById('ask-meaning-btn').style.display = 'none';
    document.getElementById('add-word-btn').style.display = 'none';
    document.getElementById('clear-btn').style.display = 'none';

    socket.emit('clear_highlight', { material_id: materialId });
}

function askMeaning() {
    if (!selectedWord) return;
    socket.emit('ask_question', {
        material_id: materialId,
        question: `What does "${selectedWord}" mean?`,
        word: selectedWord
    });
}

function askCustom() {
    const question = document.getElementById('custom-question').value.trim();
    if (!question) return;

    socket.emit('ask_question', {
        material_id: materialId,
        question: question,
        word: selectedWord
    });
    document.getElementById('custom-question').value = '';
}

function addWord() {
    if (!selectedWord) return;
    const childId = document.getElementById('child-select').value;

    socket.emit('add_word', {
        material_id: materialId,
        word: selectedWord,
        child_id: childId
    });

    clearHighlight();
}
</script>
{% endblock %}
```

**Step 3: Create child session template**

Create `templates/session_child.html`:

```html
{% extends "base.html" %}

{% block title %}Reading Session - Child{% endblock %}

{% block extra_css %}
<style>
    .reading-content {
        font-size: 24px;
        line-height: 2;
        white-space: pre-wrap;
    }
    .reading-content span.highlighted {
        background: #faf089;
        font-weight: bold;
        padding: 2px 5px;
        border-radius: 5px;
    }
    .question-modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.7);
        z-index: 100;
    }
    .question-box {
        background: white;
        max-width: 500px;
        margin: 100px auto;
        padding: 30px;
        border-radius: 20px;
        text-align: center;
    }
</style>
{% endblock %}

{% block content %}
<div style="margin-bottom: 20px;">
    <h1>{{ material.title }}</h1>
    <div style="background: #e2e8f0; padding: 10px; border-radius: 8px;">
        <span id="connection-status" style="color: #666;">Connecting to parent...</span>
    </div>
</div>

<div style="margin-bottom: 20px;">
    <label>Who's reading? </label>
    <select id="child-select" style="padding: 10px; font-size: 18px;">
        {% for child in children %}
        <option value="{{ child.id }}">{{ child.name }}</option>
        {% endfor %}
    </select>
</div>

<div class="reading-content" id="content">
    <!-- Words will be wrapped in spans -->
</div>

<div class="question-modal" id="question-modal">
    <div class="question-box">
        <h2 id="question-text">Question</h2>
        <div style="margin: 30px 0;">
            <button class="btn btn-success" style="font-size: 24px; padding: 20px 40px;" onclick="respond('I know it!')">
                👍 I Know It!
            </button>
            <button class="btn btn-warning" style="font-size: 24px; padding: 20px 40px; margin-left: 10px;" onclick="respond('I don\\'t know')">
                🤔 I Don't Know
            </button>
        </div>
        <button class="btn btn-primary" onclick="closeQuestion()">Close</button>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
<script>
const materialId = {{ material.id }};
const socket = io();
let currentQuestion = null;

// Wrap each word in a span
const content = `{{ material.content | e }}`;
const contentEl = document.getElementById('content');
contentEl.innerHTML = content.split(/(\s+)/).map((part, i) => {
    if (part.trim()) {
        return `<span data-index="${i}">${part}</span>`;
    }
    return part;
}).join('');

socket.emit('join_session', { material_id: materialId, role: 'child' });

socket.on('connect', () => {
    document.getElementById('connection-status').textContent = 'Connected to parent!';
    document.getElementById('connection-status').style.color = '#48bb78';
});

socket.on('word_highlighted', (data) => {
    // Clear previous highlights
    document.querySelectorAll('.highlighted').forEach(e => e.classList.remove('highlighted'));

    // Highlight the word
    const spans = contentEl.querySelectorAll('span');
    if (data.index !== undefined && spans[data.index]) {
        spans[data.index].classList.add('highlighted');
        spans[data.index].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
});

socket.on('highlight_cleared', () => {
    document.querySelectorAll('.highlighted').forEach(e => e.classList.remove('highlighted'));
});

socket.on('question_asked', (data) => {
    currentQuestion = data;
    document.getElementById('question-text').textContent = data.question;
    document.getElementById('question-modal').style.display = 'block';
});

socket.on('word_added', (data) => {
    // Show brief notification
    const el = document.createElement('div');
    el.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #48bb78; color: white; padding: 15px 25px; border-radius: 10px; z-index: 200;';
    el.textContent = `"${data.word}" added to your words!`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
});

function respond(response) {
    socket.emit('child_response', {
        material_id: materialId,
        response: response,
        question: currentQuestion?.question,
        word: currentQuestion?.word
    });
    closeQuestion();
}

function closeQuestion() {
    document.getElementById('question-modal').style.display = 'none';
    currentQuestion = null;
}

// Track scroll position
let lastScroll = 0;
window.addEventListener('scroll', () => {
    const now = Date.now();
    if (now - lastScroll < 500) return;
    lastScroll = now;

    const percent = Math.round((window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100);
    socket.emit('scroll_update', { material_id: materialId, percent: percent });
});
</script>
{% endblock %}
```

**Step 4: Test**

1. Go to `/materials`, create a material
2. Click "Start Session" - opens parent view
3. Open child view in another tab/device
4. Highlight words, ask questions, add to vocabulary

**Step 5: Commit**

```bash
git add .
git commit -m "feat: add interactive reading sessions with WebSocket sync"
```

---

## Task 13: Stats & Badges Page

**Files:**
- Modify: `app.py`
- Create: `templates/stats.html`

**Step 1: Add badges logic to test_engine.py**

Add to test_engine.py:

```python
BADGE_DEFINITIONS = {
    "first_steps": ("🎯 First Steps", "Add 10 words"),
    "scholar": ("📚 Scholar", "Add 50 words"),
    "sharp_mind": ("🧠 Sharp Mind", "10 correct in a row"),
    "unstoppable": ("🔥 Unstoppable", "25 correct in a row"),
    "speed_demon": ("⚡ Speed Demon", "Average < 3s per question"),
    "dedicated": ("📅 Dedicated", "Test 7 days in a row"),
    "master": ("👑 Master", "Get a word to level 5"),
}


def check_badges(child_id: int) -> list:
    """Check and award any new badges. Returns list of newly earned badges."""
    conn = get_db()
    new_badges = []

    # Get existing badges
    existing = set(row["badge_type"] for row in conn.execute(
        "SELECT badge_type FROM badge WHERE child_id = ?", (child_id,)
    ).fetchall())

    # Check word count badges
    word_count = conn.execute(
        "SELECT COUNT(*) FROM word WHERE child_id = ?", (child_id,)
    ).fetchone()[0]

    if word_count >= 10 and "first_steps" not in existing:
        new_badges.append("first_steps")
    if word_count >= 50 and "scholar" not in existing:
        new_badges.append("scholar")

    # Check streak badges (from word_progress)
    max_streak = conn.execute(
        "SELECT MAX(streak) FROM word_progress WHERE child_id = ?", (child_id,)
    ).fetchone()[0] or 0

    if max_streak >= 10 and "sharp_mind" not in existing:
        new_badges.append("sharp_mind")
    if max_streak >= 25 and "unstoppable" not in existing:
        new_badges.append("unstoppable")

    # Check master badge (any word at level 5)
    master_words = conn.execute(
        "SELECT COUNT(*) FROM word_progress WHERE child_id = ? AND difficulty_level >= 5",
        (child_id,)
    ).fetchone()[0]

    if master_words > 0 and "master" not in existing:
        new_badges.append("master")

    # Award new badges
    for badge in new_badges:
        conn.execute(
            "INSERT INTO badge (child_id, badge_type) VALUES (?, ?)",
            (child_id, badge)
        )

    conn.commit()
    conn.close()

    return [(b, BADGE_DEFINITIONS[b]) for b in new_badges]
```

**Step 2: Add stats route to app.py**

```python
from test_engine import check_badges, BADGE_DEFINITIONS


@app.route("/child/<int:child_id>/stats")
def stats_page(child_id):
    conn = get_db()
    child = conn.execute("SELECT * FROM child WHERE id = ?", (child_id,)).fetchone()
    if not child:
        return "Child not found", 404

    # Check for new badges
    check_badges(child_id)

    # Get all stats
    word_count = conn.execute(
        "SELECT COUNT(*) FROM word WHERE child_id = ?", (child_id,)
    ).fetchone()[0]

    badges = conn.execute(
        "SELECT badge_type, earned_at FROM badge WHERE child_id = ? ORDER BY earned_at DESC",
        (child_id,)
    ).fetchall()

    sessions = conn.execute(
        """SELECT test_type, SUM(correct_count) as correct, SUM(total_count) as total,
                  SUM(score) as score, COUNT(*) as count
           FROM test_session WHERE child_id = ? GROUP BY test_type""",
        (child_id,)
    ).fetchall()

    all_children = conn.execute(
        "SELECT id, name, total_points, level FROM child ORDER BY total_points DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "stats.html",
        child=dict(child),
        word_count=word_count,
        badges=[dict(b) for b in badges],
        badge_defs=BADGE_DEFINITIONS,
        sessions=[dict(s) for s in sessions],
        leaderboard=[dict(c) for c in all_children]
    )
```

**Step 3: Create stats template**

Create `templates/stats.html`:

```html
{% extends "base.html" %}

{% block title %}{{ child.name }} - Stats{% endblock %}

{% block content %}
<a href="/child/{{ child.id }}" style="color: #667eea; text-decoration: none;">&larr; Back</a>
<h1 style="margin-top: 10px;">{{ child.name }}'s Stats</h1>

<div class="grid" style="grid-template-columns: repeat(4, 1fr); margin: 20px 0;">
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #667eea;">{{ child.level }}</div>
        <div>Level</div>
    </div>
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #48bb78;">{{ child.total_points }}</div>
        <div>Points</div>
    </div>
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #ed8936;">{{ word_count }}</div>
        <div>Words</div>
    </div>
    <div class="card" style="text-align: center;">
        <div style="font-size: 36px; font-weight: bold; color: #9f7aea;">{{ badges|length }}</div>
        <div>Badges</div>
    </div>
</div>

<h2>Badges</h2>
<div class="grid" style="margin-bottom: 30px;">
    {% for badge_type, info in badge_defs.items() %}
    {% set earned = badges|selectattr('badge_type', 'equalto', badge_type)|first %}
    <div class="card" style="text-align: center; {% if not earned %}opacity: 0.4;{% endif %}">
        <div style="font-size: 36px;">{{ info[0].split()[0] }}</div>
        <div style="font-weight: bold;">{{ info[0].split()[1:] | join(' ') }}</div>
        <div style="font-size: 12px; color: #666;">{{ info[1] }}</div>
        {% if earned %}
        <div style="font-size: 11px; color: #48bb78; margin-top: 5px;">✓ Earned</div>
        {% endif %}
    </div>
    {% endfor %}
</div>

<h2>Leaderboard</h2>
<div class="card">
    {% for c in leaderboard %}
    <div style="display: flex; justify-content: space-between; padding: 10px; {% if c.id == child.id %}background: #e2e8f0; border-radius: 8px;{% endif %}">
        <div>
            <span style="font-size: 20px; margin-right: 10px;">
                {% if loop.index == 1 %}🥇{% elif loop.index == 2 %}🥈{% elif loop.index == 3 %}🥉{% else %}{{ loop.index }}.{% endif %}
            </span>
            <strong>{{ c.name }}</strong>
        </div>
        <div>
            Level {{ c.level }} • {{ c.total_points }} pts
        </div>
    </div>
    {% endfor %}
</div>

{% if sessions %}
<h2 style="margin-top: 30px;">Test History</h2>
{% for session in sessions %}
<div class="card">
    <strong>{{ session.test_type }}</strong>:
    {{ session.count }} tests,
    {{ session.correct }}/{{ session.total }} correct
    ({{ ((session.correct / session.total) * 100) | round | int }}%),
    {{ session.score }} total points
</div>
{% endfor %}
{% endif %}
{% endblock %}
```

**Step 4: Test**

Complete some tests, add words, check stats page for badges and leaderboard.

**Step 5: Commit**

```bash
git add .
git commit -m "feat: add stats page with badges, leaderboard, test history"
```

---

## Task 14: Final Polish & README

**Files:**
- Create: `README.md`

**Step 1: Create README**

```markdown
# Kid Verbal

A web app to help kids improve verbal skills through vocabulary building, gamified testing, and interactive reading sessions.

## Features

- **Multiple Profiles**: Each child has their own word list, progress, and achievements
- **Word Management**: Add words manually or from reading sessions, auto-fetch definitions
- **Four Test Types**:
  - Definition Quiz: See word, pick definition
  - Reverse Quiz: See definition, pick word
  - Spelling Bee: Hear word, type spelling
  - Fill-in-the-Blank: Complete sentences
- **Gamification**: Points, streaks, levels, badges, leaderboard
- **Adaptive Difficulty**: Questions adjust based on performance
- **Interactive Reading**: Real-time sync between parent and child devices
- **OCR Support**: Upload photos of book pages, extract text automatically

## Setup

### Prerequisites

- Python 3.11+
- Tesseract OCR (for image text extraction)

#### Install Tesseract

macOS:
```bash
brew install tesseract
```

Ubuntu/Debian:
```bash
sudo apt install tesseract-ocr
```

### Install & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python database.py

# Run server
python app.py
```

Open http://localhost:5000

## Usage

1. **Create Profiles**: Add a profile for each child on the home page
2. **Add Words**: Go to "My Words" to add vocabulary words (definitions auto-fetched)
3. **Take Tests**: Choose a test type, answer questions, earn points and badges
4. **Reading Sessions**:
   - Upload reading material (image or text)
   - Open parent view on your device
   - Open child view on kid's device (same network)
   - Highlight words, ask questions, add new vocabulary

## Project Structure

```
kid-verbal/
├── app.py              # Flask server with routes and WebSocket handlers
├── database.py         # SQLite schema and connection
├── dictionary.py       # Free Dictionary API client
├── ocr.py              # Tesseract OCR wrapper
├── test_engine.py      # Test logic, scoring, badges
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── base.html
│   ├── home.html
│   ├── dashboard.html
│   ├── words.html
│   ├── test.html
│   ├── materials.html
│   ├── stats.html
│   ├── session_parent.html
│   └── session_child.html
├── static/             # CSS, JS, images (if needed)
├── uploads/            # Uploaded reading material images
└── verbal.db           # SQLite database (auto-created)
```

## License

MIT
```

**Step 2: Final commit**

```bash
git add .
git commit -m "docs: add README with setup and usage instructions"
```

---

## Summary

Total tasks: 14

1. Project setup (Flask, SQLite schema, base templates)
2. Child profile CRUD API
3. Child dashboard page
4. Dictionary API client
5. Word management API
6. Word list page with TTS
7. Test engine core logic
8. Test API endpoints
9. Test page with all quiz types
10. OCR module
11. Reading materials management
12. Interactive reading sessions with WebSocket
13. Stats & badges page
14. README documentation

Each task includes:
- Exact file paths
- Complete code
- Test commands
- Commit after completion
