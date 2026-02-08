import subprocess
import os
from PIL import Image
from pathlib import Path

# Set Tesseract path for Homebrew installation
TESSERACT_PATHS = [
    '/opt/homebrew/bin/tesseract',
    '/usr/local/bin/tesseract',
    '/opt/homebrew/Cellar/tesseract/5.5.2/bin/tesseract',
    'tesseract'  # fallback to PATH
]


def find_tesseract():
    """Find Tesseract executable."""
    for path in TESSERACT_PATHS:
        if os.path.isfile(path):
            return path
        try:
            result = subprocess.run([path, '--version'],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                return path
        except FileNotFoundError:
            continue
    return None


def extract_text(image_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Returns extracted text or error message on failure.
    """
    tesseract_cmd = find_tesseract()

    if not tesseract_cmd:
        return "[OCR Error: Tesseract not found. Please install with 'brew install tesseract']"

    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip() if text.strip() else "[OCR returned empty - image may not contain readable text]"
    except Exception as e:
        print(f"OCR error: {e}")
        return f"[OCR Error: {str(e)}]"


if __name__ == "__main__":
    # Test with a sample image if available
    import sys
    if len(sys.argv) > 1:
        text = extract_text(sys.argv[1])
        print(text)
    else:
        print("Usage: python ocr.py <image_path>")
