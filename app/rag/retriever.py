"""
Retriever — embed question then query MongoDB Vector Search.
"""

import logging
from typing import List, Optional

from fastapi.concurrency import run_in_threadpool

from app.rag.embedder import embedder
from app.db import mongo

logger = logging.getLogger("ai-service")


class Retriever:
    async def retrieve(
        self,
        post_id: str,
        question: str,
        top_k: int = 5,
        user_id: Optional[str] = None,
    ) -> List[dict]:
        query_vector = await run_in_threadpool(embedder.embed_text, question)

        chunks = await mongo.vector_search_chunks(
            query_vector=query_vector,
            post_id=post_id,
            top_k=top_k,
            user_id=user_id,
        )

        logger.info(
            "Retrieved %s chunks for post_id=%s",
            len(chunks),
            post_id,
        )
        return chunks


retriever = Retriever()