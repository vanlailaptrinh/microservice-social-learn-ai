# Microservice Social Learn AI

AI microservice hỗ trợ xử lý tài liệu học tập (PDF/DOCX), thực hiện trích xuất nội dung, phân mảnh (chunking), tạo vector embedding (BGE-M3), tóm tắt tài liệu (Qwen3) và hỗ trợ chat RAG.

## Tính năng
- **Download**: Tải tài liệu trực tiếp từ Supabase Storage.
- **Parser**: Trích xuất text từ định dạng PDF (sử dụng PyMuPDF) và DOCX (sử dụng python-docx).
- **Chunking**: Chia văn bản thành các đoạn nhỏ với cấu hình overlap.
- **Embedding**: Sử dụng mô hình `BAAI/bge-m3` sinh vector 1024 chiều chạy hoàn toàn trên CPU.
- **Vector Search**: Kết nối trực tiếp MongoDB Atlas để truy vấn ngữ cảnh theo `post_id` và `user_id`.
- **LLM**: Kết nối Ollama API chạy mô hình Qwen local (mặc định `qwen3:1.7b`) tối ưu hóa tài nguyên CPU.
- **Caching & Caching Summary**: Trả nhanh tóm tắt tài liệu lưu sẵn trong MongoDB cho các câu hỏi tổng quan mà không cần gọi lại mô hình LLM.
- **Dynamic Output Tokens**: Tự động tinh chỉnh độ dài sinh từ của LLM dựa trên loại câu hỏi để rút ngắn thời gian phản hồi.

---

## 🛠️ Hướng dẫn cài đặt

### 1. Yêu cầu hệ thống
- **Hệ điều hành**: Linux (Azure CPU VM x86_64, Ubuntu 24.04 LTS khuyến nghị).
- **Tài nguyên**: Tối thiểu 4 vCPU, 16GB RAM.
- **Python**: 3.10 trở lên.
- **Ollama**: Đã cài đặt và đang chạy.

### 2. Chuẩn bị Môi trường
Tạo virtual environment và cài đặt các thư viện:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Cấu hình biến môi trường
Sao chép file `.env.example` thành `.env` và điền đầy đủ cấu hình:
```bash
cp .env.example .env
```
Các thông số chính cần lưu ý:
- `MONGO_URI`: Địa chỉ kết nối MongoDB Atlas/Local của bạn.
- `OLLAMA_BASE_URL`: Địa chỉ API của Ollama (ví dụ: `http://localhost:11434`).
- `QWEN_MODEL`: Tên model đã pull trong Ollama (ví dụ: `qwen3:1.7b` hoặc `qwen2.5:3b`).

### 4. Tải model LLM với Ollama
Đảm bảo Ollama đang chạy trên máy chủ, sau đó thực hiện pull model:
```bash
ollama pull qwen3:1.7b
```

---

## 🚀 Chạy ứng dụng

### Chạy trực tiếp qua Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Chạy qua Docker Compose:
Sử dụng docker-compose để chạy song song cả `ai-service` và `ollama` tự động:
```bash
docker compose up -d --build
```

---

## 📂 Tạo MongoDB Atlas Vector Search Index
Để tính năng RAG hoạt động, bạn cần tạo một Vector Search Index trên collection `document_chunks` của database `social_learn_ai` thông qua giao diện MongoDB Atlas UI:

1. Đi đến database của bạn trên MongoDB Atlas.
2. Chọn tab **Atlas Search** hoặc **Search Indexes** và nhấn **Create Search Index**.
3. Chọn **JSON Editor** và chọn collection `document_chunks`.
4. Điền tên index trùng với biến `MONGO_VECTOR_INDEX_NAME` trong `.env` (mặc định là `document_vector_index`).
5. Dán đoạn JSON cấu hình dưới đây:
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
6. Nhấn **Create Search Index**.

---

## 🧪 Kiểm thử API

### 1. Kiểm tra trạng thái hoạt động (Health check)
```bash
curl -X GET http://localhost:8000/health
```
**Phản hồi thành công:**
```json
{
  "status": "ok",
  "service": "microservice-social-learn-ai"
}
```

### 2. Yêu cầu Index tài liệu
BE gọi API này sau khi user tải file lên Supabase. File sẽ được xử lý ngầm (Background Task).
```bash
curl -X POST http://localhost:8000/api/v1/documents/index \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "65f123456789abcdef012345",
    "user_id": "65a987654321fedcba543210",
    "file_url": "https://pub-your-supabase.supabase.co/storage/v1/object/public/uploads/kubernetes.pdf",
    "file_type": "pdf",
    "file_name": "kubernetes.pdf"
  }'
```
**Phản hồi:**
```json
{
  "job_id": "65f2468a13579bdf02468ace",
  "post_id": "65f123456789abcdef012345",
  "status": "PENDING",
  "message": "Document indexing job created"
}
```

### 3. Gửi câu hỏi chat với bài viết (RAG)
```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "post_id": "65f123456789abcdef012345",
    "user_id": "65a987654321fedcba543210",
    "question": "Pod là gì?",
    "top_k": 3
  }'
```
**Phản hồi:**
```json
{
  "answer": "Pod là đối tượng nhỏ nhất có thể triển khai được trong Kubernetes...",
  "citations": [
    {
      "page_number": 2,
      "chunk_index": 4,
      "content_preview": "Pod đại diện cho một tiến trình đang chạy trong cụm của bạn..."
    }
  ]
}
```