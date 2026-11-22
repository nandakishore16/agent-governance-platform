"""Execute the graph with live Langfuse observations and SQLite accounting."""
import sqlite3
from contextlib import nullcontext
import os

from agent.config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST, DB_PATH
from agent.db import start_run, complete_run, setup_database
from agent.nodes import OUTPUT_COST_PER_M
from agent.graph import app

_langfuse_client = None

def get_langfuse():
    global _langfuse_client
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return None
    if _langfuse_client is None:
        os.environ["LANGFUSE_PUBLIC_KEY"] = LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = LANGFUSE_HOST
        from langfuse import get_client
        _langfuse_client = get_client()
    return _langfuse_client

def run_with_langfuse(task: str, autonomy_budget: int = 5) -> dict:
    setup_database()
    langfuse = get_langfuse()
    run_id = start_run(task)
    initial_state = {
        "messages": [], "task": task, "findings": [], "action_log": [],
        "autonomy_budget": autonomy_budget, "next_agent": "", "run_id": run_id,
        "error": "", "review_verdict": "", "review_attempted": False
    }
    context = (langfuse.start_as_current_observation(
        as_type="span", name="agent-governance-run",
        input={"task": "[redacted]"}, metadata={"sqlite_run_id": run_id})
        if langfuse else nullcontext(None))
    final_state = None
    try:
        with context as root_span:
            # LangGraph recursion bound limits the number of graph node transitions.
            # It is not a hard token or provider-billing cap.
            recursion_limit = max(8, min(40, int(os.getenv("AGENT_RECURSION_LIMIT", "24"))))
            final_state = app.invoke(initial_state, config={"recursion_limit": recursion_limit})
            if root_span is not None:
                if final_state.get("error"):
                    root_span.update(level="ERROR", status_message=final_state["error"])
                root_span.update(output={
                    "findings": len(final_state.get("findings", [])),
                    "actions": len(final_state.get("action_log", [])),
                    "verdict": final_state.get("review_verdict", ""),
                    "error": final_state.get("error", "")
                })
        return final_state
    finally:
        conn = sqlite3.connect(DB_PATH)
        try:
            total_tokens = conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            status = "failed" if final_state is None or final_state.get("error") else "completed"
            # Existing project cost estimate: all tokens use one flat rate.
            cost = round((total_tokens / 1_000_000) * OUTPUT_COST_PER_M, 6)
            conn.execute("UPDATE runs SET total_tokens=?, total_cost_usd=?, status=? WHERE run_id=?",
                         (total_tokens, cost, status, run_id))
            conn.commit()
        finally:
            conn.close()
        if langfuse:
            langfuse.flush()
