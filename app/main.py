import logging
import re

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas import (
    HealthResponse,
    DocumentIndexRequest,
    DocumentIndexResponse,
    SummaryRequest,
    SummaryJobResponse,
    ChatRequest,
    ChatResponse,
    Citation,
)
from app.db import mongo
from app.rag.retriever import retriever
from app.rag.prompt import build_chat_prompt
from app.llm.qwen_client import qwen_client
from app.workers.document_worker import document_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-service")

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await mongo.connect_mongo()


@app.on_event("shutdown")
async def shutdown() -> None:
    await mongo.close_mongo_connection()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
    )


@app.post("/api/v1/documents/index", response_model=DocumentIndexResponse)
async def index_document(
    request: DocumentIndexRequest,
    background_tasks: BackgroundTasks,
) -> DocumentIndexResponse:
    job_id = await mongo.create_ai_job(
        post_id=request.post_id,
        user_id=request.user_id,
        file_url=request.file_url,
        file_type=request.file_type.value,
        file_name=request.file_name,
    )

    await mongo.update_post_ai_status(request.post_id, "INDEXING")

    background_tasks.add_task(
        document_worker.process_index_job,
        job_id,
        request.post_id,
        request.user_id,
        request.file_url,
        request.file_type.value,
        request.file_name,
    )

    return DocumentIndexResponse(
        job_id=job_id,
        post_id=request.post_id,
        status="PENDING",
        message="Document index job created. Chat will be available after chunks are ready.",
    )


def is_summary_question(question: str) -> bool:
    q = question.lower()
    keywords = [
        "tóm tắt",
        "tom tat",
        "summary",
        "tổng hợp",
        "tong hop",
        "nội dung chính",
        "noi dung chinh",
        "tài liệu này nói về",
        "tai lieu nay noi ve",
    ]
    return any(k in q for k in keywords)


@app.get("/api/v1/documents/{post_id}/index-status")
async def get_document_index_status(
    post_id: str,
    user_id: str = Query(...),
):
    job = await mongo.get_latest_job_by_post(
        post_id=post_id,
        user_id=user_id,
        job_type="INDEX",
    )

    chunk_count = await mongo.count_chunks_by_post(
        post_id=post_id,
        user_id=user_id,
    )

    if not job:
        return {
            "post_id": post_id,
            "user_id": user_id,
            "status": "NOT_FOUND",
            "chat_ready": chunk_count > 0,
            "chunk_count": chunk_count,
        }

    return {
        "job_id": str(job.get("_id")),
        "post_id": post_id,
        "user_id": user_id,
        "status": job.get("status"),
        "stage": job.get("stage"),
        "chat_ready": chunk_count > 0 and job.get("status") == "DONE",
        "chunk_count": chunk_count,
        "error_message": job.get("error_message"),
    }

def get_answer_style(question: str) -> str:
    q = question.strip().lower()
    words = re.findall(r"\w+", q, flags=re.UNICODE)
    word_count = len(words)

    long_signals = [
        "phân tích chi tiết",
        "trình bày đầy đủ",
        "giải thích kỹ",
        "so sánh chi tiết",
        "tổng hợp chi tiết",
        "liệt kê đầy đủ",
        "analyze in detail",
        "explain in detail",
        "detailed comparison",
        "comprehensive",
        "in depth",
    ]

    medium_signals = [
        "so sánh",
        "phân tích",
        "giải thích",
        "vì sao",
        "tại sao",
        "how",
        "why",
        "compare",
        "explain",
        "analyze",
        "list",
    ]

    concise_signals = [
        "là gì",
        "ngắn gọn",
        "tóm tắt",
        "nội dung gì",
        "ai là",
        "khi nào",
        "ở đâu",
        "bao nhiêu",
        "define",
        "briefly",
        "summary",
        "summarize",
    ]

    if any(k in q for k in long_signals):
        return "detailed"

    if any(k in q for k in concise_signals):
        return "concise"

    if word_count <= 8 and not any(k in q for k in medium_signals):
        return "concise"

    if any(k in q for k in medium_signals):
        return "balanced"

    return "balanced"


def get_max_tokens(question: str) -> int:
    style = get_answer_style(question)
    if style == "detailed":
        return 900
    if style == "concise":
        return 220
    return 500

@app.post("/api/v1/documents/summary", response_model=SummaryJobResponse)
async def summarize_document(
    request: SummaryRequest,
    background_tasks: BackgroundTasks,
) -> SummaryJobResponse:
    chunk_count = await mongo.count_chunks_by_post(
        post_id=request.post_id,
        user_id=request.user_id,
    )

    if chunk_count == 0:
        raise HTTPException(
            status_code=409,
            detail="Document is not indexed yet. Please wait until chat_ready=true.",
        )

    job_id = await mongo.create_summary_job(
        post_id=request.post_id,
        user_id=request.user_id,
    )

    existing_summary = await mongo.get_summary_by_post_id(
        post_id=request.post_id,
        user_id=request.user_id,
    )

    if existing_summary and existing_summary.get("summary_text"):
        await mongo.update_ai_job_status(
            job_id,
            "DONE",
            stage="SUMMARY_ALREADY_EXISTS",
            chat_ready=True,
            summary_ready=True,
            chunk_count=chunk_count,
        )

        return SummaryJobResponse(
            job_id=job_id,
            post_id=request.post_id,
            status="DONE",
            message="Summary already exists.",
        )

    background_tasks.add_task(
        document_worker.process_summary_job,
        job_id,
        request.post_id,
        request.user_id,
    )

    return SummaryJobResponse(
        job_id=job_id,
        post_id=request.post_id,
        status="PENDING",
        message="Summary job created.",
    )


@app.get("/api/v1/documents/{post_id}/summary")
async def get_document_summary(
    post_id: str,
    user_id: str = Query(...),
):
    summary = await mongo.get_summary_by_post_id(
        post_id=post_id,
        user_id=user_id,
    )

    if summary and summary.get("summary_text"):
        return {
            "post_id": post_id,
            "user_id": user_id,
            "status": "READY",
            "summary_ready": True,
            "summary_text": summary.get("summary_text"),
            "key_points": summary.get("key_points", []),
            "updated_at": summary.get("updated_at"),
        }

    latest_summary_job = await mongo.get_latest_job_by_post(
        post_id=post_id,
        user_id=user_id,
        job_type="SUMMARY",
    )

    if latest_summary_job:
        return {
            "post_id": post_id,
            "user_id": user_id,
            "status": latest_summary_job.get("status"),
            "stage": latest_summary_job.get("stage"),
            "summary_ready": False,
            "summary_text": None,
            "key_points": [],
            "error_message": latest_summary_job.get("error_message"),
        }

    return {
        "post_id": post_id,
        "user_id": user_id,
        "status": "NOT_FOUND",
        "summary_ready": False,
        "summary_text": None,
        "key_points": [],
        "error_message": "Summary has not been created yet.",
    }

@app.get("/api/v1/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await mongo.get_ai_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job.get("_id")),
        "job_type": job.get("job_type"),
        "post_id": job.get("post_id"),
        "user_id": job.get("user_id"),
        "file_name": job.get("file_name"),
        "status": job.get("status"),
        "stage": job.get("stage"),
        "chat_ready": job.get("chat_ready", False),
        "summary_ready": job.get("summary_ready", False),
        "chunk_count": job.get("chunk_count", 0),
        "error_message": job.get("error_message"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    chunk_count = await mongo.count_chunks_by_post(
        post_id=request.post_id,
        user_id=request.user_id,
    )

    if chunk_count == 0:
        return ChatResponse(
            answer="Tài liệu chưa index xong. Vui lòng đợi đến khi chat_ready=true.",
            citations=[],
        )

    chunks = await retriever.retrieve(
        post_id=request.post_id,
        user_id=request.user_id,
        question=request.question,
        top_k=request.top_k,
    )

    if not chunks:
        return ChatResponse(
            answer="Không tìm thấy nội dung liên quan trong tài liệu.",
            citations=[],
        )

    answer_style = get_answer_style(request.question)
    prompt = build_chat_prompt(request.question, chunks, answer_style=answer_style)
    max_tokens = get_max_tokens(request.question)

    try:
        answer = await qwen_client.generate(
            prompt,
            max_new_tokens=max_tokens,
            temperature=0.0,
            require_vietnamese=True,
        )
    except Exception as e:
        logger.exception("LLM generate failed")
        raise HTTPException(status_code=500, detail=str(e))

    citations = [
        Citation(
            page_number=c.get("page_number"),
            chunk_index=c.get("chunk_index", 0),
            content_preview=(c.get("content", "")[:220] + "..."),
        )
        for c in chunks
    ]

    await mongo.save_chat_history(
        post_id=request.post_id,
        user_id=request.user_id,
        question=request.question,
        answer=answer,
        citations=[c.model_dump() for c in citations],
    )

    return ChatResponse(
        answer=answer,
        citations=citations,
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
