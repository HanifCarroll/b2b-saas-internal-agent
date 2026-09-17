# Switchboard internal agent

A portfolio project using synthetic company records. The current agent investigates an endpoint-change request using four read-only business tools. It cannot approve or execute changes.

## Run

```sh
uv sync
# Add DEEPSEEK_API_KEY=your-key to a local .env file (ignored by Git).
uv run python agent.py
```

This makes paid calls to DeepSeek using `deepseek-flash`, the API identifier currently serving V4.1 Flash. Each run starts a temporary SQLite database from the JSON fixtures and removes it afterward. The terminal shows tool calls, the investigation, and confirmation that business records remain unchanged.

LangChain's `create_agent` supplies the LangGraph model/tool loop. Application code supplies employee identity through `InvestigationContext`; identity and database access are excluded from model-facing tool arguments. Each tool opens its own read-only SQLite connection and uses the existing access checks. Access denials stop the run. Runs are limited to 12 graph steps, with a 60-second timeout and at most one retry per model request.

No HTTP service, real sign-in, approvals, writes, or Foundry resources are implemented. LangSmith tracing is not configured; no LangSmith key is needed to run this version.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -v
```

Tests use a scripted model, exercise the actual graph and tools, and make no paid calls. They verify access boundaries and read-only behavior; they do not measure the live model's reasoning quality.
