## Status: Done

## Objective

Extract Power Words from Science News Explores articles during RSS import, store them on the reading material, and let parents selectively add them to a child's vocabulary.

## Background

Science News Explores articles include a "Power Words" section at the bottom (`div.article-footer__power-words`) with curated, grade-appropriate word-definition pairs formatted as `<strong>word</strong>: definition`. These are valuable vocabulary-building resources that should integrate with the existing vocab system.

## Design: Option C (Extract + Store on Material + Parent Push to Vocab)

Power words are extracted at import time and stored linked to the reading material. Parents can review and selectively add them to a child's word list. Once added, all existing vocab features (flashcards, tests, mastery tracking, learning plans) work automatically.

## Implementation

### 1. Database

New table `material_power_word`:
```sql
CREATE TABLE IF NOT EXISTS material_power_word (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    FOREIGN KEY (material_id) REFERENCES reading_material(id) ON DELETE CASCADE
);
```

### 2. Extraction (backend)

In the `/api/materials/import-article` route:
- After fetching the HTML with BeautifulSoup, look for the Power Words section using selector `div.article-footer__power-words` or fallback to an `<h3>` containing "Power Words"
- Parse each `<strong>word</strong>: definition` pair
- Insert into `material_power_word` table linked to the newly created material
- Return `power_word_count` in the API response

Only Science News Explores format is supported for now. If no Power Words section is found, skip silently (no error).

### 3. Materials page (parent view)

- Show a "Power Words (N)" badge on material cards that have power words (next to question count)
- Clicking the badge (or a dedicated button) opens/toggles a power words panel for that material, similar to the questions panel

### 4. Power Words panel (parent view on materials page)

When expanded, the panel shows:
- List of power words with checkboxes, each showing word and definition
- "Select All" / "Deselect All" buttons
- Child selector dropdown (default to currently filtered child)
- "Add to Vocabulary" button
- Words already in the child's vocab should be visually marked (e.g., greyed out with "Already added" label) and excluded from selection
- After adding, refresh the panel to update the "already added" state

### 5. API endpoints

- `GET /api/materials/<id>/power-words` — returns list of power words for a material
- `GET /api/materials/<id>/power-words?child_id=<id>` — same, but includes `already_added: true/false` per word by checking the child's `word` table
- `POST /api/materials/<id>/power-words/add-to-vocab` — accepts `{ child_id, word_ids: [...] }`, bulk-inserts selected power words into the child's `word` table (skip duplicates)

### 6. Word source tracking

Add `source_material_id` column to the `word` table (nullable INTEGER, FK to `reading_material`).
When adding power words to vocab, set this field to the material ID.
In the word list UI, words with a source material show the material title as a clickable link to the source URL.

### 7. Learning plan integration

When a reading assignment is added to a learning plan:
- Check if the material has power words that exist in the child's word bank
- If yes, auto-create a vocabulary study session in the same plan containing those words
- Title the study session something like "Power Words: [material title]"
- This happens automatically — no extra prompt needed

### Out of Scope

- No child-side display of power words during reading (avoid distracting from reading flow)
- No auto-add — parent always manually selects
- No support for other article sources (only Science News Explores format)

## Acceptance Criteria

1. Importing a Science News Explores article via RSS extracts and stores power words
2. Materials page shows power word count badge on materials that have them
3. Parent can expand a power words panel, see all words with definitions
4. Parent can select individual words or "Select All" and add them to a child's vocabulary
5. Words already in the child's vocab are visually indicated and not re-added
6. Added words appear in the child's vocabulary and work with flashcards, tests, etc.
7. Articles without a Power Words section import normally with no errors
8. Adding a reading assignment to a learning plan auto-creates a study session with power words that are in the child's word bank
