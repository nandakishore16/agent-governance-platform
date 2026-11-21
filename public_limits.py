"""Server-enforced public live-run quotas.

Set QUOTA_DATABASE_URL to a durable PostgreSQL URL for public deployment.
Without it, a local SQLite fallback is used for development ONLY.
Visitor identification is approximate (request.client.host), not authentication.
"""
import datetime
import hashlib
import os
import sqlite3
import threading
import gradio as gr
from contextlib import contextmanager

from agent.config import DB_PATH

MAX_DAILY = max(1, int(os.getenv("PUBLIC_DAILY_RUNS", "20")))
MAX_VISITOR_DAILY = max(1, int(os.getenv("PUBLIC_VISITOR_DAILY_RUNS", "2")))
MAX_PROMPT_CHARS = max(100, int(os.getenv("PUBLIC_MAX_PROMPT_CHARS", "500")))
QUOTA_DATABASE_URL = os.getenv("QUOTA_DATABASE_URL", "").strip()
PUBLIC_DEPLOYMENT = os.getenv("PUBLIC_DEPLOYMENT", "0") == "1"
_RUNNING = threading.BoundedSemaphore(1)


def _visitor_hash(request):
    client = getattr(request, "client", None)
    address = getattr(client, "host", None) or "unknown"
    return hashlib.sha256(address.encode("utf-8")).hexdigest()


def _today():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _sqlite_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("""CREATE TABLE IF NOT EXISTS public_run_limits (
        day TEXT NOT NULL, visitor_hash TEXT NOT NULL, run_count INTEGER NOT NULL,
        PRIMARY KEY(day, visitor_hash))""")
    return conn


def _pg_connection():
    import psycopg
    conn = psycopg.connect(QUOTA_DATABASE_URL, connect_timeout=5)
    conn.execute("""CREATE TABLE IF NOT EXISTS public_run_limits (
        day DATE NOT NULL, visitor_hash TEXT NOT NULL, run_count INTEGER NOT NULL,
        PRIMARY KEY(day, visitor_hash))""")
    conn.commit()
    return conn


def _counts(conn, day, visitor, pg):
    marker = "%s" if pg else "?"
    global_used = conn.execute(
        f"SELECT COALESCE(SUM(run_count),0) FROM public_run_limits WHERE day={marker}",
        (day,)).fetchone()[0]
    row = conn.execute(
        f"SELECT run_count FROM public_run_limits WHERE day={marker} AND visitor_hash={marker}",
        (day, visitor)).fetchone()
    return int(global_used), int(row[0]) if row else 0


def _storage():
    if QUOTA_DATABASE_URL:
        return _pg_connection(), True
    if PUBLIC_DEPLOYMENT:
        raise RuntimeError("Public live execution requires durable QUOTA_DATABASE_URL")
    return _sqlite_connection(), False


def quota_message(request):
    try:
        conn, pg = _storage()
        try:
            global_used, own_used = _counts(conn, _today(), _visitor_hash(request), pg)
        finally:
            conn.close()
        return (f"Live runs remaining today (UTC): "
                f"{max(0, MAX_DAILY-global_used)}/{MAX_DAILY} globally; "
                f"{max(0, MAX_VISITOR_DAILY-own_used)}/{MAX_VISITOR_DAILY} for this visitor. "
                "Demo Mode is always available.")
    except Exception:
        return "Live quota is temporarily unavailable. Demo Mode is still available."


def reserve_run(request: gr.Request):
    """Atomically reserve a run. Fail closed on storage errors."""
    try:
        conn, pg = _storage()
        try:
            if pg:
                # Serialize all quota reservations across app replicas using a fixed advisory lock.
                conn.execute("BEGIN")
                conn.execute("SELECT pg_advisory_xact_lock(987643211)")
            else:
                conn.execute("BEGIN IMMEDIATE")
            day, visitor = _today(), _visitor_hash(request)
            global_used, own_used = _counts(conn, day, visitor, pg)
            if global_used >= MAX_DAILY:
                conn.rollback()
                return "Global daily live-run limit reached. Explore Demo Mode instead."
            if own_used >= MAX_VISITOR_DAILY:
                conn.rollback()
                return "Visitor daily live-run limit reached. Explore Demo Mode instead."
            marker = "%s" if pg else "?"
            conn.execute(
                f"INSERT INTO public_run_limits(day, visitor_hash, run_count) VALUES ({marker}, {marker}, 1) "
                "ON CONFLICT(day, visitor_hash) DO UPDATE SET run_count=public_run_limits.run_count+1",
                (day, visitor))
            conn.commit()
            return None
        finally:
            conn.close()
    except Exception:
        return "Live execution temporarily unavailable: quota storage error. Explore Demo Mode instead."


@contextmanager
def execution_slot():
    acquired = _RUNNING.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            _RUNNING.release()
