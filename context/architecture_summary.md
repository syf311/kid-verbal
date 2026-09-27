# Architecture Summary

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python Flask (~4720 lines in app.py) |
| Real-time | Flask-SocketIO (WebSocket for reading sessions) |
| Database | SQLite (verbal.db) |
| Frontend | Server-rendered Jinja2 templates + vanilla JS |
| Styling | Inline CSS in templates (no separate CSS files) |
| OCR | pytesseract + Pillow |
| PDF parsing | pdfplumber (science bowl, math answer keys) |
| Dictionary | Free Dictionary API (dictionaryapi.dev) |
| TTS | Browser Web Speech API |
| AI | OpenAI API (gpt-4o-mini) via `openai` Python SDK |

## Project Structure

```
kid-verbal/
├── app.py                  # Flask server — ALL routes, API endpoints, business logic (~4550 lines)
├── database.py             # SQLite schema (init_db) + migrations (~510 lines)
├── dictionary.py           # Free Dictionary API client
├── ocr.py                  # Tesseract OCR wrapper
├── test_engine.py          # Test logic, scoring, badges, word selection
├── qb_engine.py            # CogAT/i-Ready-style bank: validation, SVG sanitize, mastery, test assembly
├── pdf_parser.py           # Math answer key PDF parser (grid OCR)
├── science_parser.py       # Science Bowl PDF parser
├── requirements.txt        # Python dependencies
├── templates/              # ~35 Jinja2 HTML templates
│   ├── base.html           # Base layout
│   ├── home.html           # Landing / profile selection
│   ├── login.html / register.html
│   ├── parent_home.html    # Parent dashboard (tabbed: vocab, reading, math, writing, science, plans)
│   ├── dashboard.html      # Child dashboard
│   ├── words.html          # Word list management
│   ├── study.html          # Vocab flashcard study
│   ├── test.html / test_detail.html / test_history.html  # Vocab tests
│   ├── materials.html      # Reading materials management
│   ├── reading_assignment.html / reading_assignment_review.html
│   ├── create_math_test.html / math_test.html / math_test_review.html / manage_math_test.html
│   ├── writing_topics.html / writing_test.html / writing_test_review.html
│   ├── science_study.html / science_test.html / science_test_review.html / science_progress.html
│   ├── create_study.html / create_test.html  # Parent creates vocab study/test
│   ├── manage_plan.html / view_plan.html      # Learning plans
│   ├── session_parent.html / session_child.html  # Live reading sessions (WebSocket)
│   ├── settings.html           # Site settings (API keys, child grade levels)
│   ├── progress.html / stats.html
│   └── ...
├── uploads/                # Uploaded PDFs, images
├── verbal.db               # SQLite database (runtime)
└── ai/                     # AI context files (this directory)
```

## Authentication & Roles

- **Account-based auth** with username/password (werkzeug password hashing)
- **Two roles:** `parent` and `child`
- Parent accounts can do everything; child accounts are scoped to their profile
- `@login_required` and `@parent_required` decorators on routes
- Session-based auth via Flask `session`

## Database Schema (key tables)

### User & Profile
- `account` — login credentials, role (parent/child), linked child_id
- `child` — child profile with name, avatar, points, level, grade_level

### Vocabulary
- `word` — vocabulary words per child with definitions
- `word_progress` — per-word mastery tracking (correct/wrong counts, streak, difficulty)
- `study_session` / `study_session_word` — parent-created vocab flashcard sessions
- `parent_test` / `parent_test_word` — parent-created vocab tests
- `test_session` / `test_session_answer` — test results

### Reading
- `reading_material` — articles/passages with optional PDF content
- `material_question` — comprehension questions per material
- `reading_assignment` — assigned reading + questions to a child
- `reading_assignment_answer` — child's answers with evidence text
- `reading_assignment_unknown_word` — words child marks as unknown

### Math
- `math_test` — test with question PDF, answer PDF, parsed answer key
- `math_test_submission` — child's answers and score

### Writing
- `writing_topic` — writing prompts per child
- `writing_test` — timed writing test with word count constraints
- `writing_test_submission` — child's essay, score, feedback, inline annotations

### Science (Science Bowl format)
- `science_question` — individual questions with category, type, choices, answer
- `science_study_session` / `science_study_session_question` — flashcard study
- `science_test` / `science_test_question` — science tests
- `science_test_submission` — graded test results
- `science_question_progress` — per-question mastery tracking

### CogAT-style / i-Ready-style Practice (shared bank, not per child)
- `qb_passage` — reading passages for passage-set questions
- `qb_question` — track, grade, section, qtype, stem/stem_svg, options JSON [{text, svg}], correct_answer (index), explanation, image_path, passage_id, difficulty, status (active/archived), source_ref
- `qb_question_progress` — per child/question correct/wrong counts, last_tested, last_correct_at
- `qb_test` / `qb_test_question` / `qb_test_answer` / `qb_test_submission` — assembled tests, per-question answers, final score
- `qb_request_key` — Idempotency-Key → created resource

### Learning Plans
- `learning_plan` — bundles of activities (draft → released → completed)
- `learning_plan_item` — items in a plan (vocab study, reading, math test, writing test, science study/test)

### Configuration
- `site_config` — key-value store for app-wide settings (e.g., openai_api_key)

## Key Patterns

- **Monolithic app.py:** All routes in one file, organized by subject area
- **Raw SQL everywhere:** No ORM, direct `conn.execute()` calls with `sqlite3.Row`
- **Server-side rendering:** Jinja2 templates with data passed from routes; JS for interactivity
- **JSON APIs for CRUD:** Most create/update/delete operations use fetch() to JSON API endpoints
- **Migrations via ALTER TABLE:** `database.py init_db()` has try/except blocks for column additions
- **File uploads:** PDFs and images saved to `uploads/` directory
- **Auto-grading:** Math (answer key comparison), Science (exact match + ACCEPT patterns), Vocab (multiple choice)
- **Manual grading:** Writing (parent scores + annotations), Reading (parent marks correct/incorrect)
- **AI integration:** OpenAI API key stored in `site_config` DB table (never in code). Accessed via `get_config()` helper. Used for reading question generation; designed for reuse across future AI features.
- **API token auth (question bank only):** `parent_or_token_required` accepts a parent session or `Authorization: Bearer <token>`; SHA-256 hash in `site_config.qb_api_token_hash`. Non-idempotent creates accept an `Idempotency-Key` header.
- **Reading web proxy:** `GET /api/reading-proxy?url=...` fetches external pages, strips links/scripts/nav, converts relative URLs to absolute, serves sanitized HTML for safe kid reading. URL must belong to a known reading material (security check).
