
# DHV - Hệ thống quản lý văn bản và điều hành

Ứng dụng full-stack ReactJS + FastAPI + SQLite, mở rộng từ bộ OCR/tra cứu DHV ban đầu.

## Chạy hệ thống mới

- Windows: chạy `start.bat`.
- macOS/Linux: chạy `chmod +x start.sh && ./start.sh`.
- Production (giao diện + API): `http://localhost:8002`.
- Development frontend: `http://localhost:5174` (proxy API sang cổng `8002`).

Chạy backend thủ công từ thư mục gốc `dhv_linhp` (đã kích hoạt virtual environment và cài `backend/requirements.txt`):

```bash
python -m uvicorn backend.app:app --reload --port 8002
```

Nếu terminal đang ở `dhv_linhp/backend`, chạy `cd ..` trước. Health check của hệ thống: `http://127.0.0.1:8002/api/health`.

Không chạy `uvicorn app.main:app` trong thư mục `backend`: file `backend/app.py` sẽ che khuất package `app/` ở thư mục gốc, gây lỗi `'app' is not a package`. Entry point `app.main:app` bên dưới dành cho API OCR/search riêng.

Tài khoản hiện có (mật khẩu chung `123456`): `admin`, `hieu_truong`, `truong_vp`, `van_thu`, `phong_dao_tao`, `phong_tai_chinh_ke_toan`, `phong_cong_tac_sinh_vien`, `phong_khao_thi`, `phong_quan_ly_khoa_hoc`, `phong_truyen_thong`.

Hệ thống có công văn đến/đi, upload bản scan, đánh số riêng theo loại và năm, giữ nhiều số trước, workflow trình/duyệt/yêu cầu sửa/phân công/ký/đóng dấu/phát hành/lưu trữ, phân quyền theo vai trò và phòng ban, nhật ký, dashboard, tra cứu metadata và nội dung PDF. Email và ký số đang là mô phỏng có kiểm soát; trước production phải nối Google Drive/OneDrive/eOffice, SMTP và nhà cung cấp USB Token/HSM/ký từ xa.

Không sử dụng hình dấu tự tạo và không lưu khóa bí mật/PIN trong ứng dụng. Khách hàng phải cung cấp, xác nhận file dấu thật và chứng thư hợp lệ. Thư mục OCR/search cũ bên dưới vẫn được giữ nguyên.

## Công văn đi và công văn nội bộ

Hai loại cùng nằm trong tab **Công văn đi**. Khi tạo, chọn trực tiếp loại **Công văn đi / Quyết định / Kế hoạch / Thông báo**, rồi tải PDF do đơn vị soạn trên máy lên. Quyết định, Kế hoạch và Thông báo là các loại văn bản nội bộ.

Luồng hồ sơ có hai nhánh. Nếu lãnh đạo đơn vị ký số, văn bản được gửi BGH duyệt và BGH không ký lại. Nếu lãnh đạo đơn vị chưa ký, văn bản được gửi BGH duyệt và ký số. Sau khi hoàn tất nhánh tương ứng, hồ sơ chuyển về Văn thư để vào số/ngày, đóng dấu, gửi email và lưu trữ. Khi BGH trả lại, hệ thống tăng phiên bản, lưu lý do và người thao tác trong activity log; đơn vị sửa file rồi chọn lại một trong hai nhánh.

Admin cấp tài khoản tại **Cấu hình hệ thống → Người dùng và vai trò**. Tài khoản **Đơn vị** chỉ thấy hai tab Công văn đến, Công văn đi và chuông thông báo. Tài khoản này được tạo, tải PDF, sửa, ký số và trình BGH đối với công văn đi của đơn vị mình; đối với công văn đến được phân công, tài khoản được thảo luận và gửi lại báo cáo bằng nội dung hoặc tệp PDF/DOCX. Cần gán đúng đơn vị cho tài khoản.

Cấp số theo từng loại văn bản và năm. Lưu trữ giữ nguyên cấu trúc `backend/archive/<năm>/<loại>/`: `CÔNG VĂN ĐI`, `QUYẾT ĐỊNH`, `KẾ HOẠCH`, `THÔNG BÁO`. Ngày ban hành chọn ở form tạo/sửa văn bản, mặc định hôm nay; khi cấp số, hệ thống dùng ngày đã chọn để điền lên PDF. Hồ sơ cũ chưa có ngày sẽ dùng ngày văn phòng nhận văn bản đã được BGH ký. Khi vào số, văn thư khoanh vùng số và dòng ngày trên trang đầu, xem trước rồi xác nhận. Hệ thống thay nội dung ngay trong hai vùng đã chọn trên PDF gốc (kể cả bản scan), không thêm trang. Chữ ký và dấu vẫn là mô phỏng, chưa tích hợp chứng thư số thật. Gửi email cần cấu hình SMTP.

Trong tab **Lưu trữ**, Văn thư/Admin chọn năm tại **Sổ đăng ký số văn bản** và xuất file `.xlsx` theo mẫu của Trường. Workbook giữ các sheet của mẫu và tự điền số ký hiệu, ngày ban hành, trích yếu, người ký, chức vụ, ghi chú; sheet Công văn đến có thêm thông tin chuyển xử lý, đơn vị nhận, thời hạn và kết quả giải quyết.

Hồ sơ nội bộ cũ vẫn xuất hiện trong tab chung và tiếp tục theo trạng thái xử lý cũ; không tự chuyển đổi dữ liệu hay lịch sử đã có.

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

Tải Qwen dùng riêng cho chat completion về máy (chỉ cần chạy một lần):

```bash
python scripts/download_qwen_chat.py
```

Model Qwen3-8B 4-bit được lưu tại `models/qwen3-8b-4bit` và chạy bằng MLX trên Apple Silicon. Khi chat, hệ thống chỉ đọc model local;
BGE-M3 và BGE reranker hiện tại vẫn đảm nhiệm embedding, tìm kiếm và xếp hạng.

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

## 6. Chạy API OCR/search riêng

Khởi động FastAPI từ thư mục gốc `dhv_linhp` (chỉ chạy một API trên cổng `8002` tại một thời điểm):

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

### Chat completion bằng Qwen local

Endpoint:

```text
POST /chat
```

Ví dụ request:

```json
{
  "message": "Có văn bản nào yêu cầu các khoa nộp kế hoạch trước khai giảng không?",
  "history": [],
  "top_k": 5
}
```

API trả về `answer`, `confidence` và `sources`. Qwen chỉ viết câu trả lời từ
các đoạn do BGE-M3/FAISS và reranker tìm được. Khi nguồn không đủ rõ, câu trả
lời phải nêu rằng chưa đủ dữ liệu để xác định.

---

## 8. Tìm kiếm bằng CLI

Tìm kiếm thông thường:

```bash
python cli.py search "QĐ-305-24"
```

Hỏi bằng Qwen local:

```bash
python cli.py chat "Tìm công văn yêu cầu báo cáo tuyển sinh năm 2026"
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
├── qwen_chat.py
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

Sau khi thay đổi code API OCR/search riêng, chạy lại từ thư mục gốc `dhv_linhp`:

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


### Công văn đến: giao việc và duyệt trên hệ thống

- Sau khi cấp số, Chánh Văn phòng mở **Giao việc / phản hồi**, ghi note phân công, chọn đơn vị, nhập mục đích riêng và chọn vai trò xử lý rồi trình BGH. Mỗi đơn vị cần có tài khoản Đơn vị xử lý đang hoạt động.
- Hệ thống tạo phiếu đính kèm từ PDF gốc. BGH đọc và đồng ý trước; tiếp theo từng đơn vị bấm **Đã đọc và đồng ý** hoặc **Không đồng ý / Yêu cầu sửa**. Bình luận được lưu theo từng vòng duyệt, chưa gửi email.
- Chánh VP sửa note và trình lại sẽ tạo vòng mới; xác nhận của vòng cũ không còn hiệu lực. BGH và mọi đơn vị cần đồng ý lại. Lịch sử các vòng được giữ nguyên.
- Chỉ khi tất cả đồng ý vòng hiện tại, Chánh VP mới có nút **Gửi email báo việc**. Email sử dụng cấu hình SMTP của hệ thống và đính kèm hồ sơ hiện tại. Gửi thành công thì có thể lưu trữ.
- Hồ sơ đang xử lý theo luồng cũ cần Chánh VP mở **Giao việc / phản hồi** để lập phiếu và danh sách đơn vị theo luồng mới.

Kiểm tra quy trình (dùng dữ liệu tạm, giả lập SMTP, không gửi email thật):

```bash
backend/.venv/bin/python -m unittest backend.tests.test_incoming_review
```

Email nhận việc của mỗi phòng ban được quản lý tại **Cấu hình hệ thống → Email các phòng ban**. Phiếu giao việc không nhập email. Hệ thống lấy email cấu hình tại thời điểm gửi; đơn vị chưa có email hợp lệ sẽ chặn gửi, nhưng không chặn duyệt trên hệ thống.


### Tải văn bản PDF, DOC và DOCX

Các luồng tạo, sửa, bổ sung văn bản và tải/nộp lại hồ sơ lưu trữ nhận PDF, DOC hoặc DOCX (tối đa 25 MB). DOC/DOCX được chuyển thành PDF để xem, vào số, ký, đóng dấu và lưu trữ; tệp tải xuống trong các luồng này là PDF. Báo cáo xử lý đính kèm vẫn giữ định dạng gốc.

Máy chạy backend cần LibreOffice:
- macOS: `brew install --cask libreoffice`
- Debian/Ubuntu: `sudo apt-get install libreoffice-writer fonts-dejavu fonts-liberation`

Backend tự tìm `soffice` hoặc LibreOffice trong Applications trên macOS. Có thể đặt `LIBREOFFICE_PATH` trỏ tới executable nếu cài ở vị trí khác. Thiếu LibreOffice, tải PDF vẫn hoạt động, tải DOC/DOCX trả thông báo cấu hình chưa đủ. Bản xem trước DOC/DOCX dùng cùng cơ chế chuyển đổi với bản lưu; nên kiểm tra bố cục trước khi ký.


### Mẫu email của Văn phòng Trường

- Mẫu nhắc báo cáo tháng: ngày nhắc dự kiến 25, hạn nộp ngày 28; tự điền thứ/ngày theo tháng được chọn.
- Mẫu chuyển công văn đến: tự lấy trích yếu, số/ngày công văn, đơn vị nhận và đề xuất từ phiếu đã duyệt. Nội dung thư theo mẫu công văn đến; vai trò và hạn xử lý xem trong phiếu.
- Mẫu đơn vị gửi báo cáo: tự điền tên đơn vị, tháng báo cáo và tháng tiếp theo (kể cả chuyển năm).

Mẫu báo cáo có trong cấu hình email, màn hình soạn email và màn hình gửi báo cáo xử lý. Chọn “Dùng mẫu này” để điền nội dung rồi kiểm tra trước khi gửi. Chức năng mẫu chưa kích hoạt lịch tự gửi ngày 25; nhắc hạn vẫn hiển thị trên hệ thống, không tự gửi email.


### Soạn và gửi thư qua Gmail

Nút gửi email công văn đi, nội bộ và công văn đến mở Gmail Web, điền sẵn người nhận, tiêu đề và nội dung dạng văn bản. Đăng nhập Gmail bằng tài khoản `ngcphnglinhp6.7.2000@gmail.com`; ứng dụng không lưu mật khẩu Gmail và không dùng SMTP cho thao tác này.

Liên kết soạn thư không đính kèm file tự động. Dùng “Tải PDF để đính kèm”, thêm tệp trong Gmail, chỉnh sửa rồi tự bấm Gửi. Nếu trình duyệt chặn cửa sổ mới, dùng liên kết “Mở cửa sổ soạn thư Gmail” trong hộp thoại.

Mở Gmail không đổi trạng thái hồ sơ. Sau khi gửi thành công, người dùng bấm “Tôi đã gửi thư trong Gmail” để xác nhận và tiếp tục quy trình. Đây là xác nhận thủ công, không phải biên nhận giao thư từ Google. Đã ngừng gọi SMTP tự động khi tải thông báo nhắc hạn.


### Lưu trữ có hoặc không gửi mail

Ở bước đã đóng dấu (công văn đi/nội bộ), hoặc BGH và các đơn vị đã đồng ý (công văn đến), người có quyền lưu trữ có thể chọn:
- **Gửi mail**: mở Gmail, tự gửi, xác nhận đã gửi rồi chọn lưu trữ.
- **Lưu không gửi mail**: lưu trữ và OCR ngay, không mở Gmail.

Nhật ký lưu trữ ghi rõ có gửi mail hay không. Các bước duyệt, vào số và đóng dấu vẫn phải hoàn thành theo luồng văn bản.


### Duyệt yêu cầu xin số trước

Yêu cầu mới chờ Văn thư duyệt và chưa chiếm số. Văn thư có thể duyệt để cấp số, hoặc từ chối kèm lý do. Người tạo yêu cầu bị từ chối được chỉnh sửa rồi trình lại (cùng hồ sơ, tăng phiên bản), hoặc xoá yêu cầu. Chu kỳ từ chối/chỉnh sửa/trình lại có thể lặp nhiều lần. Mỗi lần xử lý được ghi nhật ký. Chỉ yêu cầu đã được duyệt mới được bổ sung văn bản.

Tài khoản đơn vị tự lấy đơn vị đăng nhập; Admin, Văn thư và Chánh VP chọn đơn vị trong cấu hình nhưng yêu cầu vẫn phải qua Văn thư duyệt. Các số đã cấp trước khi bổ sung quy trình này được giữ nguyên.


### Số thứ tự hồ sơ lưu trữ

Hồ sơ tải trực tiếp vào lưu trữ dùng chung sổ số với luồng xử lý văn bản và xin số đã được duyệt, theo loại văn bản và năm. Số mới lấy sau số lớn nhất đã cấp/bộ đếm hiện hành, kể cả công văn đến và đi. Hồ sơ đang chờ duyệt lưu trữ chỉ được cấp số khi được duyệt. Văn bản đã có số giữ số đó khi chuyển vào lưu trữ. Danh sách lưu trữ mặc định sắp theo số tăng dần.


### Định dạng số/ký hiệu thống nhất

Tất cả loại văn bản cấp số mới dùng cấu trúc số/năm/ký hiệu. Ví dụ: công văn đến `01/2026/CVDEN`, công văn đi `01/2026/ĐHHV`, quyết định `01/2026/QĐ-ĐHHV`, quyết định Hội đồng trường `01/2026/QĐ-HĐT`. Năm theo sổ văn bản; số ít nhất hai chữ số và không cắt bớt khi vượt 99. Áp dụng cho cấp số, xin số được duyệt và hồ sơ tải vào lưu trữ.
