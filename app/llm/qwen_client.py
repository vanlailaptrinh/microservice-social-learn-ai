"""
Qwen client via Ollama HTTP API.
CPU-friendly. Model configurable by .env.
"""

import re
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("ai-service")


class QwenClient:
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.QWEN_MODEL

    async def generate(
        self,
        prompt: str,
        max_new_tokens: int = 1200,
        temperature: float = 0.1,
        timeout: float = 180.0,
        require_vietnamese: bool = False,
    ) -> str:
        text = await self._generate_once(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            timeout=timeout,
        )

        if require_vietnamese and self._looks_english_dominant(text):
            logger.warning(
                "LLM output looks English-dominant; rewriting to Vietnamese. "
                "model=%s",
                self.model,
            )
            return await self._generate_once(
                prompt=self._build_vietnamese_rewrite_prompt(text),
                max_new_tokens=max_new_tokens,
                temperature=0.0,
                timeout=timeout,
            )

        return text

    async def _generate_once(
        self,
        prompt: str,
        max_new_tokens: int,
        temperature: float,
        timeout: float,
    ) -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
                "num_predict": max_new_tokens,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Make sure Ollama is running and model '{self.model}' is pulled."
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama HTTP error: {e.response.text}") from e
        except Exception as e:
            raise RuntimeError(f"Ollama generate failed: {e}") from e

        logger.info(
            "Ollama metrics: model=%s, max_new_tokens=%s, total=%.2fs, load=%.2fs, "
            "prompt_eval=%s tokens/%.2fs, eval=%s tokens/%.2fs",
            self.model,
            max_new_tokens,
            data.get("total_duration", 0) / 1_000_000_000,
            data.get("load_duration", 0) / 1_000_000_000,
            data.get("prompt_eval_count", 0),
            data.get("prompt_eval_duration", 0) / 1_000_000_000,
            data.get("eval_count", 0),
            data.get("eval_duration", 0) / 1_000_000_000,
        )

        raw_text = data.get("response", "").strip()
        text = self._clean_qwen_output(raw_text)
        if not text:
            logger.warning(
                "Ollama returned empty final answer after cleaning. "
                "Raw response length=%s, model=%s",
                len(raw_text),
                self.model,
            )
            raise RuntimeError(
                "LLM returned an empty final answer. "
                "The model may have generated only hidden thinking output."
            )
        return text

    def _clean_qwen_output(self, text: str) -> str:
        # Qwen3 đôi khi trả <think>...</think>, bỏ phần thinking nếu có.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
        return text

    def _looks_english_dominant(self, text: str) -> bool:
        words = re.findall(r"[a-zA-Z]+", text.lower())
        if len(words) < 12:
            return False

        vietnamese_chars = re.findall(
            r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
            text,
            flags=re.IGNORECASE,
        )
        english_markers = {
            "the", "and", "or", "is", "are", "was", "were", "based",
            "provided", "text", "context", "specific", "information",
            "document", "summary", "there", "this", "that", "with",
            "from", "about", "given", "seems", "according", "key",
            "details", "mentioned", "follows", "conversion", "reaction",
            "conditions", "optimization", "control",
        }
        marker_count = sum(1 for word in words if word in english_markers)
        marker_ratio = marker_count / len(words)

        return (
            marker_count >= 4
            and marker_ratio >= 0.08
            and len(vietnamese_chars) < max(6, len(words) * 0.08)
        )

    def _build_vietnamese_rewrite_prompt(self, text: str) -> str:
        return f"""
/no_think
Hãy viết lại nội dung sau bằng tiếng Việt tự nhiên, rõ ràng và dễ hiểu.

Yêu cầu:
- Giữ nguyên ý nghĩa, không thêm thông tin mới.
- Dịch tự nhiên theo ngữ cảnh học thuật, tránh dịch từng chữ máy móc.
- Nếu gặp cụm phổ thông trong tài liệu học thuật, hãy chuyển sang cách nói tiếng Việt tự nhiên.
- Chỉ giữ nguyên thuật ngữ kỹ thuật, tên riêng, tên sản phẩm, tên công nghệ,
  từ viết tắt hoặc ký hiệu nếu cần.
- Không viết quá trình suy nghĩ, không dùng thẻ <think>.
- Chỉ trả về phiên bản tiếng Việt cuối cùng.

NỘI DUNG:
{text}

BẢN TIẾNG VIỆT:
""".strip()


qwen_client = QwenClient()
