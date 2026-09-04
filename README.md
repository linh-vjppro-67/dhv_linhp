
# DHV - Hệ thống quản lý văn bản và điều hành

Ứng dụng full-stack ReactJS + FastAPI + SQLite, mở rộng từ bộ OCR/tra cứu DHV ban đầu.

## Chạy hệ thống mới

- Windows: chạy `start.bat`.
- macOS/Linux: chạy `chmod +x start.sh && ./start.sh`.
- Production (giao diện + API): `http://localhost:8002`.
- Development frontend: `http://localhost:5174` (proxy API sang cổng `8002`).

Tài khoản mẫu (mật khẩu chung `123456`): `admin`, `hieu_truong`, `truong_vp`, `van_thu`, `phong_dao_tao`.

Hệ thống có công văn đến/đi, upload bản scan, đánh số riêng theo loại và năm, giữ nhiều số trước, workflow trình/duyệt/yêu cầu sửa/phân công/ký/đóng dấu/phát hành/lưu trữ, phân quyền theo vai trò và phòng ban, nhật ký, dashboard, tra cứu metadata và nội dung PDF. Email và ký số đang là mô phỏng có kiểm soát; trước production phải nối Google Drive/OneDrive/eOffice, SMTP và nhà cung cấp USB Token/HSM/ký từ xa.

Không sử dụng hình dấu tự tạo và không lưu khóa bí mật/PIN trong ứng dụng. Khách hàng phải cung cấp, xác nhận file dấu thật và chứng thư hợp lệ. Thư mục OCR/search cũ bên dưới vẫn được giữ nguyên.

## 1. Yêu cầu môi trường cho OCR/search nâng cao

Khuyến nghị:

- Python 3.11 hoặc 3.12
- Tesseract OCR
- Tesseract language pack: `vie`, `eng`
- macOS, Linux hoặc Docker

### macOS

```bash
brew install tesseract tesseract-lang
```

Kiểm tra Tesseract:

```bash
tesseract --version
tesseract --list-langs
```

Danh sách ngôn ngữ cần có:

```text
eng
vie
```

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng
```

---

## 2. Cài đặt project

Tạo virtual environment:

```bash
python3 -m venv .venv
```

Kích hoạt môi trường:

### macOS / Linux

```bash
source .venv/bin/activate
```

Cài dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Kiểm tra FAISS:

```bash
python -c "import faiss; print(faiss.__version__)"
```

---

## 3. Cấu hình

Tạo file `.env` từ file mẫu:

```bash
cp .env.example .env
```

Cấu hình mặc định sử dụng chế độ search đầy đủ:

```env
SEARCH_PROFILE=smart
ENABLE_RERANKER=true
OCR_LANGUAGES=vie+eng
OCR_DPI=300
INDEX_WORKERS=2
FILENAME_FIRST_ENABLED=true
```

Nếu máy phát triển có tài nguyên hạn chế, có thể chuyển sang chế độ nhẹ:

```env
SEARCH_PROFILE=light
ENABLE_RERANKER=false
```

Lần chạy đầu tiên ở chế độ `smart`, hệ thống sẽ tải các model cần thiết về máy.

---

## 4. Chuẩn bị dữ liệu

Đặt tài liệu trong thư mục `documents`.

Ví dụ:

```text
documents/
├── 1. QUYẾT ĐỊNH/
├── 2. THÔNG BÁO/
├── 3. KẾ HOẠCH/
└── 4. CÔNG VĂN/
```

Có thể tạo thêm nhiều thư mục con bên trong từng nhóm.

Các định dạng đang hỗ trợ:

```text
.pdf
.docx
.txt
.md
```

Folder cấp đầu được sử dụng làm `category` của tài liệu.

---

## 5. Đồng bộ và lập chỉ mục tài liệu

Chạy:

```bash
python cli.py sync ./documents --workers 2
```

Hệ thống sẽ:

- đọc toàn bộ cấu trúc thư mục con;
- trích xuất text từ PDF có text;
- OCR các trang PDF scan khi cần;
- đọc nội dung DOCX/TXT/Markdown;
- cập nhật metadata;
- tạo hoặc cập nhật search index.

Sau lần đầu, quá trình sync hoạt động theo cơ chế incremental. File không thay đổi sẽ được bỏ qua; chỉ file mới, file sửa hoặc file bị xóa mới được cập nhật.

Để kiểm tra theo luồng tuần tự khi debug OCR:

```bash
python cli.py sync ./documents --workers 1
```

---

## 6. Chạy API

Khởi động FastAPI:

```bash
python -m uvicorn app.main:app --reload --port 8002
```

Swagger:

```text
http://127.0.0.1:8002/docs
```

Health check:

```text
GET /health
```

Thống kê dữ liệu:

```text
GET /stats
```

Danh sách tài liệu:

```text
GET /documents
```

---

## 7. Tìm kiếm

Endpoint:

```text
GET /search
```

Tham số chính:

```text
q
top_k
category
folder_prefix
extension
min_score
```

`q` là bắt buộc. Các tham số còn lại có thể bỏ trống.

Ví dụ:

```text
q = QĐ-305-24
```

hoặc:

```text
q = phạm thị hậu
```

hoặc:

```text
q = sinh viên được nghỉ học tạm thời
```

Mặc định smart search trả tối đa 3 tài liệu phù hợp.

Nếu query khớp mạnh với tên file hoặc số văn bản, hệ thống ưu tiên trả trực tiếp các file tương ứng. Trường hợp có nhiều file cùng tên hoặc gần giống nhau, hệ thống có thể trả nhiều hơn một file.

Output API được giữ ở dạng ngắn:

```json
{
  "query": "phạm thị hậu",
  "results": [
    {
      "rank": 1,
      "file_name": "QD 305-24 ... (PHAM THI HAU).pdf",
      "category": "1. QUYẾT ĐỊNH",
      "score": 0.995
    }
  ]
}
```

Với kết quả tìm kiếm nội dung, response có thêm `excerpt`:

```json
{
  "query": "sinh viên được nghỉ học tạm thời",
  "results": [
    {
      "rank": 1,
      "file_name": "QD 305-24 ...pdf",
      "category": "1. QUYẾT ĐỊNH",
      "excerpt": "Đoạn nội dung liên quan...",
      "score": 0.912
    }
  ]
}
```

---

## 8. Tìm kiếm bằng CLI

Tìm kiếm thông thường:

```bash
python cli.py search "QĐ-305-24"
```

Tìm kiếm nội dung:

```bash
python cli.py search "sinh viên được nghỉ học tạm thời"
```

Giới hạn theo category:

```bash
python cli.py search "305" --category "1. QUYẾT ĐỊNH"
```

Giới hạn theo loại file:

```bash
python cli.py search "kế hoạch" --extension pdf
```

---

## 9. Debug kết quả tìm kiếm

Khi cần kiểm tra nguyên nhân một tài liệu được xếp hạng cao hoặc thấp:

```bash
python cli.py debug-search "phạm thị hậu"
```

Hoặc sử dụng API:

```text
GET /search/debug
```

Endpoint debug chỉ phục vụ phát triển và kiểm tra ranking; ứng dụng phía client nên sử dụng `/search`.

---

## 10. Rebuild search index

Khi thay đổi model hoặc cấu hình search và cần tạo lại index:

```bash
python cli.py rebuild-search-indexes
```

Lệnh này tạo lại search index từ dữ liệu text đã có trong database.

Không cần OCR lại toàn bộ tài liệu nếu dữ liệu extraction hiện tại vẫn còn hợp lệ.

---

## 11. Chạy giao diện Streamlit

```bash
python -m streamlit run ui.py
```

Streamlit phục vụ mục đích kiểm thử nhanh trong quá trình phát triển.

---

## 12. Docker

Build và chạy:

```bash
docker compose up --build
```

Mặc định:

```text
API: http://127.0.0.1:8000
Swagger: http://127.0.0.1:8000/docs
```

Các thư mục được mount:

```text
./documents -> /app/documents
./data      -> /app/data
```

---

## 13. Cấu trúc chính

```text
app/
├── main.py
├── config.py
├── scanner.py
├── extractors.py
├── indexer.py
├── db.py
├── filename_router.py
├── search_engine.py
├── typo_index.py
├── dense_index.py
├── embedder.py
├── reranker.py
└── normalize.py

documents/
data/
cli.py
ui.py
requirements.txt
.env.example
Dockerfile
docker-compose.yml
```

---

## 14. Lưu ý khi phát triển

Sau khi thay đổi code API, chạy lại:

```bash
python -m uvicorn app.main:app --reload --port 8002
```

Nếu chỉ thay đổi logic ranking/search, thông thường không cần OCR lại tài liệu.

Nếu thay đổi embedding model hoặc cấu trúc vector index, chạy:

```bash
python cli.py rebuild-search-indexes
```

Nếu thay đổi logic extraction/OCR hoặc muốn lập chỉ mục lại dữ liệu nguồn:

```bash
python cli.py sync ./documents --workers 2
```
