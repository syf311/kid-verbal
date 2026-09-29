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

        CREATE TABLE IF NOT EXISTS reading_assignment_unknown_word (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assignment_id) REFERENCES reading_assignment(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS math_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            question_pdf TEXT NOT NULL,
            answer_pdf TEXT NOT NULL,
            answer_key TEXT NOT NULL,
            total_questions INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS math_test_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            math_test_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            answers TEXT NOT NULL,
            score INTEGER NOT NULL,
            correct_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (math_test_id) REFERENCES math_test(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS writing_topic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            topic_text TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS writing_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            topic_text TEXT NOT NULL,
            topic_id INTEGER,
            timer_mode TEXT DEFAULT 'none',
            time_limit_seconds INTEGER DEFAULT 0,
            min_word_count INTEGER DEFAULT 0,
            max_word_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            learning_plan_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id),
            FOREIGN KEY (topic_id) REFERENCES writing_topic(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS writing_test_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            writing_test_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            writing_text TEXT NOT NULL,
            word_count INTEGER NOT NULL DEFAULT 0,
            time_taken_seconds INTEGER DEFAULT 0,
            score INTEGER,
            feedback TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (writing_test_id) REFERENCES writing_test(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS learning_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'draft',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            released_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES account(id)
        );

        CREATE TABLE IF NOT EXISTS learning_plan_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plan_id) REFERENCES learning_plan(id) ON DELETE CASCADE
        );

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

        CREATE TABLE IF NOT EXISTS site_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS material_power_word (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            definition TEXT NOT NULL,
            FOREIGN KEY (material_id) REFERENCES reading_material(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS math_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            answer_format TEXT NOT NULL DEFAULT 'multiple_choice',
            choices TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            solution_steps TEXT,
            image_path TEXT,
            concepts TEXT,
            grade_level TEXT,
            difficulty INTEGER DEFAULT 3,
            source TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS math_bank_test (
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

        CREATE TABLE IF NOT EXISTS math_bank_test_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            FOREIGN KEY (test_id) REFERENCES math_bank_test(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES math_question(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS math_bank_test_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            answers TEXT NOT NULL,
            score INTEGER NOT NULL,
            correct_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            time_taken_seconds INTEGER DEFAULT 0,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES math_bank_test(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS math_question_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            difficulty_level INTEGER DEFAULT 1,
            last_tested DATETIME,
            last_correct_at DATETIME,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES math_question(id) ON DELETE CASCADE,
            UNIQUE(child_id, question_id)
        );

        CREATE TABLE IF NOT EXISTS science_question_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            difficulty_level INTEGER DEFAULT 1,
            last_tested DATETIME,
            last_correct_at DATETIME,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES science_question(id) ON DELETE CASCADE,
            UNIQUE(child_id, question_id)
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

    # Migration: Add is_correct to reading_assignment_answer
    try:
        conn.execute("ALTER TABLE reading_assignment_answer ADD COLUMN is_correct BOOLEAN")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add timer fields to math_test
    try:
        conn.execute("ALTER TABLE math_test ADD COLUMN timer_mode TEXT DEFAULT 'none'")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE math_test ADD COLUMN time_limit_seconds INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add time_taken_seconds to math_test_submission
    try:
        conn.execute("ALTER TABLE math_test_submission ADD COLUMN time_taken_seconds INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add learning_plan_id to study_session, reading_assignment, math_test
    try:
        conn.execute("ALTER TABLE study_session ADD COLUMN learning_plan_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE reading_assignment ADD COLUMN learning_plan_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE math_test ADD COLUMN learning_plan_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add annotations column to writing_test_submission
    try:
        conn.execute("ALTER TABLE writing_test_submission ADD COLUMN annotations TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add parent_reviewed to learning_plan_item
    try:
        conn.execute("ALTER TABLE learning_plan_item ADD COLUMN parent_reviewed BOOLEAN DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add explanations to math_test_submission
    try:
        conn.execute("ALTER TABLE math_test_submission ADD COLUMN explanations TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add content_pdf to reading_material
    try:
        conn.execute("ALTER TABLE reading_material ADD COLUMN content_pdf TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add grade_level to child
    try:
        conn.execute("ALTER TABLE child ADD COLUMN grade_level TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migration: Add verified to math_question
    try:
        conn.execute("ALTER TABLE math_question ADD COLUMN verified INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    init_question_bank_tables(conn)

    conn.close()


def init_question_bank_tables(conn):
    """CogAT-style / i-Ready-style question bank (task_014). Shared across children."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qb_passage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track TEXT NOT NULL,
            grade INTEGER NOT NULL,
            section TEXT NOT NULL,
            title TEXT,
            body TEXT NOT NULL,
            source_ref TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS qb_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track TEXT NOT NULL,
            grade INTEGER NOT NULL,
            section TEXT NOT NULL,
            qtype TEXT NOT NULL DEFAULT 'text-choice',
            stem TEXT,
            stem_svg TEXT,
            options TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            explanation TEXT,
            image_path TEXT,
            passage_id INTEGER,
            passage_order INTEGER DEFAULT 0,
            difficulty INTEGER DEFAULT 3,
            tags TEXT,
            created_by TEXT DEFAULT 'parent',
            answer_source TEXT DEFAULT 'parent',
            source_ref TEXT UNIQUE,
            source TEXT,
            status TEXT DEFAULT 'active',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (passage_id) REFERENCES qb_passage(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_qb_question_filter ON qb_question(track, grade, section, status);

        CREATE TABLE IF NOT EXISTS qb_question_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            last_tested DATETIME,
            last_correct_at DATETIME,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES qb_question(id) ON DELETE CASCADE,
            UNIQUE(child_id, question_id)
        );

        CREATE TABLE IF NOT EXISTS qb_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            track TEXT NOT NULL,
            grade INTEGER NOT NULL,
            section TEXT,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS qb_test_question (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            FOREIGN KEY (test_id) REFERENCES qb_test(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES qb_question(id)
        );

        CREATE TABLE IF NOT EXISTS qb_test_answer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            choice TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            answered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES qb_test(id) ON DELETE CASCADE,
            UNIQUE(test_id, question_id)
        );

        CREATE TABLE IF NOT EXISTS qb_test_submission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL UNIQUE,
            child_id INTEGER NOT NULL,
            correct_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            score INTEGER NOT NULL,
            time_taken_seconds INTEGER DEFAULT 0,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (test_id) REFERENCES qb_test(id) ON DELETE CASCADE,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS qb_request_key (
            key TEXT PRIMARY KEY,
            resource_type TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Migration: question source (ai_generated | human). Everything created before this column
    # existed was written by Milo (AI), so backfill those rows as ai_generated.
    try:
        conn.execute("ALTER TABLE qb_question ADD COLUMN source TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.execute("UPDATE qb_question SET source = 'ai_generated' WHERE source IS NULL")
    conn.commit()

    # Per-question attempt history + math/science-style mastery (streak, level 1-5)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qb_question_attempt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            child_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            test_id INTEGER,
            choice TEXT,
            is_correct INTEGER NOT NULL,
            attempted_at DATETIME NOT NULL,
            FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES qb_question(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_qb_attempt_child_q ON qb_question_attempt(child_id, question_id, attempted_at);
    """)
    for col in ("streak INTEGER DEFAULT 0", "difficulty_level INTEGER DEFAULT 1"):
        try:
            conn.execute(f"ALTER TABLE qb_question_progress ADD COLUMN {col}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    # One-time: backfill history from submitted tests and recompute progress from it
    if not conn.execute("SELECT 1 FROM site_config WHERE key = 'qb_migration_attempt_history_v1'").fetchone():
        import qb_engine
        qb_engine.rebuild_history(conn)
        conn.execute("INSERT INTO site_config (key, value) VALUES ('qb_migration_attempt_history_v1', 'done')")
        conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
