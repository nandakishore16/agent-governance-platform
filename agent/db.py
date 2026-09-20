"""
SQLite-backed tracing store for agent runs, events, and eval results.
Ported from the MASTER CELL (Weeks 7-8) plus the duration_ms column
added in Week 12 and the eval_runs table added in Week 14/15.
"""
import sqlite3
from datetime import datetime

from agent.config import DB_PATH


def setup_database():
    """Create all tables if they don't already exist. Safe to call every startup."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
        prompt TEXT, total_tokens INTEGER DEFAULT 0, total_cost_usd REAL DEFAULT 0.0, status TEXT)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER, event_type TEXT, tool_name TEXT, tool_input TEXT,
        tool_output TEXT, tokens INTEGER, timestamp TEXT, duration_ms INTEGER DEFAULT 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS eval_runs (
        eval_id INTEGER PRIMARY KEY AUTOINCREMENT,
        test_case_id TEXT,
        run_id INTEGER,
        structural_pass INTEGER,
        rule_pass INTEGER,
        judge_score INTEGER,
        judge_pass INTEGER,
        timestamp TEXT
    )""")
    conn.commit()
    conn.close()


def start_run(prompt):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO runs (timestamp, prompt, status) VALUES (?, ?, ?)", (ts, prompt, 'running'))
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def log_event(run_id, event_type, tool_name, tool_input, tool_output, tokens):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""INSERT INTO events (run_id, event_type, tool_name, tool_input, tool_output, tokens, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?)""", (run_id, event_type, tool_name, tool_input, tool_output, tokens, ts))
    conn.commit()
    conn.close()


def log_event_timed(run_id, event_type, tool_name, tool_input, tool_output, tokens, duration_ms):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""INSERT INTO events (run_id, event_type, tool_name, tool_input, tool_output, tokens, timestamp, duration_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (run_id, event_type, tool_name, tool_input, tool_output, tokens, ts, duration_ms))
    conn.commit()
    conn.close()


def complete_run(run_id, total_tokens, total_cost_usd):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE runs SET total_tokens=?, total_cost_usd=?, status=? WHERE run_id=?",
                   (total_tokens, total_cost_usd, 'completed', run_id))
    conn.commit()
    conn.close()


def save_eval_result(result: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""INSERT INTO eval_runs (test_case_id, run_id, structural_pass, rule_pass, judge_score, judge_pass, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?)""", (result["id"], result["run_id"], int(result["structural_pass"]),
    int(result["rule_pass"]), result["judge_score"], int(result["judge_pass"]), ts))
    conn.commit()
    conn.close()
