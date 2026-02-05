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
