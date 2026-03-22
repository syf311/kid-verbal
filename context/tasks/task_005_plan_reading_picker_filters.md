## Status: Done

## Objective

Enhance the reading assignment picker in the manage/create learning plan page with attempt-based filters and visibility info, matching the materials page experience.

## Current Behavior

- The "Add Reading Assignment" section in `manage_plan.html` shows a plain `<select>` dropdown listing materials by title and question count only
- No indication of whether the child has attempted the material before, how they scored, or when they last read it
- The API `/api/children/:child_id/reading-materials` returns only `id`, `title`, and `question_count`

## Desired Behavior

### 1. Attempt stats in the reading material list

Each material in the picker should display:
- **Attempt count** (e.g., "Tried 2x")
- **Last tried date** (e.g., "Last tried: 2026-03-15")
- **Most recent score** (e.g., "7/10 (70%)")
- **"New" badge** if never attempted

### 2. Filter buttons

Add filter buttons above the material picker (same style as materials page):
- **All** — show all materials with questions
- **New** — never attempted by this child
- **Needs Review** — last score < 80%
- **Worth Refreshing** — last attempted > 1 month ago

### 3. Visual treatment

- Use badge styling consistent with materials page (`attempt-badge` classes: `new`, `tried`, `needs-review`, `refresh`)
- Consider replacing the `<select>` dropdown with a scrollable list of cards/rows (like the word checklist) so badges and stats can be displayed inline

## Implementation Notes

- The materials page already computes attempt stats in the `/materials` route (lines ~1486-1517 in `app.py`). Reuse the same logic.
- Enhance the `/api/children/:child_id/reading-materials` API to include `times_tried`, `last_tried_at`, `last_correct`, `last_total` per material
- Filter logic runs client-side in JS (same pattern as materials page)
- The manage_plan template already has a scrollable list pattern (`word-list-scroll`) used for the word checklist — reuse that layout

## Acceptance Criteria

1. Reading material picker shows attempt count, last tried date, and most recent score for each material
2. Materials never attempted show a "New" badge
3. Filter buttons (All / New / Needs Review / Worth Refreshing) filter the list correctly
4. Selecting a material and clicking "Add Reading Assignment" still works as before
5. No changes to materials page or other functionality
