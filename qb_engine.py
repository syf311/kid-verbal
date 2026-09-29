"""CogAT-style / i-Ready-style question bank: validation, SVG sanitizing, mastery, test assembly (task_014).

Original practice questions only — not affiliated with or endorsed by the publishers of CogAT or i-Ready.
"""
import json
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

TRACKS = ("cogat-style", "iready-style")
GRADES = (4, 5, 6)
QTYPES = ("text-choice", "figure-image", "passage-set")
SOURCES = ("ai_generated", "human")  # where the question itself came from
SOURCE_LABELS = {"ai_generated": "AI generated", "human": "Human"}

# Known sections per track (display order). Unknown sections are allowed so new ones can be added later.
SECTIONS = {
    "cogat-style": [
        ("verbal-analogies", "Verbal Analogies", "Verbal"),
        ("sentence-completion", "Sentence Completion", "Verbal"),
        ("verbal-classification", "Verbal Classification", "Verbal"),
        ("number-analogies", "Number Analogies", "Quantitative"),
        ("number-puzzles", "Number Puzzles", "Quantitative"),
        ("number-series", "Number Series", "Quantitative"),
        ("figure-matrices", "Figure Matrices", "Nonverbal"),
        ("paper-folding", "Paper Folding", "Nonverbal"),
        ("figure-classification", "Figure Classification", "Nonverbal"),
    ],
    "iready-style": [
        ("vocabulary", "Vocabulary", "Reading"),
        ("reading-comprehension", "Reading Comprehension", "Reading"),
    ],
}

TRACK_LABELS = {"cogat-style": "CogAT-style practice", "iready-style": "i-Ready-style practice"}

DUE_DAYS = 7

# ── SVG sanitizing ──

_SVG_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
    "defs", "use", "symbol", "clippath", "mask", "pattern", "lineargradient", "radialgradient", "stop",
    "marker", "title", "desc",
}


# Simple inline formatting allowed in stems/options/explanations/passages (no attributes kept)
_HTML_TAGS = {"br", "b", "i", "em", "strong", "u", "sub", "sup", "span", "p", "div", "small"}


def _sanitize(markup, allowed):
    soup = BeautifulSoup(str(markup), "html.parser")
    for el in soup.find_all(True):
        if getattr(el, "decomposed", False):
            continue  # inside an element already removed
        name = el.name.lower()
        if name not in allowed:
            el.decompose()
            continue
        if name in _HTML_TAGS:
            el.attrs = {}
            continue
        for attr in list(el.attrs):
            aname = attr.lower()
            val = el.attrs[attr]
            sval = (" ".join(val) if isinstance(val, list) else str(val)).lower()
            if aname.startswith("on"):
                del el.attrs[attr]
            elif aname in ("href", "xlink:href") and not sval.startswith("#"):
                del el.attrs[attr]
            elif aname == "style" and ("url(" in sval or "expression" in sval):
                del el.attrs[attr]
    return str(soup).strip()


def sanitize_svg(svg):
    """Whitelist-sanitize an SVG fragment. Returns None for empty input."""
    if not svg or not str(svg).strip():
        return None
    return _sanitize(svg, _SVG_TAGS) or None


def sanitize_rich(text):
    """Stem/option/explanation/passage text → safe HTML (inline SVG + simple formatting allowed).

    Plain text comes back HTML-escaped, so the client can always render the result with innerHTML.
    """
    if text is None or not str(text).strip():
        return None
    return _sanitize(text, _SVG_TAGS | _HTML_TAGS) or None


# ── Validation ──

class QBValidationError(ValueError):
    pass


def _int_in(value, allowed, field):
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise QBValidationError(f"{field} must be one of {list(allowed)}")
    if v not in allowed:
        raise QBValidationError(f"{field} must be one of {list(allowed)}")
    return v


def normalize_options(options):
    """Options → list of {"text": str|None, "svg": str|None}. Accepts plain strings too."""
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            raise QBValidationError("options must be a JSON array")
    if not isinstance(options, list) or not (2 <= len(options) <= 6):
        raise QBValidationError("options must be an array of 2-6 items")
    out = []
    for o in options:
        if isinstance(o, str):
            o = {"text": o}
        if not isinstance(o, dict):
            raise QBValidationError("each option must be a string or {text, svg}")
        text = sanitize_rich(o.get("text"))
        svg = sanitize_svg(o.get("svg"))
        if not text and not svg:
            raise QBValidationError("each option needs text or svg")
        out.append({"text": text, "svg": svg})
    return out


def normalize_answer(answer, n_options):
    """Accepts 0-based index (int or digit string) or a letter A-F. Returns index as string."""
    if answer is None or str(answer).strip() == "":
        raise QBValidationError("correct_answer is required")
    a = str(answer).strip().upper()
    if a.isdigit():
        idx = int(a)
    elif len(a) == 1 and "A" <= a <= "F":
        idx = ord(a) - ord("A")
    else:
        raise QBValidationError("correct_answer must be an option index (0-based) or letter A-F")
    if not 0 <= idx < n_options:
        raise QBValidationError("correct_answer is out of range for options")
    return str(idx)


def validate_question(data, existing=None):
    """Validate a create (existing=None) or partial update payload. Returns dict of DB column values."""
    merged = dict(existing or {})
    merged.update({k: v for k, v in data.items() if v is not None or k in ("passage_id", "stem_svg", "explanation")})
    out = {}

    if merged.get("track") not in TRACKS:
        raise QBValidationError(f"track must be one of {list(TRACKS)}")
    out["track"] = merged["track"]
    out["grade"] = _int_in(merged.get("grade"), GRADES, "grade")
    section = (merged.get("section") or "").strip().lower()
    if not section:
        raise QBValidationError("section is required")
    out["section"] = section
    qtype = merged.get("qtype") or "text-choice"
    if qtype not in QTYPES:
        raise QBValidationError(f"qtype must be one of {list(QTYPES)}")
    out["qtype"] = qtype

    out["stem"] = sanitize_rich(merged.get("stem"))
    out["stem_svg"] = sanitize_svg(merged.get("stem_svg"))

    options = normalize_options(merged.get("options"))
    out["options"] = json.dumps(options)
    answer_in = data.get("correct_answer", merged.get("correct_answer"))
    out["correct_answer"] = normalize_answer(answer_in, len(options))

    out["explanation"] = sanitize_rich(merged.get("explanation"))
    out["difficulty"] = _int_in(merged.get("difficulty", 3), range(1, 6), "difficulty")

    tags = merged.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except json.JSONDecodeError:
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    out["tags"] = json.dumps([str(t) for t in tags])

    passage_id = merged.get("passage_id")
    out["passage_id"] = int(passage_id) if passage_id not in (None, "") else None
    if qtype == "passage-set" and not out["passage_id"]:
        raise QBValidationError("passage-set questions need passage_id")
    out["passage_order"] = int(merged.get("passage_order") or 0)

    for field, allowed in (("created_by", ("milo", "parent", "seed")), ("answer_source", ("milo", "parent", "seed"))):
        val = merged.get(field) or "parent"
        if val not in allowed:
            raise QBValidationError(f"{field} must be one of {list(allowed)}")
        out[field] = val

    if merged.get("source") not in SOURCES:
        raise QBValidationError(f"source is required: one of {list(SOURCES)}")
    out["source"] = merged["source"]

    status = merged.get("status") or "active"
    if status not in ("active", "archived"):
        raise QBValidationError("status must be active or archived")
    out["status"] = status
    out["source_ref"] = merged.get("source_ref") or None

    if not out["stem"] and not out["stem_svg"] and not out["passage_id"] and not merged.get("image_path"):
        raise QBValidationError("question needs a stem, stem_svg, image or passage")
    return out


def passage_to_dict(row):
    d = dict(row)
    d["body"] = d.get("body") or ""
    return d


def _clean_options(raw):
    """Stored options JSON → [{text, svg}] (plain-string options become {text})."""
    opts = json.loads(raw) if raw else []
    return [{"text": o.get("text"), "svg": o.get("svg")} if isinstance(o, dict) else {"text": o, "svg": None}
            for o in opts]


def sanitize_stored(conn):
    """One-time migration: sanitize every stored rich field so reads can serve rows as-is.
    (Rows written through the API are already sanitized; this covers anything stored before that.)"""
    for r in conn.execute("SELECT id, stem, stem_svg, explanation, options FROM qb_question").fetchall():
        opts = [{"text": sanitize_rich(o["text"]), "svg": sanitize_svg(o["svg"])} for o in _clean_options(r["options"])]
        conn.execute("UPDATE qb_question SET stem = ?, stem_svg = ?, explanation = ?, options = ? WHERE id = ?",
                     (sanitize_rich(r["stem"]), sanitize_svg(r["stem_svg"]), sanitize_rich(r["explanation"]),
                      json.dumps(opts), r["id"]))
    for r in conn.execute("SELECT id, body FROM qb_passage").fetchall():
        conn.execute("UPDATE qb_passage SET body = ? WHERE id = ?", (sanitize_rich(r["body"]) or "", r["id"]))


def question_to_dict(row, include_answer=True, lite=False):
    """Row → API dict. Rich fields are stored sanitized (on write, plus the one-time sanitize_stored
    migration), so they are served as-is. lite=True drops options/explanation for list views."""
    d = dict(row)
    if lite:
        d.pop("options", None)
        d.pop("explanation", None)
    else:
        d["options"] = _clean_options(d.get("options"))
    d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
    if not include_answer:
        for k in ("correct_answer", "explanation", "answer_source"):
            d.pop(k, None)
    return d


# ── Mastery ──
# Same rules as the math/science banks: each right answer raises level by 1 (max 5), each wrong
# answer lowers it by 1 (min 1) and resets the streak.

MASTERY_STATUSES = ("new", "needs_improvement", "due", "good", "mastered")
MASTERY_LABELS = {"new": "New", "needs_improvement": "Needs improvement", "due": "Due",
                  "good": "Good", "mastered": "Mastered"}


def mastery_status(progress, now=None):
    """progress: row/dict with correct_count, wrong_count, streak, difficulty_level,
    last_tested, last_correct_at — or None when the child never answered the question."""
    if not progress or not progress["last_tested"]:
        return "new"
    if (progress["wrong_count"] or 0) > (progress["correct_count"] or 0):
        return "needs_improvement"
    if (progress["streak"] or 0) == 0:
        return "needs_improvement"  # last answer was wrong
    if (progress["difficulty_level"] or 1) >= 4:
        return "mastered"
    now = now or datetime.now()
    cutoff = (now - timedelta(days=DUE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    if not progress["last_correct_at"] or progress["last_correct_at"] < cutoff:
        return "due"
    return "good"


def parse_mastery_filter(raw):
    """'new,needs_improvement' → {'new', 'needs_improvement'}; None/'' → None (no filter)."""
    if not raw:
        return None
    wanted = {m.strip() for m in str(raw).split(",") if m.strip()}
    bad = wanted - set(MASTERY_STATUSES)
    if bad:
        raise QBValidationError(f"mastery must be a comma list of {list(MASTERY_STATUSES)}")
    return wanted


def _apply_attempt(conn, child_id, question_id, is_correct, when):
    conn.execute(
        "INSERT OR IGNORE INTO qb_question_progress (child_id, question_id) VALUES (?, ?)",
        (child_id, question_id),
    )
    if is_correct:
        conn.execute(
            """UPDATE qb_question_progress SET correct_count = correct_count + 1,
                   streak = COALESCE(streak, 0) + 1, difficulty_level = MIN(5, COALESCE(difficulty_level, 1) + 1),
                   last_tested = ?, last_correct_at = ?
               WHERE child_id = ? AND question_id = ?""",
            (when, when, child_id, question_id),
        )
    else:
        conn.execute(
            """UPDATE qb_question_progress SET wrong_count = wrong_count + 1,
                   streak = 0, difficulty_level = MAX(1, COALESCE(difficulty_level, 1) - 1),
                   last_tested = ?
               WHERE child_id = ? AND question_id = ?""",
            (when, child_id, question_id),
        )


def record_attempt(conn, child_id, question_id, test_id, choice, is_correct, when=None):
    """Append to the per-question history and update the child's mastery progress."""
    when = when or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """INSERT INTO qb_question_attempt (child_id, question_id, test_id, choice, is_correct, attempted_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (child_id, question_id, test_id, choice, int(bool(is_correct)), when),
    )
    _apply_attempt(conn, child_id, question_id, is_correct, when)


def rebuild_history(conn):
    """One-time migration: build attempt history from already-submitted tests, then recompute
    every progress row from that history (adds streak/level to pre-existing progress)."""
    # submitted_at is SQLite CURRENT_TIMESTAMP (UTC); progress uses local time like the rest of the app
    subs = conn.execute(
        """SELECT s.test_id, s.child_id, datetime(s.submitted_at, 'localtime') AS submitted_at
           FROM qb_test_submission s ORDER BY s.submitted_at, s.id"""
    ).fetchall()
    for sub in subs:
        qids = [r["question_id"] for r in conn.execute(
            "SELECT question_id FROM qb_test_question WHERE test_id = ? ORDER BY position", (sub["test_id"],))]
        answers = {r["question_id"]: r for r in conn.execute(
            "SELECT * FROM qb_test_answer WHERE test_id = ?", (sub["test_id"],))}
        for qid in qids:
            a = answers.get(qid)
            conn.execute(
                """INSERT INTO qb_question_attempt (child_id, question_id, test_id, choice, is_correct, attempted_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sub["child_id"], qid, sub["test_id"], a["choice"] if a else None,
                 int(bool(a and a["is_correct"])), sub["submitted_at"]),
            )
    conn.execute("DELETE FROM qb_question_progress")
    for a in conn.execute("SELECT * FROM qb_question_attempt ORDER BY attempted_at, id").fetchall():
        _apply_attempt(conn, a["child_id"], a["question_id"], bool(a["is_correct"]), a["attempted_at"])
