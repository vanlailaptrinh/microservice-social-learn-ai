"""
Application configuration.
Load all settings from .env via pydantic-settings.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    APP_NAME: str = "microservice-social-learn-ai"
    APP_ENV: str = "dev"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── MongoDB ──
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "social_learn_ai"
    MONGO_VECTOR_INDEX_NAME: str = "document_vector_index"

    # ── Supabase Storage (chỉ dùng để download file) ──
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_BUCKET: str = "documents"

    # ── Embedding ──
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    # ── LLM ──
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    QWEN_MODEL: str = "qwen3:1.7b"

    # ── RAG ──
    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 120
    DEFAULT_TOP_K: int = 3

    # ── Temp ──
    TEMP_DIR: str = "./tmp"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
