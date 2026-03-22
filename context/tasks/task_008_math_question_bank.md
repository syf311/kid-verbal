## Status: Done

## Objective

Build a math question bank with AI generation, manual entry, concept tagging, and per-question progress tracking. Phase 1 of the math question bank feature (see brainstorms/math_question_bank.md).

## Scope: Phase 1 — Question Bank + AI Generation

### 1. Database

New tables:

```sql
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
    difficulty INTEGER DEFAULT 3,        -- 1 (easiest) to 5 (hardest) for grade level
    source TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
```

- `choices`: JSON object `{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}`
- `concepts`: JSON array `["Fractions", "Ratios"]`
- `source`: "AI generated", "AMC 8 2023", "manual", etc.

### 2. Math Question Bank page (parent view)

New page accessible from parent dashboard Math tab. Similar to science question bank:

- List of questions with search, inline edit
- Each question shows: question text (truncated), concept tags, grade level, difficulty (1-5), mastery badge (per-child)
- Filter by: concept tag, difficulty level (1-5), mastery status (new/needs work/due/good/mastered)
- Pagination (like science)
- "Add Question" — manual entry form with: question text, choices (A-E), correct answer, solution steps, concepts (comma-separated), grade level, difficulty, optional image upload
- Delete question

### 3. AI Generation

"Generate by AI" button on the question bank page:

**Input controls:**
- Number of questions (default 10)
- Style dropdown: Academic / Olympiad / AMC 8 / AMC 10 / Mixed
- Grade level (default to child's grade, option for +1)
- Difficulty: Mixed (balanced coverage of 1-5) / or focused level (1, 2, 3, 4, or 5)

**AI prompt** (sent to OpenAI or copyable for ChatGPT):
```
Generate {count} {style} multiple choice math problems for {grade_level} level.

Requirements:
- Each problem should be appropriately challenging for {grade_level}
- Each problem has 5 choices labeled A through E
- Tag each problem with math concepts it covers (e.g., Fractions, Geometry, Number Theory, Algebra, Combinatorics, Ratios, Percentages, Arithmetic, Measurement, Probability, etc.)
- Rate each problem's difficulty from 1 to 5 (1=easiest, 5=hardest) relative to the grade level
- Correct answers MUST be randomized across A-E. No letter should appear more than 3 times.

Output format:

PROBLEMS
1. [problem text]
A. [choice]
B. [choice]
C. [choice]
D. [choice]
E. [choice]
Concepts: [comma-separated tags]
Difficulty: [1-5]

ANSWERS
1. Answer: [letter]
Steps: [step-by-step solution]

2. Answer: [letter]
Steps: [step-by-step solution]
```

**Dual-use design:**
- "Generate" button sends directly to OpenAI API and parses response
- "Copy Prompt" button lets parent paste into ChatGPT manually
- "Paste AI Response" section shows the prompt text (so parent can copy it to ChatGPT) plus a textarea for pasting the response back
- Parser extracts questions, choices, answers, steps, concepts, difficulty
- **Duplicate detection**: before importing, check if a question with similar text already exists in the child's bank. Skip duplicates and report how many were skipped in the response (e.g., "Imported 8 questions, 2 skipped as duplicates").

### 4. API Endpoints

- `GET /api/children/<child_id>/math-questions` — list with filters (concept, difficulty, mastery status), pagination
- `POST /api/children/<child_id>/math-questions` — add single question manually
- `PUT /api/math-questions/<id>` — edit question
- `DELETE /api/math-questions/<id>` — delete question
- `POST /api/children/<child_id>/math-questions/generate-ai` — AI generation
- `POST /api/children/<child_id>/math-questions/import-ai` — parse pasted AI response

### 5. Image support

- Optional image upload when adding/editing a question
- Stored in `uploads/` with `image_path` on the question
- Displayed inline with the question text
- AI-generated questions are text-only; images are for manually added problems

## Out of Scope (Phase 2+)

- Creating tests from the bank (task_009)
- Study/flashcard mode
- Integration with learning plans
- Integration with AI learning plan generator

## Acceptance Criteria

1. Math question bank page shows questions with concept tags, difficulty, mastery badges
2. Parent can manually add questions with choices, answer, solution steps, concepts, image
3. "Generate by AI" creates questions via OpenAI API and stores them
4. "Copy Prompt" / "Paste AI Response" workflow works for ChatGPT users
5. Filter by concept tag, difficulty, mastery status works
6. Search works across question text
7. Inline edit and delete work
8. Pagination works for large question sets
