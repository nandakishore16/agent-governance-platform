"""
LangGraph node functions. Final versions after all fixes through Week 15:
- timed logging (log_event_timed) throughout (Week 12-13 fix)
- reviewer agent in the loop (Week 9 fix)
- retry + safe tool node error handling (Week 8)
"""
import time
import os
from contextlib import nullcontext

from agent.observability import observation

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.config import GEMINI_API_KEY
from agent.db import log_event, log_event_timed
from agent.state import AgentState
from agent.tools import research_tools, action_tools

# --- LLM setup ---
_base_llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=GEMINI_API_KEY, max_output_tokens=1024)
llm_with_research_tools = _base_llm.bind_tools(research_tools).with_retry(stop_after_attempt=2, wait_exponential_jitter=True)
llm_with_action_tools = _base_llm.bind_tools(action_tools).with_retry(stop_after_attempt=2, wait_exponential_jitter=True)
llm = _base_llm.with_retry(stop_after_attempt=2, wait_exponential_jitter=True)

OUTPUT_COST_PER_M = 0.30


def get_usage(response) -> dict:
    return getattr(response, "usage_metadata", None) or {}


def update_llm_observation(span, response, err, duration_ms):
    """Record Gemini usage as native Langfuse generation fields, not only metadata."""
    if span is None:
        return
    if err or response is None:
        span.update(output={"error": err}, metadata={"duration_ms": duration_ms})
        return
    usage = get_usage(response)
    usage_details = {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0),
        "total": usage.get("total_tokens", 0),
    }
    span.update(
        model=getattr(_base_llm, "model", None) or "unknown",
        usage_details=usage_details,
        output={"tool_calls": [c["name"] for c in (response.tool_calls or [])],
                "content": str(response.content)[:500]},
        metadata={"duration_ms": duration_ms},
    )


# --- Retry helper (Week 8) ---
def call_with_retry(run_id, node_name, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as e:
        log_event(run_id, "error", node_name, str(args)[:300], f"attempt 1 failed: {e}", 0)
        try:
            return fn(*args, **kwargs), None
        except Exception as e2:
            log_event(run_id, "error", node_name, str(args)[:300], f"attempt 2 failed: {e2}", 0)
            return None, str(e2)


# --- Error-safe tool node (Week 8) ---
def safe_tool_node(tools_list, node_name):
    tools_by_name = {t.name: t for t in tools_list}

    def _node(state: AgentState) -> dict:
        last_msg = state["messages"][-1]
        tool_call = last_msg.tool_calls[0]
        tool_name = tool_call["name"]
        t = tools_by_name.get(tool_name)
        if t is None:
            err = f"Unregistered tool: {tool_name}"
            log_event(state["run_id"], "error", node_name, tool_name, err, 0)
            return {"error": err, "messages": [ToolMessage(content=err, tool_call_id=tool_call["id"], name=tool_name)]}
        # Explicit opt-in fault injection for local testing only. No real action is performed.
        # Example: AGENT_TEST_FAIL_TOOL=send_notification_stub
        injected_tool = os.getenv("AGENT_TEST_FAIL_TOOL", "")
        def invoke_tool(args):
            if injected_tool and injected_tool == tool_name:
                raise RuntimeError(f"Injected test failure for {tool_name}")
            return t.invoke(args)
        start = time.perf_counter()
        with observation(f"tool:{tool_name}", "span", {"tool": tool_name, "arguments": str(tool_call["args"])[:500]}) as span:
            result, err = call_with_retry(state["run_id"], f"{node_name}_tool", invoke_tool, tool_call["args"])
            duration_ms = int((time.perf_counter() - start) * 1000)
            log_event_timed(state["run_id"], "tool_execution", tool_name, str(tool_call["args"])[:500], str(result if err is None else err)[:500], 0, duration_ms)
            if span is not None:
                span.update(output={"result": str(result)[:500] if err is None else None, "error": err, "duration_ms": duration_ms})
                if err:
                    span.update(level="ERROR", status_message=err)
        if err:
            error_msg = ToolMessage(content=f"Tool failed after retry: {err}",
                                     tool_call_id=tool_call["id"], name=tool_call["name"])
            return {"messages": [error_msg], "error": err}
        tool_msg = ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=tool_call["name"])
        return {"messages": [tool_msg]}
    return _node


research_tool_node = safe_tool_node(research_tools, "researcher")
action_tool_node = safe_tool_node(action_tools, "doer")


# --- Nodes ---
def researcher_node(state: AgentState) -> dict:
    system_msg = SystemMessage(content=("You are a research agent. Use the retrieve_governance_knowledge tool "
        "to gather relevant information for the task. Once you have enough information, summarize your findings clearly."))
    task_msg = HumanMessage(content=state["task"])
    start = time.perf_counter()
    with observation("llm:researcher", "generation", {"task": state["task"][:500]}) as span:
        response, err = call_with_retry(state["run_id"], "researcher", llm_with_research_tools.invoke, [system_msg, task_msg])
        duration_ms = int((time.perf_counter() - start) * 1000)
        if span is not None:
            update_llm_observation(span, response, err, duration_ms)
    if err:
        return {"error": err}
    usage = get_usage(response)
    content_text = response.content if isinstance(response.content, str) else str(response.content)
    log_event_timed(state["run_id"], "llm_call", None, state["task"], content_text[:500], usage.get("total_tokens", 0), duration_ms)
    return {"messages": [response]}


def capture_findings_node(state: AgentState) -> dict:
    if state.get("error"):
        return {}
    last_msg = state["messages"][-1]
    if isinstance(last_msg, ToolMessage):
        log_event(state["run_id"], "tool_call", last_msg.name, "", str(last_msg.content)[:500], 0)
        return {"findings": state.get("findings", []) + [{"source": "retrieve_governance_knowledge", "content": last_msg.content}]}
    return {}


def doer_node(state: AgentState) -> dict:
    if state["autonomy_budget"] <= 0:
        return {"messages": [AIMessage(content="Autonomy budget exhausted.")]}
    system_msg = SystemMessage(content=("You are an action-taking agent. Based on the task and research findings, "
        "take the necessary action using your available tools. Be precise and minimal."))
    findings_summary = "\n".join(f["content"] for f in state.get("findings", []))
    task_msg = HumanMessage(content=f"Task: {state['task']}\n\nResearch findings:\n{findings_summary}")
    start = time.perf_counter()
    with observation("llm:doer", "generation", {"task": state["task"][:500]}) as span:
        response, err = call_with_retry(state["run_id"], "doer", llm_with_action_tools.invoke, [system_msg, task_msg])
        duration_ms = int((time.perf_counter() - start) * 1000)
        if span is not None:
            update_llm_observation(span, response, err, duration_ms)
    if err:
        return {"error": err}
    usage = get_usage(response)
    content_text = response.content if isinstance(response.content, str) else str(response.content)
    log_event_timed(state["run_id"], "llm_call", None, findings_summary[:500], content_text[:500], usage.get("total_tokens", 0), duration_ms)
    return {"messages": [response]}


def capture_action_node(state: AgentState) -> dict:
    if state.get("error"):
        return {}
    last_msg = state["messages"][-1]
    if isinstance(last_msg, ToolMessage):
        log_event(state["run_id"], "tool_call", last_msg.name, "", str(last_msg.content)[:500], 0)
        return {"action_log": state.get("action_log", []) + [{"tool": last_msg.name, "result": last_msg.content}],
                "autonomy_budget": state["autonomy_budget"] - 1}
    return {"autonomy_budget": state["autonomy_budget"] - 1}


def reviewer_node(state: AgentState) -> dict:
    if state.get("error"):
        return {"review_verdict": "error"}
    last_action = state["action_log"][-1] if state["action_log"] else None
    findings_summary = "\n".join(f["content"] for f in state.get("findings", []))
    system_msg = SystemMessage(content=(
        "You are a reviewer agent. Check whether the action taken is well-supported by "
        "the research findings and actually addresses the task. Reply with exactly one "
        "word: 'approved' if it's good, or 'revise' if it should be redone."
    ))
    review_msg = HumanMessage(content=(
        f"Task: {state['task']}\n\nFindings:\n{findings_summary}\n\nAction taken: {last_action}"
    ))
    start = time.perf_counter()
    with observation("llm:reviewer", "generation", {"task": state["task"][:500]}) as span:
        response, err = call_with_retry(state["run_id"], "reviewer", llm.invoke, [system_msg, review_msg])
        duration_ms = int((time.perf_counter() - start) * 1000)
        if span is not None:
            update_llm_observation(span, response, err, duration_ms)
    if err:
        return {"review_verdict": "error", "error": f"Reviewer failed: {err}"}
    usage = get_usage(response)
    
    content_text = response.content if isinstance(response.content, str) else str(response.content)

    log_event_timed(
        state["run_id"],
        "llm_call",
        None,
        str(last_action)[:300],
        content_text[:200],
        usage.get("total_tokens", 0),
        duration_ms
    )

    try:
        verdict = extract_reviewer_verdict(response.content)
    except ValueError as exc:
        return {
            "review_verdict": "error",
            "error": str(exc)
        }

    return {"review_verdict": verdict}



def coordinator_node(state: AgentState) -> dict:
    if state.get("error"):
        return {"next_agent": "end"}
    if state["autonomy_budget"] <= 0:
        return {"next_agent": "end"}

    has_findings = len(state.get("findings", [])) > 0
    has_actions = len(state.get("action_log", [])) > 0
    verdict = state.get("review_verdict", "")

    if not has_findings:
        return {"next_agent": "researcher"}
    if has_findings and not has_actions:
        return {"next_agent": "doer"}
    if has_actions and verdict == "":
        return {"next_agent": "reviewer"}
    if verdict == "revise" and not state.get("review_attempted"):
        return {"next_agent": "doer", "review_attempted": True, "review_verdict": ""}
    return {"next_agent": "end"}


# --- Routing ---
def route_from_coordinator(state):
    return state["next_agent"]


def research_needs_tool(state):
    if state.get("error") or not state["messages"]:
        return "no_tool"
    return "tool" if getattr(state["messages"][-1], "tool_calls", None) else "no_tool"


def doer_needs_tool(state):
    if state.get("error") or not state["messages"]:
        return "no_tool"
    return "tool" if getattr(state["messages"][-1], "tool_calls", None) else "no_tool"


def extract_reviewer_verdict(content):
    if isinstance(content, str):
        text = content.strip()

    elif isinstance(content, list):
        text = " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
        ).strip()

    else:
        raise ValueError(
            f"Unsupported reviewer response type: {type(content).__name__}"
        )

    verdict = text.lower().strip()

    if verdict not in {"approved", "revise"}:
        raise ValueError(
            f"Invalid reviewer verdict: {text[:200]}"
        )

    return verdict
