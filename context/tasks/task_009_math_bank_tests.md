## Status: Done

## Objective

Create tests from the math question bank with auto-grading and progress tracking. Phase 2 of the math question bank feature.

## Depends On

- task_008 (Math Question Bank)

## Scope

### 1. Test Creation from Bank

On the math question bank page:
- "Create Test" button opens a test builder
- Parent selects questions manually (checkboxes, like science test builder)
- Filter by concept tags, difficulty (1-5), mastery when selecting
- Set test title, timer mode (none/stopwatch/countdown)
- "AI Pick" option: "Create a test with N questions focusing on [concepts]" — AI selects from the bank

### 2. Test Taking (child view)

- Similar to science test: show question, choices, child picks answer
- Timer if set
- Submit → auto-grade against correct answers
- Show results: correct/wrong per question, score

### 3. Review (parent + child)

- Review page shows each question, child's answer, correct answer, solution steps
- Parent can see which concepts were weak

### 4. Progress Tracking

- After test completion, update `math_question_progress` for each question
- Increment correct_count or wrong_count, update streak, difficulty_level, last_tested
- Mastery status derivable: new, needs_work, due, good, mastered (same logic as science)

### 5. Learning Plan Integration

- "Add Math Bank Test" option in learning plan management
- Works alongside existing PDF-based "Add Math Test"

## Out of Scope (Phase 3+)

- Flashcard/study mode for math
- AI learning plan generator integration
- Retry wrong questions only

## Acceptance Criteria

1. Parent can create a test by selecting questions from the bank
2. AI can auto-select questions by concept and count
3. Child can take the test with auto-grading
4. Review shows questions, answers, and solution steps
5. Progress tracking updates after each test
6. Tests can be added to learning plans
