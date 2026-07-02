"""
Prompt builder for RAG chat and summarization.
"""


def build_chat_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = []

    for c in chunks:
        page = c.get("page_number", "N/A")
        idx = c.get("chunk_index", "N/A")
        content = c.get("content", "")
        context_blocks.append(
            f"[Page {page}, Chunk {idx}]\n{content}"
        )

    context = "\n\n---\n\n".join(context_blocks)

    return f"""
Bạn là trợ lý AI cho hệ thống mạng xã hội học tập.

Nhiệm vụ:
- Chỉ trả lời dựa trên CONTEXT bên dưới.
- Nếu CONTEXT không có thông tin, hãy nói: "Tài liệu không nêu rõ thông tin này."
- Không bịa thêm kiến thức ngoài tài liệu.
- Trả lời bằng tiếng Việt, rõ ràng, dễ hiểu.
- Nếu phù hợp, hãy trình bày theo bullet points.

QUESTION:
{question}

CONTEXT:
{context}

ANSWER:
""".strip()


def build_summary_prompt(text: str) -> str:
    return f"""
Hãy tóm tắt tài liệu học tập sau bằng tiếng Việt.

Yêu cầu:
- Tóm tắt ngắn gọn nhưng đủ ý.
- Nêu các ý chính quan trọng.
- Không bịa nội dung không có trong tài liệu.
- Trình bày dễ đọc.

DOCUMENT:
{text}

SUMMARY:
""".strip()


def build_final_summary_prompt(partial_summaries: list[str]) -> str:
    joined = "\n\n---\n\n".join(partial_summaries)

    return f"""
Dưới đây là các bản tóm tắt từng phần của một tài liệu.

Hãy tổng hợp lại thành một bản tóm tắt cuối cùng bằng tiếng Việt.

Yêu cầu:
- Gộp các ý trùng lặp.
- Giữ ý chính quan trọng.
- Viết rõ ràng, dễ hiểu.
- Có thể chia thành các gạch đầu dòng.

PARTIAL SUMMARIES:
{joined}

FINAL SUMMARY:
""".strip()