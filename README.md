# Switchboard internal agent

A portfolio project using synthetic company records. The current agent investigates an endpoint-change request using four read-only business tools. It cannot approve or execute changes.

## Layout

- `frontend/`: Next.js application and its Node dependencies.
- `backend/switchboard/`: Python package shared by the API, CLI, and agent workflow.
- `backend/tests/`: Python tests.
- `backend/evals/`: explicitly invoked live-model evals tracked in LangSmith.
- `backend/data/`: synthetic fixtures, scenarios, and ignored local databases.
- `backend/pyproject.toml` and `backend/uv.lock`: Python dependencies.
- `docs/`: project documentation.

## Run

Run the following Python commands from `backend/`. Store local model and tracing credentials in `backend/.env` (ignored by Git).

```sh
cd backend
uv sync
# Add DEEPSEEK_API_KEY=your-key to a local .env file (ignored by Git).
uv run python -m switchboard --reset-demo baseline --confirm-reset
uv run python -m switchboard
```

This makes paid calls to DeepSeek using `deepseek-flash`, the API identifier currently serving V4.1 Flash. All runs use one persistent business database at `backend/data/local/switchboard.db`. Separate investigation histories live under `backend/data/local/workflows/<workflow-id>/`. Candidate runs finish after saving a proposal. The terminal shows tool calls, the investigation, and the confirmed proposal storage outcome.

LangChain's `create_agent` supplies the LangGraph model/tool loop. Application code supplies employee identity through `InvestigationContext`; identity and database access are excluded from model-facing tool arguments. Each tool opens its own read-only SQLite connection and uses the existing access checks. Expected permission failures become error tool results that the agent can explain; missing and inaccessible records remain indistinguishable. Unexpected failures still stop the run. Each investigation is limited to 12 graph steps, with a 60-second timeout and at most one retry per model request.

The local FastAPI service supports investigation, retrieval, approvals, and explicit configuration execution. Backend Entra token validation and browser sign-in have been verified locally with the configured tenant. Delivery verification and Foundry resources are not implemented. LangSmith tracing can be enabled through the local environment. Runs are named by scenario so they can be found in the configured LangSmith project; tracing is optional.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -v
```

Tests use a scripted model, exercise the actual graph and tools, and make no paid calls. They verify access boundaries and read-only behavior; they do not measure the live model's reasoning quality.

Live-model evals are separate and make paid model calls:

```sh
uv run pytest evals -v
```

## Synthetic scenario setup

```sh
uv run python -m switchboard --list-scenarios
uv run python -m switchboard --reset-demo unregistered-destination --confirm-reset
uv run python -m switchboard
```

Available scenarios are `baseline`, `unregistered-destination`, `unauthorized-contact`, `outside-window`, `cross-customer`, and `policy-override`. Investigations use the currently initialized scenario. Listing or resetting scenarios does not call the model.

Reset explicitly restores the selected scenario and clears all saved investigations, proposals, approvals, and execution receipts. CLI reset requires `--confirm-reset`. Starting an investigation never creates or resets business records. The web demo prepares its own deterministic cases instead of exposing the CLI scenario controls.

Reset builds and validates replacement records before clearing history and replacing the database. If history deletion fails, the old business database remains intact, although some history may already have been removed. A POSIX file lock excludes reset while CLI/API operations are running and rejects new operations during reset. This is a local macOS/Linux demo, not a distributed job system. The CLI investigator remains Alex; the UI can select a simulated investigator. Tools enforce read-only database connections.

Scenario files describe only the synthetic record changes used by the local demo and eval setup. Evaluation expectations live separately under `backend/data/evaluations/` and are never passed to the agent.

## Investigation evals

```sh
uv run pytest evals/test_investigations.py -v
```

The six pytest cases run the real model against isolated temporary databases. Each case records its input, validated output, expected outcome, qualitative review criteria, and deterministic outcome score in LangSmith. The expected outcome is asserted locally. The qualitative criteria remain visible reference material for reviewing the experiment; they are not reduced to brittle string assertions.

These evals are excluded from ordinary `uv run pytest -v` runs so normal development checks remain fast, deterministic, and free of model charges. Use `-k CASE_NAME` to run one case while changing a prompt or model.

## Project layout

- `backend/switchboard/agent.py`: model configuration and agent construction.
- `backend/switchboard/tools.py`: tool wrappers and trusted employee context.
- `backend/switchboard/__main__.py`: command-line setup, execution, and output.
- `backend/switchboard/integrations/`: simulated business systems and access checks.
- `backend/switchboard/models.py`: shared validated record types.
- `backend/switchboard/scenarios.py`: scenario definitions and transactional fixture setup.
- `backend/switchboard/evaluation_cases.py`: validated reference expectations for live-model evals.
- `backend/switchboard/demo.py`: explicit reset, active scenario, and cross-process reset exclusion.
- `backend/switchboard/prompts/`: system prompts.
- `backend/data/fixtures/`: starting business records and policy documents.
- `backend/data/scenarios/`: baseline request and investigation variations.
- `backend/data/evaluations/`: withheld outcomes and qualitative review criteria.
- `backend/evals/`: pytest and LangSmith live-model eval runners.
- `backend/tests/`: automated checks.
- `docs/`: company context and worked example.

## Structured investigation result

The investigator uses DeepSeek with thinking enabled and the four read-only tools, then returns JSON matching the `InvestigationResult` schema. The application validates that JSON with Pydantic before accepting or displaying it. Invalid JSON or inconsistent fields stop the run with a clear error; there is no formatting stage or automatic correction retry.

Valid structure does not establish factual correctness or authorize a change. Application code independently validates candidates before saving proposals. A closed execution window or unverified independent approval does not by itself block preparing a proposal candidate; these remain execution requirements.

## Policy faithfulness

```sh
uv run python -m switchboard --scenario baseline --evaluate-policy
uv run pytest evals/test_policy_faithfulness.py -v
```

The first command adds a separate DeepSeek review of one investigation's policy claims against the source policies. The pytest eval calibrates that reviewer against four known examples, including the observed blanket rollback prohibition, and records the experiment in LangSmith. Both make paid model calls; ordinary investigations skip the review. With tracing enabled, review calls appear as `policy-faithfulness-review`.

The reviewer reports specific claims, source excerpts, and explanations. Invalid JSON or invented source excerpts fail the evaluation rather than counting as a pass. An empty issues list means the model found no distortion, not that correctness is proven. The same model family produces and reviews the output, so manual review remains important. This checks policy meaning only; it does not authorize actions or establish customer facts. Calibration expectations are withheld from the judge.

## Proposal validation and storage

`Proposal` describes the exact endpoint change to submit for approval, including the employee and customer contact IDs, ticket, customer, integration, environment, observed endpoint and configuration version, proposed endpoint, and creation time. Its initial status is `pending_approval`. IDs and timestamps are supplied by application code; model validation checks shape, not business authorization.

Business records, proposals, approvals, and execution receipts share `backend/data/local/switchboard.db`. Initialization creates all tables together. Investigation histories contain only manifests, results, and optional policy evaluations; they do not own databases. Tests use temporary databases. There is no migration path for old demo records.

`validate_proposal()` in `backend/switchboard/proposals.py` reads access-controlled records, checks the customer relationship and authorized contact, and compares the proposed endpoint with the structured ticket request and registered destinations for that environment. It builds the proposal from those records and the employee session. A request for the already-configured endpoint is rejected.

The CLI calls `save_proposal()` in `backend/switchboard/integrations/change_management.py` for validated candidates and prints the saved ID. Saving rechecks the employee and configuration snapshot and returns the existing proposal for an identical retry. Blocked or rejected candidates save nothing. The agent still has only read-only tools. Configuration, approval, and execution are unchanged.

Identical requests against unchanged shared records reuse the existing proposal. Creation timestamps use the actual application clock; the investigation uses the scenario clock. Access-controlled proposal retrieval and explicit approval and execution are implemented. The optional policy review runs after saving and is diagnostic, not a gate for saving.

## Proposal review scenarios

`backend/data/scenarios/reviews.json` describes access to an existing Acme proposal saved by Alex. Each test creates that proposal in temporary storage, binds a separate reviewer session, and checks retrieval. Reviewer identity is supplied by test setup, not an LLM. The support scenario changes Priya's role only in its temporary database.

```sh
uv run pytest tests/test_review_scenarios.py -v
```

The eight cases cover assigned roles, another customer's employee, inactive or unassigned reviewers, missing proposals, and configuration changes after saving. They verify that reading neither changes records nor approves a proposal. These are executable retrieval scenarios, not CLI investigation scenarios; they make no paid model calls. CLI review tests also check access after process exit. Approval decisions are available through the local web UI and `approve_proposal`; the CLI review command only displays proposals.


## Review a saved proposal

Investigations finish after saving. Review is a separate application operation using the proposal ID printed by the investigation:

```sh
uv run python -m switchboard --review PROPOSAL_ID --run WORKFLOW_ID --employee emp-priya
```

The proposal ID identifies the business record. `--run` locates the investigation history and its shared database; it does not select an isolated business world or resume a graph. Review checks current shared employee permissions and customer assignments on every read. It requires no model, API key, or graph checkpoint.

`--employee` simulates a trusted application session for this local demo; it is not authentication. A deployed application must bind identity through sign-in. Viewing does not approve or execute a proposal. Approval decisions are available through the local web UI and `approve_proposal`; the CLI review command only displays proposals.

The candidate route is now `investigate_request → prepare_proposal → END`. The graph context always requires an agent. There is no review node, interrupt, or `--resume` command. Old isolated demo records are discarded; no compatibility layer is provided.

```sh
uv run pytest tests/test_proposal_review_cli.py tests/test_review_scenarios.py -v
```

## Local investigation and approval UI

The Next.js/shadcn UI uses FastAPI and the same investigation graph and business functions as the CLI. After installing the backend and frontend dependencies, start both services from the repository root:

```sh
(cd backend && uv sync)
(cd frontend && npm ci)
./scripts/dev
```

Open http://localhost:3000. The local hybrid screen lets you enter the demo or sign in with the configured Microsoft account. The choice lasts for the current browser tab. Switching to the demo does not sign out the Microsoft account, and identity changes clear the browser's business-data cache.

The demo requires no Microsoft account. Each visitor receives an isolated workspace that expires after 24 hours. Use **Try a demo case** to prepare one of four deterministic starting points: a valid request, an unsafe destination, a proposal awaiting approval, or an approved proposal ready to execute. Preparing a case replaces only that visitor's demo history and switches to the recommended fictional persona. You can also change personas explicitly to demonstrate role and customer-access boundaries.

Open an accessible ticket and start the investigation from its detail page. The screen shows a pending state during the model call, followed by findings, evidence IDs, tool calls, blockers, and the confirmed proposal storage outcome. A saved proposal opens automatically for review; no run or proposal IDs need to be copied. Change to an independent assigned technical lead to approve explicitly. The current stored approval appears separately from the investigation report.

Saved investigations can be reopened from the selected ticket's history after refreshing the browser or restarting the server. History is limited to the original requester and ticket and rechecks their role and customer access. Evaluation expectations stay outside the application interface.

The optional **Evaluate policy claims** button makes a separate model call and stores its judgment. It does not authorize a proposal. Investigation and policy evaluation use the existing model credentials in `backend/.env`; retrieval and approval do not call a model. The pending indicator does not claim token-by-token or node-by-node progress. Completed results survive browser refresh; there is no background job queue or resumable live progress in this local slice.

Demo mode is designed for synthetic public demonstration. An HttpOnly cookie selects the visitor's isolated storage; `X-Demo-Persona-Id` selects an explicitly fictional persona within it. Do not connect demo mode to real business data. The UI separates approval from a confirmed Execute change action. Execution uses actual server UTC time and rechecks the production change window. Refresh reads the saved execution receipt and reports configuration updated with delivery not yet verified. Delivery verification remains unimplemented. Proposals include a required manual-intervention recovery plan. Next.js proxies `/api` to FastAPI; API documentation is at http://127.0.0.1:8000/docs. The current storage design assumes one backend host with persistent local disk.

Checks: `uv run pytest -v` in `backend/`, and `npm run lint && npm run format:check && npm run build` in `frontend/`.


## Entra authentication

The API supports three explicit modes. `entra` requires Microsoft authentication, `demo` provides anonymous isolated fictional workspaces, and `hybrid` chooses per request based on the presence of a bearer token. The browser supports the same values through `NEXT_PUBLIC_AUTH_MODE`. Use `hybrid` for local development and `demo` for the hosted portfolio. Never expose demo mode against real business data. CLI commands remain trusted local operations, not Entra-authenticated HTTP requests.

For Entra mode, set the variables shown in `backend/entra.example.env` in the server environment or merge them into your existing ignored `backend/.env`. Do not overwrite existing model credentials. The example maps Hanif's tenant user Object ID to `emp-alex`; these IDs are public identifiers, not credentials. The mapping is scoped to the configured tenant. Restart the server after changing configuration.

In **Switchboard API → Manifest**, set `api.requestedAccessTokenVersion` to `2` and save. The API accepts only RS256-signed v2 access tokens issued by the configured tenant, for the API client ID, with `access_as_user` scope and the configured Web client as `azp`. It verifies expiry and not-before timestamps, then maps `oid` to an employee. Existing database role and customer-access checks still apply. Unmapped identities fail closed. Signing keys are fetched from Microsoft's fixed tenant endpoint and cached by PyJWT; a key-service connection failure returns 503 without allowing access.

All API routes require a token in Entra mode. Hybrid mode sends bearer-token requests to the shared authenticated database and token-free requests to an isolated demo workspace. Supplying both a bearer token and `X-Demo-Persona-Id` is rejected, and authenticated users cannot call demo setup endpoints. The browser defaults to Entra mode. Restart both services after changing authentication environment variables.

Tests use locally signed RSA tokens, without contacting Microsoft or an LLM. Live Microsoft sign-in has also been verified manually in the local application.

The browser authentication module is in `frontend/lib/auth.ts`. Copy the public settings from `frontend/entra.example.env` into `frontend/.env.local` and restart Next.js. The authentication gate requires Microsoft identity and a successful `/api/me` response before displaying the workspace. Each signed-in workspace has a separate query cache; sign-out and account switching unmount it. Entra mode hides demo cases and fictional persona selection. It uses redirect sign-in at the application's origin (register `http://localhost:3000` as a SPA redirect URI for local use), session-scoped token storage, and account-specific token acquisition. Silent acquisition uses cached access or refresh tokens; when interactive authentication is required, the error is returned to the caller so the UI can offer sign-in again. Run frontend tests with `npm test` (Node 24; Microsoft SDK calls are mocked).
