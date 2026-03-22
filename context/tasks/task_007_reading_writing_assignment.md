	## Status: Done

## Objective

Auto-create a writing assignment when a reading assignment is added to a learning plan, prompting the child to summarize the article and share their point of view.

## Behavior

When a reading assignment is added to a learning plan:
1. Auto-create a writing test in the same plan linked to that reading material
2. The writing prompt asks the child to summarize the article in their own words and share their point of view
3. Word limits are based on the child's grade level
4. Default ON — always created unless explicitly skipped
5. API response includes a flag indicating a writing assignment was also created, so the parent knows and can delete it from the plan if not needed

## Implementation

### 1. Writing prompt generation

Topic text template:
```
After reading "[article title]", write a summary in your own words. What is the article about? What is your point of view on this topic?
```

### 2. Grade-level word limits

| Grade Level | Min Words | Max Words |
|-------------|-----------|-----------|
| 2nd-3rd     | 50        | 100       |
| 4th-5th     | 100       | 200       |
| 6th-8th     | 200       | 350       |

Parse the child's `grade_level` field (e.g., "4th grade") to determine the range. Default to 4th-5th if not set.

### 3. Backend changes

In `add_plan_reading_assignment` route (app.py):
- After creating the reading assignment (and the power words study session if applicable)
- Look up the child's grade level to determine word limits
- Create a `writing_test` with:
  - `topic_text`: the summary prompt including the article title
  - `min_word_count` / `max_word_count`: based on grade level
  - `timer_mode`: "none" (no time pressure for reflective writing)
  - `learning_plan_id`: the current plan
- Add as a `learning_plan_item` with type `writing_test`
- Include `writing_test_created: true` and `writing_test_id` in the API response

### 4. Frontend notification

- After adding a reading assignment, if the API response includes `writing_test_created: true`, show a toast notification in the bottom-right corner
- Message: "A writing assignment was also created for this reading."
- Toast fades in, stays for 4 seconds, then fades out
- Parent can dismiss it early by clicking

## Acceptance Criteria

1. Adding a reading assignment to a learning plan auto-creates a writing test with a summary prompt
2. Writing prompt includes the article title
3. Word limits match the child's grade level
4. Writing test appears in the plan items list
5. Parent can delete the writing test from the plan if not needed
6. API response indicates a writing assignment was created
