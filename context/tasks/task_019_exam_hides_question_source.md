# Task 019: Exam Mode Also Hides Where a Question Comes From

**Status:** Done

## Objective

task_017 hid the "YYYY AMC ... Problem N" title line and the contest/year/number fields from kids in practice mode only; exam mode kept the originals. The parent asked (2026-10-17) to hide them in exam mode too, since a kid could look answers up during an exam as well.

## Decisions

| # | Decision |
|---|----------|
| D1 | Kid view (`_math_kid_view`) no longer depends on the mode: a child (or a parent with "Kid view" on) gets the title-free picture and no contest/year/number/source/origin on the test page and review page, in exam and practice mode. Parents keep originals and source tags. |
| D2 | The builder's "Full Exam" button fills the neutral title "Full Exam" instead of "<contest> <year>", because the kid sees the title. The builder's contest/year filters still show the source to the parent. |
| D3 | Exam titles name the contest and year ("AMC8 1986"), so a kid sees "Math Exam #<test id>" instead (`_math_test_title`): test page + browser tab, review page, learning plan item, test list and dashboard-summary APIs, and the parent's Kid view. The stored title and everything parents see are unchanged. Practice titles are shown as stored (renamed through `PUT /api/math-bank-tests/<id>`, task_018). |
