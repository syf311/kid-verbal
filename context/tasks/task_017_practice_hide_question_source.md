# Task 017: Practice Mode Hides Where a Question Comes From

**Status:** Done

## Objective

In practice mode a kid must not see the year / contest / problem number of a question (they could look the answer up online). The parent can still tell which contest question it is on the review page. Exam mode is unchanged.

## Findings (production data, 2026-10-17)

- 2208 question pictures. 1708 are website screenshots (1707 are 890 px wide, 1 is 916) that start with a blue title line "YYYY AMC ... Problem N" plus a light-blue underline. In all 1708 the title + underline end at exactly 66 px.
- The other 500 (775–1700 px wide, typeset contest pages) have no year line, only the problem number "1." inside the problem.
- None of the 1554 solution pictures has a title line.
- Cropping a fixed share of the top would cut into pictures without a title, so the title is detected from the pixels instead.

## Decisions

| # | Decision |
|---|----------|
| D1 | Kid copy: `math_images.title_header_height` finds a blue title band + full-width underline at the top; `make_kid_image` saves a copy cropped below it (`mathq_<id>_k_...`). Originals are never changed. |
| D2 | Kid view = session role `child` and test mode `practice`. Test API and review page then use the kid copy and drop `contest`, `contest_year`, `problem_number`, `source`, `origin`. Parents (also when opening a practice test) and exam mode get the original picture, as before. |
| D3 | Kid copy made on first use (`math_question.kid_image_path`, `kid_image_checked`), so existing questions need no backfill run. Replacing/removing the question picture resets it; deleting the question deletes it. |
| D4 | Review page: parent sees a blue "contest year #number" tag on every question (exam and practice); child never does. |

## Out of scope

The problem number printed inside typeset pictures ("1."), test titles chosen by the parent, and `GET /api/children/<id>/math-questions` (bank list, login_required, returns full rows incl. answers — older behaviour).
