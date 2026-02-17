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


def parse_grid_answer_pdf(pdf_path):
    """Extract answers from a grid/table answer-key PDF (e.g. Math Kangaroo).

    Expected format: rows where each line is:
        <LevelName> <A-E or -> <A-E or -> ... (up to 30 answers)
    preceded by a header row of column numbers (1 2 3 ... 30).

    Falls back to OCR (pytesseract) if no text can be extracted directly.

    Returns (rows_dict, error_string).
        rows_dict: {"Felix": {"1": "B", "2": "C", ...}, "Écolier": {...}, ...}
        error_string: None on success, descriptive message on failure
    """
    try:
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        # If no text extracted, fall back to OCR
        if not text.strip():
            try:
                import pytesseract
                from PIL import Image
                import io

                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        img = page.to_image(resolution=300)
                        # Convert PageImage to PIL Image
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        buf.seek(0)
                        pil_img = Image.open(buf)
                        ocr_text = pytesseract.image_to_string(pil_img)
                        if ocr_text:
                            text += ocr_text + "\n"
            except ImportError:
                return None, "Could not extract text from the PDF and OCR (pytesseract) is not available."
            except Exception as ocr_err:
                return None, f"Could not extract text from the PDF. OCR failed: {str(ocr_err)}"

        if not text.strip():
            return None, "Could not extract any text from the PDF (including OCR)."

        # Fix common OCR misreads
        text = text.replace("É colier", "Écolier").replace("E colier", "Écolier")
        text = text.replace("Ecolier", "Écolier")

        rows_dict = _parse_grid_text(text)

        if not rows_dict:
            return None, "No grid answer rows found. Expected format: rows with level name followed by A-E answers."

        return rows_dict, None

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

    return rows_dict[row_name], None
