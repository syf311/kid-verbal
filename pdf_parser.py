import re
import pdfplumber


def parse_answer_pdf(pdf_path):
    """Extract multiple-choice answers from an answer-key PDF.

    Recognises patterns like:
        1. A      1) B      #1 C      Q1: D      1 - A      1: E
        1. Answer (A):      Answer: B      1. (C)
    Answers must be A-E, numbering must be sequential starting at 1.

    Returns (answer_dict, error_string).
        answer_dict: {"1": "A", "2": "B", ...}  on success
        error_string: None on success, descriptive message on failure
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            return None, "Could not extract any text from the PDF."

        answers = {}

        # Try multiple patterns in priority order
        patterns = [
            # "1. Answer (A):" or "1. Answer(A)" or "1 Answer (A)"
            r'(\d+)\s*[.):\-]?\s*[Aa]nswer\s*\(?([A-Ea-e])\)?',
            # "1. (A)" or "1) (B)" or "1: (C)"
            r'(?:Q|#)?\s*(\d+)\s*[.):\-]\s*\(([A-Ea-e])\)',
            # "1. A" or "1) B" or "#1 C" or "Q1: D" or "1 - A" or "1: E"
            r'(?:Q|#)?\s*(\d+)\s*[.):\-]\s*([A-Ea-e])\b',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                for num_str, letter in matches:
                    num = int(num_str)
                    if num not in answers:
                        answers[num] = letter.upper()
                break

        if not answers:
            return None, "No answer patterns found. Expected formats: '1. A', '1) B', '#1 C', 'Q1: D', '1. Answer (A)'."

        # Validate sequential numbering starting at 1
        expected = set(range(1, max(answers.keys()) + 1))
        actual = set(answers.keys())
        missing = expected - actual
        if missing:
            return None, f"Missing answers for question(s): {sorted(missing)}."

        if min(answers.keys()) != 1:
            return None, "Question numbering must start at 1."

        # Build result dict with string keys, sorted
        result = {str(k): answers[k] for k in sorted(answers.keys())}
        return result, None

    except Exception as e:
        return None, f"Error reading PDF: {str(e)}"


def _parse_grid_text(text):
    """Parse grid answer text into rows_dict.

    Returns rows_dict: {"Felix": {"1": "B", ...}, ...} or empty dict.
    """
    rows_dict = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        tokens = line.split()
        if len(tokens) < 2:
            continue

        # Skip header rows (all numeric like "1 2 3 ... 30") and year rows (single number like "2020")
        if all(t.isdigit() for t in tokens):
            continue

        # A data row starts with a non-numeric label, followed by A-E or - tokens
        # Find where the label ends and answers begin
        label_parts = []
        answer_start = 0
        for i, t in enumerate(tokens):
            if re.match(r'^[A-Ea-e]$', t) or t == '-':
                answer_start = i
                break
            label_parts.append(t)

        if not label_parts or answer_start == 0:
            continue

        label = " ".join(label_parts)
        answer_tokens = tokens[answer_start:]

        # Validate: all answer tokens must be A-E or -
        if not all(re.match(r'^[A-Ea-e]$', t) or t == '-' for t in answer_tokens):
            continue

        # Build answer dict, skipping '-' entries
        answers = {}
        for idx, t in enumerate(answer_tokens, start=1):
            if t != '-':
                answers[str(idx)] = t.upper()

        if answers:
            rows_dict[label] = answers

    return rows_dict


def is_scanned_pdf(pdf_path):
    """Check if a PDF is image-based (no extractable text).

    Returns True if scanned/image-based, False if text-based.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    return False
        return True
    except Exception:
        return True


def pdf_page_to_png(pdf_path, page_num=0):
    """Convert a PDF page to PNG bytes.

    Returns (png_bytes, error_string).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                return None, "Page number out of range."
            page = pdf.pages[page_num]
            img = page.to_image(resolution=200)
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue(), None
    except Exception as e:
        return None, f"Error converting PDF to image: {str(e)}"


def parse_grid_answer_pdf(pdf_path):
    """Extract answers from a grid/table answer-key PDF (e.g. Math Kangaroo).

    Expected format: rows where each line is:
        <LevelName> <A-E or -> <A-E or -> ... (up to 30 answers)
    preceded by a header row of column numbers (1 2 3 ... 30).

    Returns (rows_dict, error_string).
        rows_dict: {"Felix": {"1": "B", "2": "C", ...}, ...} on success
        error_string: None on success, descriptive message on failure
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            return None, "SCANNED"

        # Fix common OCR misreads
        text = text.replace("É colier", "Écolier").replace("E colier", "Écolier")
        text = text.replace("Ecolier", "Écolier")

        rows_dict = _parse_grid_text(text)
        if rows_dict:
            return rows_dict, None

        return None, "No grid answer rows found. Expected format: rows with level name followed by A-E answers."

    except Exception as e:
        return None, f"Error reading PDF: {str(e)}"


def extract_row_answers(rows_dict, row_name):
    """Extract answers for a specific row from a parsed grid.

    Returns (answer_dict, error_string).
        answer_dict: {"1": "A", "2": "B", ...} on success
        error_string: None on success, descriptive message on failure
    """
    if row_name not in rows_dict:
        available = ", ".join(rows_dict.keys())
        return None, f"Row '{row_name}' not found. Available rows: {available}"

    # Filter out any empty or invalid entries
    answers = {k: v for k, v in rows_dict[row_name].items() if v in "ABCDE"}
    return answers, None
