# Public live quota setup

- Default: local SQLite counters (development only). Daily quotas are **not durable** across ephemeral container restarts.
- Public deployment: set `PUBLIC_DEPLOYMENT=1` and `QUOTA_DATABASE_URL` to a durable PostgreSQL connection string, such as one from a managed Postgres provider. Use a **separate least-privilege database** if possible. Never commit this URL.
- Set `PUBLIC_DAILY_RUNS=20`, `PUBLIC_VISITOR_DAILY_RUNS=2`, and `PUBLIC_MAX_PROMPT_CHARS=500` as desired.
- PostgreSQL transactions and an advisory lock enforce the global quota atomically across multiple app instances. If storage is unavailable, live execution is denied (fail closed), while Demo Mode stays available.
- The quota text refreshes on page load and after a live attempt. It is a snapshot; concurrent visitors may change it. Manual refresh is available.
- Visitors are grouped by the client address visible to Gradio. This is **best effort**, not identity or bot protection: shared IPs, proxies and NAT can combine visitors, and addresses can change. Test the client address behind your hosting proxy before relying on per-visitor fairness. Do not use an unvalidated forwarded header.
- Each accepted attempt consumes one run, including a failed run. This is an application run limit, not a guarantee of Google API cost or request limits. Per-run LLM/tool calls may vary.
- Concurrent execution is restricted to one per Python process; multi-replica deployments need a distributed concurrency mechanism.
- Keep `AGENT_TEST_FAIL_TOOL` unset in public deployments. Protect real tools if added later.
- The app's **execution/event SQLite database remains ephemeral** and is separate from the durable quota database. The public Demo Mode is static; private analytics remain disabled unless explicitly enabled.
- For public availability, also add provider-level budget alerts/quotas, monitoring and bot protection as appropriate.
