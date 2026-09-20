"""
Agent Governance & Cost Observability Dashboard — container entrypoint.

Ported from the Week 15 Colab notebook. Differences from the notebook version:
- `dashboard.launch(share=True)` (a Colab-only public tunnel) is replaced with
  `dashboard.launch(server_name="0.0.0.0", server_port=7860)` so Azure Container
  Apps' ingress can reach it.
- The SQLite DB is initialized fresh on every container start (no baked-in
  data) — see README for why.
"""
import os
import sqlite3

import gradio as gr
import pandas as pd

from agent.config import DB_PATH
from agent.db import setup_database

# Initialize schema on startup (idempotent — safe on every boot)
setup_database()


def get_cost_ranking():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""SELECT run_id, prompt, total_tokens, total_cost_usd, status
                               FROM runs WHERE status='completed'
                               ORDER BY total_cost_usd DESC LIMIT 10""", conn)
    conn.close()
    return df


def get_tool_usage():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""SELECT tool_name, COUNT(*) as calls
                               FROM events WHERE event_type='tool_call'
                               GROUP BY tool_name ORDER BY calls DESC""", conn)
    conn.close()
    return df


def get_error_rate():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""SELECT tool_name as node, COUNT(*) as error_count
                               FROM events WHERE event_type='error'
                               GROUP BY tool_name ORDER BY error_count DESC""", conn)
    conn.close()
    return df


def get_anomalies():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT AVG(total_tokens) FROM runs WHERE status='completed' AND total_tokens > 0")
    avg_tokens = cursor.fetchone()[0] or 0
    df = pd.read_sql_query("""SELECT run_id, prompt, total_tokens FROM runs
                               WHERE status='completed' AND total_tokens > ?""", conn, params=(avg_tokens * 2,))
    conn.close()
    summary = f"Average tokens/run: {avg_tokens:.0f} | Anomalies flagged (>2x avg): {len(df)}"
    return summary, df


def get_eval_summary():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM eval_runs", conn)
    conn.close()
    total = len(df)
    if total == 0:
        return "No eval results yet. Run the eval suite to populate this tab.", df
    summary = (f"Structural: {df['structural_pass'].sum()}/{total} | "
               f"Rule-based: {df['rule_pass'].sum()}/{total} | "
               f"Judge pass: {df['judge_pass'].sum()}/{total} | "
               f"Avg judge score: {df['judge_score'].mean():.1f}/5")
    return summary, df


def check_bounded_autonomy_escalation():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events WHERE event_type='error'")
    total_errors = cursor.fetchone()[0]
    conn.close()
    if total_errors >= 5:
        return f"\U0001F6A8 ESCALATE: {total_errors} total errors logged — exceeds threshold of 5. Human review recommended."
    return f"\u2705 Normal: {total_errors} total errors logged — within acceptable range."


def build_dashboard():
    with gr.Blocks(title="Agent Governance Dashboard") as dashboard:
        gr.Markdown("# Agent Governance & Cost Observability Dashboard")

        with gr.Tab("Cost Ranking"):
            gr.Dataframe(get_cost_ranking())

        with gr.Tab("Tool Usage"):
            gr.Dataframe(get_tool_usage())

        with gr.Tab("Error Rate by Node"):
            gr.Dataframe(get_error_rate())

        with gr.Tab("Anomaly Detection"):
            summary_text, anomaly_df = get_anomalies()
            gr.Markdown(summary_text)
            gr.Dataframe(anomaly_df)

        with gr.Tab("Eval Suite Results"):
            eval_summary, eval_df = get_eval_summary()
            gr.Markdown(eval_summary)
            gr.Dataframe(eval_df)

        with gr.Tab("Bounded Autonomy Escalation"):
            gr.Markdown(check_bounded_autonomy_escalation())

    return dashboard


if __name__ == "__main__":
    dashboard = build_dashboard()
    port = int(os.environ.get("PORT", 7860))
    dashboard.launch(server_name="0.0.0.0", server_port=port)
