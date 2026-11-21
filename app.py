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
import logging

from agent.config import DB_PATH
from agent.db import setup_database
from public_demo import SAMPLE_TASK, SAMPLE_FINDINGS, SAMPLE_ACTIONS, SAMPLE_EVENTS, FAILURE_EVENTS
from public_limits import MAX_PROMPT_CHARS, execution_slot, quota_message, reserve_run, PUBLIC_DEPLOYMENT, QUOTA_DATABASE_URL
def show_quota(request: gr.Request):
    return quota_message(request)

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


def execute_agent(task, budget, request: gr.Request):
    """Execute a real graph run; never expose secrets or full prompts in public logs."""
    if not task or not task.strip():
        return "Enter a task first.", [], [], "", pd.DataFrame()
    if len(task) > MAX_PROMPT_CHARS:
        return (f"Task too long (maximum {MAX_PROMPT_CHARS} characters).", [], [], "", pd.DataFrame())
    with execution_slot() as acquired:
        if not acquired:
            return ("Another live run is executing. Please try later or explore Demo Mode.", [], [], "", pd.DataFrame())
        refusal = reserve_run(request)
        if refusal:
            return (refusal, [], [], "", pd.DataFrame())
        return _execute_reserved_agent(task, budget)


def _execute_reserved_agent(task, budget):
    try:
        # Lazy import: importing agent.tracing initializes the Gemini RAG collection.
        from agent.tracing import run_with_langfuse
        state = run_with_langfuse(task.strip(), autonomy_budget=int(budget))
        run_id = state.get("run_id")
        with sqlite3.connect(DB_PATH) as conn:
            events = pd.read_sql_query(
                """SELECT event_id, event_type, tool_name, tokens, duration_ms,
                          timestamp FROM events WHERE run_id = ? ORDER BY event_id""",
                conn, params=(run_id,))
        status = (f"Run ID: {run_id} | Verdict: "
                  f"{state.get('review_verdict') or 'not reviewed'} | "
                  f"Remaining action budget: {state.get('autonomy_budget')} | "
                  f"Error: {state.get('error') or 'none'}")
        return (status, state.get("findings", []), state.get("action_log", []),
                state.get("review_verdict", ""), events)
    
    except Exception as exc:
        logging.exception(
            "Live agent execution failed"
        )
        return (
            f"Execution failed ({type(exc).__name__}). Check server logs.",
            [], [], "", pd.DataFrame()
        )



def build_dashboard():
    with gr.Blocks(title="Agent Governance Dashboard") as dashboard:
        gr.Markdown("# Agent Governance & Cost Observability Dashboard")
        gr.Markdown("Prototype only. Action tools simulate operations; they do not write files or send notifications.")

        with gr.Tab("Demo Mode — Start Here"):
            gr.Markdown("### Recorded successful execution (sample data)\nThis example is shown immediately and does **not** call Gemini. The notification tool is simulated.")
            gr.Textbox(value=SAMPLE_TASK, label="Recorded task", interactive=False)
            gr.Markdown("**Result:** Approved | **LLM calls:** 3 | **Tokens:** 793 | **Action budget remaining:** 4/5")
            gr.JSON(value=SAMPLE_FINDINGS, label="Research findings (sanitized sample)")
            gr.JSON(value=SAMPLE_ACTIONS, label="Tool execution (simulated sample)")
            gr.Dataframe(value=SAMPLE_EVENTS, label="Recorded execution events", interactive=False)
            gr.Markdown("### Failure observability (recorded example)\nThe notification tool was deliberately failed in a controlled test. Both the tool observation and root trace were marked ERROR in Langfuse.")
            gr.Dataframe(value=FAILURE_EVENTS, label="Sanitized failure example", interactive=False)
            gr.Markdown("**Want to try the real workflow?** Open the **Live Agent** tab. Live requests consume a limited shared Gemini quota.")

        with gr.Tab("Live Agent"):
            gr.Markdown("### Optional live execution\nNo login required. Live execution is subject to server-side daily limits and a single concurrent run. Actions are simulated; no real notifications are sent.")
            live_quota = gr.Textbox(value="Checking live quota...", label="Remaining live runs (UTC)", interactive=False)
            task = gr.Textbox(label="Task", lines=3, max_length=MAX_PROMPT_CHARS,
                placeholder="Research agent governance principles and notify the engineering team")
            budget = gr.Slider(minimum=1, maximum=5, step=1, value=5,
                               label="Action autonomy budget")
            run_button = gr.Button("Run Live Agent", variant="primary")
            status = gr.Textbox(label="Run status", interactive=False)
            findings = gr.JSON(label="Research findings")
            actions = gr.JSON(label="Action log (simulated tools)")
            verdict = gr.Textbox(label="Reviewer verdict", interactive=False)
            events = gr.Dataframe(label="Execution events", interactive=False)
            
            run_button.click(
                fn=execute_agent,
                inputs=[task, budget],
                outputs=[status, findings, actions, verdict, events],
                concurrency_limit=1
            ).then(
                fn=show_quota,
                outputs=live_quota
            )

            gr.Button("Refresh remaining quota").click(
                fn=show_quota,
                outputs=live_quota
            )

        dashboard.load(
            fn=show_quota,
            outputs=live_quota
        )


        if os.getenv("ENABLE_PRIVATE_ANALYTICS", "0") == "1":
            with gr.Tab("Cost Ranking"):
                ranking = gr.Dataframe(label="Completed runs")
                gr.Button("Refresh").click(get_cost_ranking, outputs=ranking)
            with gr.Tab("Tool Usage"):
                usage = gr.Dataframe(label="Tool usage")
                gr.Button("Refresh").click(get_tool_usage, outputs=usage)
            with gr.Tab("Error Rate by Node"):
                errors = gr.Dataframe(label="Error counts")
                gr.Button("Refresh").click(get_error_rate, outputs=errors)
            with gr.Tab("Anomaly Detection"):
                anomaly_summary = gr.Textbox(label="Anomaly summary")
                anomaly_table = gr.Dataframe(label="Token anomalies")
                gr.Button("Refresh").click(get_anomalies,
                    outputs=[anomaly_summary, anomaly_table])
            with gr.Tab("Eval Suite Results"):
                eval_summary = gr.Textbox(label="Evaluation summary")
                eval_table = gr.Dataframe(label="Evaluation runs")
                gr.Button("Refresh").click(get_eval_summary,
                    outputs=[eval_summary, eval_table])
            with gr.Tab("Bounded Autonomy Escalation"):
                escalation = gr.Textbox(label="Escalation status")
                gr.Button("Refresh").click(check_bounded_autonomy_escalation,
                    outputs=escalation)
    return dashboard



if __name__ == "__main__":
    dashboard = build_dashboard()

    port = int(os.environ.get("PORT", 7860))

    if PUBLIC_DEPLOYMENT and not QUOTA_DATABASE_URL:
        logging.warning("Public mode without PostgreSQL: live execution will fail closed")
    dashboard.launch(
        server_name="0.0.0.0",
        server_port=port,
        show_error=False
    )

