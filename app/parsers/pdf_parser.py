"""
PDF parser dùng PyMuPDF (fitz).
Trích xuất text theo từng trang.
"""

import logging
from typing import List, Dict

import fitz  # PyMuPDF

logger = logging.getLogger("ai-service")


def parse_pdf(file_path: str) -> List[Dict]:
    """
    Parse PDF file, trả về list page.

    Returns:
        [{"page_number": 1, "text": "..."}, ...]

    Raises:
        ValueError: Nếu file rỗng hoặc không trích xuất được text.
        RuntimeError: Nếu file hỏng.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise RuntimeError(f"Cannot open PDF file: {file_path}. Error: {e}")

    if doc.page_count == 0:
        doc.close()
        raise ValueError(f"PDF file is empty: {file_path}")

    pages: List[Dict] = []
    for i in range(doc.page_count):
        page = doc[i]
        text = page.get_text("text").strip()
        if text:
            pages.append({
                "page_number": i + 1,
                "text": text,
            })

    doc.close()

    if not pages:
        raise ValueError(
            f"No text content extracted from PDF: {file_path}. "
            "The file may be scanned/image-only."
        )

    logger.info(f"PDF parsed: {len(pages)} pages with text from {file_path}")
    return pages
