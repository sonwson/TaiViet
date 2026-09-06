"""Script đồng bộ và nạp trực tiếp toàn bộ CSDL từ runtime/tai.db lên Supabase PostgreSQL."""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
import sqlite3
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLES_IN_ORDER = [
    'source_records',
    'lexemes',
    'word_senses',
    'orthography_analyses',
    'sentences',
    'translations',
    'word_sense_examples',
    'translation_validations',
    'sentence_reviews',
    'user_roles',
    'annotations',
    'word_contributions',
    'moderation_events',
    'lexeme_search_keys',
    'sentence_submissions',
    'romanization_corrections'
]

def get_connection_url(args_url=None):
    if args_url:
        return args_url
    env_url = os.environ.get('SUPABASE_DB_URL')
    if env_url:
        return env_url
    env_file = ROOT / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('SUPABASE_DB_URL='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    return None

def main():
    parser = argparse.ArgumentParser(description="Load database from local SQLite to Supabase PostgreSQL")
    parser.add_argument('--conn', type=str, help='Supabase PostgreSQL Connection URI')
    parser.add_argument('--schema-only', action='store_true', help='Chỉ tạo Schema & RLS, không nạp dữ liệu')
    parser.add_argument('--data-only', action='store_true', help='Chỉ nạp dữ liệu, bỏ qua bước tạo Schema')
    parser.add_argument('--sqlite', type=Path, default=ROOT / 'runtime/tai.db', help='Đường dẫn file SQLite local')
    args = parser.parse_args()

    conn_url = get_connection_url(args.conn)
    if not conn_url:
        print("\n[!] LỖI: Chưa cung cấp Supabase Connection URI.")
        print("Cách cung cấp:")
        print("  1. Dùng tham số: python scripts/load_to_supabase.py --conn \"postgresql://postgres:password@...:5432/postgres\"")
        print("  2. Hoặc thêm vào file .env: SUPABASE_DB_URL=postgresql://postgres:password@...:5432/postgres\n")
        sys.exit(1)

    try:
        import psycopg2
        from psycopg2.extras import execute_batch
    except ImportError:
        print("\n[!] Đang thiếu thư viện psycopg2. Vui lòng cài đặt bằng:")
        print("    pip install psycopg2-binary\n")
        sys.exit(1)

    print("[*] Đang kết nối tới Supabase PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(conn_url)
        pg_conn.autocommit = False
        print("[+] Kết nối Supabase thành công!")
    except Exception as e:
        print(f"[-] Kết nối thất bại: {e}")
        sys.exit(1)

    if not args.data_only:
        schema_path = ROOT / 'database/supabase.sql'
        print(f"[*] Đang nạp Schema và cấu hình RLS bảo mật từ {schema_path.name}...")
        schema_sql = schema_path.read_text(encoding='utf-8')
        try:
            with pg_conn.cursor() as cur:
                cur.execute(schema_sql)
            pg_conn.commit()
            print("[+] Tạo Schema, Bảng, Chỉ mục và RLS Policies thành công!")
        except Exception as e:
            pg_conn.rollback()
            print(f"[-] Lỗi khi tạo Schema: {e}")
            sys.exit(1)

    if args.schema_only:
        print("[*] Đã hoàn thành (Chế độ --schema-only).")
        pg_conn.close()
        return

    if not args.sqlite.exists():
        print(f"[-] Không tìm thấy file SQLite tại: {args.sqlite}")
        sys.exit(1)

    print(f"[*] Đang đọc dữ liệu từ local SQLite: {args.sqlite}...")
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_cur = sqlite_conn.cursor()

    total_inserted = 0
    with pg_conn.cursor() as pg_cur:
        for table in TABLES_IN_ORDER:
            sqlite_cur.execute(f"SELECT count(*) FROM sqlite_master WHERE type='table' AND name='{table}'")
            if sqlite_cur.fetchone()[0] == 0:
                continue

            sqlite_cur.execute(f'SELECT * FROM "{table}"')
            col_names = [d[0] for d in sqlite_cur.description]
            rows = sqlite_cur.fetchall()
            count = len(rows)

            if count == 0:
                print(f"  - {table}: 0 dòng (bỏ qua)")
                continue

            print(f"  - Đang nạp bảng {table}: {count:,} dòng...", end="", flush=True)

            cols_str = ','.join(f'"{c}"' for c in col_names)
            placeholders = ','.join(['%s'] * len(col_names))
            conflict_target = 'id'
            if table == 'lexeme_search_keys':
                conflict_target = 'lexeme_id, canonical_key, rule_version'
            elif table == 'user_roles':
                conflict_target = 'user_id'

            insert_sql = f"""
                INSERT INTO public."{table}" ({cols_str})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO NOTHING
            """

            batch_size = 1000
            for i in range(0, count, batch_size):
                batch = rows[i:i + batch_size]
                execute_batch(pg_cur, insert_sql, batch)

            pg_conn.commit()
            total_inserted += count
            print(f" XONG ({count:,} dòng).")

    sqlite_conn.close()
    pg_conn.close()

    print("\n==================================================")
    print(f"[V] HOÀN TẤT! Đã nạp thành công toàn bộ CSDL lên Supabase.")
    print(f"    Tổng cộng: {total_inserted:,} bản ghi trên {len(TABLES_IN_ORDER)} bảng.")
    print("==================================================\n")

if __name__ == '__main__':
    main()
