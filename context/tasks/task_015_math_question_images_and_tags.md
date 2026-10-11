# Task 015: Math Question Bank — Images and Origin/Contest Tags

**Status:** Done

## Objective

Let the parent upload a picture for a math bank question and its solution (e.g. a screenshot of a real AMC 10 problem, with the answer choices in the picture), and tag every question with where it came from plus contest / year / problem number, so the bank and the test builder can filter by these tags.

## Decisions (confirmed 2026-10-10)

| # | Decision |
|---|----------|
| D1 | Questions stay per child (no shared bank). |
| D2 | Images are added one question at a time in the Add form / Edit modal (no bulk upload). |
| D3 | New required `origin`: `ai_generated` or `human` (human = real question). All existing rows backfilled `ai_generated`. AI generate / paste import set `ai_generated`. |
| D4 | New optional tags: `contest` (free text with suggestions: AMC 8, AMC 10A, AMC 10B, AMC 12A, AMC 12B, MATHCOUNTS, Math Kangaroo), `contest_year` (integer), `problem_number` (original sequence, integer). |
| D5 | Filter by origin / contest / year on both the bank page and the math bank test builder. |

## Data model

`math_question` new columns (ALTER TABLE migrations):
- `origin TEXT` — backfilled `ai_generated`
- `contest TEXT`, `contest_year INTEGER`, `problem_number INTEGER`
- `solution_image_path TEXT` (question picture uses the existing `image_path`)

The old free-text `source` column is kept but no longer shown.

## Behaviour

- **Question picture:** if a question has a picture, question text is optional and answer choices are optional (the choices are in the picture). With no choice text, the child picks a plain A–E letter. Without a picture, text and ≥ 2 choices are required as before. Correct answer is A–E (and must be one of the entered choices when choices are given).
- **Solution picture:** optional, shown with the solution in the bank and on the review page (after the test).
- Images: png / jpg / jpeg / gif / webp, saved to `uploads/` with a random file name; replaced or removed from the Edit modal; files deleted when the question is deleted.
- Add / update accept `multipart/form-data` (`payload` JSON + `question_image` / `solution_image` files, `remove_question_image` / `remove_solution_image` flags) as well as plain JSON.
- AI "Verify Answers" skips questions with a question picture (the AI can't see it).
- Tests list questions in original order: contest, year, problem number, then id (unchanged order for questions without tags).
- Bank card shows an origin badge (AI / Real) and a contest tag like `AMC 10A 2022 #5`. Tags are not shown to kids on the test page.

## Out of scope

Bulk upload, sharing questions between children, OCR of the pictures.
