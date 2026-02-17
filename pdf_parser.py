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


def _ocr_grid_image(pdf_path):
    """Extract answers from a grid image PDF using cell-by-cell OCR with clustering.

    Returns rows_dict or None.
    """
    import pytesseract
    from PIL import Image, ImageOps
    import io
    import numpy as np

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        img = page.to_image(resolution=600)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        pil_img = Image.open(buf).convert("L")
        arr = np.array(pil_img)
        h, w = arr.shape

    # Detect vertical grid lines
    col_dark = np.mean(arr < 128, axis=0)
    v_edges = []
    in_line = False
    start = 0
    for c in range(w):
        if col_dark[c] > 0.35:
            if not in_line:
                start = c
                in_line = True
        else:
            if in_line:
                v_edges.append((start, c))
                in_line = False

    if len(v_edges) < 3:
        return None

    # Detect horizontal dark bands (header + bottom border)
    row_dark = np.mean(arr < 128, axis=1)
    h_bands = []
    in_band = False
    for r in range(h):
        if row_dark[r] > 0.3:
            if not in_band:
                start = r
                in_band = True
        else:
            if in_band:
                h_bands.append((start, r))
                in_band = False

    if len(h_bands) < 2:
        return None

    header_band = h_bands[0]
    bottom_band = h_bands[-1]
    data_top = header_band[1] + 4
    data_bottom = bottom_band[0] - 4

    # Determine number of data rows based on vertical space
    total_height = data_bottom - data_top
    # Estimate row count: try 6 (standard Kangaroo), validate by checking
    # if rows have content
    num_rows = 6
    row_height = total_height / num_rows

    if row_height < 20:
        return None

    CELL_SIZE = 40
    margin = 14
    num_answer_cols = min(30, len(v_edges) - 2)

    def extract_cell_features(r, c):
        y1 = int(data_top + r * row_height) + margin
        y2 = int(data_top + (r + 1) * row_height) - margin
        x1 = v_edges[c + 1][1] + 8
        x2 = v_edges[c + 2][0] - 8
        cell = arr[y1:y2, x1:x2].astype(float)
        bg = np.percentile(cell, 80)
        cell = bg - cell
        cell = np.clip(cell, 0, None)
        cell_max = cell.max()
        if cell_max > 10:
            cell = cell / cell_max
        else:
            cell = np.zeros_like(cell)
        cell_img = Image.fromarray((cell * 255).astype(np.uint8), mode="L")
        cell_img = cell_img.resize((CELL_SIZE, CELL_SIZE), Image.LANCZOS)
        return np.array(cell_img, dtype=float) / 255.0

    # Extract all cells
    cells = []
    for r in range(num_rows):
        for c in range(num_answer_cols):
            feat = extract_cell_features(r, c)
            ink = np.mean(feat > 0.3)
            cells.append((r, c, feat, ink))

    content = [(r, c, f) for r, c, f, ink in cells if ink > 0.02]
    if not content:
        return None

    features = np.array([f.flatten() for _, _, f in content])

    # K-means clustering (K=12, over-segment then label)
    K = min(12, len(content))
    np.random.seed(42)
    centroids = [features[0]]
    for _ in range(K - 1):
        dists = np.array([min(np.sum((f - c) ** 2) for c in centroids) for f in features])
        centroids.append(features[np.argmax(dists)])
    centroids = np.array(centroids)

    for _ in range(30):
        labels = np.array(
            [np.argmin([np.sum((f - c) ** 2) for c in centroids]) for f in features]
        )
        new_centroids = []
        for k in range(K):
            members = features[labels == k]
            new_centroids.append(members.mean(axis=0) if len(members) > 0 else centroids[k])
        centroids = np.array(new_centroids)

    # OCR multiple representatives from each cluster to determine the letter
    cluster_letters = {}
    for k in range(K):
        member_indices = np.where(labels == k)[0]
        if len(member_indices) == 0:
            continue

        votes = {}
        dists = [np.sum((features[i] - centroids[k]) ** 2) for i in member_indices]
        sorted_members = [member_indices[j] for j in np.argsort(dists)]

        for idx in sorted_members[:8]:
            r, c, _ = content[idx]
            y1 = int(data_top + r * row_height) + margin
            y2 = int(data_top + (r + 1) * row_height) - margin
            x1 = v_edges[c + 1][1] + 8
            x2 = v_edges[c + 2][0] - 8
            cell = pil_img.crop((x1, y1, x2, y2))
            cell = cell.resize((100, 100), Image.LANCZOS)
            ca = np.array(cell)
            ca = np.where(ca < 120, 0, 255).astype(np.uint8)
            cell = Image.fromarray(ca, mode="L")
            cell = ImageOps.expand(cell, border=50, fill=255)
            letter = pytesseract.image_to_string(
                cell, config="--psm 10 -c tessedit_char_whitelist=ABCDE"
            ).strip()
            if letter and letter[0] in "ABCDE":
                l = letter[0]
                votes[l] = votes.get(l, 0) + 1

        if votes:
            cluster_letters[k] = max(votes, key=votes.get)

    # Assign letters to cells
    results = {}
    for i, (r, c, _) in enumerate(content):
        k = labels[i]
        letter = cluster_letters.get(k, "")
        if letter in "ABCDE":
            if r not in results:
                results[r] = {}
            results[r][str(c + 1)] = letter

    # OCR level names
    rows_dict = {}
    for row_idx in range(num_rows):
        y1 = int(data_top + row_idx * row_height) + margin
        y2 = int(data_top + (row_idx + 1) * row_height) - margin
        lx1 = v_edges[0][1] + 8
        lx2 = v_edges[1][0] - 8
        name_img = pil_img.crop((lx1, y1, lx2, y2))
        na = np.array(name_img)
        na[na > 140] = 255
        name_img = Image.fromarray(na, mode="L")
        name_img = ImageOps.expand(name_img, border=20, fill=255)
        name = pytesseract.image_to_string(name_img, config="--psm 7").strip().rstrip(".")
        # Normalize common OCR misreads
        for bad in ("Fcolier", "Foolier", "Ecolier", "Eécolier", "Feolier"):
            name = name.replace(bad, "Écolier")

        ans = results.get(row_idx, {})
        if ans:
            rows_dict[name] = ans

    return rows_dict if rows_dict else None


def parse_grid_answer_pdf(pdf_path):
    """Extract answers from a grid/table answer-key PDF (e.g. Math Kangaroo).

    Expected format: rows where each line is:
        <LevelName> <A-E or -> <A-E or -> ... (up to 30 answers)
    preceded by a header row of column numbers (1 2 3 ... 30).

    Falls back to cell-by-cell OCR for image-based PDFs.

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

        if text.strip():
            # Fix common OCR misreads
            text = text.replace("É colier", "Écolier").replace("E colier", "Écolier")
            text = text.replace("Ecolier", "Écolier")

            rows_dict = _parse_grid_text(text)
            if rows_dict:
                return rows_dict, None

        # Fall back to cell-by-cell OCR for image-based PDFs
        try:
            rows_dict = _ocr_grid_image(pdf_path)
        except ImportError:
            return None, "Could not extract text from the PDF and OCR (pytesseract/numpy) is not available."
        except Exception as ocr_err:
            return None, f"Could not extract text from the PDF. OCR failed: {str(ocr_err)}"

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

    # Filter out any empty or invalid entries
    answers = {k: v for k, v in rows_dict[row_name].items() if v in "ABCDE"}
    return answers, None
