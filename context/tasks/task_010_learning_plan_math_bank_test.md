## Status: Done

## Objective

Add a "+ Math Practice" option in the learning plan create/manage page that lets parents create a math bank test from the question bank, with filters for difficulty, concepts, and mastery status.

## Behavior

In the manage/create learning plan page (alongside existing + Study Session, + Reading Assignment, + Math Test, etc.):
- New "+ Math Practice" button opens a section similar to the science test/study builders
- Parent can filter questions by:
  - Concept tags
  - Difficulty level (1-5)
  - Mastery status (New / Needs Work / Due / Good / Mastered)
- Parent selects questions via checkboxes (Select All / Deselect All)
- Sets a test title and optional timer (none/stopwatch/countdown)
- Creates a `math_bank_test` linked to the learning plan

## Implementation

### 1. Frontend (manage_plan.html)

- Add "+ Math Practice" button to the add-toggle row
- New `section-math-practice` collapsible section with:
  - Title input
  - Timer mode / time limit controls
  - Concept filter bar (populated from API)
  - Difficulty filter (All / 1 / 2 / 3 / 4 / 5)
  - Mastery filter bar (New / Needs Work / Due / Good / Mastered)
  - Scrollable question checklist with Select All / Deselect All
  - Each question shows: text (truncated), concept tags, difficulty badge, mastery badge
  - "Add Math Practice" button
- Loads questions via existing `GET /api/children/:child_id/math-questions?page=1&per_page=200` with filter params

### 2. Backend API

New endpoint:
- `POST /api/learning-plans/:plan_id/items/math-bank-test` — creates a `math_bank_test` with selected question IDs, links it to the plan as a `learning_plan_item` with type `math_bank_test`

### 3. Learning plan item rendering

Update `view_plan.html` and `manage_plan.html` to handle `math_bank_test` item type:
- Show title, question count, score if completed
- Link to take test (`/child/:id/math-bank-test/:test_id`) or review (`/child/:id/math-bank-test/:test_id/review`)

### 4. Plan completion detection

Update `check_plan_completion` to include `math_bank_test` items.

## Acceptance Criteria

1. "+ Math Practice" button appears in learning plan management
2. Questions can be filtered by concept, difficulty (1-5), and mastery status
3. Parent can select questions and create a math bank test in the plan
4. Math bank test appears in the plan items list with correct status/score
5. Child can take and review the test from the plan view
6. Plan completion detection includes math bank tests
