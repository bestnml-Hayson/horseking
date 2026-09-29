#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/common.py
Shared utilities for all pipeline scripts.
Eliminates duplication of get_supabase_client, _load_dotenv, batch_upsert, etc.
"""
import os
import sys
import time
from typing import Dict, List, Optional

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed. Run: pip install supabase")
    sys.exit(1)

import httpx


def retry_supabase(fn, retries=3, delay=2, backoff=2):
    """Retry a Supabase call on transient network errors (RemoteProtocolError, etc.)."""
    for attempt in range(retries):
        try:
            return fn()
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout,
                ConnectionError, OSError) as e:
            if attempt < retries - 1:
                wait = delay * (backoff ** attempt)
                print(f"    [RETRY] {type(e).__name__}: {e} — retrying in {wait}s (attempt {attempt+2}/{retries})")
                time.sleep(wait)
            else:
                raise


def load_dotenv():
    """Load .env.local into os.environ (idempotent)."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env.local')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def get_supabase() -> Client:
    """Create Supabase client. Prefers service_role key (bypasses RLS)."""
    url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')
    if not url or not key:
        raise EnvironmentError(
            "Missing SUPABASE_URL/SUPABASE_SERVICE_KEY or "
            "NEXT_PUBLIC_SUPABASE_URL/NEXT_PUBLIC_SUPABASE_ANON_KEY"
        )
    return create_client(url, key)


def batch_upsert(supabase: Client, table: str, rows: List[Dict],
                 pk: str, batch_size: int = 200) -> int:
    """Batch upsert rows into a Supabase table. Returns count of successful rows."""
    total_ok = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            result = supabase.table(table).upsert(batch, on_conflict=pk).execute()
            total_ok += len(result.data) if result.data else len(batch)
        except Exception as e:
            print(f"    [ERROR] {table} batch {i // batch_size + 1}: {e}")
            for row in batch:
                try:
                    supabase.table(table).upsert(row, on_conflict=pk).execute()
                    total_ok += 1
                except Exception:
                    pass
    print(f"    [OK] {total_ok}/{len(rows)} rows upserted to {table}")
    return total_ok


def has_column(supabase: Client, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    try:
        supabase.table(table).select(column).limit(1).execute()
        return True
    except Exception:
        return False


def truncate(s: Optional[str], max_len: int) -> Optional[str]:
    """Safely truncate a string to fit a DB column."""
    if s is None:
        return None
    s = str(s)
    return s[:max_len] if len(s) > max_len else s
