"""
Prompt builder for RAG chat and summarization.
"""


ANSWER_STYLE_INSTRUCTIONS = {
    "concise": (
        "Trả lời bằng 1 đoạn ngắn, tối đa 2-3 câu. "
        "Không đưa ví dụ, danh sách dài hoặc giải thích mở rộng nếu QUESTION không yêu cầu."
    ),
    "balanced": (
        "Trả lời vừa đủ ý, ưu tiên 1-2 đoạn ngắn hoặc vài bullet nếu cần."
    ),
    "detailed": (
        "Trả lời đầy đủ hơn, có thể chia ý hoặc dùng bullet để làm rõ các điểm quan trọng."
    ),
}


def build_chat_prompt(question: str, chunks: list[dict], answer_style: str = "balanced") -> str:
    context_blocks = []

    for c in chunks:
        page = c.get("page_number", "N/A")
        idx = c.get("chunk_index", "N/A")
        content = c.get("content", "")
        context_blocks.append(
            f"[Page {page}, Chunk {idx}]\n{content}"
        )

    context = "\n\n---\n\n".join(context_blocks)
    style_instruction = ANSWER_STYLE_INSTRUCTIONS.get(
        answer_style,
        ANSWER_STYLE_INSTRUCTIONS["balanced"],
    )

    return f"""
/no_think
Bạn là trợ lý AI cho hệ thống mạng xã hội học tập.

Nhiệm vụ:
- Chỉ trả lời dựa trên CONTEXT bên dưới.
- CONTEXT có thể bằng tiếng Anh hoặc tiếng Việt. Nếu CONTEXT có thông tin liên quan
  đến QUESTION, kể cả khác ngôn ngữ, hãy dùng thông tin đó để trả lời bằng tiếng Việt.
- Ưu tiên đoạn CONTEXT trả lời trực tiếp nhất cho QUESTION.
- Chỉ nói "Tài liệu không nêu rõ thông tin này." khi tất cả đoạn CONTEXT đều không
  chứa thông tin liên quan đến QUESTION.
- Không bịa thêm kiến thức ngoài tài liệu.
- BẮT BUỘC trả lời bằng tiếng Việt trong mọi trường hợp.
- Nếu CONTEXT là tiếng Anh, hãy dịch và diễn giải ý liên quan sang tiếng Việt tự nhiên.
- Không được trả lời bằng tiếng Anh, trừ thuật ngữ kỹ thuật, tên riêng, tên sản phẩm,
  tên công nghệ, từ viết tắt hoặc ký hiệu xuất hiện trong tài liệu.
- Trả lời bằng tiếng Việt, rõ ràng, dễ hiểu.
- Dịch thuật ngữ phổ thông sang tiếng Việt tự nhiên; chỉ giữ nguyên thuật ngữ kỹ thuật
  chuyên ngành, tên riêng, tên sản phẩm, tên công nghệ, từ viết tắt hoặc ký hiệu
  xuất hiện trong tài liệu.
- Trả lời thẳng vào nội dung, không mở đầu bằng các cụm như "Dựa trên CONTEXT",
  "Theo CONTEXT", "Trả lời trực tiếp nhất", hoặc nhắc lại QUESTION.
- Độ dài câu trả lời: {style_instruction}
- Không viết quá trình suy nghĩ, không dùng thẻ <think>, chỉ trả về câu trả lời cuối cùng.
- Nếu phù hợp, hãy trình bày theo bullet points.

QUESTION:
{question}

CONTEXT:
{context}

ANSWER:
""".strip()


def build_summary_prompt(text: str) -> str:
    return f"""
/no_think
Hãy tóm tắt tài liệu học tập sau bằng tiếng Việt.

Yêu cầu:
- BẮT BUỘC toàn bộ bản tóm tắt phải bằng tiếng Việt.
- Nếu tài liệu gốc là tiếng Anh, hãy dịch ý chính sang tiếng Việt tự nhiên.
- Không được viết bản tóm tắt bằng tiếng Anh, trừ thuật ngữ kỹ thuật, tên riêng,
  tên sản phẩm, tên công nghệ, từ viết tắt hoặc ký hiệu xuất hiện trong tài liệu.
- Tóm tắt ngắn gọn nhưng đủ ý.
- Nêu các ý chính quan trọng.
- Không bịa nội dung không có trong tài liệu.
- Trình bày dễ đọc.
- Không viết quá trình suy nghĩ, không dùng thẻ <think>, chỉ trả về bản tóm tắt cuối cùng.

DOCUMENT:
{text}

SUMMARY:
""".strip()


def build_final_summary_prompt(partial_summaries: list[str]) -> str:
    joined = "\n\n---\n\n".join(partial_summaries)

    return f"""
/no_think
Dưới đây là các bản tóm tắt từng phần của một tài liệu.

Hãy tổng hợp lại thành một bản tóm tắt cuối cùng bằng tiếng Việt.

Yêu cầu:
- BẮT BUỘC toàn bộ bản tóm tắt cuối cùng phải bằng tiếng Việt.
- Nếu các bản tóm tắt từng phần có tiếng Anh, hãy dịch và diễn giải lại sang tiếng Việt tự nhiên.
- Không được viết bản tóm tắt cuối cùng bằng tiếng Anh, trừ thuật ngữ kỹ thuật,
  tên riêng, tên sản phẩm, tên công nghệ, từ viết tắt hoặc ký hiệu xuất hiện trong tài liệu.
- Gộp các ý trùng lặp.
- Giữ ý chính quan trọng.
- Viết rõ ràng, dễ hiểu.
- Có thể chia thành các gạch đầu dòng.
- Không viết quá trình suy nghĩ, không dùng thẻ <think>, chỉ trả về bản tóm tắt cuối cùng.

PARTIAL SUMMARIES:
{joined}

FINAL SUMMARY:
""".strip()
