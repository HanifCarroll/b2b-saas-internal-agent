# Switchboard internal agent

Switchboard is a synthetic B2B SaaS change-management demo. An AI agent investigates endpoint-change tickets with access-controlled tools, prepares a proposal, and leaves approval and execution to deterministic application code.

## Architecture

- `frontend/`: Next.js dashboard.
- `backend/switchboard/`: FastAPI, CLI, LangGraph workflow, and domain logic.
- `backend/tests/`: deterministic backend and API tests.
- `backend/evals/`: explicitly invoked live-model evaluations recorded in LangSmith.
- `cloudflare/`: Worker, private D1 operation bridge, schema migrations, and bridge tests.
- `backend/data/`: versioned synthetic fixtures, scenarios, and evaluation expectations.

The hosted application runs Next.js and FastAPI in one Cloudflare Container. The Worker routes browser traffic to the appropriate container port and binds a private outbound service at `switchboard.storage`. The container calls that service with named domain operations; it cannot submit generic SQL. D1 is the sole durable application database.

Every durable row belongs to a workspace. The public demo assigns each visitor an isolated workspace through an HttpOnly cookie and lets them select fictional personas. Authorization is rechecked at proposal review, approval, and execution. Approval and execution use D1 batches so related writes either persist together or do not persist. Unique constraints and stored receipts make proposal creation, approval, and execution safe to retry.

The Worker keeps one `basic` Container instance and allows it to sleep after two minutes of inactivity. D1 records remain available across container sleeps and restarts.

## Local development

Install the three dependency sets:

```sh
(cd backend && uv sync)
(cd frontend && npm ci)
(cd cloudflare && npm ci)
```

Put `DEEPSEEK_API_KEY` and optional LangSmith settings in `backend/.env`. To use Microsoft sign-in locally, copy the public browser values from `frontend/entra.example.env` to `frontend/.env.local` and the server values from `backend/entra.example.env` to `backend/.env`.

Start the local D1 bridge, API, and web application from the repository root:

```sh
./scripts/dev
```

Open <http://localhost:3000>. Local development uses hybrid authentication: the same build supports the isolated demo and Microsoft sign-in. Wrangler stores the local D1 database under the ignored `cloudflare/.wrangler/` directory.

The CLI uses the same storage bridge. Run it while `./scripts/dev` is active:

```sh
cd backend
uv run python -m switchboard --reset-demo baseline --confirm-reset
uv run python -m switchboard
```

Investigations make paid DeepSeek calls. Listing cases, resetting data, retrieval, approval, and execution do not call a model. The graph finishes after saving a proposal; review, approval, and execution are separate application operations.

## Demo behavior

The public hosted build uses anonymous demo mode. Each visitor receives an isolated workspace and can prepare one of four deterministic cases: a valid request, an unsafe destination, a proposal awaiting approval, or an approved proposal ready to execute. Preparing a case resets only that workspace and selects the recommended fictional persona.

The agent has read-only, access-controlled tools for tickets, customers, integrations, and policies. It returns a structured investigation result that Pydantic validates. Application code then validates the current business records before saving a proposal. The model cannot approve or execute a change.

An independent assigned technical lead must approve a production proposal. Execution rechecks the actor, proposal snapshot, approval, change window, and current configuration. The configuration update and execution receipt are one atomic D1 batch. A repeated request returns the existing receipt without applying the change twice. Delivery verification remains a separate unimplemented step.

Synthetic scenarios live under `backend/data/scenarios/`. Their withheld evaluation expectations live under `backend/data/evaluations/` and are never passed to the agent.

## Checks

Run all deterministic checks from the repository root:

```sh
(cd backend && uv run ruff check .)
(cd backend && uv run ruff format --check .)
(cd backend && uv run pyright)
(cd backend && uv run pytest -v)

(cd frontend && npm test)
(cd frontend && npm run lint)
(cd frontend && npm run format:check)
(cd frontend && npm run build)

(cd cloudflare && npm run check)
(cd cloudflare && npm run test:storage)
git diff --check
```

`test:storage` runs the real Worker-to-D1 bridge against a temporary local D1 database. It checks workspace isolation, rejection of unknown operations, atomic execution, and an idempotent retry after restarting the Worker. Ordinary tests make no model calls.

Live-model evaluations are separate:

```sh
cd backend
uv run pytest evals/test_investigations.py -v
```

## Deploy to Cloudflare

The Cloudflare account needs Workers, Containers, and D1 access. Wrangler must be authenticated before deployment.

Create the production database once and copy its ID into `cloudflare/wrangler.jsonc`:

```sh
cd cloudflare
npx wrangler d1 create switchboard
npx wrangler d1 migrations apply switchboard --remote
```

Store the model key as a Worker secret. Do not put it in Wrangler configuration or Git:

```sh
npx wrangler secret put DEEPSEEK_API_KEY
```

Deploy the Worker and Container:

```sh
npm run deploy
```

The production configuration compiles the browser and runs the API in `demo` mode. Entra settings are only needed if a hosted authenticated mode is deliberately enabled later. The container image targets Linux AMD64 and exposes Next.js on port 3000 and FastAPI on port 8000.

After deployment, verify the Worker URL, prepare two browser sessions and confirm they receive different workspace data, run a real investigation, and exercise an approved execution twice. The second execution must return the existing receipt rather than update configuration again.

### Automatic production deployment

`.github/workflows/deploy.yml` runs the full deterministic check suite on every push to `main`. If every check passes, it applies pending remote D1 migrations and deploys the Worker and Container. Production deployments are serialized so two pushes cannot update D1 or Cloudflare at the same time.

Configure these GitHub Actions repository secrets before pushing the workflow:

- `CLOUDFLARE_ACCOUNT_ID`: the account ID from `cloudflare/wrangler.jsonc`.
- `CLOUDFLARE_API_TOKEN`: a Cloudflare API token created with the **Edit Cloudflare Workers** template.

The existing `DEEPSEEK_API_KEY` remains a Worker secret in Cloudflare. It is not copied into GitHub.

## Authentication

The API supports `entra`, `demo`, and `hybrid` modes. `entra` validates tenant-specific RS256 access tokens, audience, `access_as_user` scope, authorized client, timestamps, and the mapped employee Object ID. `demo` uses an isolated fictional workspace. `hybrid` selects the mode per request based on the presence of a bearer token.

Hosted portfolio deployment uses `demo`. Local development uses `hybrid`. Supplying both a bearer token and `X-Demo-Persona-Id` is rejected, authenticated users cannot call demo setup endpoints, and all business authorization continues to use the employee and customer assignments stored in D1.
