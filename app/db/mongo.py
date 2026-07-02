"""
MongoDB async client + repository helpers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger("ai-service")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _post_id_filter(post_id: str) -> dict:
    """
    BE có thể lưu posts._id là string hoặc ObjectId.
    Hàm này giúp update được cả 2 trường hợp.
    """
    filters: list[Any] = [post_id]

    try:
        filters.append(ObjectId(post_id))
    except (InvalidId, TypeError):
        pass

    return {"_id": {"$in": filters}}


def _to_object_id(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def connect_mongo() -> None:
    global _client, _db

    _client = AsyncIOMotorClient(settings.MONGO_URI)
    _db = _client[settings.MONGO_DB_NAME]

    await _client.admin.command("ping")

    # Normal indexes. Vector Search index phải tạo trong MongoDB Atlas UI.
    await _db["ai_jobs"].create_index([("post_id", 1), ("user_id", 1), ("job_type", 1)])
    await _db["ai_jobs"].create_index([("post_id", 1), ("status", 1)])
    await _db["ai_jobs"].create_index([("created_at", -1)])

    await _db["document_chunks"].create_index([("post_id", 1), ("user_id", 1)])
    await _db["document_chunks"].create_index([("post_id", 1), ("user_id", 1), ("chunk_index", 1)])

    # Nếu trước đây bạn đã tạo unique index chỉ theo post_id thì không sao.
    # Compound unique này đúng hơn cho trường hợp có user_id.
    await _db["document_summaries"].create_index(
        [("post_id", 1), ("user_id", 1)],
        unique=True,
    )

    await _db["chat_histories"].create_index([("post_id", 1), ("user_id", 1)])
    await _db["chat_histories"].create_index([("created_at", -1)])

    logger.info("✅ MongoDB connected: %s", settings.MONGO_DB_NAME)


async def close_mongo_connection() -> None:
    global _client

    if _client:
        _client.close()
        logger.info("🛑 MongoDB disconnected")


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB not connected. Call connect_mongo() first.")
    return _db


# =========================================================
# AI JOBS
# =========================================================

async def create_ai_job(
    post_id: str,
    user_id: str,
    file_url: str,
    file_type: str,
    file_name: str,
) -> str:
    """
    Tạo job INDEX:
    download -> parse -> chunk -> embedding -> save document_chunks.
    DONE nghĩa là chat_ready=true.
    """
    db = get_database()
    now = _now()

    doc = {
        "job_type": "INDEX",
        "post_id": post_id,
        "user_id": user_id,
        "file_url": file_url,
        "file_type": file_type,
        "file_name": file_name,
        "status": "PENDING",
        "stage": "PENDING",
        "chat_ready": False,
        "summary_ready": False,
        "chunk_count": 0,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await db["ai_jobs"].insert_one(doc)
    return str(result.inserted_id)


async def create_summary_job(
    post_id: str,
    user_id: str,
) -> str:
    """
    Tạo job SUMMARY:
    đọc document_chunks đã có -> summarize -> save document_summaries.
    DONE nghĩa là summary_ready=true.
    """
    db = get_database()
    now = _now()

    doc = {
        "job_type": "SUMMARY",
        "post_id": post_id,
        "user_id": user_id,
        "status": "PENDING",
        "stage": "PENDING",
        "chat_ready": True,
        "summary_ready": False,
        "chunk_count": 0,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await db["ai_jobs"].insert_one(doc)
    return str(result.inserted_id)


async def get_ai_job(job_id: str) -> Optional[Dict[str, Any]]:
    db = get_database()

    oid = _to_object_id(job_id)
    if oid is None:
        return None

    return await db["ai_jobs"].find_one({"_id": oid})


async def update_ai_job_status(
    job_id: str,
    status: str,
    error_message: Optional[str] = None,
    **extra_fields,
) -> None:
    """
    Update trạng thái job.
    Có thể truyền thêm field:
    stage="EMBEDDING",
    chat_ready=True,
    summary_ready=False,
    chunk_count=12
    """
    db = get_database()

    oid = _to_object_id(job_id)
    if oid is None:
        logger.warning("Invalid job_id: %s", job_id)
        return

    set_data: Dict[str, Any] = {
        "status": status,
        "updated_at": _now(),
    }

    if error_message is not None:
        set_data["error_message"] = error_message

    set_data.update(extra_fields)

    await db["ai_jobs"].update_one(
        {"_id": oid},
        {"$set": set_data},
    )


async def get_latest_job_by_post(
    post_id: str,
    user_id: Optional[str] = None,
    job_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    db = get_database()

    query: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        query["user_id"] = user_id

    if job_type:
        query["job_type"] = job_type

    return await db["ai_jobs"].find_one(
        query,
        sort=[("created_at", -1)],
    )


# =========================================================
# POSTS
# =========================================================

async def update_post_ai_status(post_id: str, ai_status: str) -> None:
    """
    Update trạng thái AI vào collection posts nếu có.
    Nếu posts không tồn tại trong AI DB thì update_one không match gì, không gây lỗi.
    """
    db = get_database()

    await db["posts"].update_one(
        _post_id_filter(post_id),
        {
            "$set": {
                "ai_status": ai_status,
                "updated_at": _now(),
            }
        },
    )


# =========================================================
# DOCUMENT CHUNKS
# =========================================================

async def delete_old_chunks_by_post(
    post_id: str,
    user_id: Optional[str] = None,
) -> int:
    db = get_database()

    query: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        query["user_id"] = user_id

    result = await db["document_chunks"].delete_many(query)
    return result.deleted_count


async def insert_chunks(chunks: List[dict]) -> int:
    if not chunks:
        return 0

    db = get_database()
    result = await db["document_chunks"].insert_many(chunks)
    return len(result.inserted_ids)


async def count_chunks_by_post(
    post_id: str,
    user_id: Optional[str] = None,
) -> int:
    db = get_database()

    query: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        query["user_id"] = user_id

    return await db["document_chunks"].count_documents(query)


async def get_chunks_by_post(
    post_id: str,
    user_id: Optional[str] = None,
) -> List[dict]:
    db = get_database()

    query: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        query["user_id"] = user_id

    cursor = db["document_chunks"].find(
        query,
        {
            "_id": 0,
            "content": 1,
            "chunk_index": 1,
            "page_number": 1,
        },
    ).sort("chunk_index", 1)

    return [doc async for doc in cursor]


async def vector_search_chunks(
    query_vector: List[float],
    post_id: str,
    top_k: int = 5,
    user_id: Optional[str] = None,
) -> List[dict]:
    db = get_database()
    collection = db["document_chunks"]

    safe_top_k = max(1, min(top_k, 10))

    vector_filter: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        vector_filter["user_id"] = user_id

    num_candidates = max(safe_top_k * 20, 100)

    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.MONGO_VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": num_candidates,
                "limit": safe_top_k,
                "filter": vector_filter,
            }
        },
        {
            "$project": {
                "_id": 0,
                "content": 1,
                "chunk_index": 1,
                "page_number": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    results: List[dict] = []

    async for doc in collection.aggregate(pipeline):
        results.append(doc)

    return results


# =========================================================
# SUMMARY
# =========================================================

async def save_summary(
    post_id: str,
    user_id: str,
    summary_text: str,
    key_points: Optional[List[str]] = None,
) -> str:
    db = get_database()
    now = _now()

    doc = {
        "post_id": post_id,
        "user_id": user_id,
        "summary_text": summary_text,
        "key_points": key_points or [],
        "updated_at": now,
    }

    result = await db["document_summaries"].update_one(
        {"post_id": post_id, "user_id": user_id},
        {
            "$set": doc,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    return str(result.upserted_id) if result.upserted_id else post_id


async def get_summary_by_post_id(
    post_id: str,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    db = get_database()

    query: Dict[str, Any] = {"post_id": post_id}

    if user_id:
        query["user_id"] = user_id

    return await db["document_summaries"].find_one(
        query,
        {"_id": 0},
    )


# =========================================================
# CHAT HISTORY
# =========================================================

async def save_chat_history(
    post_id: str,
    user_id: str,
    question: str,
    answer: str,
    citations: Optional[List[dict]] = None,
) -> None:
    db = get_database()

    await db["chat_histories"].insert_one(
        {
            "post_id": post_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "citations": citations or [],
            "created_at": _now(),
        }
    )