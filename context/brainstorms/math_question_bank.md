# Math Question Bank & AI Problem Generation

## The Vision

Build a math question bank (like the science question bank) where:
1. AI generates grade-appropriate problems (academic, olympiad, AMC 8/10 style)
2. Problems are stored with answers, solution steps, concept tags, and grade level
3. Parents can create tests from the bank (manually or AI-picked)
4. Per-child progress tracking per question (tries, mastery, last attempted)
5. Filter by concept tags, grade level, mastery when building tests

## Parallel with Science System

| Science (exists) | Math (to build) |
|------------------|-----------------|
| `science_question` | `math_question` |
| `science_question_progress` | `math_question_progress` |
| `science_study_session` | math study/practice session |
| `science_test` | math bank test |
| category (Life Science, etc.) | concept tags (Fractions, Geometry, etc.) |
| PDF import (Science Bowl) | AI generation + manual entry |

## AI Prompt Design

### What we ask AI to generate

For each request:
- X number of problems (e.g., 10)
- Style: academic / olympiad / AMC 8 / AMC 10 / mixed
- Grade level: child's grade or +1
- Format: always multiple choice (A-E)

### Prompt structure

```
Generate {count} {style} math problems for grade {grade_level}.

Requirements:
- Each problem should be challenging but solvable for a {grade_level} student
- Tag each problem with the math concepts it covers (e.g., Fractions, Geometry, Number Theory, Algebra, Combinatorics, Ratios, Percentages, etc.)
- For multiple choice: provide 5 choices (A-E)
- Provide a SEPARATE answer key with the correct answer AND step-by-step solution

Output format:

PROBLEMS
1. [problem text]
A. ...
B. ...
C. ...
D. ...
E. ...
Concepts: [comma-separated tags]

2. [problem text]
...

ANSWERS
1. Answer: B
Steps: [step-by-step solution]

2. Answer: D
Steps: [step-by-step solution]
```

### Dual-use design

The prompt should work for:
1. **Direct API integration** — app sends to OpenAI, parses response, stores in DB
2. **Copy/paste** — parent copies prompt to ChatGPT, copies response back into the app for parsing

## Database Schema

### `math_question`
```sql
CREATE TABLE IF NOT EXISTS math_question (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    answer_format TEXT NOT NULL DEFAULT 'multiple_choice',
    choices TEXT NOT NULL,              -- JSON: {"A": "...", "B": "...", ...}
    correct_answer TEXT NOT NULL,       -- "B" or "42" etc.
    solution_steps TEXT,                -- step-by-step explanation
    image_path TEXT,                    -- optional diagram/figure image
    concepts TEXT,                      -- JSON array: ["Fractions", "Ratios"]
    grade_level TEXT,                   -- "4th grade", "AMC 8", etc.
    difficulty INTEGER DEFAULT 3,        -- 1-5 scale (1=easiest, 5=hardest for grade)
    source TEXT,                        -- "AI generated", "AMC 8 2023", "manual"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (child_id) REFERENCES child(id) ON DELETE CASCADE
);
```

### `math_question_progress`
```sql
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

## Math Concept Tags (Taxonomy)

Suggested tag set for elementary/middle school:

**Arithmetic**: Addition, Subtraction, Multiplication, Division, Order of Operations
**Number Theory**: Factors, Multiples, Primes, Divisibility, GCD/LCM
**Fractions & Decimals**: Fractions, Decimals, Percentages, Ratios, Proportions
**Algebra**: Equations, Inequalities, Patterns, Variables, Functions
**Geometry**: Angles, Area, Perimeter, Volume, Triangles, Circles, Coordinate Geometry
**Measurement**: Units, Conversion, Time, Money
**Data & Statistics**: Mean, Median, Mode, Probability, Graphs
**Combinatorics**: Counting, Permutations, Combinations
**Logic & Problem Solving**: Word Problems, Logic Puzzles, Estimation

## Features & UX

### Phase 1: Question Bank + AI Generation
- Parent page to view/manage math question bank (like science question bank)
- "Generate by AI" button — choose count, style, grade level
- Also support pasting AI output for manual import
- Each question shows: text, answer, concepts, difficulty, mastery badge
- Search, filter by concept tag, filter by mastery status

### Phase 2: Test Creation from Bank
- Select questions from bank → create a math bank test
- AI-assisted: "Create a test with 10 questions focusing on Fractions and Geometry"
- Auto-graded (MC) or parent-graded (open-ended)
- Results update `math_question_progress`

### Phase 3: Study Mode
- Flashcard-style practice from the bank
- Show problem → child answers → reveal solution steps
- Spaced repetition based on mastery

### Future: Integration with AI Learning Plan Generator
- AI plan generator (brainstorm: ai_learning_plan_generator.md) can pick from the math bank
- Solves "Option M2" from that brainstorm — AI has text-based math content to assign

## How This Coexists with Existing PDF Math Tests

- Existing `math_test` (PDF-based) stays unchanged — it's good for scanned worksheets, competitions
- New `math_question` bank is for text-based problems (AI-generated, typed)
- Both contribute to the child's math practice
- In learning plans, parent can add either type
- Future: could even parse PDF test results to identify weak concepts and generate targeted practice from the bank

## Decisions Made

1. **Per-child** — questions are per-child since kids are at different grade levels
2. **Multiple choice only** — no open-ended for now. Simpler, auto-gradable
3. **Coexists with PDF tests** — PDF tests serve real past competitions (formal practice), bank is for AI-generated concept practice
4. Concept tags: free-form (AI suggests, parent can edit)
5. **AI estimates difficulty on a 1-5 scale** (1=easiest, 5=hardest for that grade level). Stored as integer, filterable in the bank.
6. **Start empty** — no pre-populated problems
7. **Support diagrams** — optional `image_path` field on questions. AI-generated questions are text-only (AI describes geometry in words). Parent can attach images when manually adding or importing problems that need diagrams.
8. **A-E choices** — 5 choices to match AMC format. A-D also fine (flexible)
