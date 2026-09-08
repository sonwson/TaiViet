from pathlib import Path
import sys
if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8',errors='replace')
if hasattr(sys.stderr,'reconfigure'): sys.stderr.reconfigure(encoding='utf-8',errors='replace')
from contextlib import contextmanager
from collections import defaultdict,deque
import csv
import html
import io
import json
import os
import secrets
import sqlite3
import time
import uuid
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from tai_engine.engine import Engine,ROOT

ENV_FILE=ROOT/'.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1)
            os.environ.setdefault(k.strip(),v.strip())

DB_PATH=Path(os.environ.get('TAI_DB_PATH',ROOT/'runtime/tai.db'))
DB_PATH.parent.mkdir(exist_ok=True,parents=True)
TOKEN_PATH=ROOT/'runtime/admin-token.txt'
ADMIN_TOKEN=os.environ.get('TAI_ADMIN_TOKEN')
if not ADMIN_TOKEN:
    if not TOKEN_PATH.exists(): TOKEN_PATH.write_text(secrets.token_urlsafe(32),encoding='utf-8')
    ADMIN_TOKEN=TOKEN_PATH.read_text(encoding='utf-8').strip()
ADMIN_USERNAME=os.environ.get('TAI_ADMIN_USER','admin')
ADMIN_PASSWORD=os.environ.get('TAI_ADMIN_PASS','admin123')
import hashlib
import jwt
def hash_pass(p): return hashlib.sha256(p.encode('utf-8')).hexdigest()
ADMIN_HASH=hash_pass(ADMIN_PASSWORD)
JWT_SECRET=os.environ.get('TAI_JWT_SECRET',ADMIN_HASH+'_tai_jwt_key_2026')
JWT_ALGORITHM='HS256'
JWT_EXPIRATION_SECONDS=86400*7

def create_admin_jwt(user_id=None,username=ADMIN_USERNAME):
    now=int(time.time())
    payload={'sub':user_id or str(uuid.uuid4()),'username':username,'role':'admin','admin':True,'iat':now,'exp':now+JWT_EXPIRATION_SECONDS}
    return jwt.encode(payload,JWT_SECRET,algorithm=JWT_ALGORITHM)

def verify_admin_jwt(token):
    if not token: return None
    try:
        data=jwt.decode(token,JWT_SECRET,algorithms=[JWT_ALGORITHM])
        if data.get('admin') is True or data.get('role')=='admin': return data
    except Exception: return None
    return None

def get_admin_jwt_claims(request):
    auth_header=request.headers.get('authorization','')
    jwt_token=None
    if auth_header.startswith('Bearer '): jwt_token=auth_header[7:].strip()
    if not jwt_token: jwt_token=request.cookies.get('tai_admin_token')
    return verify_admin_jwt(jwt_token)
engine=Engine()
app=FastAPI(title='Tai Việt — cộng đồng dữ liệu',docs_url='/api/docs')
sessions={}; limits=defaultdict(deque)
login_failures=defaultdict(list); login_lockouts={}
CONSENT='not_collected-local-v2'

DB_BACKEND=os.environ.get('DB_BACKEND','sqlite').lower().strip()
SUPABASE_DB_URL=os.environ.get('SUPABASE_DB_URL')
pg_pool=None

if DB_BACKEND=='supabase' and SUPABASE_DB_URL:
    try:
        import psycopg2
        from psycopg2 import pool
        from psycopg2.extras import DictCursor
        pg_pool=pool.ThreadedConnectionPool(
            1,10,SUPABASE_DB_URL,connect_timeout=10,
            keepalives=1,keepalives_idle=30,keepalives_interval=10,
            keepalives_count=3,tcp_user_timeout=15000)
        DB_INTEGRITY_ERRORS=(sqlite3.IntegrityError,psycopg2.IntegrityError)
        print(f"[*] Chế độ CSDL: Supabase PostgreSQL (Cloud)")
    except Exception as e:
        print(f"[!] Lỗi kết nối Supabase Pool ({e}). Chuyển sang SQLite.")
        DB_BACKEND='sqlite'
        DB_INTEGRITY_ERRORS=(sqlite3.IntegrityError,)
else:
    DB_BACKEND='sqlite'
    DB_INTEGRITY_ERRORS=(sqlite3.IntegrityError,)


import re

class PgCursorWrapper:
    def __init__(self,cursor):
        self._cursor=cursor

    def _convert_sql(self,sql):
        sql_conv=sql.replace('?','%s')
        if 'INSERT OR IGNORE INTO' in sql_conv.upper():
            sql_conv=re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO','INSERT INTO',sql_conv,flags=re.IGNORECASE)
            sql_conv=sql_conv.rstrip().rstrip(';')+' ON CONFLICT DO NOTHING'
        sql_conv=re.sub(r'\bLIKE\b','ILIKE',sql_conv)
        return sql_conv

    def execute(self,sql,params=None):
        converted=self._convert_sql(sql)
        if params is not None:
            clean_params=[]
            for p in params:
                if isinstance(p,(dict,list)): clean_params.append(json.dumps(p,ensure_ascii=False))
                else: clean_params.append(p)
            self._cursor.execute(converted,tuple(clean_params))
        else:
            self._cursor.execute(converted)
        return self

    def fetchone(self): return self._cursor.fetchone()
    def fetchall(self): return self._cursor.fetchall()
    def __iter__(self): return iter(self._cursor)
    @property
    def description(self): return self._cursor.description


class PgConnectionWrapper:
    def __init__(self,conn):
        self._conn=conn
        self._cursor=conn.cursor(cursor_factory=DictCursor)

    def execute(self,sql,params=None):
        wrapper=PgCursorWrapper(self._cursor)
        return wrapper.execute(sql,params)

    def commit(self): self._conn.commit()
    def rollback(self): self._conn.rollback()
    def close(self): self._cursor.close()


def checkout_pg_connection():
    # Probe before starting application work: idle pooled sockets may have expired.
    for attempt in range(2):
        conn=pg_pool.getconn()
        wrapper=None
        try:
            wrapper=PgConnectionWrapper(conn)
            wrapper.execute('SELECT 1').fetchone()
            wrapper.rollback()
            return conn,wrapper
        except Exception:
            if wrapper is not None:
                try: wrapper.close()
                except Exception: pass
            pg_pool.putconn(conn,close=True)
            if attempt==1: raise


@contextmanager
def database():
    if DB_BACKEND=='supabase' and pg_pool:
        conn,wrapper=checkout_pg_connection()
        discard=False
        try:
            yield wrapper
            wrapper.commit()
        except Exception:
            # Never replay a transaction: a failed commit may already have succeeded.
            try: wrapper.rollback()
            except Exception: discard=True
            raise
        finally:
            try: wrapper.close()
            except Exception: discard=True
            pg_pool.putconn(conn,close=discard or bool(conn.closed))
    else:
        db=sqlite3.connect(DB_PATH); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        db.create_function('LOWER', 1, lambda s: s.lower() if s is not None else None)
        try:
            with db: yield db
        finally: db.close()


try:
    from scripts.upgrade_promt34 import upgrade
except ImportError:
    upgrade = None

if DB_BACKEND=='sqlite':
    with database() as db:
        db.executescript((ROOT/'database/local.sql').read_text(encoding='utf-8'))
        db.execute('''CREATE TABLE IF NOT EXISTS sentence_corrections (
            id TEXT PRIMARY KEY, sentence_id TEXT NOT NULL REFERENCES sentences(id), base_tai_text TEXT,
            suggested_tai_text TEXT NOT NULL, suggested_romanization TEXT NOT NULL, suggested_meaning TEXT DEFAULT '',
            contributor_id TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
    if upgrade:
        try: upgrade(DB_PATH,engine)
        except Exception: pass
else:
    with database() as db:
        initial_count=db.execute('SELECT count(*) FROM word_senses').fetchone()[0]
        print(f"[+] Đã kết nối Supabase Cloud. Số bản ghi word_senses hiện có: {initial_count:,}")

from accounts import Accounts, resend_ready
accounts = Accounts(sys.modules[__name__])


def get_client_ip(request:Request)->str:
    xff=request.headers.get('x-forwarded-for')
    if xff: return xff.split(',')[0].strip()
    return request.client.host if request.client else '127.0.0.1'


def check_login_rate(ip:str):
    now=time.time()
    if ip in login_lockouts:
        locked_until=login_lockouts[ip]
        if now<locked_until:
            rem=int(locked_until-now)
            raise HTTPException(429,f'Quá nhiều lần đăng nhập thất bại. IP tạm thời bị khóa trong {rem} giây.')
        del login_lockouts[ip]
        login_failures[ip].clear()


def record_login_failure(ip:str):
    now=time.time()
    login_failures[ip]=[t for t in login_failures[ip] if now-t<900]
    login_failures[ip].append(now)
    if len(login_failures[ip])>=5:
        login_lockouts[ip]=now+900
        raise HTTPException(429,'Bạn đã nhập sai mật khẩu 5 lần liên tiếp. IP đã bị tạm khóa 15 phút.')


def record_login_success(ip:str):
    login_failures.pop(ip,None)
    login_lockouts.pop(ip,None)


@app.middleware('http')
async def local_guard(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin:
            host=request.headers.get('host','')
            forwarded_host=request.headers.get('x-forwarded-host', host)
            allowed_origins={
                f'http://{host}', f'https://{host}',
                f'http://{forwarded_host}', f'https://{forwarded_host}'
            }
            if origin not in allowed_origins:
                return JSONResponse({'detail':'Cross-origin write denied'},status_code=403)
        if 'application/json' not in request.headers.get('content-type',''):
            return JSONResponse({'detail':'JSON required'},status_code=415)
        body=await request.body()
        if len(body)>65536: return JSONResponse({'detail':'Input too large'},status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='geolocation=(), camera=(), microphone=()'
    if request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https':
        response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


def session(request):
    admin_claims=get_admin_jwt_claims(request)
    user=accounts.user(request)
    if user:
        is_adm=bool(admin_claims or user.get('role')=='admin')
        return {**user,'admin':is_adm,'expires':time.time()+86400}
    token=request.cookies.get('tai_session')
    s=sessions.get(token)
    if not s or s['expires']<time.time():
        if admin_claims:
            s={'id':admin_claims.get('sub') or str(uuid.uuid4()),'admin':True,'expires':time.time()+86400*7}
            return s
        raise HTTPException(401,'Phiên đã hết hạn; tải lại trang.')
    if admin_claims: s['admin']=True
    return s


def admin(request):
    admin_claims=get_admin_jwt_claims(request)
    if admin_claims:
        return {'id':admin_claims.get('sub'),'username':admin_claims.get('username'),'admin':True}
    user=accounts.user(request)
    if user and user.get('role')=='admin':
        return {'id':user['id'],'username':user.get('display_name') or 'Admin','admin':True}
    s=session(request)
    if not s.get('admin'): raise HTTPException(403,'Chỉ quản trị viên được thực hiện thao tác này.')
    return s


def throttle(key,count=12,seconds=60):
    q=limits[key]; now=time.time()
    while q and q[0]<now-seconds: q.popleft()
    if len(q)>=count: raise HTTPException(429,'Bạn gửi quá nhanh. Vui lòng thử lại sau một phút.')
    q.append(now)


async def payload(request):
    try: p=await request.json()
    except Exception: raise HTTPException(400,'JSON không hợp lệ.')
    if not isinstance(p,dict): raise HTTPException(400,'Cần một object JSON.')
    return p


def text(p,key,required=False,maximum=5000):
    value=p.get(key)
    if value is None and not required: return None
    if not isinstance(value,str) or len(value)>maximum or '\x00' in value or (required and not value.strip()):
        raise HTTPException(422,f'Trường {key} không hợp lệ (tối đa {maximum} ký tự).')
    return html.escape(value.strip(), quote=True)


def generation_inputs(p,maximum):
    contexts=p.get('generation_inputs',{})
    if not isinstance(contexts,dict):raise HTTPException(422,'Nguồn gợi ý không hợp lệ.')
    return text(contexts,'tai',maximum=maximum),text(contexts,'roman',maximum=maximum)


def submission(request,p):
    if p.get('hp_check') or p.get('website'):
        raise HTTPException(400,'Yêu cầu không hợp lệ.')
    s=session(request); ip=get_client_ip(request)
    throttle('submit:'+s['id'], count=15, seconds=60)
    throttle('ip:'+ip, count=25, seconds=60)
    return s


def insert(db,table,row):
    row={'id':str(uuid.uuid4()),**row}
    values=[json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for v in row.values()]
    db.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in values)})',values)
    return row['id']


def approved(db,table,id):
    row=db.execute(f'SELECT * FROM {table} WHERE id=? AND status=?',(id,'approved')).fetchone()
    if not row: raise HTTPException(404,'Không tìm thấy dữ liệu đã duyệt.')
    return dict(row) if row else None


def get_record(db,table,id,approved_only=False):
    if approved_only: return approved(db,table,id)
    row=db.execute(f'SELECT * FROM {table} WHERE id=?',(id,)).fetchone()
    if not row: raise HTTPException(404,f'Không tìm thấy bản ghi trong {table}.')
    return dict(row) if row else None


@app.get('/api/session')
def get_session(request:Request):
    user=accounts.user(request)
    if user:
        is_adm=bool(user.get('role')=='admin' or get_admin_jwt_claims(request))
        return {'contributor_id':user['id'],'user':user,'admin':is_adm,
                'consent_version':CONSENT,'mode':DB_BACKEND,'password_reset_available':resend_ready()}
    now=time.time()
    for key in [k for k,v in sessions.items() if v['expires']<now]: sessions.pop(key,None)
    token=request.cookies.get('tai_session'); s=sessions.get(token)
    if not s:
        throttle('sessions:'+get_client_ip(request),30)
        token=secrets.token_urlsafe(32); s={'id':str(uuid.uuid4()),'admin':False,'expires':now+86400}; sessions[token]=s
    admin_claims=get_admin_jwt_claims(request)
    is_admin=bool(admin_claims or s.get('admin'))
    if is_admin: s['admin']=True
    response=JSONResponse({'contributor_id':s['id'],'admin':is_admin,'user':None,
                           'consent_version':CONSENT,'mode':DB_BACKEND,'password_reset_available':resend_ready()})
    is_https = request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    response.set_cookie('tai_session',token,httponly=True,samesite='lax',secure=is_https,max_age=86400)
    return response


def parse_json(val):
    if val is None: return None
    if isinstance(val,(dict,list)): return val
    try: return json.loads(val)
    except Exception: return val


@app.post('/api/admin/login')
async def login(request:Request):
    ip=get_client_ip(request)
    check_login_rate(ip)
    throttle('login:'+ip,5,60)
    p=await payload(request)
    username=p.get('username')
    password=p.get('password')
    token=p.get('token')
    authenticated=False
    if username and password:
        if secrets.compare_digest(username.strip(),ADMIN_USERNAME) and secrets.compare_digest(hash_pass(password),ADMIN_HASH):
            authenticated=True
    elif token:
        if secrets.compare_digest(token.strip(),ADMIN_TOKEN):
            authenticated=True
    if not authenticated:
        record_login_failure(ip)
        raise HTTPException(401,'Tên đăng nhập hoặc mật khẩu không chính xác.')
    record_login_success(ip)
    user_id=str(uuid.uuid4())
    s=sessions.get(request.cookies.get('tai_session'))
    if s: s['admin']=True; user_id=s['id']
    jwt_token=create_admin_jwt(user_id=user_id,username=ADMIN_USERNAME)
    is_https = request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
    response=JSONResponse({'ok':True,'token':jwt_token,'username':ADMIN_USERNAME})
    response.set_cookie('tai_admin_token',jwt_token,httponly=True,samesite='lax',secure=is_https,max_age=JWT_EXPIRATION_SECONDS)
    return response


@app.post('/api/admin/logout')
def logout(request:Request):
    s=sessions.get(request.cookies.get('tai_session'))
    if s: s['admin']=False
    response=JSONResponse({'ok':True})
    response.delete_cookie('tai_admin_token')
    return response


@app.post('/api/engine')
async def convert(request:Request):
    session(request); throttle('engine:'+get_client_ip(request),120,60)
    p=await payload(request); is_sent=bool(p.get('sentence'))
    value=text(p,'text',True,5000 if is_sent else 120)
    if p.get('direction')=='tai':
        result=engine.tai_sentence_to_romanization(value,dictionary=True) if is_sent else engine.tai_to_romanization(value,dictionary=True)
        return {**result,'parse':{'tokens':result.get('tokens')} if 'tokens' in result else engine.parse_tai_word(value)}
    if p.get('direction')=='roman':
        result=engine.romanization_sentence_to_tai(value,dictionary=True) if is_sent else engine.romanization_to_tai(value,dictionary=True)
        return {**result,'parse':{'tokens':result.get('tokens')} if 'tokens' in result else engine.parse_romanization(value)}
    raise HTTPException(422,'Hướng chuyển đổi không hợp lệ.')


def consistency(tai,roman):
    if not tai or not roman: return 'not_comparable'
    forward=engine.tai_to_romanization(tai,dictionary=True)
    if any(engine.aliases_equivalent(roman,x['romanization']) for x in forward['candidates']): return 'rule_match'
    if any(engine.aliases_equivalent(roman,x['romanization']) for x in forward['dictionary_candidates']): return 'dictionary_match'
    if forward['candidates'] or forward['dictionary_candidates']: return 'mismatch'
    return 'unknown'


@app.post('/api/words/check')
async def check_word(request:Request):
    session(request); p=await payload(request)
    return {'consistency_status':consistency(text(p,'tai',maximum=120),text(p,'romanization',maximum=120))}


@app.post('/api/words')
async def contribute_word(request:Request):
    p=await payload(request)
    tai=text(p,'tai_text_original',maximum=120); roman=text(p,'romanization_original',maximum=120)
    meaning=text(p,'vietnamese_meaning',True)
    if not (tai and tai.strip()) and not (roman and roman.strip()): raise HTTPException(422,'Nhập chữ Tai hoặc phiên âm.')
    tf=text(p,'tai_text_final',maximum=120); rf=text(p,'romanization_final',maximum=120)
    tf=tai if tf is None else tf; rf=roman if rf is None else rf
    if not (tf and tf.strip()) and not (rf and rf.strip()):
        raise HTTPException(422,'Giá trị cuối cùng cần có chữ Tai hoặc phiên âm.')
    tai_context,roman_context=generation_inputs(p,120)
    roman_input=tai_context or roman or rf;tai_input=roman_context or tai or tf
    generated_t=engine.romanization_to_tai(roman_input,dictionary=True) if roman_input and roman_input.strip() else {}
    generated_r=engine.tai_to_romanization(tai_input,dictionary=True) if tai_input and tai_input.strip() else {}
    selected_t=text(p,'tai_text_generated',maximum=120); selected_r=text(p,'romanization_generated',maximum=120)
    for selected,data,field in [(selected_t,generated_t,'tai'),(selected_r,generated_r,'romanization')]:
        if selected is not None and selected not in [x[field] for x in data.get('candidates',[])+data.get('dictionary_candidates',[])]:
            raise HTTPException(422,'Gợi ý đã chọn không còn khớp đầu vào. Lấy gợi ý lại.')
    state=consistency(tf,rf)
    # Keep mismatch diagnostics for moderation without adding a submission step.
    s=submission(request,p)
    def source(selected,final): return 'user' if selected is None else 'generated' if selected==final else 'generated_then_edited'
    with database() as db:
        id=insert(db,'word_contributions',dict(tai_text_original=tai,romanization_original=roman,
            tai_text_generated=selected_t,romanization_generated=selected_r,tai_text_final=tf,romanization_final=rf,
            vietnamese_meaning=meaning,value_sources={'tai':source(selected_t,tf),'romanization':source(selected_r,rf)},
            generated_suggestions={'tai':generated_t,'romanization':generated_r},
            analysis=engine.parse_tai_word(tf) if tf else {},rule_version=engine.version,
            consistency_status=state,inconsistency_confirmed=int(p.get('confirm_inconsistency') is True),
            contributor_id=s['id'],contributor_name=text(p,'contributor_name',maximum=100),consent_version=CONSENT,status='pending'))
    return {'id':id,'status':'pending','message':'Cảm ơn bạn đã đóng góp!'}


@app.post('/api/sentences')
async def contribute_sentence(request:Request):
    p=await payload(request); tai=text(p,'tai_text_original');roman=text(p,'romanization_original')
    if not (tai and tai.strip()) and not (roman and roman.strip()):raise HTTPException(422,'Nhập câu Tai hoặc phiên âm.')
    tf=text(p,'tai_text_final');rf=text(p,'romanization_final')
    tf=tai if tf is None else tf;rf=roman if rf is None else rf
    tg=text(p,'tai_text_generated');rg=text(p,'romanization_generated')
    tai_context,roman_context=generation_inputs(p,5000)
    roman_input=tai_context or roman or rf;tai_input=roman_context or tai or tf
    generated_t=engine.romanization_sentence_to_tai(roman_input,dictionary=True) if roman_input else {}
    generated_r=engine.tai_sentence_to_romanization(tai_input,dictionary=True) if tai_input else {}
    for value,result,field in [(tg,generated_t,'tai'),(rg,generated_r,'romanization')]:
        if value is not None and value not in [c[field] for c in result.get('candidates',[])+result.get('dictionary_candidates',[])]:
            raise HTTPException(422,'Gợi ý không còn khớp đầu vào; hãy tạo lại hoặc nhập trực tiếp.')
    source=p.get('source_type','self')
    if source not in ('self','oral','book','other'): raise HTTPException(422,'Nguồn không hợp lệ.')
    meaning=text(p,'vietnamese_meaning',maximum=5000) or text(p,'vietnamese_translation',maximum=5000)
    s=submission(request,p)
    with database() as db:
        id=insert(db,'sentences',dict(tai_text_original=tf,romanization=rf,source_type=source,
            source_reference=text(p,'source_reference',maximum=300),region_original=text(p,'region_original',maximum=100),
            contributor_id=s['id'],contributor_name=text(p,'contributor_name',maximum=100),consent_version=CONSENT,status='pending')) if tf and tf.strip() else None
        if id and meaning and meaning.strip():
            insert(db,'translations',dict(sentence_id=id,vietnamese_text=meaning.strip(),origin='contributor',
                contributor_id=s['id'],contributor_name=text(p,'contributor_name',maximum=100),consent_version=CONSENT,status='pending'))
        def origin(original,generated,final):return 'user' if generated is None else 'generated' if generated==final else 'generated_then_edited'
        submission_id=insert(db,'sentence_submissions',dict(sentence_id=id,tai_text_original=tai,romanization_original=roman,
            tai_text_generated=tg,romanization_generated=rg,tai_text_final=tf,romanization_final=rf,
            value_sources={'tai':origin(tai,tg,tf),'romanization':origin(roman,rg,rf)},
            generated_suggestions={'tai':generated_t,'romanization':generated_r},analysis=engine.parse_tai_word(tf) if tf else {},
            rule_version=engine.version,consistency_status=consistency(tf,rf),contributor_id=s['id'],status='pending'))
    return {'id':id or submission_id,'submission_id':submission_id,'status':'pending','message':'Cảm ơn bạn đã đóng góp!'}


def batch_sentence_details(db,rows):
    if not rows: return []
    rows=[dict(r) for r in rows]
    sids=[r.get('sentence_id') or r['id'] for r in rows]
    placeholders=','.join('?' for _ in sids)

    trans_rows=db.execute(f"SELECT id, sentence_id, vietnamese_text, status FROM translations WHERE sentence_id IN ({placeholders}) ORDER BY (status='approved') DESC, created_at,id", sids).fetchall()
    sent_status_map = {r.get('sentence_id') or r['id']: r.get('status') for r in rows}
    trans_map=defaultdict(list)
    for tr in trans_rows:
        sid = tr['sentence_id']
        if sent_status_map.get(sid) == 'approved':
            if tr['status'] == 'approved':
                trans_map[sid].append(dict(tr))
        else:
            trans_map[sid].append(dict(tr))

    sent_corr_rows=db.execute(f"SELECT id, sentence_id, suggested_tai_text, suggested_romanization FROM sentence_corrections WHERE sentence_id IN ({placeholders}) AND status='approved' ORDER BY created_at DESC", sids).fetchall()
    sent_corr_map={}
    for scr in sent_corr_rows:
        if scr['sentence_id'] not in sent_corr_map: sent_corr_map[scr['sentence_id']]=dict(scr)

    corr_rows=db.execute(f"SELECT id, sentence_id, suggested_romanization FROM romanization_corrections WHERE sentence_id IN ({placeholders}) AND status='approved' ORDER BY created_at DESC", sids).fetchall()
    corr_map={}
    for cr in corr_rows:
        if cr['sentence_id'] not in corr_map: corr_map[cr['sentence_id']]=cr

    sub_rows=db.execute(f"SELECT * FROM sentence_submissions WHERE sentence_id IN ({placeholders}) ORDER BY created_at DESC", sids).fetchall()
    sub_map={}
    for sub in sub_rows:
        if sub['sentence_id'] not in sub_map: sub_map[sub['sentence_id']]=sub

    result=[]
    for row in rows:
        sid=row.get('sentence_id') or row['id']
        submission=sub_map.get(sid)
        if submission:
            row['provenance']={k:submission[k] for k in ('tai_text_original','romanization_original','tai_text_generated','romanization_generated','value_sources','consistency_status','rule_version')}
        sent_corr=sent_corr_map.get(sid)
        if sent_corr:
            row['tai_text_original']=sent_corr['suggested_tai_text']
            if sent_corr.get('suggested_romanization') and sent_corr['suggested_romanization'].strip():
                row['romanization']=sent_corr['suggested_romanization']
                row['romanization_source']='sentence_correction'
        correction=corr_map.get(sid)
        row['romanization_original']=row.get('romanization')
        if correction:
            row.update(romanization=correction['suggested_romanization'],romanization_source='community_correction',correction_id=correction['id'])
        elif row.get('romanization') and row['romanization'].strip():
            sources=parse_json(submission['value_sources']) if submission else None
            row['romanization_source']=sources.get('romanization') if sources else 'imported' if row.get('source_type')=='dictionary' else 'stored'
        else:
            tai_txt=row.get('tai_text_original') or ''
            if tai_txt.strip():
                generated=engine.tai_sentence_to_romanization(tai_txt,dictionary=True)
                row['romanization_suggestions']=generated;row['romanization_source']='generated_suggestion'
                cands=generated.get('candidates',[]) or generated.get('dictionary_candidates',[])
                if cands: row['romanization']=cands[0]['romanization']
                else:
                    parts=[]
                    for t in generated.get('tokens',[]):
                        if t.get('kind')=='word':
                            tc=t.get('candidates',[]) or t.get('dictionary_candidates',[])
                            parts.append(tc[0]['romanization'] if tc else t['text'])
                        else: parts.append(t['text'])
                    row['romanization']="".join(parts) if parts else None
            else:
                row['romanization']=None
        row['translations']=trans_map.get(sid,[])
        result.append(row)
    return result


def sentence_details(db,row):
    res=batch_sentence_details(db,[row])
    return res[0] if res else None


@app.post('/api/romanization-corrections')
async def correct_romanization(request:Request):
    p=await payload(request);sid=text(p,'sentence_id',True,40);suggested=text(p,'suggested_romanization',True)
    s=submission(request,p)
    with database() as db:
        sentence=sentence_details(db,get_record(db,'sentences',sid))
        id=insert(db,'romanization_corrections',dict(sentence_id=sid,base_romanization=sentence.get('romanization'),
            suggested_romanization=suggested,base_source=sentence['romanization_source'],rule_version=engine.version,
            analysis=sentence.get('romanization_suggestions',{}),contributor_id=s['id'],status='pending'))
    return {'id':id,'status':'pending','message':'Đã gửi phiên âm sửa để duyệt; phiên âm gốc được giữ lại.'}


@app.post('/api/sentence-corrections')
async def correct_sentence(request:Request):
    p=await payload(request)
    sid=text(p,'sentence_id',True,40)
    tai=text(p,'suggested_tai_text',True,5000)
    roman=text(p,'suggested_romanization',True,5000)
    meaning=text(p,'suggested_meaning',True,5000)
    s=submission(request,p)
    is_admin=bool(s.get('admin'))
    status='approved' if is_admin else 'pending'
    with database() as db:
        sent=get_record(db,'sentences',sid)
        cid=insert(db,'sentence_corrections',dict(
            sentence_id=sid,base_tai_text=sent.get('tai_text_original'),
            suggested_tai_text=tai,suggested_romanization=roman,suggested_meaning=meaning,
            contributor_id=s['id'],status=status
        ))
        if is_admin:
            db.execute("UPDATE sentences SET tai_text_original=?, romanization=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (tai, roman, sid))
            if meaning and meaning.strip():
                existing_tr=db.execute("SELECT id FROM translations WHERE sentence_id=? ORDER BY (status='approved') DESC, created_at LIMIT 1", (sid,)).fetchone()
                if existing_tr:
                    db.execute("UPDATE translations SET vietnamese_text=?, status='approved', updated_at=CURRENT_TIMESTAMP WHERE id=?", (meaning.strip(), existing_tr['id']))
                else:
                    insert(db,'translations',dict(
                        sentence_id=sid,vietnamese_text=meaning.strip(),origin='admin_correction',
                        contributor_id=s['id'],status='approved'
                    ))
            insert(db,'moderation_events',dict(
                entity_table='sentence_corrections',entity_id=cid,
                previous_status='pending',new_status='approved',admin_id=s['id']
            ))
            msg='Đã cập nhật câu gốc, phiên âm và nghĩa thành công (Quyền Quản trị)!'
        else:
            msg='Đã gửi đề xuất sửa câu gốc (kèm phiên âm và nghĩa) để Admin duyệt!'
    return {'id':cid,'status':status,'message':msg}


@app.get('/api/sentences')
def sentences(request:Request,q:str='',offset:int=0,limit:int=20,status:str='approved',source:str='all',meaning:str='all',roman:str='all'):
    if len(q)>120 or offset<0: raise HTTPException(422,'Bộ lọc không hợp lệ.')
    limit=min(max(1,limit),100)
    clauses=[]; params=[]
    if status!='all':
        clauses.append('sentences.status=?'); params.append(status)
    if q:
        q_pat='%'+q.strip()+'%'
        clauses.append('(sentences.tai_text_original LIKE ? OR LOWER(sentences.romanization) LIKE LOWER(?))')
        params.extend([q_pat,q_pat])
    if source=='community':
        clauses.append("sentences.source_type IN ('community','self','oral','book','other')")
    elif source=='dictionary':
        clauses.append("sentences.source_type='dictionary'")
    if meaning=='has_meaning':
        if status=='approved':
            clauses.append("EXISTS (SELECT 1 FROM translations tr WHERE tr.sentence_id=sentences.id AND tr.status='approved' AND length(trim(tr.vietnamese_text))>0)")
        else:
            clauses.append("EXISTS (SELECT 1 FROM translations tr WHERE tr.sentence_id=sentences.id AND length(trim(tr.vietnamese_text))>0)")
    elif meaning=='no_meaning':
        if status=='approved':
            clauses.append("NOT EXISTS (SELECT 1 FROM translations tr WHERE tr.sentence_id=sentences.id AND tr.status='approved' AND length(trim(tr.vietnamese_text))>0)")
        else:
            clauses.append("NOT EXISTS (SELECT 1 FROM translations tr WHERE tr.sentence_id=sentences.id AND length(trim(tr.vietnamese_text))>0)")
    if roman=='has_roman':
        clauses.append("sentences.romanization IS NOT NULL AND trim(sentences.romanization)<>''")
    elif roman=='no_roman':
        clauses.append("(sentences.romanization IS NULL OR trim(sentences.romanization)='')")
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    with database() as db:
        rows=db.execute(f'''SELECT id,tai_text_original,romanization,source_type,region_original,status FROM sentences
            {where}
            ORDER BY 
                CASE WHEN romanization IS NULL OR trim(romanization)='' THEN 0 ELSE 1 END ASC,
                (SELECT count(*) FROM translations tr WHERE tr.sentence_id=sentences.id AND tr.status='approved') ASC,
                id ASC
            LIMIT ? OFFSET ?''',params+[limit,offset]).fetchall()
        return {'items':batch_sentence_details(db,rows)}


@app.post('/api/translations')
async def translate(request:Request):
    p=await payload(request); sentence_id=text(p,'sentence_id',True,40); vietnamese=text(p,'vietnamese_text',True)
    s=submission(request,p)
    with database() as db:
        get_record(db,'sentences',sentence_id)
        id=insert(db,'translations',dict(sentence_id=sentence_id,vietnamese_text=vietnamese,origin='community',
            contributor_id=s['id'],contributor_name=text(p,'contributor_name',maximum=100),consent_version=CONSENT,status='pending'))
    return {'id':id,'status':'pending','message':'Cảm ơn bạn đã đóng góp!'}


@app.get('/api/review-queue')
def review_queue(request:Request,offset:int=0,limit:int=20,status:str='approved',sentence_status:str='all',source:str='all',meaning:str='has_meaning',roman:str='all'):
    s=session(request)
    if offset<0: raise HTTPException(422,'Offset không hợp lệ')
    limit=min(max(1,limit),100)
    with database() as db:
        if meaning=='no_meaning':
            clauses=[
                "NOT EXISTS (SELECT 1 FROM translations tr WHERE tr.sentence_id=s.id AND length(trim(tr.vietnamese_text))>0)",
                "(s.contributor_id IS NULL OR s.contributor_id<>?)",
                "NOT EXISTS (SELECT 1 FROM sentence_reviews sr WHERE sr.sentence_id=s.id AND sr.contributor_id=?)"
            ]
            params=[s['id'],s['id']]
            if sentence_status!='all':
                clauses.append("s.status=?")
                params.append(sentence_status)
            if source=='community':
                clauses.append("s.source_type IN ('community','self','oral','book','other')")
            elif source=='dictionary':
                clauses.append("s.source_type='dictionary'")
            if roman=='has_roman':
                clauses.append("s.romanization IS NOT NULL AND trim(s.romanization)<>''")
            elif roman=='no_roman':
                clauses.append("(s.romanization IS NULL OR trim(s.romanization)='')")
            where=' WHERE '+' AND '.join(clauses)
            rows=db.execute(f'''SELECT s.id, s.id as sentence_id, s.tai_text_original, s.romanization, s.source_type, s.status as sentence_status, '' as vietnamese_text
                FROM sentences s {where}
                ORDER BY 
                    CASE WHEN (SELECT count(*) FROM sentence_reviews sr WHERE sr.sentence_id=s.id) = 0 THEN 0 ELSE 1 END ASC,
                    (SELECT count(*) FROM sentence_reviews sr WHERE sr.sentence_id=s.id) ASC,
                    CASE WHEN s.romanization IS NULL OR trim(s.romanization)='' THEN 0 ELSE 1 END ASC,
                    s.created_at DESC,
                    s.id ASC
                LIMIT ? OFFSET ?''', params+[limit,offset]).fetchall()
            return {'items':batch_sentence_details(db,rows)}
        else:
            clauses=[
                '(t.contributor_id IS NULL OR t.contributor_id<>?)',
                'NOT EXISTS (SELECT 1 FROM translation_validations v JOIN translations tr ON tr.id=v.translation_id WHERE tr.sentence_id=t.sentence_id AND v.contributor_id=?)',
                'NOT EXISTS (SELECT 1 FROM sentence_reviews sr WHERE sr.sentence_id=t.sentence_id AND sr.contributor_id=?)'
            ]
            params=[s['id'],s['id'],s['id']]
            if status!='all':
                clauses.append('t.status=?'); params.append(status)
            if sentence_status!='all':
                clauses.append('s.status=?'); params.append(sentence_status)
            if source=='community':
                clauses.append("(s.source_type IN ('community','self','oral','book','other') OR t.origin IN ('community','contributor','correction','admin_correction'))")
            elif source=='dictionary':
                clauses.append("(s.source_type='dictionary' OR t.origin='dictionary')")
            if roman=='has_roman':
                clauses.append("s.romanization IS NOT NULL AND trim(s.romanization)<>''")
            elif roman=='no_roman':
                clauses.append("(s.romanization IS NULL OR trim(s.romanization)='')")
            where=' WHERE '+' AND '.join(clauses)
            rows=db.execute(f'''SELECT t.id,t.sentence_id,t.vietnamese_text,t.status as translation_status,s.tai_text_original,s.romanization,s.source_type,s.status as sentence_status FROM translations t
                JOIN sentences s ON s.id=t.sentence_id
                {where}
                ORDER BY 
                    CASE WHEN (SELECT count(*) FROM translation_validations v2 WHERE v2.translation_id=t.id) = 0 THEN 0 ELSE 1 END ASC,
                    (SELECT count(*) FROM translation_validations v2 WHERE v2.translation_id=t.id) ASC,
                    CASE WHEN (SELECT count(*) FROM sentence_reviews sr WHERE sr.sentence_id=s.id) = 0 THEN 0 ELSE 1 END ASC,
                    (SELECT count(*) FROM sentence_reviews sr WHERE sr.sentence_id=s.id) ASC,
                    CASE WHEN s.romanization IS NULL OR trim(s.romanization)='' THEN 0 ELSE 1 END ASC,
                    t.created_at DESC,
                    t.id ASC
                LIMIT ? OFFSET ?''',params+[limit,offset]).fetchall()
            return {'items':batch_sentence_details(db,rows)}


@app.post('/api/validations')
async def validate_translation(request:Request):
    p=await payload(request); tid=text(p,'translation_id',True,40); status=p.get('validation_status')
    if status not in ('correct','needs_correction','incorrect'): raise HTTPException(422,'Đánh giá không hợp lệ.')
    suggestion=text(p,'suggested_translation',required=status=='needs_correction')
    s=submission(request,p)
    try:
        with database() as db:
            t=get_record(db,'translations',tid)
            if t['contributor_id']==s['id']: raise HTTPException(403,'Hãy kiểm tra bản dịch của người khác.')
            id=insert(db,'translation_validations',dict(translation_id=tid,validation_status=status,
                suggested_translation=suggestion,contributor_id=s['id'],consent_version=CONSENT))
    except DB_INTEGRITY_ERRORS: raise HTTPException(409,'Bạn đã kiểm tra bản dịch này.')
    return {'id':id,'message':'Cảm ơn bạn đã kiểm tra!'}


@app.post('/api/sentence-reviews')
async def review_sentence(request:Request):
    p=await payload(request); sid=text(p,'sentence_id',True,40); natural=p.get('naturalness')
    if natural not in ('natural','problematic','unsure'): raise HTTPException(422,'Đánh giá không hợp lệ.')
    s=submission(request,p)
    try:
        with database() as db:
            get_record(db,'sentences',sid)
            id=insert(db,'sentence_reviews',dict(sentence_id=sid,naturalness=natural,contributor_id=s['id'],consent_version=CONSENT))
    except DB_INTEGRITY_ERRORS: raise HTTPException(409,'Bạn đã đánh giá câu này.')
    return {'id':id,'message':'Cảm ơn bạn đã đánh giá!'}


@app.get('/api/dictionary')
def dictionary(q:str='',offset:int=0):
    if len(q)>120 or offset<0: raise HTTPException(422,'Bộ lọc không hợp lệ.')
    q_clean=q.strip()
    with database() as db:
        keys=engine.canonical_keys(q_clean) if q_clean else []
        placeholders=','.join('?' for _ in keys) or 'NULL'
        pattern='%'+q_clean+'%'

        lex_rows=db.execute('''SELECT l.id,l.tai_text_original,l.romanization,w.id sense_id,w.vietnamese_meaning,w.part_of_speech,'word' as kind
        FROM lexemes l JOIN word_senses w ON w.lexeme_id=l.id WHERE l.status='approved' AND w.status='approved'
        AND (l.tai_text_original LIKE ? OR LOWER(l.romanization) LIKE LOWER(?) OR LOWER(w.vietnamese_meaning) LIKE LOWER(?) OR EXISTS
        (SELECT 1 FROM lexeme_search_keys sk WHERE sk.lexeme_id=l.id AND sk.rule_version=? AND sk.canonical_key IN ('''+placeholders+'''))) ORDER BY l.id,w.id LIMIT 25 OFFSET ?''',
        (pattern,pattern,pattern,engine.version,*keys,offset)).fetchall()

        contrib_rows=[]
        if offset==0 or len(lex_rows)<25:
            contrib_rows=db.execute('''SELECT wc.id,
                coalesce(wc.tai_text_final, wc.tai_text_original) as tai_text_original,
                coalesce(wc.romanization_final, wc.romanization_original) as romanization,
                wc.id as sense_id, wc.vietnamese_meaning, 'Từ đóng góp' as part_of_speech, 'contribution' as kind
            FROM word_contributions wc
            WHERE wc.status='approved'
            AND (coalesce(wc.tai_text_final, wc.tai_text_original) LIKE ?
                 OR LOWER(coalesce(wc.romanization_final, wc.romanization_original)) LIKE LOWER(?)
                 OR LOWER(wc.vietnamese_meaning) LIKE LOWER(?))
            ORDER BY wc.created_at DESC, wc.id DESC LIMIT 21 OFFSET ?''',
            (pattern,pattern,pattern,offset)).fetchall()

        seen=set()
        all_items=[]
        for r in lex_rows:
            d=dict(r)
            seen.add(((d.get('tai_text_original') or '').strip(), (d.get('vietnamese_meaning') or '').strip().lower()))
            all_items.append(d)

        for r in contrib_rows:
            d=dict(r)
            if not (d.get('tai_text_original') and d['tai_text_original'].strip()) and d.get('romanization'):
                gen=engine.romanization_to_tai(d['romanization'].strip())
                cands=gen.get('candidates',[]) or gen.get('dictionary_candidates',[])
                if cands: d['tai_text_original']=cands[0]['tai']
            key=((d.get('tai_text_original') or '').strip(), (d.get('vietnamese_meaning') or '').strip().lower())
            if key not in seen:
                seen.add(key)
                all_items.append(d)

    return {'items':all_items[:20], 'has_more': len(all_items) > 20}


@app.get('/api/words/meanings')
def word_meanings(tai:str='',roman:str=''):
    if len(tai)>120 or len(roman)>120:raise HTTPException(422,'Từ quá dài.')
    tai=tai.strip(); roman=roman.strip()
    keys=engine.canonical_keys(roman) if roman else []
    placeholders=','.join('?' for _ in keys) or 'NULL'
    with database() as db:
        rows=db.execute('''SELECT DISTINCT l.tai_text_original,l.romanization,w.vietnamese_meaning
          FROM lexemes l JOIN word_senses w ON w.lexeme_id=l.id
          WHERE l.status='approved' AND w.status='approved' AND
          ((?<>'' AND l.tai_text_original=?) OR (?='' AND ?<>'' AND
          (LOWER(l.romanization)=LOWER(?) OR EXISTS (SELECT 1 FROM lexeme_search_keys sk
           WHERE sk.lexeme_id=l.id AND sk.rule_version=? AND sk.canonical_key IN ('''+placeholders+''')))))
          ORDER BY l.tai_text_original,w.vietnamese_meaning''',
          (tai,tai,tai,roman,roman,engine.version,*keys)).fetchall()
        contribs=db.execute('''SELECT DISTINCT coalesce(tai_text_final,tai_text_original) as tai_text_original,
          coalesce(romanization_final,romanization_original) as romanization,vietnamese_meaning
          FROM word_contributions
          WHERE status='approved' AND
          ((?<>'' AND (tai_text_final=? OR tai_text_original=?)) OR
           (?='' AND ?<>'' AND LOWER(coalesce(romanization_final,romanization_original))=LOWER(?)))
          ORDER BY vietnamese_meaning''',
          (tai,tai,tai,tai,roman,roman)).fetchall()
    all_items=[dict(r) for r in rows]+[dict(r) for r in contribs]
    seen=set(); unique_items=[]
    for item in all_items:
        m=item.get('vietnamese_meaning','').strip().lower()
        if m and m not in seen:
            seen.add(m)
            unique_items.append(item)
    return {'items':unique_items}


MODERATED={'sentences','translations','word_contributions','annotations','lexemes','word_senses','romanization_corrections','sentence_submissions','sentence_corrections'}
READABLE=MODERATED|{'translation_validations','sentence_reviews','moderation_events'}
def admin_filter(table, status, q):
    if table not in READABLE or status not in ('all','pending','approved','rejected') or not isinstance(q,str) or len(q)>120:
        raise HTTPException(422,'Bộ lọc không hợp lệ.')
    clauses=[]; params=[]
    if status!='all' and table in MODERATED: clauses.append('status=?'); params.append(status)
    fields={'sentences':'tai_text_original','translations':'vietnamese_text','word_contributions':'vietnamese_meaning','lexemes':'tai_text_original','word_senses':'vietnamese_meaning','sentence_submissions':'romanization_final','romanization_corrections':'suggested_romanization','sentence_corrections':'suggested_tai_text'}
    fields.update({'translation_validations':'suggested_translation','sentence_reviews':'naturalness','moderation_events':'entity_table','annotations':'annotation_data'})
    if q:
        q_pat='%'+q.strip()+'%'
        if table=='word_contributions':
            clauses.append('(coalesce(tai_text_final,tai_text_original) LIKE ? OR LOWER(coalesce(romanization_final,romanization_original)) LIKE LOWER(?) OR LOWER(vietnamese_meaning) LIKE LOWER(?))')
            params.extend([q_pat,q_pat,q_pat])
        elif table=='sentences':
            clauses.append('(tai_text_original LIKE ? OR LOWER(romanization) LIKE LOWER(?))')
            params.extend([q_pat,q_pat])
        elif table=='sentence_corrections':
            clauses.append('(suggested_tai_text LIKE ? OR LOWER(suggested_romanization) LIKE LOWER(?) OR LOWER(suggested_meaning) LIKE LOWER(?))')
            params.extend([q_pat,q_pat,q_pat])
        elif table in fields:
            clauses.append(f'LOWER({fields[table]}) LIKE LOWER(?)'); params.append(q_pat)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    return where, params

@app.get('/api/admin/records')
def admin_records(request:Request,table:str='sentences',status:str='pending',q:str='',offset:int=0):
    admin(request)
    if table not in READABLE or offset<0 or len(q)>120 or status not in ('all','pending','approved','rejected'): raise HTTPException(422,'Bộ lọc không hợp lệ.')
    with database() as db:
        where,params=admin_filter(table,status,q)
        total=db.execute(f'SELECT count(*) FROM {table}{where}',params).fetchone()[0]
        raw_rows=db.execute(f'SELECT * FROM {table}{where} ORDER BY created_at DESC,id LIMIT 30 OFFSET ?',params+[offset]).fetchall()
        raw_rows=[dict(r) for r in raw_rows]
        items=[]
        if raw_rows:
            if table=='translation_validations':
                tids=list({r['translation_id'] for r in raw_rows if r.get('translation_id')})
                tr_map={}
                if tids:
                    placeholders=','.join('?' for _ in tids)
                    trs=db.execute(f'SELECT t.id, s.tai_text_original, t.vietnamese_text FROM translations t JOIN sentences s ON s.id=t.sentence_id WHERE t.id IN ({placeholders})',tids).fetchall()
                    tr_map={t['id']:t for t in trs}
                for r in raw_rows:
                    d=dict(r)
                    tr=tr_map.get(d.get('translation_id'))
                    if tr:
                        d['sentence_tai']=tr['tai_text_original']
                        d['vietnamese_text']=tr['vietnamese_text']
                    items.append(d)
            elif table=='sentences':
                sids=[r['id'] for r in raw_rows if r.get('id')]
                tr_map={}
                if sids:
                    placeholders=','.join('?' for _ in sids)
                    trs=db.execute(f'SELECT sentence_id, vietnamese_text FROM translations WHERE sentence_id IN ({placeholders}) ORDER BY created_at ASC',sids).fetchall()
                    for tr in trs: tr_map[tr['sentence_id']]=tr['vietnamese_text']
                for r in raw_rows:
                    d=dict(r)
                    if d['id'] in tr_map: d['vietnamese_text']=tr_map[d['id']]
                    items.append(d)
            elif any('sentence_id' in r and r.get('sentence_id') for r in raw_rows):
                sids=list({r['sentence_id'] for r in raw_rows if r.get('sentence_id')})
                sent_map={}
                if sids:
                    placeholders=','.join('?' for _ in sids)
                    sents=db.execute(f'SELECT id, tai_text_original FROM sentences WHERE id IN ({placeholders})',sids).fetchall()
                    sent_map={s['id']:s['tai_text_original'] for s in sents}
                for r in raw_rows:
                    d=dict(r)
                    if d.get('sentence_id') in sent_map: d['sentence_tai']=sent_map[d['sentence_id']]
                    items.append(d)
            else:
                items=[dict(r) for r in raw_rows]
    return {'items':items,'total':total}


def delete_admin_rows(db, table, ids):
    # Remove dependent records first, within the caller's transaction.
    marks=','.join('?' for _ in ids)
    if table=='sentences':
        translations=[r['id'] for r in db.execute(f'SELECT id FROM translations WHERE sentence_id IN ({marks})',ids).fetchall()]
        if translations: delete_admin_rows(db,'translations',translations)
        for child in ('word_sense_examples','sentence_reviews','annotations','sentence_submissions','romanization_corrections','sentence_corrections'):
            db.execute(f'DELETE FROM {child} WHERE sentence_id IN ({marks})',ids)
    elif table=='translations':
        for child in ('translation_validations','word_sense_examples'):
            db.execute(f'DELETE FROM {child} WHERE translation_id IN ({marks})',ids)
    elif table=='lexemes':
        senses=[r['id'] for r in db.execute(f'SELECT id FROM word_senses WHERE lexeme_id IN ({marks})',ids).fetchall()]
        if senses: delete_admin_rows(db,'word_senses',senses)
        for child in ('lexeme_search_keys','orthography_analyses'):
            db.execute(f'DELETE FROM {child} WHERE lexeme_id IN ({marks})',ids)
    elif table=='word_senses':
        db.execute(f'DELETE FROM word_sense_examples WHERE word_sense_id IN ({marks})',ids)
    db.execute(f'DELETE FROM {table} WHERE id IN ({marks})',ids)


@app.post('/api/admin/delete')
async def delete_admin_records(request:Request):
    actor=admin(request); p=await payload(request)
    table=p.get('table'); status=p.get('status','all'); q=p.get('q','')
    if not isinstance(table,str) or table not in READABLE-{'moderation_events'}:
        raise HTTPException(422,'Loại dữ liệu không được phép xóa.')
    where,params=admin_filter(table,status,q)
    if p.get('scope')=='selected':
        ids=p.get('ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=30 or any(not isinstance(i,str) or not i or len(i)>40 for i in ids):
            raise HTTPException(422,'Chọn từ 1 đến 30 bản ghi trên trang.')
        where+=(' AND ' if where else ' WHERE ')+ 'id IN ('+','.join('?' for _ in ids)+')'
        params+=ids
    elif p.get('scope')!='filtered':
        raise HTTPException(422,'Phạm vi xóa không hợp lệ.')
    expected=p.get('expected_count')
    if type(expected) is not int or expected<1:
        raise HTTPException(422,'Số lượng xác nhận không hợp lệ.')
    with database() as db:
        lock=' FOR UPDATE' if DB_BACKEND=='supabase' else ''
        if DB_BACKEND=='sqlite': db.execute('BEGIN IMMEDIATE')
        rows=[dict(r) for r in db.execute(f'SELECT * FROM {table}{where}'+lock,params).fetchall()]
        if len(rows)!=expected:
            raise HTTPException(409,'Dữ liệu đã thay đổi. Hãy tải lại và chọn lại trước khi xóa.')
        for offset in range(0,len(rows),200):
            batch=rows[offset:offset+200]
            delete_admin_rows(db,table,[r['id'] for r in batch])
            for row in batch:
                insert(db,'moderation_events',dict(entity_table=table,entity_id=row['id'],previous_status=row.get('status') or 'untracked',new_status='deleted',admin_id=actor['id']))
    return {'ok':True,'deleted':len(rows)}


@app.post('/api/admin/words/edit')
async def edit_word_contribution(request:Request):
    s=admin(request); p=await payload(request)
    wid=text(p,'id',True,40)
    tai=text(p,'tai_text',True,120)
    roman=text(p,'romanization',False,120) or ''
    meaning=text(p,'vietnamese_meaning',True,5000)
    status=p.get('status','approved')
    if status not in ('approved','rejected','pending'): status='approved'
    with database() as db:
        old=db.execute('SELECT * FROM word_contributions WHERE id=?',(wid,)).fetchone()
        if not old: raise HTTPException(404,'Không tìm thấy từ đóng góp.')
        old_dict=dict(old)
        old_tai=old_dict.get('tai_text_final') or old_dict.get('tai_text_original') or ''
        old_meaning=old_dict.get('vietnamese_meaning') or ''

        cons=consistency(tai,roman)
        analysis=engine.parse_tai_word(tai) if tai else {}
        db.execute('''UPDATE word_contributions
            SET tai_text_original=?, tai_text_final=?,
                romanization_original=?, romanization_final=?,
                vietnamese_meaning=?, status=?, consistency_status=?, analysis=?
            WHERE id=?''',
            (tai, tai, roman, roman, meaning, status, cons, json.dumps(analysis, ensure_ascii=False), wid))

        if status=='approved':
            old_sense=None; old_lex=None
            if old_tai:
                old_lex=db.execute('SELECT id FROM lexemes WHERE tai_text_original=?',(old_tai,)).fetchone()
                if old_lex:
                    old_sense=db.execute('SELECT id, lexeme_id FROM word_senses WHERE lexeme_id=? AND vietnamese_meaning=?',(old_lex['id'],old_meaning)).fetchone()

            if old_sense:
                if old_tai == tai:
                    target_lex_id = old_lex['id']
                    db.execute('UPDATE word_senses SET vietnamese_meaning=?, status=? WHERE id=?',(meaning,'approved',old_sense['id']))
                    if roman:
                        db.execute('UPDATE lexemes SET romanization=?, status=? WHERE id=?',(roman,'approved',target_lex_id))
                else:
                    target_lex=db.execute('SELECT id FROM lexemes WHERE tai_text_original=?',(tai,)).fetchone()
                    if target_lex:
                        target_lex_id=target_lex['id']
                        if roman: db.execute('UPDATE lexemes SET romanization=coalesce(romanization,?),status=? WHERE id=?',(roman,'approved',target_lex_id))
                    else:
                        target_lex_id=insert(db,'lexemes',dict(tai_text_original=tai,romanization=roman,status='approved',source_type='community'))
                    db.execute('UPDATE word_senses SET lexeme_id=?, vietnamese_meaning=?, status=? WHERE id=?',(target_lex_id,meaning,'approved',old_sense['id']))
                    rem=db.execute('SELECT count(*) FROM word_senses WHERE lexeme_id=?',(old_lex['id'],)).fetchone()[0]
                    if rem==0 and old_lex['id']!=target_lex_id:
                        db.execute('DELETE FROM lexeme_search_keys WHERE lexeme_id=?',(old_lex['id'],))
                        db.execute("DELETE FROM lexemes WHERE id=? AND source_type='community'",(old_lex['id'],))
            else:
                target_lex=db.execute('SELECT id FROM lexemes WHERE tai_text_original=?',(tai,)).fetchone()
                if target_lex:
                    target_lex_id=target_lex['id']
                    if roman: db.execute('UPDATE lexemes SET romanization=coalesce(romanization,?),status=? WHERE id=?',(roman,'approved',target_lex_id))
                else:
                    target_lex_id=insert(db,'lexemes',dict(tai_text_original=tai,romanization=roman,status='approved',source_type='community'))
                existing_sense=db.execute('SELECT id FROM word_senses WHERE lexeme_id=? AND vietnamese_meaning=?',(target_lex_id,meaning)).fetchone()
                if not existing_sense:
                    insert(db,'word_senses',dict(lexeme_id=target_lex_id,vietnamese_meaning=meaning,status='approved'))

            if roman:
                keys=engine.canonical_keys(roman)
                for k in keys:
                    db.execute('INSERT OR IGNORE INTO lexeme_search_keys (lexeme_id,canonical_key,rule_version) VALUES (?,?,?)',(target_lex_id,k,engine.version))
        elif old_dict.get('status')=='approved':
            if old_tai:
                lex=db.execute('SELECT id FROM lexemes WHERE tai_text_original=?',(old_tai,)).fetchone()
                if lex:
                    db.execute('UPDATE word_senses SET status=? WHERE lexeme_id=? AND vietnamese_meaning=?',(status,lex['id'],old_meaning))

        insert(db,'moderation_events',dict(entity_table='word_contributions',entity_id=wid,previous_status=old_dict['status'],new_status=status,admin_id=s['id']))
    return {'ok':True,'message':'Đã cập nhật từ đóng góp thành công (ghi đè bản cũ)!'}


@app.post('/api/admin/sentence-corrections/edit')
async def edit_sentence_correction(request:Request):
    s=admin(request); p=await payload(request)
    cid=text(p,'id',True,40)
    tai=text(p,'suggested_tai_text',True,5000)
    roman=text(p,'suggested_romanization',True,5000)
    meaning=text(p,'suggested_meaning',True,5000)
    status=p.get('status','approved')
    if status not in ('approved','rejected','pending'): status='approved'
    with database() as db:
        old=db.execute('SELECT * FROM sentence_corrections WHERE id=?',(cid,)).fetchone()
        if not old: raise HTTPException(404,'Không tìm thấy bản ghi sửa câu.')
        db.execute('UPDATE sentence_corrections SET suggested_tai_text=?, suggested_romanization=?, suggested_meaning=?, status=? WHERE id=?',
                   (tai,roman,meaning,status,cid))
        sid=old['sentence_id']
        if status=='approved':
            db.execute("UPDATE sentences SET tai_text_original=?, romanization=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (tai, roman, sid))
            if meaning and meaning.strip():
                existing_tr=db.execute("SELECT id FROM translations WHERE sentence_id=? ORDER BY (status='approved') DESC, created_at LIMIT 1", (sid,)).fetchone()
                if existing_tr:
                    db.execute("UPDATE translations SET vietnamese_text=?, status='approved', updated_at=CURRENT_TIMESTAMP WHERE id=?", (meaning.strip(), existing_tr['id']))
                else:
                    insert(db,'translations',dict(sentence_id=sid,vietnamese_text=meaning.strip(),origin='correction',contributor_id=old.get('contributor_id'),status='approved'))
        insert(db,'moderation_events',dict(entity_table='sentence_corrections',entity_id=cid,previous_status=old['status'],new_status=status,admin_id=s['id']))
    return {'ok':True,'message':'Đã cập nhật và duyệt câu sửa thành công (ghi đè bản cũ)!'}


@app.post('/api/admin/moderate')
async def moderate(request:Request):
    s=admin(request); p=await payload(request); table=p.get('table'); status=p.get('status'); id=text(p,'id',True,40)
    if table not in MODERATED or status not in ('approved','rejected'): raise HTTPException(422,'Thao tác không hợp lệ.')
    with database() as db:
        old=db.execute(f'SELECT status FROM {table} WHERE id=?',(id,)).fetchone()
        if not old: raise HTTPException(404,'Không tìm thấy bản ghi.')
        db.execute(f'UPDATE {table} SET status=? WHERE id=?',(status,id))
        if table=='sentences':
            db.execute('UPDATE sentence_submissions SET status=? WHERE sentence_id=?',(status,id))
            db.execute('UPDATE translations SET status=? WHERE sentence_id=? AND origin=\'contributor\'',(status,id))
        if table=='sentence_submissions':
            sid=db.execute('SELECT sentence_id FROM sentence_submissions WHERE id=?',(id,)).fetchone()['sentence_id']
            if sid:db.execute('UPDATE sentences SET status=? WHERE id=?',(status,sid))
        if table=='sentence_corrections' and status=='approved':
            sc=dict(db.execute('SELECT * FROM sentence_corrections WHERE id=?',(id,)).fetchone())
            sid=sc['sentence_id']
            if sc.get('suggested_tai_text'):
                db.execute("UPDATE sentences SET tai_text_original=?, romanization=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                           (sc['suggested_tai_text'], sc.get('suggested_romanization') or '', sid))
            if sc.get('suggested_meaning') and sc['suggested_meaning'].strip():
                existing_tr=db.execute("SELECT id FROM translations WHERE sentence_id=? ORDER BY (status='approved') DESC, created_at LIMIT 1", (sid,)).fetchone()
                if existing_tr:
                    db.execute("UPDATE translations SET vietnamese_text=?, status='approved', updated_at=CURRENT_TIMESTAMP WHERE id=?", (sc['suggested_meaning'].strip(), existing_tr['id']))
                else:
                    insert(db,'translations',dict(sentence_id=sid,vietnamese_text=sc['suggested_meaning'].strip(),origin='correction',contributor_id=sc.get('contributor_id'),status='approved'))
        if table=='word_contributions' and status=='approved':
            wc=dict(db.execute('SELECT * FROM word_contributions WHERE id=?',(id,)).fetchone())
            tai_text=wc.get('tai_text_final') or wc.get('tai_text_original')
            roman=wc.get('romanization_final') or wc.get('romanization_original')
            meaning=wc.get('vietnamese_meaning')
            if tai_text and meaning:
                lex=db.execute('SELECT id FROM lexemes WHERE tai_text_original=? LIMIT 1',(tai_text,)).fetchone()
                if lex:
                    lex_id=lex['id']
                    if roman:db.execute('UPDATE lexemes SET romanization=coalesce(romanization,?),status=? WHERE id=?',(roman,'approved',lex_id))
                else:
                    lex_id=insert(db,'lexemes',dict(tai_text_original=tai_text,romanization=roman,status='approved',source_type='community'))
                existing_sense=db.execute('SELECT id FROM word_senses WHERE lexeme_id=? AND vietnamese_meaning=? LIMIT 1',(lex_id,meaning)).fetchone()
                if not existing_sense:
                    insert(db,'word_senses',dict(lexeme_id=lex_id,vietnamese_meaning=meaning,status='approved'))
                if roman:
                    keys=engine.canonical_keys(roman)
                    for k in keys:
                        db.execute('INSERT OR IGNORE INTO lexeme_search_keys (lexeme_id,canonical_key,rule_version) VALUES (?,?,?)',(lex_id,k,engine.version))
        insert(db,'moderation_events',dict(entity_table=table,entity_id=id,previous_status=old['status'],new_status=status,admin_id=s['id']))
    return {'ok':True}


@app.get('/api/admin/stats')
def admin_stats(request:Request):
    admin(request)
    stats={}
    with database() as db:
        for table in ('sentences','translations','word_contributions','romanization_corrections','sentence_corrections'):
            rows=db.execute(f"SELECT status, count(*) as count FROM {table} GROUP BY status").fetchall()
            stats[table]={r['status']:r['count'] for r in rows}
    return {'stats':stats}


def export_corpus(db, status_filter='approved'):
    query='SELECT * FROM sentences' if status_filter=='all' else f"SELECT * FROM sentences WHERE status='{status_filter}'"
    sentences=[dict(r) for r in db.execute(query+' ORDER BY id')]
    translations=defaultdict(list); validations=defaultdict(list); reviews=defaultdict(list)
    for r in db.execute('SELECT * FROM translation_validations ORDER BY id'): validations[r['translation_id']].append(dict(r))
    for r in db.execute('SELECT * FROM translations ORDER BY id'):
        t=dict(r);t['validations']=validations[t['id']];translations[t['sentence_id']].append(t)
    for r in db.execute('SELECT * FROM sentence_reviews ORDER BY id'): reviews[r['sentence_id']].append(dict(r))
    corrections=defaultdict(list);submissions=defaultdict(list)
    for r in db.execute('SELECT * FROM romanization_corrections ORDER BY created_at,id'):corrections[r['sentence_id']].append(dict(r))
    for r in db.execute('SELECT * FROM sentence_submissions ORDER BY created_at,id'):submissions[r['sentence_id']].append(dict(r))
    for s in sentences:
        s['translations']=translations[s['id']];s['reviews']=reviews[s['id']]
        s['romanization_corrections']=corrections[s['id']];s['submission_history']=submissions[s['id']]
    return sentences


@app.get('/api/admin/export')
def export(request:Request,format:str='json',table:str='all',status:str='all',bom:bool=False):
    admin(request)
    if status not in ('all','pending','approved','rejected'): raise HTTPException(422,'Trạng thái không hợp lệ.')
    with database() as db:
        where=f" WHERE status='{status}'" if status!='all' else ""
        if table=='sentences':
            data=[dict(r) for r in db.execute(f'SELECT * FROM sentences{where} ORDER BY id')]
            filename=f"tai-sentences-{status}.{format}"
        elif table=='word_contributions':
            data=[dict(r) for r in db.execute(f'SELECT * FROM word_contributions{where} ORDER BY id')]
            filename=f"tai-word-contributions-{status}.{format}"
        elif table=='translations':
            data=[dict(r) for r in db.execute(f'SELECT * FROM translations{where} ORDER BY id')]
            filename=f"tai-translations-{status}.{format}"
        elif table=='lexemes':
            data=[dict(r) for r in db.execute(f'SELECT * FROM lexemes{where} ORDER BY id')]
            filename=f"tai-lexemes-{status}.{format}"
        else:
            corpus=export_corpus(db, status)
            wc_where=f" WHERE status='{status}'" if status!='all' else ""
            contributions=[dict(r) for r in db.execute(f'SELECT * FROM word_contributions{wc_where} ORDER BY id')]
            annotations=[dict(r) for r in db.execute(f'SELECT * FROM annotations{wc_where} ORDER BY id')]
            sentence_submissions=[dict(r) for r in db.execute(f'SELECT * FROM sentence_submissions{wc_where} ORDER BY id')]
            data={'schema_version':2,'sentences':corpus,'word_contributions':contributions,'sentence_submissions':sentence_submissions,'annotations':annotations}
            filename=f"tai-corpus-{status}.{format}"

    if format=='json':
        content=json.dumps(data,ensure_ascii=False,indent=2)
        return Response(content,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{filename}"'})
    if format!='csv': raise HTTPException(422,'Chọn json hoặc csv.')

    out=io.StringIO(newline=''); writer=csv.writer(out,lineterminator='\n')
    if isinstance(data,list) and data:
        writer.writerow(list(data[0].keys()))
        for row in data:
            writer.writerow([json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for v in row.values()])
    elif isinstance(data,dict) and 'sentences' in data:
        writer.writerow(['sentence_id','tai_text_original','sentence_json','translations_json','reviews_json'])
        for s in data['sentences']:
            writer.writerow([s['id'],s['tai_text_original'],json.dumps({k:v for k,v in s.items() if k not in ('translations','reviews')},ensure_ascii=False),
                json.dumps(s['translations'],ensure_ascii=False),json.dumps(s['reviews'],ensure_ascii=False)])
    else:
        writer.writerow(['empty'])
    csv_str = ('\ufeff' if bom else '') + out.getvalue()
    return Response(csv_str.encode('utf-8'), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@app.get('/api/health')
def health():
    with database() as db: count=db.execute('SELECT count(*) FROM word_senses').fetchone()[0]
    return {'ok':True,'mode':DB_BACKEND,'senses':count,'rule_version':engine.version}

accounts.install()

app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
@app.get('/favicon.ico')
def favicon(): return FileResponse(ROOT/'web/favicon.ico',media_type='image/x-icon')
@app.get('/apple-touch-icon.png')
def apple_icon(): return FileResponse(ROOT/'web/apple-touch-icon.png',media_type='image/png')
@app.get('/')
def home(): return FileResponse(ROOT/'web/index.html')

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('TAI_PORT','8000')))
