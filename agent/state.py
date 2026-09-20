from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    task: str
    findings: list[dict]
    action_log: list[dict]
    autonomy_budget: int
    next_agent: str
    run_id: int
    error: str
    review_verdict: str      # "approved" / "revise" / ""
    review_attempted: bool   # prevents infinite reviewer<->doer loop
