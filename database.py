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
            image_path TEXT,
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

        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            child_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS study_session (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS study_session_word (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES study_session(id) ON DELETE CASCADE,
            FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_session_answer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            word_text TEXT NOT NULL,
            question_type TEXT NOT NULL,
            child_answer TEXT,
            correct_answer TEXT,
            is_correct BOOLEAN NOT NULL,
            FOREIGN KEY (session_id) REFERENCES test_session(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS parent_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT,
            status TEXT DEFAULT 'pending',
            source_type TEXT NOT NULL,
            source_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS parent_test_word (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_test_id INTEGER NOT NULL,
            word_id INTEGER NOT NULL,
            FOREIGN KEY (parent_test_id) REFERENCES parent_test(id) ON DELETE CASCADE,
            FOREIGN KEY (word_id) REFERENCES word(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS material_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            answer_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES reading_material(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reading_assignment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (material_id) REFERENCES reading_material(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reading_assignment_answer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            child_answer TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assignment_id) REFERENCES reading_assignment(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES material_question(id) ON DELETE CASCADE
        );
    """)
    conn.commit()

    # Migration: Add image_path to word table if not exists
    try:
        conn.execute("ALTER TABLE word ADD COLUMN image_path TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: Add last_correct_at to word_progress table if not exists
    try:
        conn.execute("ALTER TABLE word_progress ADD COLUMN last_correct_at DATETIME")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: Add created_by and parent_test_id to test_session
    try:
        conn.execute("ALTER TABLE test_session ADD COLUMN created_by TEXT DEFAULT 'child'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE test_session ADD COLUMN parent_test_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add choices column to test_session_answer
    try:
        conn.execute("ALTER TABLE test_session_answer ADD COLUMN choices TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add question_text column to test_session_answer
    try:
        conn.execute("ALTER TABLE test_session_answer ADD COLUMN question_text TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add source_material_id to word table
    try:
        conn.execute("ALTER TABLE word ADD COLUMN source_material_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add source_url to reading_material
    try:
        conn.execute("ALTER TABLE reading_material ADD COLUMN source_url TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add child_id to reading_material
    try:
        conn.execute("ALTER TABLE reading_material ADD COLUMN child_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add evidence_text to reading_assignment_answer
    try:
        conn.execute("ALTER TABLE reading_assignment_answer ADD COLUMN evidence_text TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
