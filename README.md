# Dịch Chữ Thái Việt (Tai Viet Translation & Corpus Platform)

## Tài khoản cộng đồng và Resend

Thành viên có thể đăng ký email/mật khẩu, xem từ và câu đã đóng góp theo trạng thái,
và tham gia bảng xếp hạng tính trên đóng góp đã duyệt. Tra cứu chỉ hiển thị từ đóng
góp đã duyệt. Các bảng tài khoản được tạo bổ sung khi backend khởi động; dùng
Supabase trên Render để giữ dữ liệu qua các lần triển khai.
Khi cấu hình Supabase nhưng không kết nối được, backend dừng khởi động để tránh
lưu tài khoản sang SQLite tạm thời; hãy kiểm tra kết nối rồi khởi động lại.

Để bật email quên mật khẩu, cấu hình trong Render Environment:

- `RESEND_API_KEY`: khóa gửi email Resend, chỉ giữ phía server.
- `RESEND_FROM`: địa chỉ gửi thuộc domain đã xác minh, ví dụ `Tai Việt <taikhoan@example.com>`.
- `PUBLIC_BASE_URL`: URL HTTPS chính thức, ví dụ `https://taiviet.onrender.com`.

Sau khi lưu cấu hình, redeploy. Liên kết đặt lại mật khẩu dùng một lần, hết hạn
sau 30 phút và thu hồi các phiên đăng nhập cũ khi đổi mật khẩu thành công.
Nếu chưa cấu hình Resend, đăng ký/đăng nhập vẫn dùng được; khôi phục mật khẩu
thông báo chưa sẵn sàng. Không đưa API key vào mã frontend hoặc Git.

Hệ thống hỗ trợ học tập, tra cứu và số hóa ngôn ngữ **chữ Thái Việt** (Tai Dam / Tai Don). Ứng dụng tích hợp bộ quy tắc chuyển đổi ngữ âm – văn tự Thái Việt hai chiều, kết hợp nền tảng cộng đồng đóng góp dữ liệu và quản trị kiểm duyệt.

---

## ✨ Tính năng chính

1. **Chuyển đổi & Gợi ý phiên âm tự động:**
   - Chuyển đổi hai chiều: **Chữ Thái Việt ⇄ Phiên âm Latinh**.
   - Hỗ trợ đầy đủ hệ 6 thanh điệu, các vần đặc biệt (*special rimes*) và tra cứu từ điển chuẩn.
   - Tự động phiên âm câu chữ Thái theo quy tắc ngữ âm khi câu chưa có phiên âm lưu sẵn.

2. **Tra cứu từ điển mở rộng (Multi-source Search):**
   - Tìm kiếm đồng thời trên:
     - Từ điển mục từ chuẩn hóa.
     - Các từ mới do cộng đồng đóng góp đã được duyệt.
     - Các câu dịch ngữ cảnh thực tế đã được kiểm duyệt.

3. **Nền tảng đóng góp cộng đồng:**
   - **Đóng góp từ:** Nhập chữ Thái, phiên âm, kèm nghĩa tiếng Việt. Tự động kiểm tra độ nhất quán giữa chữ và phiên âm.
   - **Đóng góp câu:** Đóng góp câu chữ Thái nguyên bản, hỗ trợ thêm nghĩa tiếng Việt tham khảo.
   - **Dịch câu & Kiểm tra:** Cộng đồng tham gia dịch các câu tiếng Thái sang tiếng Việt, thẩm định và đánh giá độ tự nhiên của bản dịch.

4. **Trang quản trị (Admin Dashboard):**
   - Kiểm duyệt các mục đóng góp (Duyệt / Từ chối / Hoàn tác).
   - Thống kê thời gian thực số lượng bản ghi theo trạng thái.
   - Xuất dữ liệu sạch sang định dạng **JSON** hoặc **CSV** chuẩn UTF-8.

5. **Hiệu năng cao & Hỗ trợ đa nền tảng CSDL:**
   - Hỗ trợ chạy với **Supabase Cloud PostgreSQL** hoặc **SQLite Cục bộ**.
   - Cơ chế truy vấn gộp (Batch queries), giảm thiểu độ trễ mạng Internet và tải trang gần như tức thì (< 300ms).

---

## 🚀 Cài đặt & Chạy cục bộ

### Yêu cầu
- **Python 3.10+** (khuyên dùng Python 3.11)
- Git

### 1. Cài đặt môi trường

```powershell
# Di chuyển vào thư mục dự án
cd D:\DichTaiViet

# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt môi trường ảo (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 2. Cấu hình môi trường (.env)

Tạo file `.env` từ file mẫu `.env.example`:

```powershell
cp .env.example .env
```

Nội dung cấu hình mẫu trong `.env`:
```ini
# Chế độ kết nối: 'supabase' (Cloud PostgreSQL) hoặc 'sqlite' (Cục bộ)
DB_BACKEND=supabase

# Chuỗi kết nối Supabase Pooler (nếu dùng Supabase)
SUPABASE_DB_URL=postgresql://postgres.your-ref:your-password@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres

# Tài khoản đăng nhập quản trị
TAI_ADMIN_USER=admin
TAI_ADMIN_PASS=admin123
```
> *Lưu ý:* Nếu không cấu hình `SUPABASE_DB_URL`, hệ thống sẽ tự động sử dụng SQLite cục bộ tại `runtime/tai.db`.

### 3. Khởi chạy ứng dụng

```powershell
python server.py
```
Hoặc dùng `uvicorn`:
```powershell
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Truy cập giao diện web tại: **http://127.0.0.1:8000**  
Tài liệu API Swagger UI tại: **http://127.0.0.1:8000/api/docs**

---

## 🚢 Hướng dẫn Triển khai (Deployment)

Dự án được thiết kế sẵn sàng để deploy lên các nền tảng đám mây như **Render**, **Railway**, **Fly.io**, hoặc **Docker VPS**:

### Lệnh chạy (Start Command)
```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

### Biến môi trường cần thiết trên Server
| Tên biến | Mô tả | Mẫu giá trị |
| :--- | :--- | :--- |
| `DB_BACKEND` | Loại cơ sở dữ liệu | `supabase` |
| `SUPABASE_DB_URL` | Chuỗi kết nối PostgreSQL Supabase | `postgresql://postgres.[id]:[pass]@[host]:6543/postgres` |
| `TAI_ADMIN_USER` | Tên đăng nhập Admin | `admin` |
| `TAI_ADMIN_PASS` | Mật khẩu Admin | `mat_khau_bao_mat_cua_ban` |

---

## 📂 Cấu trúc thư mục

```
DichTaiViet/
├── data/                       # Dữ liệu từ điển runtime (JSON)
│   ├── taiviet_dictionary_dataset.json
│   └── taiviet_tokenizer.json
├── database/                   # Schema CSDL (PostgreSQL & SQLite)
│   ├── supabase.sql
│   ├── security.sql
│   └── extensions.sql
├── scripts/                    # Scripts đồng bộ & migration DB
│   └── load_to_supabase.py
├── tai_engine/                 # Engine quy tắc chuyển đổi âm tự chữ Thái
│   ├── engine.py
│   ├── validator.py
│   └── confirmed_rules.json
├── web/                        # Giao diện người dùng (Frontend SPA)
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── fonts/
├── .env.example                # Mẫu biến môi trường
├── .gitignore                  # Cấu hình bỏ qua file rác / nháp
├── requirements.txt            # Danh sách thư viện Python
├── server.py                   # FastAPI Application Backend
└── README.md
```

---

## 📄 Bản quyền & Phông chữ

- Phông chữ **Tai Viet Times** (`tvtimes.ttf`) và **Noto Sans Tai Viet** được tích hợp trong thư mục `web/fonts/` phục vụ hiển thị chính xác bảng mã Unicode chữ Thái Việt.
