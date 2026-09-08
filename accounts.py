"""Member accounts, private contribution history, and Resend password recovery."""
import hashlib
import logging
import os
import re
import secrets
import time
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

COOKIE = 'tai_account'
SESSION_SECONDS = 7 * 86400
RESET_SECONDS = 30 * 60
ITERATIONS = 600000
LOG = logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt}${value.hex()}'


DUMMY_HASH = hash_password('unused-password-for-timing')


def verify_password(password, stored):
    try:
        algorithm, iterations, salt, expected = stored.split('$')
        if algorithm != 'pbkdf2_sha256': return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iterations))
        return secrets.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def email_input(data):
    email = data.get('email')
    if not isinstance(email, str) or len(email) > 254:
        raise HTTPException(422, 'Email không hợp lệ.')
    email = email.strip().lower()
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", email):
        raise HTTPException(422, 'Email không hợp lệ.')
    return email


def password_input(data, new=True):
    password = data.get('password')
    if not isinstance(password, str) or not (10 if new else 1) <= len(password) <= 128 or '\x00' in password:
        raise HTTPException(422, 'Mật khẩu cần từ 10 đến 128 ký tự.' if new else 'Mật khẩu không hợp lệ.')
    return password


def login_identifier_input(data):
    val = data.get('email') or data.get('username')
    if not isinstance(val, str) or not val.strip() or len(val) > 254:
        raise HTTPException(422, 'Vui lòng nhập email hoặc tên đăng nhập.')
    return val.strip().lower()


def format_cooldown_time(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days} ngày {hours} giờ" if hours > 0 else f"{days} ngày"
    if hours > 0:
        return f"{hours} giờ {mins} phút" if mins > 0 else f"{hours} giờ"
    return f"{max(1, mins)} phút"


def resend_ready():
    url = urlsplit(os.environ.get('PUBLIC_BASE_URL', ''))
    return bool(os.environ.get('RESEND_API_KEY') and os.environ.get('RESEND_FROM')
                and url.scheme == 'https' and url.netloc and not url.query and not url.fragment)


def send_reset_email(email, token):
    # The fragment keeps the reset secret out of access logs and Referer headers.
    link = os.environ['PUBLIC_BASE_URL'].rstrip('/') + '/#reset-password?token=' + token
    response = httpx.post('https://api.resend.com/emails',
        headers={'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY'],
                 'Idempotency-Key': 'password-reset-' + digest(token)},
        json={'from': os.environ['RESEND_FROM'], 'to': [email],
              'subject': 'Đặt lại mật khẩu Tai Việt',
              'text': 'Bạn đã yêu cầu đặt lại mật khẩu Tai Việt.\n\n'
                      + link + '\n\nLiên kết dùng một lần, có hiệu lực trong 30 phút. '
                      'Nếu bạn không yêu cầu, hãy bỏ qua email này.'}, timeout=15)
    response.raise_for_status()


class Accounts:
    def __init__(self, server):
        self.s = server

    def initialize(self):
        sql = (self.s.ROOT / 'database/accounts.sql').read_text(encoding='utf-8')
        if self.s.DB_BACKEND == 'supabase':
            sql = re.sub(r'\b(id|user_id) TEXT', r'\1 UUID', sql)
            sql = sql.replace('created_at TEXT', 'created_at TIMESTAMPTZ')
        with self.s.database() as db:
            for statement in sql.split(';'):
                if statement.strip():
                    db.execute(statement.strip())

        with self.s.database() as db:
            if self.s.DB_BACKEND == 'supabase':
                cols = [r[0] for r in db.execute("SELECT column_name FROM information_schema.columns WHERE table_name='user_accounts'").fetchall()]
            else:
                cols = [r[1] for r in db.execute("PRAGMA table_info(user_accounts)").fetchall()]

            for col, col_def in [
                ('role', "TEXT NOT NULL DEFAULT 'user'"),
                ('name_updated_at', 'BIGINT DEFAULT 0'),
                ('password_updated_at', 'BIGINT DEFAULT 0')
            ]:
                if col not in cols:
                    db.execute(f'ALTER TABLE user_accounts ADD COLUMN {col} {col_def}')

        with self.s.database() as db:
            if self.s.DB_BACKEND == 'supabase':
                for table in ('user_accounts', 'account_sessions', 'password_resets', 'account_feedback', 'password_change_logs'):
                    try:
                        db.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
                        db.execute(f'REVOKE ALL ON {table} FROM PUBLIC, anon, authenticated')
                    except Exception:
                        if hasattr(db, 'rollback'): db.rollback()

            admin_user = getattr(self.s, 'ADMIN_USERNAME', 'admin')
            admin_pass = getattr(self.s, 'ADMIN_PASSWORD', 'admin123')
            admin_email = os.environ.get('TAI_ADMIN_EMAIL', f'{admin_user}@taiviet.local')
            existing_admin = db.execute("SELECT id FROM user_accounts WHERE role='admin' OR email=?", (admin_email,)).fetchone()
            if not existing_admin:
                admin_id = str(uuid.uuid4())
                stored = hash_password(admin_pass)
                now = int(time.time())
                try:
                    db.execute(
                        "INSERT INTO user_accounts(id,email,password_hash,display_name,role,name_updated_at,password_updated_at) VALUES(?,?,?,?,'admin',?,?)",
                        (admin_id, admin_email, stored, 'Quản trị viên', now, now)
                    )
                except Exception:
                    if hasattr(db, 'rollback'): db.rollback()

    def user(self, request):
        token = request.cookies.get(COOKIE)
        if not token or len(token) > 128: return None
        with self.s.database() as db:
            row = db.execute('''SELECT u.id,u.email,u.display_name,
                coalesce(u.role,'user') AS role,
                coalesce(u.name_updated_at,0) AS name_updated_at,
                coalesce(u.password_updated_at,0) AS password_updated_at,
                u.created_at
                FROM user_accounts u
                JOIN account_sessions s ON s.user_id=u.id
                WHERE s.token_hash=? AND s.expires_at>?''', (digest(token), int(time.time()))).fetchone()
            if not row: return None
            user_data = {**dict(row), 'id': str(row['id'])}
            now = int(time.time())
            recent = [r[0] for r in db.execute('SELECT changed_at FROM password_change_logs WHERE user_id=? AND changed_at > ? ORDER BY changed_at ASC', (user_data['id'], now - 86400)).fetchall()]
            user_data['password_changes_count'] = len(recent)
            user_data['password_lock_until'] = (recent[0] + 86400) if len(recent) >= 3 else 0
            return user_data

    def required_user(self, request):
        user = self.user(request)
        if not user: raise HTTPException(401, 'Đăng nhập để xem đóng góp của bạn.')
        return user

    def create_session(self, db, user_id, request):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        db.execute('DELETE FROM account_sessions WHERE expires_at<=?', (now,))
        db.execute('INSERT INTO account_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)',
                   (digest(token), user_id, now + SESSION_SECONDS))
        old = request.cookies.get(COOKIE)
        if old: db.execute('DELETE FROM account_sessions WHERE token_hash=?', (digest(old),))
        return token

    def claim_guest(self, db, user_id, request):
        guest = self.s.sessions.get(request.cookies.get('tai_session'))
        if not guest or guest.get('admin') or guest['expires'] <= time.time(): return
        for table in ('word_contributions', 'sentences', 'translations', 'sentence_submissions',
                      'sentence_corrections', 'romanization_corrections'):
            db.execute(f'UPDATE {table} SET contributor_id=? WHERE contributor_id=?', (user_id, guest['id']))

    def login_response(self, token, request, is_admin=False, admin_token=None):
        payload = {'ok': True, 'admin': is_admin}
        if admin_token: payload['token'] = admin_token
        response = JSONResponse(payload)
        secure = request.url.scheme == 'https' or request.headers.get('x-forwarded-proto') == 'https'
        response.set_cookie(COOKIE, token, httponly=True, secure=secure, samesite='lax', max_age=SESSION_SECONDS)
        if is_admin and admin_token:
            response.set_cookie('tai_admin_token', admin_token, httponly=True, secure=secure, samesite='lax', max_age=SESSION_SECONDS)
        self.s.sessions.pop(request.cookies.get('tai_session'), None)
        response.delete_cookie('tai_session')
        return response

    async def register(self, request: Request):
        self.s.throttle('register:' + self.s.get_client_ip(request), 5, 3600)
        data = await self.s.payload(request)
        email = email_input(data)
        password = password_input(data)
        user_id = str(uuid.uuid4())
        name = data.get('display_name', '')
        if not isinstance(name, str) or len(name) > 60 or any(ord(c) < 32 for c in name):
            raise HTTPException(422, 'Tên hiển thị tối đa 60 ký tự.')
        name = name.strip() or 'Thành viên ' + user_id[:8]
        stored = await run_in_threadpool(hash_password, password)
        now = int(time.time())
        try:
            with self.s.database() as db:
                db.execute('INSERT INTO user_accounts(id,email,password_hash,display_name,role,name_updated_at,password_updated_at) VALUES(?,?,?,?,?,?,?)',
                           (user_id, email, stored, name, 'user', now, now))
                self.claim_guest(db, user_id, request)
                token = self.create_session(db, user_id, request)
        except self.s.DB_INTEGRITY_ERRORS:
            raise HTTPException(409, 'Không thể đăng ký email này. Hãy đăng nhập hoặc dùng Quên mật khẩu.')
        return self.login_response(token, request)

    async def login(self, request: Request):
        data = await self.s.payload(request)
        ident = login_identifier_input(data)
        password = password_input(data, new=False)
        self.s.throttle('account-login-ip:' + self.s.get_client_ip(request), 15, 900)
        self.s.throttle('account-login-email:' + digest(ident), 10, 900)

        admin_user = getattr(self.s, 'ADMIN_USERNAME', 'admin')
        admin_pass = getattr(self.s, 'ADMIN_PASSWORD', 'admin123')
        is_sys_admin = (ident == admin_user.lower() and secrets.compare_digest(self.s.hash_pass(password), self.s.ADMIN_HASH))

        with self.s.database() as db:
            row = db.execute('''SELECT id,email,password_hash,display_name,
                coalesce(role,'user') AS role,
                coalesce(name_updated_at,0) AS name_updated_at,
                coalesce(password_updated_at,0) AS password_updated_at
                FROM user_accounts WHERE email=? OR (role='admin' AND ?=?)''',
                (ident, ident, admin_user.lower())).fetchone()

        if is_sys_admin and not row:
            with self.s.database() as db:
                row = db.execute("SELECT id,email,password_hash,display_name,coalesce(role,'user') AS role,coalesce(name_updated_at,0) AS name_updated_at,coalesce(password_updated_at,0) AS password_updated_at FROM user_accounts WHERE role='admin' LIMIT 1").fetchone()

        if row: row = dict(row)
        stored = row['password_hash'] if row else DUMMY_HASH
        valid = is_sys_admin or await run_in_threadpool(verify_password, password, stored)
        if not row or not valid: raise HTTPException(401, 'Email hoặc mật khẩu không chính xác.')

        with self.s.database() as db:
            lock = ' FOR UPDATE' if self.s.DB_BACKEND == 'supabase' else ''
            current = db.execute('SELECT password_hash FROM user_accounts WHERE id=?' + lock, (row['id'],)).fetchone()
            if not is_sys_admin and current['password_hash'] != stored: raise HTTPException(401, 'Mật khẩu đã thay đổi. Hãy đăng nhập lại.')
            self.claim_guest(db, row['id'], request)
            token = self.create_session(db, row['id'], request)

        is_admin = bool(row.get('role') == 'admin' or is_sys_admin)
        admin_jwt = self.s.create_admin_jwt(user_id=row['id'], username=row.get('display_name') or admin_user) if is_admin else None
        return self.login_response(token, request, is_admin=is_admin, admin_token=admin_jwt)

    def logout(self, request: Request):
        token = request.cookies.get(COOKIE)
        if token:
            with self.s.database() as db:
                db.execute('DELETE FROM account_sessions WHERE token_hash=?', (digest(token),))
        s = self.s.sessions.get(request.cookies.get('tai_session'))
        if s: s['admin'] = False
        response = JSONResponse({'ok': True})
        response.delete_cookie(COOKIE)
        response.delete_cookie('tai_admin_token')
        return response

    def deliver_reset(self, email):
        token = secrets.token_urlsafe(32)
        try:
            with self.s.database() as db:
                row = db.execute('SELECT id FROM user_accounts WHERE email=?', (email,)).fetchone()
                if not row: return
                now = int(time.time())
                db.execute('DELETE FROM password_resets WHERE expires_at<=?', (now,))
                db.execute('INSERT INTO password_resets(token_hash,user_id,expires_at) VALUES(?,?,?)',
                           (digest(token), row['id'], now + RESET_SECONDS))
            send_reset_email(email, token)
        except Exception as exc:
            if hasattr(exc, 'response') and getattr(exc.response, 'status_code', None):
                try:
                    err_detail = exc.response.json().get('message') or exc.response.text[:200]
                except Exception:
                    err_detail = getattr(exc.response, 'text', '')[:200] or str(exc)
                LOG.error('Password reset delivery failed (HTTP %s: %s)', exc.response.status_code, err_detail)
            else:
                LOG.error('Password reset delivery failed (%s: %s)', type(exc).__name__, exc)
            try:
                with self.s.database() as db:
                    db.execute('DELETE FROM password_resets WHERE token_hash=?', (digest(token),))
            except Exception:
                LOG.error('Password reset cleanup failed')

    async def forgot(self, request: Request, background_tasks: BackgroundTasks):
        data = await self.s.payload(request)
        email = email_input(data)
        self.s.throttle('reset-ip:' + self.s.get_client_ip(request), 5, 3600)
        self.s.throttle('reset-email:' + digest(email), 3, 3600)
        if not resend_ready():
            raise HTTPException(503, 'Khôi phục mật khẩu chưa sẵn sàng. Vui lòng thử lại sau.')
        background_tasks.add_task(self.deliver_reset, email)
        return {'message': 'Nếu email đã đăng ký, bạn sẽ nhận được liên kết đặt lại mật khẩu. Hãy kiểm tra cả thư rác.'}

    async def reset(self, request: Request):
        self.s.throttle('reset-confirm:' + self.s.get_client_ip(request), 10, 900)
        data = await self.s.payload(request)
        token = data.get('token')
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            raise HTTPException(422, 'Liên kết không hợp lệ hoặc đã hết hạn.')
        password = password_input(data)
        stored = await run_in_threadpool(hash_password, password)
        with self.s.database() as db:
            # DELETE RETURNING atomically consumes the token, including concurrent requests.
            row = db.execute('DELETE FROM password_resets WHERE token_hash=? AND expires_at>? RETURNING user_id',
                             (digest(token), int(time.time()))).fetchone()
            if not row: raise HTTPException(422, 'Liên kết không hợp lệ hoặc đã hết hạn. Hãy yêu cầu liên kết mới.')
            db.execute('UPDATE user_accounts SET password_hash=? WHERE id=?', (stored, row['user_id']))
            db.execute('DELETE FROM account_sessions WHERE user_id=?', (row['user_id'],))
            db.execute('DELETE FROM password_resets WHERE user_id=?', (row['user_id'],))
        response = JSONResponse({'message': 'Đã đổi mật khẩu. Hãy đăng nhập bằng mật khẩu mới.'})
        response.delete_cookie(COOKIE)
        return response

    def save_feedback(self, db, actor, table, record, message, decision):
        if not isinstance(message, str) or len(message)>2000 or '\x00' in message:
            raise HTTPException(422, 'Phản hồi tối đa 2.000 ký tự.')
        message=message.strip()
        if not message: return None
        owner=record.get('contributor_id')
        if not owner or not db.execute('SELECT id FROM user_accounts WHERE id=?',(owner,)).fetchone():
            raise HTTPException(422, 'Người đóng góp chưa có tài khoản để nhận phản hồi.')
        preview=next((record.get(k) for k in ('vietnamese_text','vietnamese_meaning','tai_text_final','tai_text_original','suggested_tai_text','suggested_translation','suggested_romanization') if record.get(k)), str(record['id']))
        return self.s.insert(db,'account_feedback',dict(user_id=owner,entity_table=table,entity_id=str(record['id']),
            message=message,decision=decision,preview=str(preview)[:500],admin_id=str(actor['id'])))

    def feedback(self, request: Request, offset: int = 0):
        user=self.required_user(request)
        if offset<0: raise HTTPException(422, 'Trang không hợp lệ.')
        with self.s.database() as db:
            rows=db.execute('SELECT id,entity_table,entity_id,message,decision,preview,read_at,created_at FROM account_feedback WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 21 OFFSET ?', (user['id'],offset)).fetchall()
            unread=db.execute('SELECT count(*) FROM account_feedback WHERE user_id=? AND read_at IS NULL',(user['id'],)).fetchone()[0]
        return {'items':[dict(r) for r in rows[:20]],'has_more':len(rows)>20,'unread':unread}

    async def read_feedback(self, request: Request):
        user=self.required_user(request); data=await self.s.payload(request)
        fid=self.s.text(data,'id',True,40)
        with self.s.database() as db:
            row=db.execute('SELECT id FROM account_feedback WHERE id=? AND user_id=?',(fid,user['id'])).fetchone()
            if not row: raise HTTPException(404,'Không tìm thấy phản hồi.')
            db.execute('UPDATE account_feedback SET read_at=coalesce(read_at,?) WHERE id=? AND user_id=?',(int(time.time()),fid,user['id']))
        return {'ok':True}

    def contributions(self, request: Request, kind: str = 'all', status: str = 'all', offset: int = 0):
        user = self.required_user(request)
        if kind not in ('all', 'word', 'sentence', 'translation') or status not in ('all', 'pending', 'approved', 'rejected') or offset < 0:
            raise HTTPException(422, 'Bộ lọc không hợp lệ.')
        union = '''SELECT id,'word' AS kind,coalesce(tai_text_final,tai_text_original) AS tai_text,
            coalesce(romanization_final,romanization_original) AS romanization,vietnamese_meaning AS meaning,status,created_at
            FROM word_contributions WHERE contributor_id=?
            UNION ALL SELECT id,'sentence' AS kind,tai_text_original AS tai_text,romanization,
            '' AS meaning,status,created_at FROM sentences WHERE contributor_id=?
            UNION ALL SELECT t.id,'translation' AS kind,s.tai_text_original AS tai_text,s.romanization,
            t.vietnamese_text AS meaning,t.status,t.created_at FROM translations t JOIN sentences s ON s.id=t.sentence_id WHERE t.contributor_id=?'''
        clauses, params = [], [user['id'], user['id'],user['id']]
        if kind != 'all': clauses.append('kind=?'); params.append(kind)
        if status != 'all': clauses.append('status=?'); params.append(status)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.s.database() as db:
            rows = db.execute('SELECT * FROM (' + union + ') c' + where + ' ORDER BY created_at DESC,id DESC LIMIT 21 OFFSET ?',
                              params + [offset]).fetchall()
            stats = db.execute('SELECT status,count(*) AS total FROM (' + union + ') c GROUP BY status',
                               (user['id'], user['id'],user['id'])).fetchall()
        return {'items': [dict(r) for r in rows[:20]], 'has_more': len(rows) > 20,
                'counts': {r['status']: r['total'] for r in stats}}

    def leaderboard(self):
        with self.s.database() as db:
            rows = db.execute('''SELECT u.display_name,
                sum(c.words) AS words,sum(c.sentences) AS sentences,count(*) AS total
                FROM user_accounts u JOIN (
                    SELECT contributor_id,1 AS words,0 AS sentences FROM word_contributions WHERE status='approved'
                    UNION ALL SELECT contributor_id,0 AS words,1 AS sentences FROM sentences WHERE status='approved'
                ) c ON c.contributor_id=u.id GROUP BY u.id,u.display_name
                ORDER BY total DESC,u.id ASC LIMIT 50''').fetchall()
        items, rank, previous = [], 0, None
        for index, row in enumerate(rows, 1):
            if row['total'] != previous: rank = index
            previous = row['total']
            items.append({**dict(row), 'rank': rank})
        return {'items': items}

    async def update_profile(self, request: Request):
        user = self.required_user(request)
        self.s.throttle('update-profile:' + user['id'], 10, 3600)
        data = await self.s.payload(request)
        name = data.get('display_name', '')
        if not isinstance(name, str) or len(name.strip()) < 2 or len(name.strip()) > 60 or any(ord(c) < 32 for c in name):
            raise HTTPException(422, 'Tên hiển thị phải từ 2 đến 60 ký tự hợp lệ.')
        name = name.strip()

        now = int(time.time())
        last_updated = user.get('name_updated_at') or 0
        cooldown = 7 * 86400
        if last_updated > 0 and (now - last_updated) < cooldown:
            remaining = cooldown - (now - last_updated)
            time_str = format_cooldown_time(remaining)
            raise HTTPException(429, f'Bạn chỉ có thể đổi tên hiển thị 7 ngày một lần. Lần đổi tiếp theo sau {time_str}.')

        with self.s.database() as db:
            db.execute('UPDATE user_accounts SET display_name=?, name_updated_at=? WHERE id=?', (name, now, user['id']))
        return {'ok': True, 'display_name': name, 'name_updated_at': now, 'message': 'Đã đổi tên hiển thị thành công.'}

    async def change_password(self, request: Request):
        user = self.required_user(request)
        self.s.throttle('change-password:' + user['id'], 5, 3600)
        data = await self.s.payload(request)
        current_password = data.get('current_password', '')
        if not current_password:
            raise HTTPException(422, 'Vui lòng nhập mật khẩu hiện tại.')
        new_password = password_input({'password': data.get('new_password')}, new=True)
        confirm_password = data.get('confirm_password', '')
        if new_password != confirm_password:
            raise HTTPException(422, 'Mật khẩu mới và xác nhận mật khẩu chưa khớp.')

        now = int(time.time())
        with self.s.database() as db:
            recent = [r[0] for r in db.execute('SELECT changed_at FROM password_change_logs WHERE user_id=? AND changed_at > ? ORDER BY changed_at ASC', (user['id'], now - 86400)).fetchall()]
            if len(recent) >= 3:
                remaining = (recent[0] + 86400) - now
                time_str = format_cooldown_time(remaining)
                raise HTTPException(429, f'Bạn đã đổi mật khẩu 3 lần trong 24 giờ qua. Bạn có thể đổi lại sau {time_str}.')

            row = db.execute('SELECT password_hash FROM user_accounts WHERE id=?', (user['id'],)).fetchone()
            if not row or not await run_in_threadpool(verify_password, current_password, row['password_hash']):
                raise HTTPException(401, 'Mật khẩu hiện tại không chính xác.')

            new_hash = await run_in_threadpool(hash_password, new_password)
            db.execute('UPDATE user_accounts SET password_hash=?, password_updated_at=? WHERE id=?', (new_hash, now, user['id']))
            self.s.insert(db, 'password_change_logs', dict(user_id=user['id'], changed_at=now))
        return {'ok': True, 'password_updated_at': now, 'password_changes_count': len(recent) + 1, 'message': 'Đã cập nhật mật khẩu thành công.'}

    def stats(self, request: Request):
        user = self.required_user(request)
        with self.s.database() as db:
            w_rows = db.execute('SELECT status, count(*) AS cnt FROM word_contributions WHERE contributor_id=? GROUP BY status', (user['id'],)).fetchall()
            s_rows = db.execute('SELECT status, count(*) AS cnt FROM sentences WHERE contributor_id=? GROUP BY status', (user['id'],)).fetchall()

            w_stats = {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}
            for r in w_rows:
                st = r['status']
                cnt = int(r['cnt'])
                if st in w_stats: w_stats[st] = cnt
                w_stats['total'] += cnt

            s_stats = {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}
            for r in s_rows:
                st = r['status']
                cnt = int(r['cnt'])
                if st in s_stats: s_stats[st] = cnt
                s_stats['total'] += cnt

            score = w_stats['approved'] + s_stats['approved']
            t_stats={'pending':0,'approved':0,'rejected':0,'total':0}
            for row in db.execute('SELECT status,count(*) AS cnt FROM translations WHERE contributor_id=? GROUP BY status',(user['id'],)).fetchall():
                t_stats[row['status']]=int(row['cnt'])
                t_stats['total']+=int(row['cnt'])
            total = w_stats['total'] + s_stats['total'] + t_stats['total']

            rank = None
            if score > 0:
                higher = db.execute('''SELECT count(*) FROM (
                    SELECT contributor_id, sum(approved_cnt) as score FROM (
                        SELECT contributor_id, count(*) as approved_cnt FROM word_contributions WHERE status='approved' GROUP BY contributor_id
                        UNION ALL
                        SELECT contributor_id, count(*) as approved_cnt FROM sentences WHERE status='approved' GROUP BY contributor_id
                    ) GROUP BY contributor_id HAVING sum(approved_cnt) > ?
                )''', (score,)).fetchone()[0]
                rank = int(higher) + 1

        return {
            'words': w_stats,
            'sentences': s_stats,
            'translations': t_stats,
            'total': total,
            'score': score,
            'rank': rank
        }

    def install(self):
        self.initialize()
        for path, handler, method in (
            ('auth/register', self.register, 'POST'), ('auth/login', self.login, 'POST'),
            ('auth/logout', self.logout, 'POST'), ('auth/forgot-password', self.forgot, 'POST'),
            ('auth/reset-password', self.reset, 'POST'), ('me/contributions', self.contributions, 'GET'),
            ('me/profile', self.update_profile, 'POST'), ('me/change-password', self.change_password, 'POST'),
            ('me/stats', self.stats, 'GET'),
            ('me/feedback', self.feedback, 'GET'), ('me/feedback/read', self.read_feedback, 'POST'),
            ('leaderboard', self.leaderboard, 'GET')):
            self.s.app.add_api_route('/api/' + path, handler, methods=[method])
