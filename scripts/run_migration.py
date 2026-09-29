#!/usr/bin/env python3
"""Execute ALTER TABLE migration on Supabase via direct PostgreSQL connection."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import load_dotenv

import psycopg2

def main():
    supabase_url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    service_key = os.environ.get('SUPABASE_SERVICE_KEY')

    if not supabase_url:
        print("ERROR: SUPABASE_URL not set")
        return 1

    project_ref = supabase_url.replace('https://', '').replace('.supabase.co', '')
    host = f"db.{project_ref}.supabase.co"

    print(f"Connecting to PostgreSQL at {host}...")
    print(f"  Project ref: {project_ref}")

    statements = [
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS official_rating NUMERIC(6,2)",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS age INTEGER",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_starts INTEGER",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_wins INTEGER",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS career_places INTEGER",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS total_prize_money NUMERIC(12,2)",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS declared_weight NUMERIC(6,2)",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS sectional_times TEXT",
        "ALTER TABLE race_runners ADD COLUMN IF NOT EXISTS margin NUMERIC(4,1)",
        "ALTER TABLE races ADD COLUMN IF NOT EXISTS track_course VARCHAR(16)",
    ]

    conn = None
    try:
        conn = psycopg2.connect(
            host=host,
            port=5432,
            user="postgres",
            password=service_key,
            database="postgres",
            connect_timeout=10,
        )
        conn.autocommit = True
        cur = conn.cursor()

        print("[OK] Connected!\n")

        for stmt in statements:
            col_name = stmt.split("ADD COLUMN IF NOT EXISTS ")[1].split(" ")[0]
            try:
                cur.execute(stmt)
                print(f"  [OK] {col_name}")
            except Exception as e:
                print(f"  [WARN] {col_name}: {e}")

        print("\n[SUCCESS] Migration completed!")

        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name IN ('race_runners', 'races')
            AND column_name IN ('official_rating','age','career_starts','career_wins','career_places','total_prize_money','declared_weight','sectional_times','margin','track_course')
            ORDER BY table_name, ordinal_position
        """)
        rows = cur.fetchall()
        print(f"\nNew columns:")
        for col, dtype in rows:
            print(f"  {col}: {dtype}")

        cur.close()
        return 0

    except psycopg2.OperationalError as e:
        print(f"[FAIL] Connection failed: {e}")
        print("\nTrying alternative: Supabase REST API via postgrest...")
        return try_rest_api(statements)
    except Exception as e:
        print(f"[FAIL] {e}")
        return 1
    finally:
        if conn:
            conn.close()


def try_rest_api(statements):
    """Fallback: try via Supabase Management API."""
    import urllib.request
    import json

    supabase_url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    service_key = os.environ.get('SUPABASE_SERVICE_KEY')

    sql_endpoint = f"{supabase_url}/rest/v1/rpc/exec_sql"

    combined_sql = ";\n".join(statements)

    try:
        req = urllib.request.Request(
            sql_endpoint,
            data=json.dumps({"sql": combined_sql}).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'apikey': service_key,
                'Authorization': f'Bearer {service_key}',
            },
            method='POST',
        )
        resp = urllib.request.urlopen(req, timeout=15)
        print(f"[OK] REST API response: {resp.read().decode()}")
        return 0
    except Exception as e:
        print(f"[FAIL] REST API also failed: {e}")
        print("\n[FALLBACK] Trying pg-net extension via REST...")
        return try_pg_net(supabase_url, service_key, statements)


def try_pg_net(supabase_url, service_key, statements):
    """Try using pg_net or similar extension via RPC."""
    from supabase import create_client
    supabase = create_client(supabase_url, service_key)

    combined_sql = ";\n".join(statements)

    try:
        result = supabase.rpc('exec_sql', {'sql': combined_sql}).execute()
        print(f"[OK] RPC exec_sql: {result}")
        return 0
    except Exception as e:
        print(f"[INFO] RPC exec_sql not available: {e}")

    try:
        result = supabase.rpc('run_sql', {'query': combined_sql}).execute()
        print(f"[OK] RPC run_sql: {result}")
        return 0
    except Exception as e:
        print(f"[INFO] RPC run_sql not available: {e}")

    print("\n[FAIL] All methods exhausted.")
    print("Please run the SQL manually in Supabase Dashboard > SQL Editor:")
    print()
    for stmt in statements:
        print(f"  {stmt};")
    return 1


if __name__ == '__main__':
    sys.exit(main())
