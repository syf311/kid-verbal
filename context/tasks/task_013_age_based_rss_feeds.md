## Status: Done

## Objective

Make the Browse Articles RSS feed system age-appropriate per child, so each child sees feeds suited to their reading level. Add new free feeds covering science, technology, engineering, health, and business.

## Problem

Currently `RSS_FEEDS` is a static global list — all 4 feeds show regardless of which child is selected. "Time for Kids" and "Curious Kids" are too young for Qian (12, reads at 13-15 level), while feeds like Ars Technica or IEEE Spectrum would be too advanced for Lang (9, reads at 9-10 level). Also, the "imported" badge is global — if Lang imports an article, it shows as "Imported" for Qian too, preventing per-child import of the same article.

## Context

- **Lang**: age 9, reading level 9-10 (grade 3-4)
- **Qian**: age 12, reading level 13-15 (grade 8-9)
- Each child has a `grade_level` field in the `child` table
- AI question generation already adapts to child's grade level, so importing the same article for both kids will produce age-appropriate questions automatically

## Scope

### 1. Add `age_min` / `age_max` to RSS_FEEDS

Update `RSS_FEEDS` in `app.py` (~line 32) to include age range per feed:

```python
RSS_FEEDS = [
    # Lang (age 9-10)
    {"name": "Science News Explores", "url": "https://www.snexplores.org/feed", "category": "Science", "age_min": 9, "age_max": 15},
    {"name": "Time for Kids", "url": "https://www.timeforkids.com/feed/", "category": "News", "age_min": 8, "age_max": 11},
    {"name": "Curious Kids", "url": "https://theconversation.com/us/topics/curious-kids-us-74795/articles.atom", "category": "Science", "age_min": 8, "age_max": 12},
    {"name": "NASA Climate Kids", "url": "https://climatekids.nasa.gov/rss/feed.xml", "category": "Science", "age_min": 8, "age_max": 12},
    {"name": "Wonderopolis", "url": "https://wonderopolis.org/feed", "category": "General", "age_min": 8, "age_max": 12},
    # Qian (age 13-15)
    {"name": "NYT Education", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Education.xml", "category": "News", "age_min": 12, "age_max": 18},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index", "category": "Technology", "age_min": 13, "age_max": 18},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml", "category": "Technology", "age_min": 13, "age_max": 18},
    {"name": "IEEE Spectrum", "url": "https://spectrum.ieee.org/feeds/feed.rss", "category": "Engineering", "age_min": 13, "age_max": 18},
    {"name": "NIH News in Health", "url": "https://newsinhealth.nih.gov/rss/NewsinHealth.xml", "category": "Health", "age_min": 12, "age_max": 18},
    {"name": "Live Science", "url": "https://www.livescience.com/feeds/all", "category": "Science", "age_min": 12, "age_max": 18},
    {"name": "Phys.org", "url": "https://phys.org/rss-feed/", "category": "Science", "age_min": 13, "age_max": 18},
    {"name": "NPR Business", "url": "https://feeds.npr.org/1006/rss.xml", "category": "Business", "age_min": 13, "age_max": 18},
]
```

**Important**: Verify each RSS feed URL actually returns valid feed data before finalizing. Replace any broken URLs with working alternatives.

### 2. Filter feeds by child's age in browse API

Update `browse_articles()` (~line 1782):

- Accept optional `child_id` query param
- Look up child's `grade_level` from DB, convert to approximate age (e.g., "3rd" → 9, "8th" → 14). Use a simple mapping dict.
- Filter `RSS_FEEDS` to only those where `age_min <= child_age <= age_max`
- If no child selected, show all feeds (parent browsing mode)

### 3. Fix per-child "imported" detection

Update the "imported" check in `browse_articles()` (~line 1833-1840):

**Current** (global):
```python
existing_titles = set(
    row[0] for row in conn.execute("SELECT title FROM reading_material").fetchall()
)
```

**New** (per-child):
```python
if child_id:
    existing_titles = set(
        row[0] for row in conn.execute(
            "SELECT title FROM reading_material WHERE child_id = ?", (child_id,)
        ).fetchall()
    )
else:
    existing_titles = set(
        row[0] for row in conn.execute("SELECT title FROM reading_material").fetchall()
    )
```

This allows the same article to be imported separately for each child.

### 4. Pass child_id from frontend to browse API

In `materials.html`, update `loadArticles()` (~line 493):

- Read the child filter dropdown value
- Append `child_id` to the browse API request params:

```javascript
const childFilter = document.getElementById('child-filter').value;
if (childFilter) params += (params ? '&' : '?') + 'child_id=' + childFilter;
```

### 5. Dynamic source filter dropdown

Update `materials.html` source filter dropdown (~line 323):

- Remove hardcoded `<option>` values
- Populate dynamically after browse API returns articles (extract unique source names from results)
- OR: add a new endpoint that returns available feed names for a given child_id

Simpler approach: after `loadArticles()` receives articles, extract unique source names and rebuild the dropdown options while preserving the current selection.

### 6. Reload articles when child filter changes

The child filter dropdown currently reloads the page (`window.location.href`). Since the browse API now filters by child, articles will automatically update on page reload. No additional change needed — just verify this works.

## Acceptance Criteria

1. When Lang is selected, Browse Articles only shows feeds appropriate for age 9-10 (Science News Explores, Time for Kids, Curious Kids, NASA Climate Kids, Wonderopolis)
2. When Qian is selected, Browse Articles shows feeds for age 13-15 (Science News Explores, NYT Education, Ars Technica, The Verge, IEEE Spectrum, NIH News in Health, Live Science, Phys.org, NPR Business)
3. When no child is selected, all feeds are shown
4. Source filter dropdown only shows sources that are available for the selected child
5. Same article can be imported for both Lang and Qian separately — "Imported" badge is per-child
6. After importing the same article for both kids, AI question generation produces age-appropriate questions for each
7. All RSS feed URLs return valid feed data (no broken feeds)
8. No regressions to existing reading material functionality (manual add, PDF upload, questions, assignments)

## Grade-to-Age Mapping

Use this mapping for converting `grade_level` string to age:

```python
GRADE_TO_AGE = {
    "k": 6, "1st": 7, "2nd": 8, "3rd": 9, "4th": 10,
    "5th": 11, "6th": 12, "7th": 13, "8th": 14, "9th": 15,
    "10th": 16, "11th": 17, "12th": 18,
}
```

If grade_level is not set or not recognized, default to showing all feeds.
