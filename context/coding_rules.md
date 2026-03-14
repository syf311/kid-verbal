# Coding Rules

## General

- Python 3.14 is installed at `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- Run the app with `python3 app.py` (starts on port 5001)
- No external CSS/JS frameworks — everything is vanilla HTML/CSS/JS
- No ORM — use raw SQL with `sqlite3` and `conn.row_factory = sqlite3.Row`

## Backend Conventions

- All routes go in `app.py` (monolithic file, organized by subject)
- Use `@login_required` for routes accessible by any logged-in user
- Use `@parent_required` for parent-only routes (creating content, managing tests)
- Database connections: `conn = get_db()` ... `conn.close()` (no context managers used)
- Return `jsonify({...})` for API endpoints, `render_template(...)` for page routes
- File uploads go to `uploads/` directory, use `secure_filename()` + timestamp prefix
- Schema changes: add new tables in `init_db()` CREATE block; add columns via ALTER TABLE migration pattern in `database.py`

## Frontend Conventions

- Templates extend `base.html`
- CSS is inline in each template's `<style>` block (not extracted to files)
- JavaScript is inline in each template's `<script>` block
- Use `fetch()` for API calls, not jQuery or axios
- Mobile-friendly: responsive design with large touch targets
- Use CSS variables and consistent color scheme from base.html
- Modals for create/edit operations on parent dashboard

## Naming Conventions

- Routes: `/child/<int:child_id>/...` for child-scoped pages
- API routes: `/api/...` for JSON endpoints
- Template files: `snake_case.html`
- Python functions: `snake_case`
- Database tables: `snake_case`
- JavaScript: `camelCase` for functions and variables

## Testing

- No automated test suite exists
- Manual testing via browser
- Test by starting app and navigating through flows

## Git

- Commit messages: `feat:`, `fix:`, `refactor:` prefixes
- Commit after each logical feature unit
- Single `main` branch
