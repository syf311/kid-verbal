import re
import pdfplumber


def parse_science_bowl_pdf(pdf_path):
    """Parse a Science Bowl PDF into structured questions.

    Returns (questions_list, error_string).
        questions_list: list of dicts on success
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

        # Extract round name from text (e.g., "ROUND 1")
        round_match = re.search(r'ROUND\s+(\d+)', text, re.IGNORECASE)
        round_name = f"Round {round_match.group(1)}" if round_match else ""

        # Remove footer lines like "Middle School Round 1 Page 1"
        text = re.sub(r'(?:Middle|High)\s+School\s+Round\s+\d+\s+Page\s+\d+', '', text)

        questions = []

        # Split into blocks by TOSS-UP / BONUS markers
        blocks = re.split(r'\n(?=(?:TOSS-UP|BONUS)\s*\n)', text)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Determine question type
            if block.startswith('TOSS-UP'):
                q_type = 'toss_up'
                block = block[len('TOSS-UP'):].strip()
            elif block.startswith('BONUS'):
                q_type = 'bonus'
                block = block[len('BONUS'):].strip()
            else:
                continue

            # Strip leading stray lines that are just numbers (PDF artifacts from fractions etc.)
            lines = block.split('\n')
            while lines and re.match(r'^\d+$', lines[0].strip()):
                # Only strip if next line looks like a question start (N) CATEGORY)
                if len(lines) > 1 and re.match(r'\d+\)', lines[1].strip()):
                    lines.pop(0)
                else:
                    break
            block = '\n'.join(lines)

            # Parse the question line: N) CATEGORY (Short Answer|Multiple Choice) question text
            q_match = re.match(
                r'(\d+)\)\s+'
                r'(LIFE SCIENCE|PHYSICAL SCIENCE|EARTH SCIENCE|EARTH AND SPACE|GENERAL SCIENCE|MATH|ENERGY|BIOLOGY|CHEMISTRY|PHYSICS)\s+'
                r'(Short Answer|Multiple Choice)\s+'
                r'(.+)',
                block, re.DOTALL | re.IGNORECASE
            )

            if not q_match:
                continue

            q_num = int(q_match.group(1))
            category = q_match.group(2).upper()
            answer_format = 'short_answer' if 'short' in q_match.group(3).lower() else 'multiple_choice'
            rest = q_match.group(4)

            # Normalize category names
            category_map = {
                'BIOLOGY': 'LIFE SCIENCE',
                'CHEMISTRY': 'PHYSICAL SCIENCE',
                'PHYSICS': 'PHYSICAL SCIENCE',
                'EARTH AND SPACE': 'EARTH SCIENCE',
            }
            category = category_map.get(category, category)

            choices = None
            correct_answer = ""
            explanation = ""

            if answer_format == 'multiple_choice':
                # Extract question text (everything before first choice line)
                q_text_match = re.match(r'(.+?)(?=\n[WXYZABCD]\))', rest, re.DOTALL)
                if q_text_match:
                    question_text = re.sub(r'\s+', ' ', q_text_match.group(1)).strip()
                else:
                    question_text = re.sub(r'\s+', ' ', rest.split('\n')[0]).strip()

                # Remove trailing colon
                if question_text.endswith(':'):
                    question_text = question_text[:-1].strip()

                # Extract choices
                choice_matches = re.findall(r'([WXYZABCD])\)\s*(.+?)(?=\n[WXYZABCD]\)|\nANSWER:)', rest, re.DOTALL)
                if choice_matches:
                    choices = {}
                    for letter, choice_text in choice_matches:
                        choices[letter.upper()] = re.sub(r'\s+', ' ', choice_text).strip()

                # Extract answer
                ans_match = re.search(r'ANSWER:\s*([WXYZABCD])\)\s*(.*)', rest, re.IGNORECASE)
                if ans_match:
                    correct_answer = ans_match.group(1).upper()
                    ans_text = ans_match.group(2).strip()
                    if choices and correct_answer in choices:
                        explanation = f"The answer is {correct_answer}) {choices[correct_answer]}"
                    elif ans_text:
                        explanation = f"The answer is {correct_answer}) {ans_text}"
            else:
                # Short answer - question text is everything before ANSWER:
                parts = re.split(r'\nANSWER:', rest, flags=re.IGNORECASE)
                question_text = re.sub(r'\s+', ' ', parts[0]).strip()
                if question_text.endswith(':'):
                    question_text = question_text[:-1].strip()

                if len(parts) > 1:
                    correct_answer = parts[1].strip().split('\n')[0].strip()
                    explanation = f"Answer: {correct_answer}"

            if not correct_answer:
                continue

            questions.append({
                'number': q_num,
                'question_type': q_type,
                'category': category,
                'answer_format': answer_format,
                'question_text': question_text,
                'choices': choices,
                'correct_answer': correct_answer,
                'explanation': explanation,
                'round_name': round_name,
            })

        if not questions:
            return None, "No Science Bowl questions found in the PDF. Expected format: TOSS-UP/BONUS markers with numbered questions."

        return questions, None

    except Exception as e:
        return None, f"Error reading PDF: {str(e)}"
