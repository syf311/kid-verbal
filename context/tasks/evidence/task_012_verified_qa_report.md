# QA Report: Task 012 — Verified Tracking (AC 18-24)

## Date: 2026-04-04

---

## 1. Code Review

### AC 18: ALTER TABLE migration for `verified` column
- **Location**: `database.py` lines 594-599
- **Finding**: Uses the standard try/except `ALTER TABLE` pattern, matching all other migrations in the file. Column is `INTEGER DEFAULT 0`.
- **Verdict**: PASS

### AC 19: AI verify marks CORRECT questions as verified=1
- **Location**: `app.py` lines 4521-4522 and 4544-4545
- **Finding**: When parsing AI response, if entry does NOT contain "WRONG", `batch[num]["id"]` is appended to `correct_ids`. Also, false positives (marked WRONG but suggested answer matches current) are added to `correct_ids`. At end (lines 4562-4568), all `correct_ids` are bulk-updated to `verified=1`.
- **Batch indexing check**: `num = int(num_match.group(1)) - 1` correctly converts 1-indexed AI output to 0-indexed `batch` array. `batch[num]["id"]` retrieves the correct question ID.
- **Verdict**: PASS

### AC 20: Bulk fix marks fixed questions as verified=1
- **Location**: Bulk fix calls `PUT /api/math-questions/<id>` which sets `verified=1` (line 4349)
- **Finding**: Correct. The PUT endpoint unconditionally sets `verified=1` on every update.
- **Verdict**: PASS

### AC 21: Manual edit marks question as verified=1
- **Location**: `app.py` lines 4346-4350, PUT endpoint
- **Finding**: Same PUT endpoint is used for manual edit. `verified = 1` is included in the UPDATE SQL.
- **Verdict**: PASS

### AC 22: Verify endpoint skips verified questions
- **Location**: `app.py` lines 4451-4457
- **Finding**: Both query paths include `AND verified = 0`:
  - With IDs: `WHERE child_id = ? AND verified = 0 AND id IN (...)`
  - Without IDs: `WHERE child_id = ? AND verified = 0`
- **Verdict**: PASS

### AC 23: Verified badge on question cards
- **Location**: `templates/math_questions.html` line 535
- **Finding**: `${q.verified ? '<span class="verified-badge">&#10003; Verified</span>' : ''}` renders a green badge with checkmark. CSS class `.verified-badge` defined at lines 42-45.
- **Verdict**: PASS

### AC 24: Verify button shows unverified count
- **Location**: `templates/math_questions.html` lines 455-457
- **Finding**: After `loadQuestions()`, button text is set to `Verify Answers (N unverified)` when N > 0, or plain `Verify Answers` when 0. Button is refreshed in the `finally` block of `verifyAnswers()` and after `bulkFixSelected()` via `loadQuestions()`.
- **Verdict**: PASS

### Coding conventions check
- Raw SQL: PASS (no ORM)
- Inline CSS/JS: PASS (all in template)
- Decorators: `@parent_required` used on all relevant endpoints: PASS
- `conn = get_db()` / `conn.close()` pattern: PASS (connection closed on all paths including error paths)

### Minor note
- `flagged_in_batch` set is populated but never read. This is dead code but harmless — not a blocking issue.

---

## 2. API Testing

### Test 1: GET returns unverified_count
```
curl -b cookies "http://localhost:5001/api/children/4/math-questions?page=1&per_page=5"
```
- **Result**: Response includes `"unverified_count": 20` (initially all 20 unverified)
- **Verdict**: PASS

### Test 2: PUT marks question verified=1
```
curl -X PUT -H "Content-Type: application/json" -d '{"correct_answer":"A"}' "http://localhost:5001/api/math-questions/1"
```
- **Before**: question 1 `verified=0`, `unverified_count=20`
- **After**: question 1 `verified=1`, `unverified_count=19`
- **Verdict**: PASS

### Test 3: Verify endpoint skips already-verified questions
```
curl -X POST -H "Content-Type: application/json" -d '{"question_ids":[1]}' ".../verify"
```
- **Result**: `{"flagged": [], "total_checked": 0}` — question 1 (verified=1) was skipped
- **Verdict**: PASS

### Test 4: Verify processes unverified questions and marks correct ones
```
curl -X POST -H "Content-Type: application/json" -d '{"question_ids":[2]}' ".../verify"
```
- **Result**: `total_checked=1`, `flagged=0` — AI confirmed correct
- **After**: question 2 `verified=1`, `unverified_count=18`
- **Verdict**: PASS

### Test 5: Full verify run only processes unverified
```
curl -X POST -H "Content-Type: application/json" -d '{"question_ids":[]}' ".../verify"
```
- **Result**: `total_checked=18` (not 20 — skipped 2 already verified), `flagged=2`
- **After**: `unverified_count=2` (16 confirmed correct + 2 flagged remain unverified)
- **Verdict**: PASS

### Test 6: Second verify run processes fewer questions
```
curl -X POST -H "Content-Type: application/json" -d '{"question_ids":[]}' ".../verify"
```
- **Result**: `total_checked=2` (only the 2 remaining unverified)
- **Verdict**: PASS — semantic validation confirms verified questions are consistently skipped

### Test 7: Bulk fix via PUT marks question verified
```
curl -X PUT -H "Content-Type: application/json" -d '{"correct_answer":"A"}' ".../math-questions/7"
```
- **After**: question 7 `verified=1`, `unverified_count=1`
- **Verdict**: PASS

---

## 3. UI Testing

Browser-based Playwright testing was not available in this session (MCP tools not connected). However, the frontend logic was verified through thorough code review:

- **Verified badge**: Template renders `<span class="verified-badge">&#10003; Verified</span>` conditionally on `q.verified` — confirmed via code and the `verified` field being present in API responses
- **Button text**: JavaScript in `loadQuestions()` updates `verify-btn` text with unverified count from API response — logic verified correct
- **Post-verify refresh**: `loadQuestions()` called in `finally` block of `verifyAnswers()` and after `bulkFixSelected()` — ensures button text and badges update

---

## 4. Summary

| AC | Description | Verdict |
|----|-------------|---------|
| 18 | ALTER TABLE migration for `verified` column | PASS |
| 19 | AI verify marks CORRECT questions as verified=1 | PASS |
| 20 | Bulk fix marks fixed questions as verified=1 | PASS |
| 21 | Manual edit marks question as verified=1 | PASS |
| 22 | Verify endpoint skips verified questions | PASS |
| 23 | Verified badge on question cards | PASS |
| 24 | Verify button shows unverified count | PASS |

---

## Verdict: SIGNOFF

All 7 acceptance criteria (AC 18-24) are met. The implementation correctly:
- Adds the `verified` column via the standard migration pattern
- Marks questions verified=1 through all three paths (AI correct, bulk fix PUT, manual edit PUT)
- Skips already-verified questions in the verify endpoint (both query paths)
- Returns `unverified_count` in the GET response
- Renders the verified badge and dynamic button text in the frontend
- Follows all coding conventions (raw SQL, inline CSS/JS, proper decorators, conn.close() on all paths)

Minor note: `flagged_in_batch` is dead code (populated but unused) — non-blocking, can be cleaned up in a future pass.
