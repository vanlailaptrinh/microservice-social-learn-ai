# Microservice Social Learn AI

AI microservice xử lý tài liệu học tập đính kèm bài đăng, hỗ trợ:

- Index tài liệu PDF/DOCX/ảnh.
- Trích xuất text, chia chunk, tạo embedding bằng `BAAI/bge-m3`.
- Lưu chunks, jobs, summaries, chat history vào MongoDB.
- Dùng MongoDB Vector Search để tìm chunks liên quan khi chat.
- Dùng Qwen qua Ollama để tóm tắt tài liệu và trả lời câu hỏi theo RAG.

## Kiến Trúc

```txt
PDF/DOCX/Image URL
-> download file tạm
-> parse text
   PDF   : theo trang thật
   DOCX  : page logic theo heading/section + giới hạn số từ
   Image : OCR bằng Tesseract
-> chunk text
-> embedding chunks bằng BGE-M3
-> lưu MongoDB document_chunks
-> MongoDB Vector Search
-> prompt + top_k chunks
-> Qwen qua Ollama
-> answer / summary
```

## Công Nghệ Chính

- **FastAPI**: cung cấp API index, summary, chat.
- **MongoDB / MongoDB Atlas**: lưu chunks, jobs, summaries, chat history.
- **MongoDB Vector Search**: tìm chunks liên quan theo embedding.
- **BGE-M3**: embedding model đa ngôn ngữ, vector 1024 chiều.
- **Ollama**: runtime/API server để chạy LLM local.
- **Qwen2.5**: LLM sinh câu trả lời và tóm tắt.
- **PyMuPDF**: extract text từ PDF.
- **python-docx**: extract text từ DOCX.
- **Tesseract OCR**: extract text từ ảnh.

## Cấu Hình

Tạo file `.env` từ file mẫu:

```bash
cp .env.example .env
```

Ví dụ `.env` dùng với Docker Compose:

```env
APP_NAME=microservice-social-learn-ai
APP_ENV=dev
HOST=0.0.0.0
PORT=8000

MONGO_URI=mongodb+srv://<username>:<password>@<cluster-url>/?retryWrites=true&w=majority
MONGO_DB_NAME=social_learn_ai
MONGO_VECTOR_INDEX_NAME=document_vector_index

EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
QWEN_MODEL=qwen2.5:3b

CHUNK_SIZE=900
CHUNK_OVERLAP=120
DEFAULT_TOP_K=3

TEMP_DIR=/app/tmp
```

Ghi chú:

- Khi chạy bằng Docker Compose, `OLLAMA_BASE_URL` nên là `http://ollama:11434`.
- Nếu chạy FastAPI trực tiếp ngoài Docker, đổi thành `http://localhost:11434`.
- `QWEN_MODEL` sẽ được service `ollama-pull` tự pull khi chạy compose.
- `CHUNK_SIZE=900`: giới hạn tối đa mỗi chunk khoảng 900 từ.
- `CHUNK_OVERLAP=120`: chunk sau lặp lại 120 từ cuối của chunk trước khi cần cắt tiếp.
- API index nhận `file_url` trực tiếp từ BE. URL này nên là public URL hoặc signed URL có quyền download.

## MongoDB Vector Search Index

Tạo Vector Search Index trên collection `document_chunks`.

Tên index phải trùng với:

```env
MONGO_VECTOR_INDEX_NAME=document_vector_index
```

JSON index trong MongoDB Atlas:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1024,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "post_id"
    },
    {
      "type": "filter",
      "path": "user_id"
    }
  ]
}
```

## Chạy Bằng Docker Compose

Build và chạy:

```bash
docker compose up -d --build
```

Xem container:

```bash
docker compose ps
```

Xem log AI service:

```bash
docker logs -f social-learn-ai-service
```

Xem model Ollama đã pull:

```bash
docker exec -it social-learn-ollama ollama list
```

Tắt service:

```bash
docker compose down
```

## Bật GPU Cho Ollama

`docker-compose.yml` hiện có:

```yaml
gpus: all
```

Máy host cần có:

- NVIDIA driver hoạt động (`nvidia-smi` chạy được).
- NVIDIA Container Toolkit để Docker container nhìn thấy GPU.

Nếu máy không có GPU NVIDIA, có thể bỏ dòng `gpus: all`; Ollama sẽ chạy CPU.

## Cloudflare Tunnel Tùy Chọn

Nếu muốn public AI service qua Cloudflare Tunnel, thêm service sau vào `docker-compose.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: social-learn-cloudflared
    env_file:
      - .env.tunnel
    entrypoint: ["/bin/sh", "-c"]
    command: cloudflared tunnel --no-autoupdate run --token "$${CLOUDFLARE_TUNNEL_TOKEN}"
    depends_on:
      - ai-service
    restart: unless-stopped
```

Tạo file `.env.tunnel`:

```bash
CLOUDFLARE_TUNNEL_TOKEN=your-cloudflare-tunnel-token
```

Sau đó chạy:

```bash
docker compose up -d cloudflared
```

Không nên thêm token Cloudflare vào `.env` chính nếu app Python của bạn đang strict config. `.env` chính nên chỉ chứa config của AI service.

Trong Cloudflare Tunnel dashboard, trỏ public hostname tới service nội bộ:

```txt
http://ai-service:8000
```

## Chạy Trên Server AI Cloud

Khi deploy lên server/cloud, thường không build source trực tiếp trên server. Thay vào đó:

```txt
local/dev machine
-> docker build
-> docker push lên Docker Hub/GitHub Container Registry
-> server pull image đúng tag
-> docker compose up -d
```

Ví dụ build và push image:

```bash
docker build -t vantrandevops/social-learn-ai:v7 .
docker push vantrandevops/social-learn-ai:v7
```

Trên server, sửa service `ai-service` trong `docker-compose.yml` từ dạng build local:

```yaml
  ai-service:
    build:
      context: .
      dockerfile: Dockerfile
```

sang dạng dùng image registry:

```yaml
  ai-service:
    image: vantrandevops/social-learn-ai:v7
    container_name: social-learn-ai-service
    env_file:
      - .env
    environment:
      HOST: 0.0.0.0
      PORT: 8000
      TEMP_DIR: /app/tmp
      OLLAMA_BASE_URL: http://ollama:11434
      HF_HOME: /root/.cache/huggingface
      TRANSFORMERS_CACHE: /root/.cache/huggingface
    ports:
      - "8000:8000"
    volumes:
      - ./tmp:/app/tmp
      - hf_cache:/root/.cache/huggingface
    depends_on:
      - ollama
    restart: unless-stopped
```

Sau đó trên server chạy:

```bash
docker compose pull ai-service
docker compose up -d
```

Nếu image private, login Docker registry trước:

```bash
docker login
```

Checklist `.env` trên server:

```env
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=social_learn_ai
MONGO_VECTOR_INDEX_NAME=document_vector_index
OLLAMA_BASE_URL=http://ollama:11434
QWEN_MODEL=qwen2.5:3b
TEMP_DIR=/app/tmp
```

Nếu server không có NVIDIA GPU hoặc chưa cài NVIDIA Container Toolkit, bỏ dòng này ở service `ollama`:

```yaml
gpus: all
```

Nếu đổi version image mới, chỉ cần đổi tag:

```yaml
image: vantrandevops/social-learn-ai:v8
```

rồi chạy:

```bash
docker compose pull ai-service
docker compose up -d ai-service
```

## Kiểm Tra API Bằng curl

Các ví dụ dưới đây dùng:

```bash
BASE_URL=http://localhost:8000
POST_ID=demo-post-001
USER_ID=demo-user-001
```

Nếu dùng tunnel, đổi `BASE_URL` thành domain Cloudflare của bạn.

### 1. Health Check

```bash
curl -s "$BASE_URL/health" | jq
```

Response:

```json
{
  "status": "ok",
  "service": "microservice-social-learn-ai"
}
```

### 2. Index Tài Liệu

Hỗ trợ `file_type`: `pdf`, `docx`, `jpg`, `jpeg`, `png`, `webp`.

```bash
curl -s -X POST "$BASE_URL/api/v1/documents/index" \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "demo-post-001",
    "user_id": "demo-user-001",
    "file_url": "https://example.com/sample.pdf",
    "file_type": "pdf",
    "file_name": "sample.pdf"
  }' | jq
```

Response:

```json
{
  "job_id": "...",
  "post_id": "demo-post-001",
  "status": "PENDING",
  "message": "Document index job created. Chat will be available after chunks are ready."
}
```

### 3. Check Job

Thay `JOB_ID` bằng `job_id` nhận được ở bước index:

```bash
curl -s "$BASE_URL/api/v1/jobs/JOB_ID" | jq
```

Khi index xong:

```json
{
  "status": "DONE",
  "stage": "INDEX_DONE",
  "chat_ready": true,
  "chunk_count": 12
}
```

### 4. Check Index Status Theo Tài Liệu

```bash
curl -s "$BASE_URL/api/v1/documents/demo-post-001/index-status?user_id=demo-user-001" | jq
```

### 5. Tạo Summary

Chỉ gọi sau khi `chat_ready=true`.

```bash
curl -s -X POST "$BASE_URL/api/v1/documents/summary" \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "demo-post-001",
    "user_id": "demo-user-001"
  }' | jq
```

Summary chạy background job. Check job bằng `job_id` trả về.

### 6. Lấy Summary

```bash
curl -s "$BASE_URL/api/v1/documents/demo-post-001/summary?user_id=demo-user-001" | jq
```

Response khi có summary:

```json
{
  "post_id": "demo-post-001",
  "user_id": "demo-user-001",
  "status": "READY",
  "summary_ready": true,
  "summary_text": "...",
  "key_points": []
}
```

### 7. Chat Với Tài Liệu

```bash
curl -s -X POST "$BASE_URL/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "demo-post-001",
    "user_id": "demo-user-001",
    "question": "Tóm tắt nội dung chính của tài liệu này?",
    "top_k": 3
  }' | jq
```

Response:

```json
{
  "answer": "...",
  "citations": [
    {
      "page_number": 1,
      "chunk_index": 0,
      "content_preview": "..."
    }
  ]
}
```

## Summary Flow

Summary không dùng Vector Search. Nó lấy toàn bộ chunks của tài liệu:

```txt
chunks trong MongoDB
-> gom mỗi 6 chunks thành 1 nhóm
-> Qwen tóm tắt từng nhóm, tối đa 700 output tokens
-> nếu có nhiều nhóm, Qwen tổng hợp lần cuối, tối đa 1000 output tokens
-> lưu summary vào MongoDB để cache
```

Ví dụ tài liệu có 18 chunks:

```txt
chunks 0-5   -> partial summary 1
chunks 6-11  -> partial summary 2
chunks 12-17 -> partial summary 3
partial summaries -> final summary
```

Tổng cộng 4 lần gọi LLM.

## Chat RAG Flow

Chat dùng Retrieval-Augmented Generation:

```txt
question
-> embedding question bằng BGE-M3
-> MongoDB Vector Search tìm top_k chunks liên quan
-> build prompt gồm QUESTION + CONTEXT
-> Qwen sinh câu trả lời
-> trả answer + citations
```

Qwen không đọc toàn bộ file trực tiếp. Qwen chỉ đọc những chunks được retrieve và đưa vào prompt.

## Build Và Push Docker Image

Nếu chỉ muốn build/push image source code:

```bash
docker build -t your-dockerhub-user/social-learn-ai:v1 .
docker push your-dockerhub-user/social-learn-ai:v1
```

Ví dụ:

```bash
docker build -t vantrandevops/social-learn-ai:v7 .
docker push vantrandevops/social-learn-ai:v7
```
