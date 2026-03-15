# Decisions Log

Key architectural and design decisions made during development.

## D1: Monolithic app.py

**Decision:** Keep all routes in a single `app.py` file.
**Rationale:** Started simple, grew organically. Works fine for a single-developer project.
**Trade-off:** File is now ~4550 lines. Navigation is harder. Blueprint split would help but isn't blocking.

## D2: No ORM

**Decision:** Use raw SQL with `sqlite3` throughout.
**Rationale:** Direct control, no abstraction overhead, SQLite-specific features accessible.
**Trade-off:** More verbose CRUD code, no migration framework, manual schema management.

## D3: Inline CSS/JS in Templates

**Decision:** Keep styles and scripts in each template rather than external files.
**Rationale:** Self-contained templates, no build step, easy to see everything in one file.
**Trade-off:** CSS duplication across templates. Harder to maintain consistent styling.

## D4: Server-Side Rendering + Fetch APIs

**Decision:** Use Jinja2 for page rendering, fetch() for dynamic operations.
**Rationale:** Simple architecture, no frontend framework needed, progressive enhancement.
**Trade-off:** Some pages have complex JS for interactivity (parent dashboard tabs, inline editing).

## D5: Local-Only Testing and OCI cloud deployment 

**Decision:** Run on local network for testing only, production deployed to cloud hosting. DB sits with APP no matter what environment.
**Rationale:** Easy testing. But kids and parents can access production everywhere via internet
**Trade-off:** Security issue since currently only HTTP supported. need to manually run backup db regularly.

## D6: Parent Creates All Content with gradually increasing AI assistance

**Decision:** Parent role controls all content creation (tests, assignments, materials) while ramping up more AI assistance (e.g., AI come up questions and answers for reading materials).
**Rationale:** Age-appropriate — parent curates what children study. Leverage AI to some extend to free parent time as well as better memorize kids learning needs.
**Trade-off:** AI token cost

## D7: Science Bowl PDF Format

**Decision:** Parse Science Bowl competition PDFs as the primary science question source.
**Rationale:** Free, high-quality, standardized format, grade-appropriate content.
**Trade-off:** Parser is fragile to format variations. Limited to Science Bowl question style.

## D8: Learning Plans as Activity Bundles

**Decision:** Learning plans are ordered lists of activities across subjects.
**Rationale:** Gives structure to daily practice. Parent controls pacing.
**Trade-off:** Plan management UI is complex. Auto-completion logic spans all activity types.

## D9: ALTER TABLE Migrations

**Decision:** Use try/except ALTER TABLE pattern for schema migrations in `init_db()`.
**Rationale:** Simple, no dependencies, works with SQLite limitations.
**Trade-off:** Migration blocks accumulate. No rollback capability. No migration versioning.

## D10: Threading Mode for SocketIO

**Decision:** Use `async_mode="threading"` for Flask-SocketIO.
**Rationale:** Simpler than eventlet/gevent, works for local use with few concurrent users.
**Trade-off:** Not suitable for high concurrency. Eventlet listed in requirements but not used.

## D11: Server-Side Proxy for Kid Web Reading

**Decision:** Use a server-side proxy (`/api/reading-proxy`) to fetch, sanitize, and serve external web pages for kid reading, rather than a direct iframe with sandbox attributes.
**Rationale:** Full control over content — can strip all links, scripts, nav, ads, and social elements. Direct iframe sandbox blocks top-level navigation but links still work within the frame. Proxy approach ensures kids cannot click any link at all.
**Trade-off:** Extra server request per page load. Proxy must handle relative URLs for images/CSS. Some complex pages may not render perfectly after sanitization.

## D12: Client-Side Auto-Save and Checkpoints for Writing

**Decision:** Use localStorage for writing auto-save and 5-minute checkpoint snapshots (last 2 kept), rather than server-side storage.
**Rationale:** Client-side approach is simpler, has no server cost, works offline, and avoids adding DB columns/API endpoints. Sufficient for the use case since writing happens in a single browser session.
**Trade-off:** Drafts don't sync across devices/browsers. localStorage can be cleared by the user. Acceptable since kids typically use the same device.
