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
        temperature: float = 0.3,
        timeout: float = 180.0,
    ) -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
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

        text = data.get("response", "").strip()
        return self._clean_qwen_output(text)

    def _clean_qwen_output(self, text: str) -> str:
        # Qwen3 đôi khi trả <think>...</think>, bỏ phần thinking nếu có.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        return text


qwen_client = QwenClient()