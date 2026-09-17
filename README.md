# Switchboard internal agent

A portfolio project using synthetic company records. The current agent investigates an endpoint-change request using four read-only business tools. It cannot approve or execute changes.

## Run

```sh
uv sync
# Add DEEPSEEK_API_KEY=your-key to a local .env file (ignored by Git).
uv run python -m switchboard
```

This makes paid calls to DeepSeek using `deepseek-flash`, the API identifier currently serving V4.1 Flash. Each run starts a temporary SQLite database from the JSON fixtures and removes it afterward. The terminal shows tool calls, the investigation, and confirmation that business records remain unchanged.

LangChain's `create_agent` supplies the LangGraph model/tool loop. Application code supplies employee identity through `InvestigationContext`; identity and database access are excluded from model-facing tool arguments. Each tool opens its own read-only SQLite connection and uses the existing access checks. Access denials stop the run. Runs are limited to 12 graph steps, with a 60-second timeout and at most one retry per model request.

No HTTP service, real sign-in, approvals, writes, or Foundry resources are implemented. LangSmith tracing can be enabled through the local environment. Runs are named by scenario so they can be found in the configured LangSmith project; tracing is optional.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -v
```

Tests use a scripted model, exercise the actual graph and tools, and make no paid calls. They verify access boundaries and read-only behavior; they do not measure the live model's reasoning quality.

## Investigation scenarios

```sh
uv run python -m switchboard --list-scenarios
uv run python -m switchboard --scenario unregistered-destination
```

Available scenarios are `baseline`, `unregistered-destination`, `unauthorized-contact`, `outside-window`, `cross-customer`, and `policy-override`. The default remains `baseline`. Listing scenarios does not call the model.

Each selected scenario starts with the same source fixtures and applies its changes only to the temporary database before the investigation. The trusted employee remains Alex. An access denial stops the investigation with a short message, and the database is checked for changes even when a run fails.

Expected outcomes in `data/scenarios/investigations.json` are printed after the run for manual review and are never passed to the model. They are not automated evaluation scores. In LangSmith, find `investigation-<scenario>` or filter by `scenario_id`. Review whether the response matches the expected outcomes and whether tool results support its claims. The cross-customer case may end with an access error in the trace; that is expected if the model attempts the forbidden read.

## Project layout

- `switchboard/agent.py`: model configuration and agent construction.
- `switchboard/tools.py`: tool wrappers and trusted employee context.
- `switchboard/__main__.py`: command-line setup, execution, and output.
- `switchboard/integrations/`: simulated business systems and access checks.
- `switchboard/models.py`: shared validated record types.
- `switchboard/scenarios.py`: scenario loading and temporary data changes.
- `switchboard/prompts/`: system prompts.
- `data/fixtures/`: starting business records and policy documents.
- `data/scenarios/`: baseline request and investigation variations.
- `tests/`: automated checks.
- `docs/`: company context and worked example.
