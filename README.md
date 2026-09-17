# Switchboard internal agent

A portfolio project using synthetic company records. The current agent investigates an endpoint-change request using four read-only business tools. It cannot approve or execute changes.

## Run

```sh
uv sync
# Add DEEPSEEK_API_KEY=your-key to a local .env file (ignored by Git).
uv run python -m switchboard
```

This makes paid calls to DeepSeek using `deepseek-flash`, the API identifier currently serving V4.1 Flash. Each run starts a temporary SQLite database from the JSON fixtures and removes it afterward. The terminal shows tool calls, the investigation, and confirmation that business records remain unchanged.

LangChain's `create_agent` supplies the LangGraph model/tool loop. Application code supplies employee identity through `InvestigationContext`; identity and database access are excluded from model-facing tool arguments. Each tool opens its own read-only SQLite connection and uses the existing access checks. Expected permission failures become error tool results that the agent can explain; missing and inaccessible records remain indistinguishable. Unexpected failures still stop the run. Each investigation is limited to 12 graph steps, with a 60-second timeout and at most one retry per model request.

No HTTP service, real sign-in, approvals, configuration writes, or Foundry resources are implemented. LangSmith tracing can be enabled through the local environment. Runs are named by scenario so they can be found in the configured LangSmith project; tracing is optional.

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

Each selected scenario starts with the same source fixtures and applies its changes only to the temporary database before the investigation. The trusted employee remains Alex. An unavailable record produces a safe tool error and the agent explains the incomplete investigation. The database is checked for changes even when a run fails.

Expected outcomes in `data/scenarios/investigations.json` are printed after the run for manual review and are never passed to the model. They are not automated evaluation scores. In LangSmith, find `investigation-<scenario>` or filter by `scenario_id`. Review whether the response matches the expected outcomes and whether tool results support its claims. The cross-customer case should finish with an explanation of the unavailable record. Its tool result retains error status; a completed response does not mean access succeeded.

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

## Structured investigation result

The investigator uses DeepSeek with thinking enabled and the four read-only tools, then returns JSON matching the `InvestigationResult` schema. The application validates that JSON with Pydantic before accepting or displaying it. Invalid JSON or inconsistent fields stop the run with a clear error; there is no formatting stage or automatic correction retry.

Valid structure does not establish factual correctness or authorize a change. Application code independently validates candidates before saving proposals. A closed execution window or unverified independent approval does not by itself block preparing a proposal candidate; these remain execution requirements.

## Policy faithfulness

```sh
uv run python -m switchboard --scenario baseline --evaluate-policy
uv run python -m switchboard.policy_evaluation
```

The first command adds a separate DeepSeek review of the investigation's policy claims against the source policies. The second calibrates that reviewer against four known examples, including the observed blanket rollback prohibition. Both make paid model calls; ordinary investigations skip the review. With tracing enabled, review calls appear as `policy-faithfulness-review`.

The reviewer reports specific claims, source excerpts, and explanations. Invalid JSON or invented source excerpts fail the evaluation rather than counting as a pass. An empty issues list means the model found no distortion, not that correctness is proven. The same model family produces and reviews the output, so manual review remains important. This checks policy meaning only; it does not authorize actions or establish customer facts. Calibration expectations are withheld from the judge.

## Proposal validation and storage

`Proposal` describes the exact endpoint change to submit for approval, including the employee and customer contact IDs, ticket, customer, integration, environment, observed endpoint and configuration version, proposed endpoint, and creation time. Its initial status is `pending_approval`. IDs and timestamps are supplied by application code; model validation checks shape, not business authorization.

`initialize_proposal_database()` in `switchboard/integrations/database.py` creates `data/local/proposals.db` without clearing existing proposals. This local directory is ignored by Git. Proposal storage is separate from the temporary scenario databases, so fixture resets cannot delete saved proposals. References to business records are checked by application code before saving; they are not cross-database foreign keys.

`validate_proposal()` in `switchboard/proposals.py` reads access-controlled records, checks the customer relationship and authorized contact, and compares the proposed endpoint with the structured ticket request and registered destinations for that environment. It builds the proposal from those records and the employee session. A request for the already-configured endpoint is rejected.

The CLI calls `save_proposal()` in `switchboard/integrations/change_management.py` for validated candidates and prints the saved ID. Saving rechecks the employee and configuration snapshot and returns the existing proposal for an identical retry. Blocked or rejected candidates save nothing. The agent still has only read-only tools. Configuration, approval, and execution are unchanged.

These are synthetic scenario proposals: identical snapshots across scenarios share a proposal. Creation timestamps use the actual application clock; the investigation uses the scenario clock. Proposal retrieval and the approval workflow are not implemented yet. The optional policy review runs after saving and is diagnostic, not a gate for saving.
