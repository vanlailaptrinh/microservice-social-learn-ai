"""
Text cleaner + chunker.
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger("ai-service")


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def chunk_pages(
    pages: List[Dict],
    chunk_size: int = 900,
    chunk_overlap: int = 120,
) -> List[Dict]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: List[Dict] = []
    chunk_index = 0

    for page in pages:
        page_number = page["page_number"]
        text = clean_text(page.get("text", ""))

        if not text:
            continue

        words = text.split()

        if len(words) <= chunk_size:
            content = " ".join(words)
            if len(content) > 20:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "page_number": page_number,
                        "content": content,
                    }
                )
                chunk_index += 1
            continue

        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            content = " ".join(words[start:end])

            if len(content) > 20:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "page_number": page_number,
                        "content": content,
                    }
                )
                chunk_index += 1

            if end >= len(words):
                break

            start = end - chunk_overlap

    logger.info("Chunking done: %s chunks created", len(chunks))
    return chunks