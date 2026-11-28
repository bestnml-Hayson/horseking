#!/usr/bin/env python3
"""Apply a .sql migration file to Supabase (direct PG, then RPC exec_sql)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import load_dotenv

import psycopg2


def statements_from(path):
    sql = open(path, encoding='utf-8').read()
    return [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]


def direct(sql_text):
    supabase_url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    service_key = os.environ.get('SUPABASE_SERVICE_KEY')
    db_url = os.environ.get('SUPABASE_DB_URL') or os.environ.get('DATABASE_URL')
    if db_url:
        conn = psycopg2.connect(db_url, connect_timeout=15)
    else:
        ref = supabase_url.replace('https://', '').replace('.supabase.co', '')
        conn = psycopg2.connect(
            host=f"db.{ref}.supabase.co", port=5432, user="postgres",
            password=service_key, database="postgres", connect_timeout=15, sslmode='require',
        )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.close()


def via_rpc(statements):
    from supabase import create_client
    sb = create_client(
        os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL'),
        os.environ['SUPABASE_SERVICE_KEY'],
    )
    for name, arg in (('exec_sql', 'sql'), ('run_sql', 'query')):
        try:
            sb.rpc(name, {arg: ';\n'.join(statements)}).execute()
            return True
        except Exception as e:
            print(f"  [RPC {name}] {e}")
    return False


def main():
    statements = statements_from(sys.argv[1])
    try:
        direct(';\n'.join(statements))
        print('[OK] migration applied via direct PostgreSQL')
        return 0
    except Exception as e:
        print(f'[WARN] direct PostgreSQL failed: {e}')
    if via_rpc(statements):
        print('[OK] migration applied via RPC')
        return 0
    print('[FAIL] migration not applied')
    return 1


if __name__ == '__main__':
    sys.exit(main())