# Task 014: CogAT-style / i-Ready-style Question Bank & Tests

**Status:** In progress — phases 1–3 built & verified locally (2026-09-27); phase 4 (seed import) blocked on O1
**Source requirements:** `family-brain/03_Kids-Education/kid-verbal-cogat-iready-requirements.md` (v1.0, 2026-09-27)
**Scope:** Local build + test only. No OCI deploy. Not wired into learning plans in v1.

## Decisions (confirmed)

| # | Decision |
|---|----------|
| D1 | Auth for external agent (Milo): API token stored in `site_config.api_token`, sent as `Authorization: Bearer <token>`. New endpoints never unauthenticated. |
| D2 | Paths namespaced: `/api/question-bank/...` and `/api/qb-tests/...` |
| D3 | Figure questions: inline SVG field (keeps `currentColor` theming) + optional `image_path` for photos |
| D4 | Two fully separate tracks: `cogat-style`, `iready-style`. Grades 4/5/6. Both kids. |
| D5 | Difficulty 1–5, set by question author |
| D6 | i-Ready math not in v1; section list is open-ended so it can be added later |
| D7 | Default test mix 50% new / 30% needs_work / 20% due |
| D8 | Answers recorded per question via `POST /api/qb-tests/{id}/answer` (first answer final) so the child gets immediate feedback without the test GET leaking answers; submit scores from recorded answers |
| D9 | Only the SHA-256 hash of the API token is stored (`site_config.qb_api_token_hash`, plus last-4 hint) |
| D10 | Routes stay in `app.py` per coding rules; pure logic lives in `qb_engine.py` (like `test_engine.py`) |

## Naming & compliance (hard rule)

- UI/docs always say **"CogAT-style practice"** / **"i-Ready-style practice"** and label questions as original practice questions.
- Footer disclaimer on every page of this feature: *"Original practice questions. Not affiliated with or endorsed by the publishers of CogAT® or i-Ready®."* (Don't name publishers; note the requirements doc says Pearson, but CogAT is published by Riverside Insights, so naming nobody avoids getting it wrong.)

## Data model (new tables, `database.py` `init_db()`)

```
qb_passage        id, track, grade, section, title, body, created_at
qb_question       id, track, grade, section, qtype ('text-choice'|'figure-image'|'passage-set'),
                  stem, stem_svg, options (JSON), correct_answer, explanation, image_path,
                  passage_id → qb_passage, passage_order, difficulty (1–5), tags (JSON),
                  created_by ('milo'|'parent'|'seed'), answer_source ('milo'|'parent'|'seed'),
                  source_ref (seed id e.g. 'g5-va-1', UNIQUE when not null),
                  status ('active'|'archived'), created_at, updated_at
qb_question_progress  child_id, question_id, correct_count, wrong_count,
                      last_tested, last_correct_at    UNIQUE(child_id, question_id)
qb_test           id, child_id, track, grade, section (nullable), title,
                  status ('pending'|'completed'), created_at
qb_test_question  test_id, question_id, position
qb_test_answer    test_id, question_id, choice, is_correct, answered_at   UNIQUE(test_id, question_id)
qb_test_submission test_id (UNIQUE), child_id, correct_count, total_count,
                   score, time_taken_seconds, submitted_at
qb_request_key    key (PK, "<type>:<Idempotency-Key>"), resource_type, resource_id, created_at
```

- `options`: JSON array of `{ "text": str|null, "svg": str|null }` (plain strings accepted on input); `correct_answer` stored as the 0-based option index string. Input accepts an index or letter A–F.
- SVG is sanitized on write: `<script>`, `on*` attributes, `<foreignObject>` and external `href`s are stripped.

## Auth

- New decorator `parent_or_token_required`: passes for a parent session OR a valid bearer token.
- Child session may only GET/submit **its own** qb-tests (`/child/<id>/...` pages + submit API).
- Settings page: "API token" section → Generate / Rotate button; full token shown once on generate, masked afterwards.

## Idempotency (flaky-server rule)

- `POST /api/question-bank/questions` and `POST /api/qb-tests` accept an optional `Idempotency-Key` header. A repeat key returns the **original** resource (200, same id) instead of creating a duplicate.
- `POST /api/qb-tests/{id}/submit` is idempotent by state: a second submit on a completed test returns the existing result and does not double-count progress.

## API

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/question-bank/questions` | parent/token | Create question (FR-1 fields). Returns `{id}` |
| GET | `/api/question-bank/questions/{id}` | parent/token | For verify-after-POST |
| PUT | `/api/question-bank/questions/{id}` | parent/token | Partial update |
| DELETE | `/api/question-bank/questions/{id}` | parent/token | Soft delete → `status=archived` (keeps history intact) |
| POST/DELETE | `/api/question-bank/questions/{id}/image` | parent/token | multipart field `image`, saved to `uploads/qb_{id}_{ts}_{name}` |
| POST | `/api/question-bank/passages` | parent/token | Create passage; sub-questions link via `passage_id` |
| GET/PUT/DELETE | `/api/question-bank/passages/{id}` | parent/token | GET includes sub-questions |
| GET | `/api/question-bank?track=&grade=&section=&qtype=&status=&child_id=&mastery=&page=` | parent/token | `mastery` filter needs `child_id` |
| GET | `/api/question-bank/sections?track=` | parent/token | Section list + counts per grade |
| GET | `/api/question-bank/export?track=` | parent/token | Full JSON backup (questions + passages) |
| POST | `/api/qb-tests` | parent/token | `{child_id, track, grade, section?, count, mastery_mix?}` → `{id, question_ids, shortfall}` |
| GET | `/api/qb-tests/{id}` | parent/token/owning child | Answers/explanations only for already-answered questions (child) |
| POST | `/api/qb-tests/{id}/answer` | owning child/parent | `{question_id, choice}` → `{is_correct, correct_answer, explanation}`; first answer final |
| POST | `/api/qb-tests/{id}/submit` | owning child/parent | `{time_taken_seconds}` → score; unanswered = wrong; idempotent |
| POST | `/api/question-bank/token` | parent session | Generate/rotate API token (returned once) |
| GET | `/api/question-bank/pool?child_id=&track=&grade=&section=` | parent/token | Mastery bucket counts for the builder |
| DELETE | `/api/qb-tests/{id}` | parent/token | |
| GET | `/api/children/{id}/qb-test-history?track=` | parent/token/owning child | |

## Mastery & test assembly (FR-5)

Per (child, question):
- **new**: no progress row, or correct + wrong = 0
- **needs_work**: wrong_count > correct_count
- **due**: not needs_work, and last_correct_at is null or more than 7 days ago
- **mastered**: everything else. Never put in a test.

Assembly for `count = N` with mix 50/30/20 (overridable via `mastery_mix`):
1. Target per bucket = round(N × pct). Random pick within each bucket; ties sorted by fewest `last_tested` first.
2. If a bucket is short, backfill from the other buckets in priority order new → needs_work → due.
3. If the whole pool is short, return what exists plus `shortfall: <n>` (no error).
4. **Passage sets are picked as a unit** (all sub-questions together, counted toward N). The unit's bucket is its weakest sub-question's bucket. A unit is skipped if it would push the total over N + 2.
5. Order: passage units stay contiguous, sub-questions kept in `passage_order`.

Progress is updated on submit: correct → `correct_count++`, `last_correct_at=now`; wrong → `wrong_count++`; always `last_tested=now`.

## UI (English, kid-friendly, styled like the existing artifact)

- **Parent dashboard:** new sidebar tab "CogAT-style / i-Ready-style" with links to:
  - `/parent/question-bank`: browse with filters (track, grade, section, qtype, mastery-for-child), inline SVG preview, add/edit modal (supports SVG paste and image upload), archive, and a passage editor
  - `/parent/qb-tests/new`: pick child, track, grade, optional section, count, mix; shows the available count per bucket before creating
- **Child dashboard:** "Practice tests" card listing pending qb-tests
- `/child/<id>/qb-test/<tid>`: one question per screen, click an option → immediate right/wrong + explanation → Next; passage shown alongside its sub-questions; progress bar; localStorage auto-save; submit at end
- `/child/<id>/qb-test/<tid>/review`: score + every question with the child's answer, the correct answer and the explanation
- `/child/<id>/qb-history`: list filtered by track, showing grade/section/score/date

## Seed import (FR-7, one-time)

- `scripts/seed_cogat_iready.py` reads `seeds/cogat_iready_seed.json` (a JSON conversion of the artifact's `questions.ts` + `grade5Questions.ts`, committed to the repo) and upserts by `source_ref`, so it's safe to re-run.
- Section keys: verbal-analogies, sentence-completion, verbal-classification, number-analogies, number-puzzles, number-series, figure-matrices, paper-folding, figure-classification (cogat-style); iready block "Words & Reading" → iready-style sections `vocabulary` and `reading-comprehension`.
- Expect 69 (G4) + 44 (G5) = 113 questions after import; the script prints per track/grade/section counts.

## Acceptance

1. Via token API: create a figure question with SVG + image, verify via GET, build a test that includes it.
2. A parent-sourced question stored with `answer_source=parent` has the given answer.
3. Assembly returns correct buckets; mastered is never included; shortfall reported.
4. Track/grade filters correct; disclaimer on every page; the word "official" appears nowhere.
5. Repeating a POST with the same Idempotency-Key does not duplicate.
6. Existing vocab/reading/math/writing/science flows unchanged (smoke test).

## Build phases

1. Schema + auth token + question/passage CRUD + image + export
2. Mastery + test assembly API
3. Parent bank/builder pages, child test/review/history pages, dashboard links
4. Seed import
5. Smoke test + context updates

## Progress

- [x] Phase 1: schema, token auth, question/passage CRUD, image upload, export
- [x] Phase 2: mastery buckets + assembly (`qb_engine.py`)
- [x] Phase 3: pages — `/parent/question-bank`, `/parent/qb-tests/new`, `/child/<id>/qb-test/<tid>` (+`/review`), `/child/<id>/qb-history`; parent dashboard tab "CogAT/i-Ready-style"; child dashboard "Practice Tests"; Settings token section
- [ ] Phase 4: seed import (blocked on O1)
- [x] Phase 5 (partial): API smoke test (30+ checks incl. auth, idempotency, mastery exclusion, shortfall, passage units) + browser check on a DB copy

## Open Items (blocking)

- **O1:** The seed files `questions.ts` / `grade5Questions.ts` aren't on this Mac (`~/workspace` doesn't exist). Need them copied into the repo (e.g. `seeds/`) so the option/answer/SVG format can be confirmed.
