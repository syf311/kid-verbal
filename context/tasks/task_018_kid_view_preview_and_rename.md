# Task 018: Kid-View Preview for Parents, and Renaming Plans/Tests

**Status:** Done (batch rename pending: waiting for the old → new title table)

## Objective

1. A parent can switch on a "Kid view" preview to see exactly what the kid sees (task_017 hides the question source from kids in practice mode, but parents always see originals, which made it hard to check).
2. Plans and math bank tests can be renamed, so practice titles like "AMC8 2024 - Problems 13-15" can get neutral names. A batch rename of practice plans/tests follows once the old → new title table is provided.

## Decisions (2026-10-17)

| # | Decision |
|---|----------|
| D1 | Kid view = `?view=kid` on the math test page, its review page and the math question bank page, honoured for parents only. It shows what a kid would see: in practice mode the title-free pictures and no source fields/tags; in exam mode the originals (as a kid sees them). The bank page preview shows practice-mode pictures. |
| D2 | The preview is read-only on the test page: no answers saved, no timer, no submit. |
| D3 | `PUT /api/learning-plans/<id>` and `PUT /api/math-bank-tests/<id>`, parent only, body `{"title": "..."}`. Only the title changes; any other field is rejected (400). Empty title → 400, unknown id → 404. Works for exam and practice tests (keeping exam titles is a rule of the batch rename, not of the API). |
| D4 | Batch rename (practice plans/tests only, exam titles unchanged) waits for the old → new title table. |
