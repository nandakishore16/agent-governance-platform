"""Sanitized, prerecorded demonstration data. No model calls or private traces."""
import pandas as pd

SAMPLE_TASK = "Research agent governance principles and notify the engineering team about bounded autonomy."
SAMPLE_FINDINGS = [
    {"source": "Governance knowledge base", "content": "Use explicit action budgets, registered tools, and human escalation for risky operations."},
    {"source": "Governance knowledge base", "content": "Monitor agent tool calls, latency, token usage, failures, and reviewer outcomes."},
]
SAMPLE_ACTIONS = [{"tool": "send_notification_stub", "result": "Simulated notification to engineering team; no real message was sent."}]
SAMPLE_EVENTS = pd.DataFrame([
    {"step": 1, "event_type": "llm_call", "tool_name": "researcher", "tokens": 135, "duration_ms": 10214},
    {"step": 2, "event_type": "tool_call", "tool_name": "retrieve_governance_knowledge", "tokens": 0, "duration_ms": None},
    {"step": 3, "event_type": "llm_call", "tool_name": "doer", "tokens": 384, "duration_ms": 8598},
    {"step": 4, "event_type": "tool_call", "tool_name": "send_notification_stub", "tokens": 0, "duration_ms": None},
    {"step": 5, "event_type": "llm_call", "tool_name": "reviewer", "tokens": 274, "duration_ms": 9647},
])
FAILURE_EVENTS = pd.DataFrame([
    {"step": 1, "event_type": "tool_error", "tool_name": "send_notification_stub", "error": "Injected test failure for send_notification_stub", "duration_ms": 2000},
    {"step": 2, "event_type": "run_error", "tool_name": "agent-governance-run", "error": "Failure propagated to root trace", "duration_ms": None},
])
