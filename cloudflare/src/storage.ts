export interface StorageEnvironment {
  DB: D1Database;
}

type JsonObject = Record<string, unknown>;

class StorageRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const RECORD_OPERATIONS = {
  "customer.get": "customers",
  "integration.get": "integrations",
  "ticket.get": "tickets",
} as const;

const PROPOSAL_COLUMNS = [
  "id",
  "proposed_by_employee_id",
  "ticket_id",
  "requester_contact_id",
  "customer_id",
  "integration_id",
  "environment",
  "current_endpoint",
  "proposed_endpoint",
  "expected_configuration_version",
  "recovery_plan",
  "created_at",
  "status",
] as const;

export async function handleStorageRequest(
  request: Request,
  env: StorageEnvironment,
): Promise<Response> {
  if (request.method !== "POST") {
    return jsonResponse({ error: "Storage operations require POST" }, 405);
  }

  try {
    const body = await readRequest(request);
    const data = await dispatchStorageOperation(body.operation, body.workspaceId, body.payload, env.DB);
    return jsonResponse({ data });
  } catch (error) {
    if (error instanceof StorageRequestError) {
      return jsonResponse({ error: error.message }, error.status);
    }

    console.error("Storage operation failed", error);
    return jsonResponse({ error: "Storage operation failed" }, 500);
  }
}

async function dispatchStorageOperation(
  operation: string,
  workspaceId: string,
  payload: JsonObject,
  db: D1Database,
): Promise<unknown> {
  const recordTable = RECORD_OPERATIONS[operation as keyof typeof RECORD_OPERATIONS];
  if (recordTable) {
    return getJsonRecord(db, recordTable, workspaceId, requiredString(payload, "id"));
  }

  switch (operation) {
    case "workspace.get":
      return getWorkspace(db, workspaceId);
    case "workspace.reset":
      return resetWorkspace(db, workspaceId, payload);
    case "workspace.delete":
      await db.prepare("DELETE FROM workspaces WHERE id = ?1").bind(workspaceId).run();
      return null;
    case "workspace.touch":
      await db
        .prepare("UPDATE workspaces SET updated_at = ?1 WHERE id = ?2")
        .bind(requiredString(payload, "updatedAt"), workspaceId)
        .run();
      return null;
    case "employee.get":
      return db
        .prepare(
          "SELECT id, name, active, role FROM employees WHERE workspace_id = ?1 AND id = ?2",
        )
        .bind(workspaceId, requiredString(payload, "id"))
        .first();
    case "employee.name": {
      const employee = await db
        .prepare("SELECT name FROM employees WHERE workspace_id = ?1 AND id = ?2")
        .bind(workspaceId, requiredString(payload, "id"))
        .first<{ name: string }>();
      return employee?.name ?? null;
    }
    case "employee.list": {
      const result = await db
        .prepare(
          "SELECT id, name, role FROM employees WHERE workspace_id = ?1 AND active = 1 ORDER BY id",
        )
        .bind(workspaceId)
        .all();
      return result.results;
    }
    case "employee.assignments": {
      const result = await db
        .prepare(
          "SELECT customer_id FROM assignments WHERE workspace_id = ?1 AND employee_id = ?2 ORDER BY customer_id",
        )
        .bind(workspaceId, requiredString(payload, "employeeId"))
        .all<{ customer_id: string }>();
      return result.results.map((row) => row.customer_id);
    }
    case "ticket.list":
      return listJsonRecords(db, "tickets", workspaceId);
    case "policy.list": {
      const result = await db
        .prepare("SELECT id, content FROM policies WHERE workspace_id = ?1 ORDER BY id")
        .bind(workspaceId)
        .all();
      return result.results.map(stripWorkspaceId);
    }
    case "proposal.get":
      return getProposal(db, workspaceId, requiredString(payload, "id"));
    case "proposal.list": {
      const result = await db
        .prepare(
          `SELECT proposal.*
             FROM proposals AS proposal
             LEFT JOIN approvals AS approval
               ON approval.workspace_id = proposal.workspace_id
              AND approval.proposal_id = proposal.id
             LEFT JOIN executions AS execution
               ON execution.workspace_id = proposal.workspace_id
              AND execution.proposal_id = proposal.id
            WHERE proposal.workspace_id = ?1
              AND approval.id IS NULL
              AND execution.id IS NULL
            ORDER BY proposal.created_at DESC`,
        )
        .bind(workspaceId)
        .all();
      return result.results.map(stripWorkspaceId);
    }
    case "proposal.save":
      return saveProposal(db, workspaceId, requiredObject(payload, "proposal"));
    case "approval.get":
      return getReceipt(db, "approvals", workspaceId, requiredString(payload, "proposalId"));
    case "approval.save":
      return saveApproval(db, workspaceId, requiredObject(payload, "approval"));
    case "execution.get":
      return getReceipt(db, "executions", workspaceId, requiredString(payload, "proposalId"));
    case "execution.apply":
      return applyExecution(db, workspaceId, payload);
    case "verification.get":
      return getDeliveryVerification(
        db,
        workspaceId,
        requiredString(payload, "executionId"),
      );
    case "verification.record":
      return recordDeliveryVerification(db, workspaceId, payload);
    case "run.get":
      return getRun(db, workspaceId, requiredString(payload, "id"));
    case "run.list":
      return listRuns(db, workspaceId, requiredString(payload, "ticketId"));
    case "run.save":
      return saveRun(db, workspaceId, requiredObject(payload, "run"));
    case "run.findProposal":
      return findProposalRun(db, workspaceId, requiredString(payload, "proposalId"));
    case "run.savePolicyReview":
      return savePolicyReview(db, workspaceId, payload);
    default:
      throw new StorageRequestError("Unknown storage operation", 404);
  }
}

async function getWorkspace(db: D1Database, workspaceId: string): Promise<unknown> {
  const row = await db
    .prepare(
      "SELECT identity_mode, scenario_id, inputs_json, updated_at FROM workspaces WHERE id = ?1",
    )
    .bind(workspaceId)
    .first<{ identity_mode: string; scenario_id: string; inputs_json: string; updated_at: string }>();
  if (!row) return null;
  return {
    identityMode: row.identity_mode,
    scenarioId: row.scenario_id,
    inputs: JSON.parse(row.inputs_json),
    updatedAt: row.updated_at,
  };
}

async function resetWorkspace(
  db: D1Database,
  workspaceId: string,
  payload: JsonObject,
): Promise<null> {
  const records = requiredObject(payload, "records");
  const statements: D1PreparedStatement[] = [
    db.prepare("DELETE FROM workspaces WHERE id = ?1").bind(workspaceId),
    db
      .prepare(
        "INSERT INTO workspaces (id, identity_mode, scenario_id, inputs_json, updated_at) VALUES (?1, ?2, ?3, ?4, ?5)",
      )
      .bind(
        workspaceId,
        requiredString(payload, "identityMode"),
        requiredString(payload, "scenarioId"),
        JSON.stringify(requiredObject(payload, "inputs")),
        requiredString(payload, "updatedAt"),
      ),
  ];

  for (const employee of requiredObjectArray(records, "employees")) {
    statements.push(
      db
        .prepare(
          "INSERT INTO employees (workspace_id, id, name, active, role) VALUES (?1, ?2, ?3, ?4, ?5)",
        )
        .bind(
          workspaceId,
          requiredString(employee, "id"),
          requiredString(employee, "name"),
          employee.active === true ? 1 : 0,
          requiredString(employee, "role"),
        ),
    );
    for (const customerId of requiredStringArray(employee, "customer_ids")) {
      statements.push(
        db
          .prepare(
            "INSERT INTO assignments (workspace_id, employee_id, customer_id) VALUES (?1, ?2, ?3)",
          )
          .bind(workspaceId, requiredString(employee, "id"), customerId),
      );
    }
  }

  for (const customer of requiredObjectArray(records, "customers")) {
    statements.push(insertJsonRecord(db, "customers", workspaceId, customer));
  }
  for (const integration of requiredObjectArray(records, "integrations")) {
    statements.push(insertJsonRecord(db, "integrations", workspaceId, integration));
  }
  for (const ticket of requiredObjectArray(records, "tickets")) {
    statements.push(insertJsonRecord(db, "tickets", workspaceId, ticket));
  }
  for (const policy of requiredObjectArray(records, "policies")) {
    statements.push(
      db
        .prepare("INSERT INTO policies (workspace_id, id, content) VALUES (?1, ?2, ?3)")
        .bind(workspaceId, requiredString(policy, "id"), requiredString(policy, "content")),
    );
  }

  await db.batch(statements);
  return null;
}

function insertJsonRecord(
  db: D1Database,
  table: "customers" | "integrations" | "tickets",
  workspaceId: string,
  record: JsonObject,
): D1PreparedStatement {
  if (table === "customers") {
    return db
      .prepare("INSERT INTO customers (workspace_id, id, body_json) VALUES (?1, ?2, ?3)")
      .bind(workspaceId, requiredString(record, "id"), JSON.stringify(record));
  }
  return db
    .prepare(
      `INSERT INTO ${table} (workspace_id, id, customer_id, body_json) VALUES (?1, ?2, ?3, ?4)`,
    )
    .bind(
      workspaceId,
      requiredString(record, "id"),
      requiredString(record, "customer_id"),
      JSON.stringify(record),
    );
}

async function getJsonRecord(
  db: D1Database,
  table: "customers" | "integrations" | "tickets",
  workspaceId: string,
  id: string,
): Promise<unknown> {
  const row = await db
    .prepare(`SELECT body_json FROM ${table} WHERE workspace_id = ?1 AND id = ?2`)
    .bind(workspaceId, id)
    .first<{ body_json: string }>();
  return row ? JSON.parse(row.body_json) : null;
}

async function listJsonRecords(
  db: D1Database,
  table: "tickets",
  workspaceId: string,
): Promise<unknown[]> {
  const result = await db
    .prepare(`SELECT body_json FROM ${table} WHERE workspace_id = ?1 ORDER BY id`)
    .bind(workspaceId)
    .all<{ body_json: string }>();
  return result.results.map((row) => JSON.parse(row.body_json));
}

async function getProposal(db: D1Database, workspaceId: string, id: string): Promise<unknown> {
  const row = await db
    .prepare("SELECT * FROM proposals WHERE workspace_id = ?1 AND id = ?2")
    .bind(workspaceId, id)
    .first();
  return stripWorkspaceId(row);
}

async function saveProposal(
  db: D1Database,
  workspaceId: string,
  proposal: JsonObject,
): Promise<unknown> {
  const values = PROPOSAL_COLUMNS.map((column) => proposal[column]);
  const result = await db
    .prepare(
      `INSERT OR IGNORE INTO proposals (
         workspace_id, ${PROPOSAL_COLUMNS.join(", ")}
       ) VALUES (?1, ${PROPOSAL_COLUMNS.map((_, index) => `?${index + 2}`).join(", ")})`,
    )
    .bind(workspaceId, ...values)
    .run();
  if (result.meta.changes === 1) {
    return { proposal, wasCreated: true };
  }

  const where = PROPOSAL_COLUMNS.filter((column) => column !== "id" && column !== "created_at")
    .map((column, index) => `${column} = ?${index + 2}`)
    .join(" AND ");
  const comparable = PROPOSAL_COLUMNS.filter(
    (column) => column !== "id" && column !== "created_at",
  ).map((column) => proposal[column]);
  const existing = await db
    .prepare(`SELECT * FROM proposals WHERE workspace_id = ?1 AND ${where}`)
    .bind(workspaceId, ...comparable)
    .first();
  if (!existing) throw new StorageRequestError("Proposal could not be saved", 409);
  return { proposal: stripWorkspaceId(existing), wasCreated: false };
}

async function getReceipt(
  db: D1Database,
  table: "approvals" | "executions",
  workspaceId: string,
  proposalId: string,
): Promise<unknown> {
  const row = await db
    .prepare(`SELECT * FROM ${table} WHERE workspace_id = ?1 AND proposal_id = ?2`)
    .bind(workspaceId, proposalId)
    .first();
  return stripWorkspaceId(row);
}

async function saveApproval(
  db: D1Database,
  workspaceId: string,
  approval: JsonObject,
): Promise<unknown> {
  await db
    .prepare(
      `INSERT OR IGNORE INTO approvals (
         workspace_id, id, proposal_id, approved_by_employee_id, created_at
       ) VALUES (?1, ?2, ?3, ?4, ?5)`,
    )
    .bind(
      workspaceId,
      requiredString(approval, "id"),
      requiredString(approval, "proposal_id"),
      requiredString(approval, "approved_by_employee_id"),
      requiredString(approval, "created_at"),
    )
    .run();
  const saved = await getReceipt(
    db,
    "approvals",
    workspaceId,
    requiredString(approval, "proposal_id"),
  );
  if (!saved) throw new StorageRequestError("Approval could not be saved", 409);
  return saved;
}

async function applyExecution(
  db: D1Database,
  workspaceId: string,
  payload: JsonObject,
): Promise<unknown> {
  const execution = requiredObject(payload, "execution");
  const proposalId = requiredString(execution, "proposal_id");
  const existing = await getReceipt(db, "executions", workspaceId, proposalId);
  if (existing) return { execution: existing, wasCreated: false };

  const integrationId = requiredString(payload, "integrationId");
  const customerId = requiredString(payload, "customerId");
  const expectedVersion = requiredNumber(payload, "expectedVersion");
  const currentEndpoint = requiredString(payload, "currentEndpoint");
  const proposedEndpoint = requiredString(payload, "proposedEndpoint");
  const resultingVersion = requiredNumber(execution, "resulting_configuration_version");
  const [update, insert] = await db.batch([
    db
      .prepare(
        `UPDATE integrations
            SET body_json = json_set(body_json, '$.endpoint', ?1, '$.version', ?2)
          WHERE workspace_id = ?3
            AND id = ?4
            AND customer_id = ?5
            AND json_extract(body_json, '$.version') = ?6
            AND json_extract(body_json, '$.endpoint') = ?7`,
      )
      .bind(
        proposedEndpoint,
        resultingVersion,
        workspaceId,
        integrationId,
        customerId,
        expectedVersion,
        currentEndpoint,
      ),
    db
      .prepare(
        `INSERT INTO executions (
           workspace_id, id, proposal_id, executed_by_employee_id, approval_id,
           executed_at, previous_configuration_version, resulting_configuration_version
         )
         SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8
          WHERE changes() = 1`,
      )
      .bind(
        workspaceId,
        requiredString(execution, "id"),
        proposalId,
        requiredString(execution, "executed_by_employee_id"),
        nullableString(execution, "approval_id"),
        requiredString(execution, "executed_at"),
        requiredNumber(execution, "previous_configuration_version"),
        resultingVersion,
      ),
  ]);

  if (update.meta.changes !== 1 || insert.meta.changes !== 1) {
    const retry = await getReceipt(db, "executions", workspaceId, proposalId);
    if (retry) return { execution: retry, wasCreated: false };
    throw new StorageRequestError("Configuration changed since the proposal was prepared", 409);
  }
  return { execution, wasCreated: true };
}

async function getDeliveryVerification(
  db: D1Database,
  workspaceId: string,
  executionId: string,
): Promise<unknown> {
  const row = await db
    .prepare(
      "SELECT * FROM delivery_verifications WHERE workspace_id = ?1 AND execution_id = ?2",
    )
    .bind(workspaceId, executionId)
    .first();
  return stripWorkspaceId(row);
}

async function recordDeliveryVerification(
  db: D1Database,
  workspaceId: string,
  payload: JsonObject,
): Promise<unknown> {
  const verification = requiredObject(payload, "verification");
  const executionId = requiredString(verification, "execution_id");
  const existing = await getDeliveryVerification(db, workspaceId, executionId);
  if (existing) return { verification: existing, wasCreated: false };

  const proposalId = requiredString(verification, "proposal_id");
  const outcome = requiredString(verification, "outcome");
  if (!["delivered", "failed", "inconclusive"].includes(outcome)) {
    throw new StorageRequestError("Invalid verification outcome", 400);
  }
  const ticketStatus = outcome === "delivered" ? "closed" : "needs_attention";
  const [insert, update] = await db.batch([
    db
      .prepare(
        `INSERT OR IGNORE INTO delivery_verifications (
           workspace_id, id, execution_id, proposal_id, verified_by_employee_id,
           outcome, test_event_id, destination, evidence, verified_at
         )
         SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10
           FROM executions AS execution
           JOIN proposals AS proposal
             ON proposal.workspace_id = execution.workspace_id
            AND proposal.id = execution.proposal_id
           JOIN integrations AS integration
             ON integration.workspace_id = proposal.workspace_id
            AND integration.id = proposal.integration_id
           JOIN tickets AS ticket
             ON ticket.workspace_id = proposal.workspace_id
            AND ticket.id = proposal.ticket_id
          WHERE execution.workspace_id = ?1
            AND execution.id = ?3
            AND execution.proposal_id = ?4
            AND json_extract(integration.body_json, '$.endpoint') = ?8
            AND json_extract(integration.body_json, '$.version') = execution.resulting_configuration_version`,
      )
      .bind(
        workspaceId,
        requiredString(verification, "id"),
        executionId,
        proposalId,
        requiredString(verification, "verified_by_employee_id"),
        outcome,
        requiredString(verification, "test_event_id"),
        requiredString(verification, "destination"),
        requiredString(verification, "evidence"),
        requiredString(verification, "verified_at"),
      ),
    db
      .prepare(
        `UPDATE tickets
            SET body_json = json_set(body_json, '$.status', ?1)
          WHERE workspace_id = ?2
            AND id = (
              SELECT ticket_id FROM proposals
               WHERE workspace_id = ?2 AND id = ?3
            )
            AND changes() = 1`,
      )
      .bind(ticketStatus, workspaceId, proposalId),
  ]);

  if (insert.meta.changes === 1 && update.meta.changes === 1) {
    return { verification, wasCreated: true };
  }
  const retry = await getDeliveryVerification(db, workspaceId, executionId);
  if (retry) return { verification: retry, wasCreated: false };
  throw new StorageRequestError("Delivery verification requirements changed", 409);
}

async function getRun(db: D1Database, workspaceId: string, id: string): Promise<unknown> {
  const row = await db
    .prepare("SELECT * FROM investigation_runs WHERE workspace_id = ?1 AND id = ?2")
    .bind(workspaceId, id)
    .first<Record<string, unknown>>();
  return row ? decodeRun(row) : null;
}

async function listRuns(
  db: D1Database,
  workspaceId: string,
  ticketId: string,
): Promise<unknown[]> {
  const result = await db
    .prepare(
      "SELECT * FROM investigation_runs WHERE workspace_id = ?1 AND ticket_id = ?2 ORDER BY created_at DESC",
    )
    .bind(workspaceId, ticketId)
    .all<Record<string, unknown>>();
  return result.results.map(decodeRun);
}

async function saveRun(
  db: D1Database,
  workspaceId: string,
  run: JsonObject,
): Promise<null> {
  await db
    .prepare(
      `INSERT INTO investigation_runs (
         workspace_id, id, ticket_id, scenario_id, requester_employee_id,
         requester_role, customer_ids_json, result_json, policy_review_json, created_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, NULL, ?9)`,
    )
    .bind(
      workspaceId,
      requiredString(run, "id"),
      requiredString(run, "ticket_id"),
      nullableString(run, "scenario_id"),
      requiredString(run, "requester_employee_id"),
      requiredString(run, "requester_role"),
      JSON.stringify(requiredStringArray(run, "customer_ids")),
      JSON.stringify(requiredObject(run, "result")),
      requiredString(run, "created_at"),
    )
    .run();
  return null;
}

async function findProposalRun(
  db: D1Database,
  workspaceId: string,
  proposalId: string,
): Promise<string | null> {
  const result = await db
    .prepare("SELECT id, result_json FROM investigation_runs WHERE workspace_id = ?1 ORDER BY created_at DESC")
    .bind(workspaceId)
    .all<{ id: string; result_json: string }>();
  const match = result.results.find((row) => {
    const saved = JSON.parse(row.result_json) as { proposal?: { id?: string } };
    return saved.proposal?.id === proposalId;
  });
  return match?.id ?? null;
}

async function savePolicyReview(
  db: D1Database,
  workspaceId: string,
  payload: JsonObject,
): Promise<null> {
  const result = await db
    .prepare(
      "UPDATE investigation_runs SET policy_review_json = ?1 WHERE workspace_id = ?2 AND id = ?3",
    )
    .bind(
      JSON.stringify(requiredObject(payload, "review")),
      workspaceId,
      requiredString(payload, "id"),
    )
    .run();
  if (result.meta.changes !== 1) throw new StorageRequestError("Investigation unavailable", 404);
  return null;
}

function decodeRun(row: Record<string, unknown>): JsonObject {
  return {
    id: row.id,
    ticket_id: row.ticket_id,
    scenario_id: row.scenario_id,
    requester_employee_id: row.requester_employee_id,
    requester_role: row.requester_role,
    customer_ids: JSON.parse(String(row.customer_ids_json)),
    result: JSON.parse(String(row.result_json)),
    policy_review: row.policy_review_json ? JSON.parse(String(row.policy_review_json)) : null,
    created_at: row.created_at,
  };
}

function stripWorkspaceId(row: Record<string, unknown> | null): JsonObject | null {
  if (!row) return null;
  const { workspace_id: _, ...record } = row;
  return record;
}

async function readRequest(
  request: Request,
): Promise<{ operation: string; workspaceId: string; payload: JsonObject }> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    throw new StorageRequestError("Invalid JSON body", 400);
  }
  if (!isObject(body)) throw new StorageRequestError("Invalid storage request", 400);
  return {
    operation: requiredString(body, "operation"),
    workspaceId: requiredString(body, "workspaceId"),
    payload: body.payload === undefined ? {} : requiredObject(body, "payload"),
  };
}

function requiredObject(value: JsonObject, field: string): JsonObject {
  const item = value[field];
  if (!isObject(item)) throw new StorageRequestError(`Invalid ${field}`, 400);
  return item;
}

function requiredObjectArray(value: JsonObject, field: string): JsonObject[] {
  const items = value[field];
  if (!Array.isArray(items) || !items.every(isObject)) {
    throw new StorageRequestError(`Invalid ${field}`, 400);
  }
  return items;
}

function requiredString(value: JsonObject, field: string): string {
  const item = value[field];
  if (typeof item !== "string" || item.length === 0) {
    throw new StorageRequestError(`Invalid ${field}`, 400);
  }
  return item;
}

function nullableString(value: JsonObject, field: string): string | null {
  const item = value[field];
  if (item === null) return null;
  return requiredString(value, field);
}

function requiredNumber(value: JsonObject, field: string): number {
  const item = value[field];
  if (typeof item !== "number" || !Number.isFinite(item)) {
    throw new StorageRequestError(`Invalid ${field}`, 400);
  }
  return item;
}

function requiredStringArray(value: JsonObject, field: string): string[] {
  const items = value[field];
  if (!Array.isArray(items) || !items.every((item) => typeof item === "string")) {
    throw new StorageRequestError(`Invalid ${field}`, 400);
  }
  return items;
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}
