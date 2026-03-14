# Current State

*Last updated: 2026-03-14*

## What's Built and Working

### Vocabulary (Language Arts tab)
- Word management: add manually, paste import (word-definition pairs), auto-fetch definitions
- Word images support
- Flashcard study sessions (parent-created)
- Four test types: definition quiz, reverse quiz, spelling bee, fill-in-blank
- Gamification: points, streaks, levels, badges
- Adaptive difficulty per word
- Word mastery tracking with progress visualization

### Reading Comprehension
- Reading material management: paste text, upload images (OCR), source URLs, PDF content
- Comprehension questions per material
- **AI question generation:** "Generate by AI" button in batch import uses OpenAI to create 10 MCQs from material content/URL, grade-level aware, answers evenly distributed across A/B/C/D
- Article import auto-assigns to currently filtered child
- Reading assignments to children
- Child answers with required evidence text ("Why?")
- Unknown word marking (integrates with vocab)
- Parent review of answers (mark correct/incorrect)

### Math
- Math test creation with question PDF + answer PDF
- Answer key parsing: grid OCR (Kangaroo format), manual entry fallback
- Timed tests (stopwatch or countdown)
- Auto-grading against answer key
- Retry wrong questions only
- Score tracking with original vs retry scores
- Auto-save drafts

### Writing
- Writing topics management
- Timed writing tests with word count constraints
- Inline text annotations by parent
- Score and feedback
- Send-back-for-revision flow
- Auto-save drafts

### Science (Science Bowl)
- PDF import of Science Bowl format questions
- Question bank with search, inline edit, category filtering
- Flashcard study sessions
- Auto-graded tests (MC + short answer with ACCEPT patterns)
- Per-question mastery tracking with progress page
- Category rollup statistics
- Mastery filters + pagination

### Learning Plans
- Bundle activities across subjects into daily plans
- Supports all activity types: vocab study, vocab test, reading, math test, writing test, science study, science test
- Draft → released → completed lifecycle
- Auto-completion detection when all items done
- Parent review tracking per item
- Child view with plan navigation
- Plan badges on dashboard

### Infrastructure
- Account auth (parent + child roles)
- Parent dashboard with tabbed interface (sidebar navigation)
- Child dashboard showing pending work
- Interactive reading sessions via WebSocket (parent-child sync)
- Database backup script
- **Settings page** (`/settings`): OpenAI API key management (stored in DB, masked display) and per-child grade level configuration
- **Site config table** (`site_config`): key-value store for app-wide configuration, reusable across all AI features
- **Child grade levels**: stored on child profile, used by AI for complexity calibration

## Known Issues / Tech Debt

- `app.py` is very large (~4550 lines) — could benefit from splitting into blueprints
- All CSS is inline in templates — lots of duplication
- No automated tests
- No input validation library — manual validation in each route
- Migrations are try/except ALTER TABLE blocks that accumulate over time
- `database.py` `init_db()` is getting long with migrations
- No error logging framework
- Secret key is hardcoded (`REDACTED-SECRET`)

## Recent Changes (latest commits)

1. **AI question generation for reading materials** (task_001) — OpenAI integration, settings page, child grade levels, article import child assignment fix
2. Auto-save drafts for math/writing tests
3. Mastery filters with pagination for science questions
4. PDF content support for reading assignments
5. Parent review tracking + required explanations for reading/math tests
6. Search and inline edit for science question bank
7. Writing test send-back-for-revision
8. Science question mastery tracking with progress page
