# Task 016: Math Bank Tests — Exam Mode and Practice Mode, with Resume

**Status:** Done

## Objective

Math bank tests get two modes, chosen by the parent when creating the test:

- **Exam mode (真题模式):** a full past contest, timed like the real one. Score, answers and solutions only after the whole test is submitted.
- **Practice mode (单元练习):** no timer. Each question is submitted on its own and immediately shows right/wrong, the correct answer and the solution.

Both modes can be left half done and continued later. In exam mode the timer is paused while the test isn't open and continues from where it stopped.

## Decisions (confirmed 2026-10-17)

| # | Decision |
|---|----------|
| D1 | Exam scoring follows the official rules plus a percentage: AMC 10/12 = 6 per correct, 1.5 per blank, 0 per wrong; AMC 8 = 1 per correct. Other contests (or mixed contests) show correct count + percentage only. |
| D2 | Practice: the first answer counts (no retry). Feedback (right/wrong, answer, solution) shown right after submitting the question. |
| D3 | Existing tests not yet done: timed (`countdown`/`stopwatch`) → exam, untimed → practice. Completed tests unchanged. |
| D4 | Practice ends automatically when the last question is answered (no "finish early"). |
| D5 | Exam blanks are allowed (click the chosen answer again to clear it). Blank counts as wrong for mastery, 1.5 points for AMC 10/12 scoring. |
| D6 | Exam timer: counts only while the test page is open (also when the tab is in the background). Pause button hides the questions. Leaving/closing the page pauses. Progress saved on every answer, every 15 s and when leaving. Countdown reaching 0 submits automatically. |
| D7 | "Full exam" button in the test builder when a contest + year filter is set: selects that set, titles it "<contest> <year>", exam mode, countdown with the official time (AMC 8 = 40 min, AMC 10/12 = 75 min; other contests: parent enters). |
| D8 | The test API no longer sends correct answers or solutions to the page before they may be shown (exam: after submit; practice: after that question is answered). |

## Data model

- `math_bank_test.mode` (`exam` | `practice`, backfilled per D3), `math_bank_test.elapsed_seconds` (saved timer, only grows).
- New `math_bank_test_answer` (test_id, question_id, child_answer, is_correct, answered_at; unique per test/question). Exam rows have `is_correct` NULL until submit; practice rows are graded when saved.
- `math_bank_test_submission.points`, `max_points`, `blank_count`.
- `status` stays `pending` until completed (in-progress = pending with saved answers or time).

## API

- `GET /api/math-bank-tests/<id>` — adds `mode`, `elapsed_seconds`, `answers` (saved answers; practice includes feedback for answered questions). Correct answers/solutions stripped per D8.
- `POST /api/math-bank-tests/<id>/answer` `{question_id, choice, elapsed_seconds}` — exam: save/replace/clear a choice; practice: grade once, update mastery, return feedback; last practice answer completes the test.
- `POST /api/math-bank-tests/<id>/progress` `{elapsed_seconds}` — save the exam timer (heartbeat / pause / leaving page).
- `POST /api/math-bank-tests/<id>/submit` — grades saved answers (body `answers` still accepted), applies D1 scoring.
- Create (`/api/math-bank-tests`, learning-plan math practice) accept `mode`.

## UI

- Test builder and learning-plan Math Practice: mode choice (exam: countdown/stopwatch + minutes; practice: no timer) and the "Full exam" button (builder).
- Test page: exam = all questions, timer, Pause/Resume, Submit; practice = per-question Submit with inline feedback, finishes on the last one.
- Review: official points when scored (e.g. "96 / 150"), blanks shown.
- Parent Math tab and child plan view: mode badge and "In progress x/y" / "Continue".

## Out of scope

Retaking a test, finishing practice early, changing a test's mode after creation.
