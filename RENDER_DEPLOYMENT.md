# Render deployment guide — hardened experimental build

This project is a portfolio prototype, not a security-audited production service. Test with a private preview before sharing the URL.

## 1. GitHub

Upload the source files in this ZIP to a NEW private GitHub repository or a branch. Do not upload `.env`, API keys, `governance.db`, or any `*.db` files. Confirm `.gitignore` and `.dockerignore` are retained. Use a private repository until public deployment is validated.

## 2. Durable PostgreSQL

Provision managed PostgreSQL (Render Postgres if available for your account/region, or another provider). Use a connection URL compatible with psycopg 3. Enable TLS according to the provider's instructions. The app creates `public_run_limits` on its first connection, so the DB role needs CREATE TABLE privilege in its schema (or precreate the table and use a restricted role). PostgreSQL advisory locks serialize quota reservations across processes. Do not put the DB URL in GitHub.

## 3. Render web service

Create a new Render **Web Service** connected to the repo. Select **Docker** runtime and the repository's Dockerfile. One instance only to start. If Render's selected instance sleeps or has ephemeral storage, the demo remains static, and the SQLite run history may disappear; quota counters persist in PostgreSQL.

Configure these environment variables in Render's environment settings:

| Name | Value |
|---|---|
| PUBLIC_DEPLOYMENT | `1` |
| QUOTA_DATABASE_URL | `postgresql://...` (secret) |
| QUOTA_HASH_SALT | random secret, at least 16 characters, kept stable across deploys |
| PUBLIC_DAILY_RUNS | `20` |
| PUBLIC_VISITOR_DAILY_RUNS | `2` |
| PUBLIC_MAX_PROMPT_CHARS | `500` |
| AGENT_RECURSION_LIMIT | `24` |
| GEMINI_API_KEY | your API key (secret) |
| LANGFUSE_PUBLIC_KEY | optional |
| LANGFUSE_SECRET_KEY | optional secret |
| LANGFUSE_HOST | correct Langfuse host for your region |
| ENABLE_PRIVATE_ANALYTICS | `0` |

`PORT` is supplied by Render. The app listens on `0.0.0.0` and uses that port. Never enable `AGENT_TEST_FAIL_TOOL` in public deployment. Use the host provider's secrets UI, not committed files.

## 4. Verification before publishing

- Open the Render URL in a private window: Demo Mode should show recorded sample data without an API call.
- Check the quota status: if DB is unavailable, it must say quota unavailable and block live execution.
- Make one live run with a non-sensitive prompt; check reviewer verdict, event rows and optional Langfuse trace.
- Refresh: visitor and global counters should decrement. Rejected attempts should not decrement global counter.
- Restart/redeploy and verify quota persists. Check in another browser/network to assess visitor address handling.
- Test direct Gradio endpoint invocation; `execute_agent` itself performs validation, acquires the semaphore, and reserves quota. UI-only restrictions are insufficient.
- Ensure private analytics remain disabled. Do not put customer secrets or personal data into prompts.
- Verify the hosting provider's actual proxy/client IP behavior: `request.client.host` is **not** a robust visitor identity. A reverse proxy may group all visitors under one address; VPNs and rotating IPs can bypass per-visitor fairness. Do not trust arbitrary forwarded headers. If the hosting proxy obscures client IP, keep Live Agent disabled until a trusted identity or edge rate-limiter is implemented.

## 5. Costs, logging, and limitations

- Each accepted live run may call Gemini multiple times and also call the embeddings API when the in-memory RAG collection initializes. The daily *run* limit does not cap actual provider requests or charges. The agent graph now has a recursion limit, shorter retry policy, and max output token configuration, but these are **not** billing guarantees. Configure Google-side quota/budget alerts and watch actual usage.
- Local SQLite stores execution data and is ephemeral on Render. The app's recorded Demo Mode is static and does not require DB persistence.
- Langfuse may store prompts/tool data; use only synthetic prompts in the public prototype. Logs of exceptions may include user data. Treat logs as sensitive.
- A local semaphore restricts execution per Python process only. Start with one process/instance; scale-out requires distributed concurrency controls.
- Keep `QUOTA_HASH_SALT` constant. Rotating it resets the apparent visitor identity and changes visitor quota accounting, although global counts remain.
- If public traffic is untrusted, consider requiring an access code or disabling Live Agent after demonstrations. A daily quota alone is not abuse protection.
