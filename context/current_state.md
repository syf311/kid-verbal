# Current State

*Last updated: 2026-04-04*

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
- **Power Words:** Auto-extracted from Science News Explores articles during RSS import. Parent can selectively add to child's vocabulary with source link tracking.
- **Web reading view:** RSS-imported materials with source URL show the original website in a sandboxed proxy iframe (images, formatting preserved). All links disabled, no navigation possible. Questions panel shown by default alongside web content.
- Reading assignments to children
- Child answers with required evidence text ("Why?")
- Unknown word marking (integrates with vocab)
- Parent review of answers (mark correct/incorrect)
- **Attempt tracking:** Materials page shows per-child attempt count, last tried date, and most recent correct ratio (e.g., "Tried 2x — 7/10 (70%)"). Filter buttons: All / New / Needs Review (<80%) / Worth Refreshing (>1 month ago). Only shown when a child filter is active.

### Math
- Math test creation with question PDF + answer PDF
- Answer key parsing: grid OCR (Kangaroo format), manual entry fallback
- Timed tests (stopwatch or countdown)
- Auto-grading against answer key
- Retry wrong questions only
- Score tracking with original vs retry scores
- Auto-save drafts
- **Math Question Bank:** AI-generated or manually added MC questions with concept tags, difficulty (1-5), solution steps, and per-question mastery tracking
- **Math Bank Tests:** Create tests from the question bank with concept/difficulty/mastery filters, auto-graded, solution steps in review
- **Copy/paste prevention:** Text selection, right-click, and Ctrl+C disabled on test pages to deter cheating

### Writing
- Writing topics management
- Timed writing tests with word count constraints
- Inline text annotations by parent
- Score and feedback
- Send-back-for-revision flow
- Auto-save drafts (client-side localStorage, debounced 3s + periodic 30s)
- **Checkpoint snapshots:** every 5 minutes, a snapshot is saved locally (last 2 kept). Checkpoint bar shows revert buttons with minute mark and word count. Cleared on submit.

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
- Supports all activity types: vocab study, vocab test, reading, math test, math bank test, writing test, science study, science test
- Adding reading assignment auto-creates a writing summary assignment (grade-level word limits)
- Adding reading assignment auto-creates power words study session if words are in child's vocab
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

- `app.py` is very large (~5500+ lines) — could benefit from splitting into blueprints
- All CSS is inline in templates — lots of duplication
- No automated tests
- No input validation library — manual validation in each route
- Migrations are try/except ALTER TABLE blocks that accumulate over time
- `database.py` `init_db()` is getting long with migrations
- No error logging framework
- Secret key is hardcoded (`REDACTED-SECRET`)

## Recent Changes (latest commits)

1. **Verified tracking & progress bar** (task_012) — Questions marked verified after AI confirms correct or after edit/bulk fix. Verify skips already-verified questions. Progress bar during verification. Bulk fix stays on results panel, removes fixed items. Verified badge on question cards, unverified count on button.
1. **Bulk fix for verified answers** (task_012) — Select multiple flagged questions with checkboxes, Select All toggle, "Bulk Fix Selected" applies AI-suggested answers in one click. Skips items with no valid suggestion.
1. **Fix verify false positives** — Skip flagging questions where AI suggests the same answer that's already selected
1. **Math question edit modal and batch verify** (task_012) — Full edit modal replacing prompt dialog (question text, choices A-E, correct answer radio, solution steps, concepts, difficulty). Batch verify button sends questions to OpenAI to flag answer inconsistencies with Fix buttons.
2. **Prevent copy/paste on math tests** (task_011) — Disable text selection, right-click, and Ctrl+C on math bank test page to deter cheating
2. **Math practice in learning plans** (task_010) — "+ Math Practice" button in learning plan management with concept/difficulty/mastery filters, plan completion detection
3. **Math bank tests with auto-grading and progress tracking** (task_009) — Create tests from math question bank, child takes MC test with timer, auto-graded with solution steps in review, per-question mastery tracking, dashboard integration with Bank badge
2. **Math question bank with AI generation** (task_008) — New math_question/math_question_progress tables, question bank page with search/filters (concept, difficulty 1-5, mastery), manual add, AI generate via OpenAI, copy prompt/paste response for ChatGPT, duplicate detection, difficulty control (mixed or focused)
2. **Auto-create writing assignment for reading** (task_007) — Adding a reading assignment to a learning plan auto-creates a writing test prompting the child to summarize and share their point of view, with grade-level word limits and toast notification
2. **Fix AI question answer distribution** (bug_002) — Expanded few-shot example and strengthened prompt to distribute correct answers evenly across A/B/C/D
2. **Power Words extraction from articles** (task_006) — Extract Power Words from Science News Explores articles during RSS import, store on material, parent can selectively add to child's vocab, source link shown in word bank, auto-creates study session in learning plans
2. **Reading picker filters in learning plan** (task_005) — Reading assignment picker in manage/create plan replaced with scrollable card list showing attempt badges, scores, last tried date, and filter buttons (All / New / Needs Review / Worth Refreshing)
2. **Fix vocab test detail back link** (bug_001) — Back link on vocab test review now navigates to learning plan page when accessed from a plan, falls back to dashboard otherwise
2. **Reading material attempt tracking** (task_004) — per-child attempt count, last tried date, correct ratio on materials page with filter buttons (New / Needs Review / Worth Refreshing)
2. **Writing auto-save with checkpoints** (task_003) — client-side auto-save (debounced + periodic), 5-minute checkpoint snapshots (last 2), revert UI, beforeunload warning, cleared on submit
2. **Web reading view for RSS materials** (task_002) — server-side proxy serves sanitized website content in sandboxed iframe, all links disabled, questions panel open by default
3. **AI question generation for reading materials** (task_001) — OpenAI integration, settings page, child grade levels, article import child assignment fix
4. Auto-save drafts for math/writing tests
3. Mastery filters with pagination for science questions
4. PDF content support for reading assignments
5. Parent review tracking + required explanations for reading/math tests
6. Search and inline edit for science question bank
7. Writing test send-back-for-revision
8. Science question mastery tracking with progress page
