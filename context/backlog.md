# Backlog

Ideas and potential improvements, roughly prioritized.

## High Priority

- [x] (yifeng)need to handle writing is not saved and gets lost in the middle by accident (task_003 — client-side auto-save + checkpoints)
- [x] (yifeng)need to have a way to record/view how many times a reading material is read by a kid (task_004 — attempt tracking, correct ratio, filters on materials page)
- [ ] Split `app.py` into Flask blueprints by subject (vocab, reading, math, writing, science, plans)
- [ ] Extract shared CSS into a static stylesheet to reduce template duplication
- [ ] Add basic automated tests (at least for API endpoints and grading logic)
- [ ] Proper error logging (replace silent failures)

## Medium Priority

- [ ] (yifeng)parent review kids reading need to switch to browser mode as well like kids. also need to investigate why kids questions got duplicated
- [ ] Word categories/tags for organization
- [ ] Export/import word lists (CSV/JSON)
- [ ] Progress charts and analytics (beyond current stats page)
- [ ] Spaced repetition algorithm for vocab review scheduling
- [ ] Reading assignment due dates
- [ ] Parent notification when child completes an assignment
- [ ] Bulk operations (delete multiple questions, bulk assign)

## Low Priority / Future Ideas

- [ ] Speech recognition for verbal responses in vocab tests
- [ ] Custom audio recordings for pronunciation
- [ ] Multiple language support
- [ ] Dark mode
- [ ] Print-friendly views for test reviews
- [ ] Mobile app wrapper (PWA)
- [ ] Cloud backup/sync option
- [ ] Multi-family support (currently single-family)

## Design Considerations from Original Spec (not yet implemented)

- Custom avatar selection for children
- Leaderboard between children (basic version exists via points)
- Confetti/celebration animations on achievements
- Reading session scroll position sync (WebSocket infrastructure exists)
