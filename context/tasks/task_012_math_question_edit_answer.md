## Status: Pending

## Objective

Enhance the Math Question Bank edit functionality to allow editing answers (correct choice + choice text) and add a batch verify feature that compares solution steps with selected answers to flag inconsistencies.

## Problem

AI-generated math questions sometimes have:
1. Wrong correct answer selected (e.g., solution says "24" but correct_answer is "B" which maps to "18")
2. All choices are wrong (the correct value doesn't appear in any choice)

The current "Edit" button only edits the question text via a simple `prompt()` dialog. There's no way to edit choices or the correct answer from the UI.

## Scope

### 1. Full Edit Modal (replace current prompt-based edit)

Replace the `editQuestion()` function (currently at `math_questions.html:434`) which only edits question text, with a proper modal that allows editing all fields:

- **Question text** (textarea)
- **Choices A–E** (text inputs, pre-filled with current values)
- **Correct answer** (radio buttons A–E, pre-selected to current)
- **Solution steps** (textarea)
- **Concepts** (text input, comma-separated)
- **Difficulty** (dropdown 1–5)

The modal should:
- Pre-populate all fields from the existing question data
- Highlight the currently correct answer
- Save via `PUT /api/math-questions/<id>` (endpoint already exists and supports all fields)
- Show success/error feedback
- Refresh the question list after save

### 2. Batch Verify Feature

Add a "Verify Answers" button on the question bank page that uses AI to check answer consistency:

**How it works:**
- Sends selected questions (or all visible questions) to OpenAI API
- For each question, AI checks: does the solution/correct choice match the actual answer?
- Returns a list of flagged questions with discrepancies

**UI:**
- "Verify Answers" button in the toolbar area (near search/filters)
- When clicked, shows a progress indicator
- Results displayed as a list of flagged questions with:
  - Question text (truncated)
  - Current correct answer and what the solution suggests
  - "Fix" button that opens the edit modal pre-populated

**API endpoint:**
- `POST /api/children/<child_id>/math-questions/verify` — accepts list of question IDs (or empty for all), returns flagged questions

**AI prompt structure:**
```
For each math problem below, verify if the marked correct answer is actually correct.
Check the solution steps and the choices. Report any discrepancies.

Question 1: [text]
Choices: A. [a] B. [b] C. [c] D. [d] E. [e]
Marked Answer: [letter]
Solution: [steps]

Output format:
1. Status: CORRECT | WRONG
   Issue: [if wrong, explain what the correct answer should be]
   Suggested Answer: [letter or "NONE" if no choice matches]
```

## API Changes

### Existing (no changes needed)
- `PUT /api/math-questions/<id>` — already supports all fields

### New
- `POST /api/children/<child_id>/math-questions/verify` — batch verify answers via AI

## UI Changes

### math_questions.html
1. Replace `editQuestion()` prompt dialog with a full edit modal
2. Add "Verify Answers" button to the toolbar
3. Add verify results display with per-question "Fix" buttons

## Acceptance Criteria

1. Clicking "Edit" on a question opens a modal with all fields pre-populated
2. Parent can change correct answer (A–E radio), choice text, solution steps, concepts, difficulty
3. Save updates the question and refreshes the list
4. "Verify Answers" button sends questions to AI for consistency checking
5. Flagged questions are displayed with discrepancy details
6. "Fix" button on flagged questions opens the edit modal for that question
7. Works for both AI-generated and manually-added questions
