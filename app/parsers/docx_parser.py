"""
DOCX parser dùng python-docx.
Trích xuất text từ tất cả paragraphs.
"""

import logging
from typing import List, Dict

from docx import Document

logger = logging.getLogger("ai-service")


def parse_docx(file_path: str) -> List[Dict]:
    """
    Parse DOCX file, trả về list page.
    DOCX không có page thật nên gom hết vào page_number=1.

    Returns:
        [{"page_number": 1, "text": "..."}]

    Raises:
        ValueError: Nếu file rỗng.
        RuntimeError: Nếu file hỏng.
    """
    try:
        doc = Document(file_path)
    except Exception as e:
        raise RuntimeError(f"Cannot open DOCX file: {file_path}. Error: {e}")

    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    if not paragraphs:
        raise ValueError(f"No text content extracted from DOCX: {file_path}")

    full_text = "\n".join(paragraphs)

    logger.info(
        f"DOCX parsed: {len(paragraphs)} paragraphs from {file_path}"
    )
    return [{"page_number": 1, "text": full_text}]
