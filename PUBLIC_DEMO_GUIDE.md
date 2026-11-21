# Public demo-first interface — experimental

## What changed

- **Demo Mode** is the first tab and displays sanitized prerecorded results immediately. No Gemini calls on page load.
- **Live Agent** runs the real workflow with a maximum 500-character prompt, action budget up to 5, 20 total live runs/day, 2 runs/day per visitor, and one concurrent execution per Python process.
- Limits are checked **server-side** in `public_limits.py`, before invoking Gemini. Rejected requests do not run the agent. A failed or interrupted request still consumes its reserved run slot.
- `public_demo.py` contains only sanitized sample records and does not query live telemetry.
- Original analytics tabs and tracing remain in the source, but the live SQLite analytics tabs are **hidden by default** for public safety. Set `ENABLE_PRIVATE_ANALYTICS=1` for trusted local testing only.

## Limitations and safety

- This is a **portfolio prototype**, not hardened public infrastructure.
- SQLite counters **reset if Render's ephemeral filesystem is replaced**. They are not reliable across multiple replicas. Use a durable transactional store (e.g. managed Postgres) and platform-level abuse controls before broad public exposure.
- Per-visitor identification uses the address exposed by Gradio's request object; reverse proxies, NAT, shared IPs, and restarts can make per-visitor limits inaccurate. It is not an identity system or robust abuse prevention.
- These controls limit *runs*, not exact Gemini requests or tokens. Each run can make several LLM/embedding calls; Google project quotas still apply. For stricter protection add a per-run LLM-call/token budget and platform-level rate limits.
- Live SQLite analytics tabs can expose visitors' prompts and event details. They are disabled by default and must **not** be enabled on the public deployment without authorization and privacy controls. Live runs still display their own results to the initiating browser session.
- `AGENT_TEST_FAIL_TOOL` must be unset in public deployment. Do not commit API keys or `.env` files.
- Tool stubs do not send notifications or write files.

## Local test

Set `GEMINI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` in CMD, then run `python app.py`. Open http://127.0.0.1:7860. Verify Demo Mode is populated before running a task. In Live Agent, test a task, verify a trace, and check remaining quota. Test the third request from the same visitor to verify the per-visitor limit. Do not deploy until the public-data exposure noted above is addressed.

## Docker

Build from this folder: `docker build -t agent-governance:demo .`

Run with your existing CMD environment variables and port 7861 inside container:

`docker run --rm -p 7860:7861 -e GEMINI_API_KEY -e LANGFUSE_PUBLIC_KEY -e LANGFUSE_SECRET_KEY -e LANGFUSE_HOST -e PORT=7861 -e AGENT_TEST_FAIL_TOOL= --name agent-governance-demo agent-governance:demo`

## Configuration

- `PUBLIC_DAILY_RUNS` default `20`
- `PUBLIC_VISITOR_DAILY_RUNS` default `2`
- `PUBLIC_MAX_PROMPT_CHARS` default `500`
- `GOVERNANCE_DB_PATH` SQLite path (temporary on ephemeral hosts)
