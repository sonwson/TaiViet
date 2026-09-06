# Tai Việt — hệ thống dữ liệu ngôn ngữ local

**Bản hiện tại đã thực hiện promt3 + promt4:** xem [REPORT_PROMT34.md](REPORT_PROMT34.md) để biết hệ 6 thanh chính thức, special rimes, alias search, chuyển câu, lịch sử sửa phiên âm và kết quả kiểm thử mới. `REPORT.md` giữ kết quả giai đoạn trước.

Sau khi cập nhật code, chạy `python scripts/upgrade_promt34.py` để bổ sung bảng/index cho database hiện có, rồi khởi động lại server. Các schema cũ và dữ liệu import được giữ nguyên.

Bản thực thi theo `Promt1.md`, `Promt2.md` và tài liệu TASK 1. Có migration, database quan hệ, engine quy tắc có truy vết, website đóng góp và quản trị. Dữ liệu gốc không bị chuẩn hóa hoặc sửa để tăng accuracy.

Theo lựa chọn của bạn, ứng dụng hiện chạy local bằng SQLite. SQL PostgreSQL/Supabase đã được tạo và kiểm thử trên PostgreSQL nhúng; chưa có dự án Supabase hoặc website online. Xem [báo cáo thực hiện](REPORT.md) để biết kết quả, giới hạn và các trường hợp cần xác minh.

## Chạy nhanh trên Windows PowerShell

Mở PowerShell tại `D:\DichTaiViet`. Python 3.11 đã được dùng để kiểm thử.

```powershell
cd D:\DichTaiViet
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/audit.py
.\.venv\Scripts\python.exe scripts/migrate.py --dry-run --postgres-sql
.\.venv\Scripts\python.exe scripts/migrate.py --sqlite runtime/tai.db
.\.venv\Scripts\python.exe server.py
```

Mở **http://127.0.0.1:8000**. Frontend và backend dùng chung địa chỉ; không cần npm để chạy app. Nếu dùng môi trường Python hiện tại đã có thư viện, có thể chạy ngay `python server.py`.

**Cập nhật form tối giản:** nhập phiên âm sẽ chuyển sau khoảng 350 ms; một candidate được tự điền, nhiều candidate cần chọn theo promt3; chiều ngược cũng được hỗ trợ. Có thể sửa trực tiếp, phần đã sửa không bị tự ghi đè. Form không còn checkbox đồng ý, CAPTCHA hay xác nhận khi chưa khớp; backend vẫn giới hạn tốc độ và lưu pending. Metadata mới ghi `not_collected-local-v2`, không giả lập việc người dùng đã đồng ý. Đây là thay đổi bản local; SQL Supabase chuẩn bị trước đó vẫn giữ chính sách consent ban đầu.

Quản trị: xem mã sinh riêng tại `runtime/admin-token.txt`, rồi nhập vào tab **Quản trị**. Không commit hoặc gửi mã này cho người khác. Có thể cấu hình `TAI_ADMIN_TOKEN` bằng biến môi trường. Mã không nằm trong frontend. Đăng nhập admin chỉ dùng cho bản local này, không phải Supabase Auth.

App chỉ bind `127.0.0.1`, kiểm tra Host/Origin, cookie HttpOnly/SameSite, giới hạn độ dài, tốc độ gửi và mặc định `pending`. Khi đưa lên mạng cần tích hợp CAPTCHA có xác minh phía server, Supabase Anonymous Auth và backend deployment phù hợp; không public server local này trực tiếp.

Nhấn `Ctrl+C` tại terminal server để dừng. Dữ liệu nằm tại `runtime/tai.db`, không phụ thuộc vào phiên trình duyệt. Phiên người dùng local nằm trong bộ nhớ; restart server sẽ cấp danh tính anonymous mới.

## Các chức năng

- Đóng góp từ: nhập phiên âm và/hoặc chữ Tai, bắt buộc nghĩa. Tự điền gợi ý ngay trong ô bên cạnh và cho phép sửa trực tiếp; giữ riêng đầu vào, gợi ý, giá trị cuối cùng, nguồn và snapshot rule version.
- Đóng góp câu: lưu nguyên văn, nguồn, khu vực (tùy chọn); chờ duyệt.
- Dịch: thêm các bản dịch độc lập cho cùng câu, không ghi đè.
- Kiểm tra: `correct`, `needs_correction`, `incorrect`; lưu bản dịch đề xuất riêng. Không tự kiểm tra bản dịch mình gửi; mỗi danh tính một lượt trên mỗi bản dịch.
- Đánh giá câu: `natural`, `problematic`, `unsure`.
- Tra cứu chữ Tai, phiên âm, nghĩa trong từ điển đã import.
- Quản trị: lọc, tìm, approve/reject, xem dữ liệu, lịch sử và export JSON/CSV. Từ cộng đồng được duyệt vẫn nằm trong `word_contributions` và export JSON, chờ biên tập nhập mục từ; không tự động merge vào từ điển.

CSV có một dòng/câu với các cột JSON chứa metadata, tất cả translations và validations, reviews. JSON đầy đủ còn chứa từ đóng góp và annotations. Không chỉ lấy bản dịch cuối. Cả hai export giữ nguyên UTF-8 và khoảng trắng; dùng CSV như dữ liệu máy, không coi nội dung ô người dùng nhập là công thức bảng tính.

## Kiểm thử và báo cáo

```powershell
python -m unittest discover -s tests -v
python scripts/audit.py
python scripts/migrate.py --dry-run --postgres-sql
python scripts/migrate.py --sqlite runtime/tai.db
```

Migration không có `--sqlite` mặc định chỉ sinh bundle/báo cáo; `--dry-run` luôn không ghi database. Dry-run vẫn tạo bản sao dữ liệu, báo cáo và SQL nếu yêu cầu. ID sinh ổn định bằng UUIDv5. Chạy lại SQLite không thêm trùng; nếu cùng ID nhưng nội dung khác sẽ rollback transaction và báo lỗi. Trước khi ghi database đã có, SQLite backup API tạo `runtime/tai.db.before-*.bak`. Migration giữ source JSON nguyên vẹn và toàn bộ dòng Excel trong `source_records`.

`audit.py` cần chạy trước migration nếu muốn kèm archive Excel. `reports/migration_bundle.json` là gói quan hệ có thể kiểm tra; `reports/duplicates.json` liệt kê các nhóm cần xem xét. Bản sao lưu nguồn đầu phiên nằm trong `backups/source-20260906-022408/`, có manifest SHA-256. Script migration còn giữ bản JSON content-addressed trong `backups/`.

Kiểm thử SQL/RLS local, không cần tài khoản Supabase (Node.js và npm):

```powershell
npm.cmd install --prefix runtime/sql-check --no-audit --no-fund @electric-sql/pglite@0.5.8
python scripts/build_postgres_schema.py
python scripts/migrate.py --dry-run --postgres-sql
node scripts/test_postgres.mjs
```

PGlite dùng PostgreSQL thực chạy trong WebAssembly, có shim `auth.uid()` chỉ dành cho test. Nó kiểm tra SQL, full import/rerun, Unicode, grants, RLS và moderation; không thay thế kiểm thử tích hợp Supabase Auth/REST thật.

## Chuẩn bị PostgreSQL / Supabase

`database/supabase.sql` là schema hoàn chỉnh gồm tables, indexes, RLS, immutable triggers, rate limit cơ bản và RPC admin. `database/local.sql` là schema local; `database/security.sql` là phần bảo mật PostgreSQL; thay đổi chúng rồi chạy `python scripts/build_postgres_schema.py` để cập nhật file đích.

Khi có Supabase, đặt connection string riêng vào `DATABASE_URL` ngoài repository, rồi dùng PostgreSQL client:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f database/supabase.sql
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f reports/migration.sql
```

Chỉ chạy schema bằng migration owner. SQL import dùng transaction và `ON CONFLICT(id) DO NOTHING`, giữ nguyên dữ liệu đã có; bản JSON nguồn khác hash được coi là snapshot khác, cần review trước khi import để tránh thêm phiên bản ngoài ý muốn. Script không tự xóa dữ liệu cũ. Rollback khi lỗi xảy ra trong transaction là tự động; để hoàn tác một lần import đã commit, dùng backup database riêng đã tạo trước deployment. Không chạy DROP/TRUNCATE trên corpus cộng đồng.

Tạo user quản trị bằng Supabase Auth, rồi **qua SQL Editor với quyền owner** chèn UUID người đó vào `public.user_roles(user_id,role)` với `role='admin'`. Không cấp quyền quản lý roles cho frontend. Anonymous Auth tạo người dùng có role `authenticated`; `anon` không có danh tính và chỉ được đọc dữ liệu đã duyệt. Tham khảo [RLS của Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security) và [Anonymous Sign-Ins](https://supabase.com/docs/guides/auth/auth-anonymous).

Browser không được insert trực tiếp `word_contributions` trên Supabase vì snapshot engine cần backend tin cậy. Khi triển khai sau này, viết adapter backend xác minh Supabase JWT, chạy engine và ghi snapshot bằng quyền giới hạn. Bản server hiện tại cố ý chưa có adapter cloud vì bạn chọn local + SQL trước.

## Engine dùng trong Python

```python
from tai_engine import parse_tai_word, compose_tai_word
from tai_engine import parse_romanization, romanization_to_tai, tai_to_romanization

parsed = parse_tai_word('ꪀ꪿ꪱ')
assert compose_tai_word(parsed) == 'ꪀ꪿ꪱ'
result = romanization_to_tai('khảu', dictionary=True)
```

`candidates` là kết quả tạo bằng quy tắc; `dictionary_candidates` là tra cứu từ điển, luôn tách riêng. Thứ tự dùng tần suất từ điển rồi thứ tự chữ; không phải xác suất đúng. `confidence=null` vì chưa hiệu chuẩn. Layout dấu thanh khi sinh chữ có nguồn quan sát corpus, không được gọi là quy tắc ngôn ngữ đã xác nhận. Bảng 6 thanh mới nằm trong `tai_engine/confirmed_rules.json` theo promt3. Các pattern trong `reports/promt34/special_rime_inference.json` chỉ là thống kê và **không được tự kích hoạt**.

Parser trả candidates theo từng âm tiết và giữ separator nguyên bản. Không suy đoán tách từ viết liền không có ranh giới. Compose dựng từ components/pattern và vị trí dấu, không chép lại trường `original`. Các cấu trúc không hỗ trợ trả diagnostics hoặc lỗi rõ ràng. `group_rules.py` được đọc như JSON, không import/eval, không sửa file nguồn.

## Script chuẩn bị dữ liệu học máy cũ

`data/prepare_data.py` đã sửa đường dẫn đầu vào, bỏ tự thêm `u` vào phiên âm, giữ nguyên khoảng trắng và chia train/validation theo chữ Tai để các hướng của cùng từ không rơi vào hai tập. Đây là tùy chọn, không cần chạy để dùng website:

```powershell
python -m pip install -r requirements-training.txt
python data/prepare_data.py
```

Không có model nào được train trong công việc này. Tokenizer gốc được giữ nguyên; không dùng decode của nó làm bản gốc corpus.
