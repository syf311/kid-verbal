# Task 013: Age-Based RSS Feeds — QA Report

## Date: 2026-04-05

## Code Review

### Changes reviewed:
- `app.py`: GRADE_TO_AGE mapping, RSS_FEEDS with age_min/age_max, browse_articles() filtering by child age, per-child imported detection, response format changed to include feed_names
- `templates/materials.html`: loadArticles() passes child_id, dynamic source dropdown population, hardcoded source options removed

### Logic Review:
- **Grade parsing**: `grade_level.lower().strip().replace(" grade", "")` correctly converts "4th grade" -> "4th" and "8th grade" -> "8th" to match GRADE_TO_AGE keys
- **Age filtering**: `f["age_min"] <= child_age <= f["age_max"]` correctly inclusive on both ends
- **Fallback**: If child_id is invalid, grade_level is null, or grade doesn't map, defaults to all feeds (correct)
- **Per-child import detection**: SQL filters by child_id when provided, global otherwise
- **Response format**: Changed from `jsonify(all_articles)` to `jsonify({"articles": all_articles, "feed_names": feed_names})` — only caller in materials.html is updated accordingly
- **Source filter**: Filters against `available_feeds` (already age-filtered), not global `RSS_FEEDS` — correct
- **Feed replacement**: NASA Climate Kids (returns HTML, not RSS), Wonderopolis (404), NIH News in Health (404) were replaced with working alternatives (Mongabay Kids, Cool Kid Facts, ScienceDaily Health)

### Coding Rules Compliance:
- Raw SQL used (no ORM) ✓
- Inline CSS/JS in template ✓
- `conn = get_db()` / `conn.close()` pattern ✓
- camelCase in JS, snake_case in Python ✓
- `fetch()` for API calls ✓
- No authentication decorator on browse_articles — pre-existing, not a regression

## API & Functional Testing

### Test 1: Lang (child_id=4, grade "4th grade" -> age 10)
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/api/materials/browse?child_id=4"
```
**Result**: PASS
- feed_names: ['Science News Explores', 'Time for Kids', 'Curious Kids', 'Mongabay Kids', 'Cool Kid Facts']
- 65 articles returned, all from age-appropriate sources
- No older-reader feeds (Ars Technica, IEEE Spectrum, etc.) present

### Test 2: Qian (child_id=11, grade "8th grade" -> age 14)
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/api/materials/browse?child_id=11"
```
**Result**: PASS
- feed_names: ['Science News Explores', 'NYT Education', 'Ars Technica', 'The Verge', 'IEEE Spectrum', 'ScienceDaily Health', 'Live Science', 'Phys.org', 'NPR Business']
- 125 articles returned, all from age-appropriate sources
- No younger-reader feeds (Time for Kids, Cool Kid Facts, etc.) present
- Science News Explores correctly appears for both children (age 9-15)

### Test 3: No child selected (all feeds)
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/api/materials/browse"
```
**Result**: PASS
- feed_names: all 13 feeds
- 175 articles returned from all sources

### Test 4: Source filter with child_id
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/api/materials/browse?child_id=4&source=Time%20for%20Kids"
```
**Result**: PASS
- feed_names still shows all 5 age-appropriate feeds (for dropdown population)
- Articles filtered to only "Time for Kids" (15 articles)

### Test 5: Invalid child_id
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/api/materials/browse?child_id=999"
```
**Result**: PASS
- Falls back to all 13 feeds (graceful degradation)

### Test 6: All RSS feed URLs return valid data
Each of the 13 feeds tested individually with HTTP requests:
- All returned HTTP 200
- All returned valid XML/RSS/Atom content
- All produced parseable articles via feedparser
**Result**: PASS

### Test 7: Frontend elements
```
curl -b /tmp/qa_cookies.txt "http://localhost:5001/materials"
```
- source-filter dropdown exists ✓
- Old hardcoded source options removed ✓
- child-filter dropdown exists ✓
- child_id referenced in JS for API calls ✓
- loadArticles called on DOMContentLoaded ✓
- Source filter change triggers loadArticles ✓
- Child filter change reloads page ✓
**Result**: PASS

### Test 8: Import functionality (regression check)
- Import endpoint (`/api/materials/import-article`) accepts child_id in request body
- Frontend `importArticle()` function reads child-filter value and includes it
- Materials page loads with HTTP 200
**Result**: PASS

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Lang sees age 9-10 feeds | PASS | API returns 5 feeds: Science News Explores, Time for Kids, Curious Kids, Mongabay Kids, Cool Kid Facts. (Mongabay Kids and Cool Kid Facts replace NASA Climate Kids and Wonderopolis which were broken — 404/not-RSS) |
| 2 | Qian sees age 13-15 feeds | PASS | API returns 9 feeds: Science News Explores, NYT Education, Ars Technica, The Verge, IEEE Spectrum, ScienceDaily Health, Live Science, Phys.org, NPR Business. (ScienceDaily Health replaces NIH News in Health which returned 404) |
| 3 | No child = all feeds | PASS | API returns all 13 feeds |
| 4 | Source dropdown dynamic per child | PASS | feed_names in response matches available feeds; JS rebuilds dropdown options |
| 5 | Per-child imported badge | PASS | SQL filters by child_id; same article can be imported for each child independently |
| 6 | AI questions age-appropriate per child | N/A | Pre-existing behavior — AI question generation already uses child's grade_level. Not modified by this task. |
| 7 | All RSS feed URLs valid | PASS | All 13 feeds return HTTP 200 with valid content |
| 8 | No regressions | PASS | Materials page loads, existing APIs unaffected, import endpoint unchanged |

## Verdict: SIGNOFF

All acceptance criteria are met. The implementation correctly filters RSS feeds by child age, provides per-child import detection, dynamically populates the source dropdown, and handles edge cases gracefully. Feed substitutions for broken URLs (NASA Climate Kids, Wonderopolis, NIH News in Health) are justified and verified. Code follows project conventions.
