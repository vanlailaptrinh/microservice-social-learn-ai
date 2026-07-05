"""
Image OCR parser using Tesseract.
"""

import logging
from typing import Dict, List

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("ai-service")


def parse_image(file_path: str) -> List[Dict]:
    """
    Parse image file with OCR, returning a single pseudo-page.

    Returns:
        [{"page_number": 1, "text": "..."}]
    """
    try:
        with Image.open(file_path) as img:
            image = ImageOps.exif_transpose(img).convert("RGB")
    except UnidentifiedImageError as e:
        raise RuntimeError(f"Cannot open image file: {file_path}. Error: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Image OCR failed while opening file: {file_path}. Error: {e}") from e

    try:
        text = pytesseract.image_to_string(image, lang="vie+eng").strip()
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError("Tesseract OCR binary is not installed or not found in PATH.") from e
    except Exception as e:
        raise RuntimeError(f"Image OCR failed: {file_path}. Error: {e}") from e

    if not text:
        raise ValueError(
            f"No text content extracted from image: {file_path}. "
            "The image may be blurry, handwritten, or contain no readable text."
        )

    logger.info("Image OCR parsed: 1 page with text from %s", file_path)
    return [{"page_number": 1, "text": text}]
