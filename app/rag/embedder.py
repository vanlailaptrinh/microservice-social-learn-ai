"""
BGE-M3 Embedder.
Lazy-load singleton, chạy CPU, normalize embeddings.
"""

import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = logging.getLogger("ai-service")


class Embedder:
    """Singleton embedder using BAAI/bge-m3."""

    _instance = None
    _model: SentenceTransformer = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self) -> None:
        if self._model is not None:
            return
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL} ...")
        self._model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device="cpu",
        )
        logger.info(
            f"✅ Embedding model loaded. "
            f"Dim={self._model.get_sentence_embedding_dimension()}"
        )

    def embed_text(self, text: str) -> List[float]:
        """Embed single text → vector (1024-dim)."""
        self._load_model()
        embedding = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed batch of texts → list of vectors."""
        if not texts:
            return []
        self._load_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        # Đảm bảo JSON serializable
        if isinstance(embeddings, np.ndarray):
            return embeddings.tolist()
        return [e.tolist() if hasattr(e, "tolist") else list(e) for e in embeddings]


# Singleton instance
embedder = Embedder()
