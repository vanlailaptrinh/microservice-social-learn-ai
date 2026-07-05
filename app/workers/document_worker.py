"""
Document worker pipeline:
download -> parse -> chunk -> embed -> save MongoDB -> summarize.
"""

import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import httpx
from fastapi.concurrency import run_in_threadpool

from app.config import settings
from app.db import mongo
from app.parsers.pdf_parser import parse_pdf
from app.parsers.docx_parser import parse_docx
from app.parsers.image_parser import parse_image
from app.rag.chunker import chunk_pages
from app.rag.embedder import embedder
from app.rag.prompt import build_summary_prompt, build_final_summary_prompt
from app.llm.qwen_client import qwen_client

logger = logging.getLogger("ai-service")


class DocumentWorker:
    async def process_index_job(
        self,
        job_id: str,
        post_id: str,
        user_id: str,
        file_url: str,
        file_type: str,
        file_name: str,
    ) -> None:
        tmp_path: str | None = None

        try:
            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="DOWNLOADING",
                chat_ready=False,
                summary_ready=False,
            )
            await mongo.update_post_ai_status(post_id, "INDEXING")

            tmp_path = await self._download_file(file_url, file_name)

            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="PARSING",
            )

            pages = await self._parse_file(tmp_path, file_type)

            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="CHUNKING",
            )

            chunks = chunk_pages(
                pages=pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
            )

            if not chunks:
                raise ValueError("No chunks created from document.")

            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="EMBEDDING",
                chunk_count=len(chunks),
            )

            await mongo.delete_old_chunks_by_post(post_id)

            contents = [c["content"] for c in chunks]
            embeddings = await run_in_threadpool(embedder.embed_texts, contents)

            now = datetime.now(timezone.utc)
            chunk_docs = []

            for chunk, emb in zip(chunks, embeddings):
                chunk_docs.append(
                    {
                        "post_id": post_id,
                        "user_id": user_id,
                        "chunk_index": chunk["chunk_index"],
                        "page_number": chunk.get("page_number"),
                        "content": chunk["content"],
                        "embedding": emb,
                        "metadata": {
                            "file_name": file_name,
                            "file_type": file_type,
                        },
                        "created_at": now,
                    }
                )

            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="SAVING_CHUNKS",
            )

            inserted_count = await mongo.insert_chunks(chunk_docs)

            await mongo.update_ai_job_status(
                job_id,
                "DONE",
                stage="INDEX_DONE",
                chat_ready=True,
                summary_ready=False,
                chunk_count=inserted_count,
            )

            await mongo.update_post_ai_status(post_id, "CHAT_READY")

            logger.info(
                "✅ Document index done: post_id=%s, chunks=%s",
                post_id,
                inserted_count,
            )

        except Exception as e:
            logger.exception("Index job failed: post_id=%s", post_id)

            err = str(e)
            try:
                await mongo.update_ai_job_status(
                    job_id,
                    "FAILED",
                    err,
                    stage="FAILED",
                    chat_ready=False,
                    summary_ready=False,
                )
                await mongo.update_post_ai_status(post_id, "FAILED")
            except Exception:
                logger.exception("Failed to update FAILED status")

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    logger.warning("Cannot remove temp file: %s", tmp_path)

    async def process_summary_job(
        self,
        job_id: str,
        post_id: str,
        user_id: str,
    ) -> None:
        try:
            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="LOADING_CHUNKS",
                chat_ready=True,
                summary_ready=False,
            )

            chunks = await mongo.get_chunks_by_post(
                post_id=post_id,
                user_id=user_id,
            )

            if not chunks:
                raise ValueError(
                    "Document has no chunks yet. Please run index job first."
                )

            await mongo.update_ai_job_status(
                job_id,
                "PROCESSING",
                stage="SUMMARIZING",
                chunk_count=len(chunks),
            )

            summary_text = await self._summarize_chunks(chunks)

            await mongo.save_summary(
                post_id=post_id,
                user_id=user_id,
                summary_text=summary_text,
                key_points=[],
            )

            await mongo.update_ai_job_status(
                job_id,
                "DONE",
                stage="SUMMARY_DONE",
                chat_ready=True,
                summary_ready=True,
                chunk_count=len(chunks),
            )

            await mongo.update_post_ai_status(post_id, "READY")

            logger.info("✅ Summary done: post_id=%s", post_id)

        except Exception as e:
            logger.exception("Summary job failed: post_id=%s", post_id)

            err = str(e)
            try:
                await mongo.update_ai_job_status(
                    job_id,
                    "FAILED",
                    err,
                    stage="FAILED",
                    chat_ready=True,
                    summary_ready=False,
                )
            except Exception:
                logger.exception("Failed to update summary FAILED status")

    async def _download_file(self, file_url: str, file_name: str) -> str:
        os.makedirs(settings.TEMP_DIR, exist_ok=True)

        safe_name = Path(file_name).name
        tmp_path = os.path.join(settings.TEMP_DIR, safe_name)

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(file_url)
            resp.raise_for_status()

        with open(tmp_path, "wb") as f:
            f.write(resp.content)

        logger.info("Downloaded file to %s", tmp_path)
        return tmp_path

    async def _parse_file(self, file_path: str, file_type: str) -> List[dict]:
        ft = file_type.lower()

        if ft == "pdf":
            return await run_in_threadpool(parse_pdf, file_path)

        if ft == "docx":
            return await run_in_threadpool(parse_docx, file_path)

        if ft in {"jpg", "jpeg", "png", "webp"}:
            return await run_in_threadpool(parse_image, file_path)

        raise ValueError(f"Unsupported file type: {file_type}")

    async def _summarize_chunks(self, chunks: List[dict]) -> str:
        """
        Summary theo kiểu hierarchical:
        - Nếu ít chunk: tóm tắt trực tiếp.
        - Nếu nhiều chunk: tóm tắt từng nhóm rồi tổng hợp lần cuối.
        """
        group_size = 6
        partial_summaries: list[str] = []

        for i in range(0, len(chunks), group_size):
            group = chunks[i:i + group_size]
            text = "\n\n".join(c["content"] for c in group)
            prompt = build_summary_prompt(text)

            summary = await qwen_client.generate(
                prompt,
                max_new_tokens=700,
                temperature=0.0,
                require_vietnamese=True,
            )
            partial_summaries.append(summary)

        if len(partial_summaries) == 1:
            return partial_summaries[0]

        final_prompt = build_final_summary_prompt(partial_summaries)
        return await qwen_client.generate(
            final_prompt,
            max_new_tokens=1000,
            temperature=0.0,
            require_vietnamese=True,
        )


document_worker = DocumentWorker()
