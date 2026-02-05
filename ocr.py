import pytesseract
from PIL import Image
from pathlib import Path


def extract_text(image_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Returns extracted text or empty string on failure.
    """
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        print(f"OCR error: {e}")
        return ""


if __name__ == "__main__":
    # Test with a sample image if available
    import sys
    if len(sys.argv) > 1:
        text = extract_text(sys.argv[1])
        print(text)
    else:
        print("Usage: python ocr.py <image_path>")
