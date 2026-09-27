"""CogAT-style / i-Ready-style question bank: validation, SVG sanitizing, mastery, test assembly (task_014).

Original practice questions only — not affiliated with or endorsed by the publishers of CogAT or i-Ready.
"""
import json
import random
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

TRACKS = ("cogat-style", "iready-style")
GRADES = (4, 5, 6)
QTYPES = ("text-choice", "figure-image", "passage-set")

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

DEFAULT_MIX = {"new": 0.5, "needs_work": 0.3, "due": 0.2}
BUCKET_ORDER = ("new", "needs_work", "due")
DUE_DAYS = 7

# ── SVG sanitizing ──

_SVG_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
    "defs", "use", "symbol", "clippath", "mask", "pattern", "lineargradient", "radialgradient", "stop",
    "marker", "title", "desc",
}


def sanitize_svg(svg):
    """Whitelist-sanitize an SVG fragment. Returns None for empty input."""
    if not svg or not str(svg).strip():
        return None
    soup = BeautifulSoup(str(svg), "html.parser")
    for el in soup.find_all(True):
        if el.name.lower() not in _SVG_TAGS:
            el.decompose()
            continue
        for attr in list(el.attrs):
            name = attr.lower()
            val = el.attrs[attr]
            sval = " ".join(val) if isinstance(val, list) else str(val)
            if name.startswith("on"):
                del el.attrs[attr]
            elif name in ("href", "xlink:href") and not sval.startswith("#"):
                del el.attrs[attr]
            elif name == "style" and ("url(" in sval.lower() or "expression" in sval.lower()):
                del el.attrs[attr]
    out = str(soup).strip()
    return out or None


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
        text = (o.get("text") or "").strip() or None
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

    out["stem"] = (merged.get("stem") or "").strip() or None
    out["stem_svg"] = sanitize_svg(merged.get("stem_svg"))

    options = normalize_options(merged.get("options"))
    out["options"] = json.dumps(options)
    answer_in = data.get("correct_answer", merged.get("correct_answer"))
    out["correct_answer"] = normalize_answer(answer_in, len(options))

    out["explanation"] = (merged.get("explanation") or "").strip() or None
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

    status = merged.get("status") or "active"
    if status not in ("active", "archived"):
        raise QBValidationError("status must be active or archived")
    out["status"] = status
    out["source_ref"] = merged.get("source_ref") or None

    if not out["stem"] and not out["stem_svg"] and not out["passage_id"] and not merged.get("image_path"):
        raise QBValidationError("question needs a stem, stem_svg, image or passage")
    return out


def question_to_dict(row, include_answer=True):
    d = dict(row)
    d["options"] = json.loads(d["options"]) if d.get("options") else []
    d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
    if not include_answer:
        for k in ("correct_answer", "explanation", "answer_source"):
            d.pop(k, None)
    return d


# ── Mastery ──

def mastery_bucket(progress, now=None):
    """progress: row/dict with correct_count, wrong_count, last_correct_at, or None."""
    if not progress or (progress["correct_count"] or 0) + (progress["wrong_count"] or 0) == 0:
        return "new"
    if (progress["wrong_count"] or 0) > (progress["correct_count"] or 0):
        return "needs_work"
    now = now or datetime.now()
    cutoff = (now - timedelta(days=DUE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    if not progress["last_correct_at"] or progress["last_correct_at"] < cutoff:
        return "due"
    return "mastered"


def update_progress(conn, child_id, question_id, is_correct):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT OR IGNORE INTO qb_question_progress (child_id, question_id) VALUES (?, ?)",
        (child_id, question_id),
    )
    if is_correct:
        conn.execute(
            """UPDATE qb_question_progress SET correct_count = correct_count + 1,
               last_tested = ?, last_correct_at = ? WHERE child_id = ? AND question_id = ?""",
            (now, now, child_id, question_id),
        )
    else:
        conn.execute(
            """UPDATE qb_question_progress SET wrong_count = wrong_count + 1,
               last_tested = ? WHERE child_id = ? AND question_id = ?""",
            (now, child_id, question_id),
        )


def load_pool(conn, child_id, track, grade, section=None):
    """Active questions for a filter, each annotated with its mastery bucket for child_id."""
    sql = """SELECT q.id, q.passage_id, q.passage_order,
                    p.correct_count, p.wrong_count, p.last_tested, p.last_correct_at
             FROM qb_question q
             LEFT JOIN qb_question_progress p ON p.question_id = q.id AND p.child_id = ?
             WHERE q.status = 'active' AND q.track = ? AND q.grade = ?"""
    params = [child_id, track, grade]
    if section:
        sql += " AND q.section = ?"
        params.append(section)
    rows = conn.execute(sql, params).fetchall()
    now = datetime.now()
    pool = []
    for r in rows:
        prog = r if r["correct_count"] is not None else None
        pool.append({
            "id": r["id"], "passage_id": r["passage_id"], "passage_order": r["passage_order"] or 0,
            "last_tested": r["last_tested"] or "", "bucket": mastery_bucket(prog, now),
        })
    return pool


def _units(pool):
    """Group questions into selection units: a passage set is one unit, other questions stand alone."""
    rank = {b: i for i, b in enumerate(BUCKET_ORDER + ("mastered",))}
    by_passage, units = {}, []
    for q in pool:
        if q["passage_id"]:
            by_passage.setdefault(q["passage_id"], []).append(q)
        else:
            units.append({"questions": [q], "bucket": q["bucket"], "last_tested": q["last_tested"]})
    for qs in by_passage.values():
        qs.sort(key=lambda q: (q["passage_order"], q["id"]))
        # A passage set's bucket is its weakest non-mastered sub-question's bucket
        live = [q for q in qs if q["bucket"] != "mastered"]
        bucket = min((q["bucket"] for q in live), key=lambda b: rank[b]) if live else "mastered"
        units.append({"questions": qs, "bucket": bucket, "last_tested": min(q["last_tested"] for q in qs)})
    return units


def bucket_counts(pool):
    counts = {"new": 0, "needs_work": 0, "due": 0, "mastered": 0}
    for q in pool:
        counts[q["bucket"]] += 1
    return counts


def assemble_test(pool, count, mix=None, rng=None):
    """Pick question ids by mastery. Returns (question_ids, shortfall).

    Targets per bucket from mix; shortfalls backfilled in order new → needs_work → due.
    Mastered questions are never picked. Passage sets are picked whole and may overshoot count by ≤ 2.
    """
    rng = rng or random.Random()
    mix = mix or DEFAULT_MIX
    total_pct = sum(mix.get(b, 0) for b in BUCKET_ORDER) or 1
    targets = {b: round(count * mix.get(b, 0) / total_pct) for b in BUCKET_ORDER}
    # Fix rounding drift so targets sum to count
    drift = count - sum(targets.values())
    targets[BUCKET_ORDER[0]] += drift

    buckets = {b: [] for b in BUCKET_ORDER}
    for u in _units(pool):
        if u["bucket"] in buckets:
            buckets[u["bucket"]].append(u)
    for b in BUCKET_ORDER:
        rng.shuffle(buckets[b])
        buckets[b].sort(key=lambda u: u["last_tested"])  # least recently tested first (stable over shuffle)

    chosen, picked = [], 0

    def take(bucket, limit):
        nonlocal picked
        got = 0
        remaining = []
        for u in buckets[bucket]:
            size = len(u["questions"])
            if got < limit and picked < count and picked + size <= count + 2 and (size == 1 or got + size <= limit + 2):
                chosen.append(u)
                got += size
                picked += size
            else:
                remaining.append(u)
        buckets[bucket] = remaining

    for b in BUCKET_ORDER:
        take(b, targets[b])
    for b in BUCKET_ORDER:  # backfill
        if picked >= count:
            break
        take(b, count - picked)

    # Keep passage units contiguous; interleave order otherwise random
    rng.shuffle(chosen)
    ids = [q["id"] for u in chosen for q in u["questions"]]
    return ids, max(0, count - len(ids))


def parse_mix(raw):
    """mastery_mix as {"new":50,"needs_work":30,"due":20} (percent or fraction). None → default."""
    if not raw:
        return dict(DEFAULT_MIX)
    if not isinstance(raw, dict):
        raise QBValidationError("mastery_mix must be an object like {new, needs_work, due}")
    mix = {}
    for b in BUCKET_ORDER:
        try:
            mix[b] = max(0.0, float(raw.get(b, 0)))
        except (TypeError, ValueError):
            raise QBValidationError(f"mastery_mix.{b} must be a number")
    if sum(mix.values()) <= 0:
        raise QBValidationError("mastery_mix must have at least one positive value")
    return mix
