import assert from "node:assert/strict";

const baseUrl = process.env.STORAGE_TEST_URL ?? "http://127.0.0.1:8799";
const token = process.env.LOCAL_STORAGE_BRIDGE_TOKEN ?? "storage-test";
const mode = process.argv[2];
const workspaceId = "storage-integration-test";

async function operation(name, payload = {}, expectedStatus = 200, selectedWorkspace = workspaceId) {
  const response = await fetch(baseUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ operation: name, workspaceId: selectedWorkspace, payload }),
  });
  const body = await response.json();
  assert.equal(response.status, expectedStatus, JSON.stringify(body));
  return body.data;
}

const proposal = {
  id: "proposal-one",
  proposed_by_employee_id: "emp-alex",
  ticket_id: "CHG-1042",
  requester_contact_id: "contact-jordan",
  customer_id: "acme",
  integration_id: "int-acme-prod",
  environment: "production",
  current_endpoint: "https://old.acme.example/deals",
  proposed_endpoint: "https://events.acme.example/deals",
  expected_configuration_version: 7,
  recovery_plan: "manual_intervention",
  created_at: "2026-09-19T12:00:00Z",
  status: "pending_approval",
};

const execution = {
  id: "execution-one",
  proposal_id: proposal.id,
  executed_by_employee_id: "emp-alex",
  approval_id: "approval-one",
  executed_at: "2026-09-22T14:15:00Z",
  previous_configuration_version: 7,
  resulting_configuration_version: 8,
};

if (mode === "prepare") {
  await operation("workspace.reset", {
    identityMode: "eval",
    scenarioId: "baseline",
    updatedAt: "2026-09-19T12:00:00Z",
    inputs: { ticket_id: "CHG-1042" },
    records: {
      employees: [{
        id: "emp-alex",
        name: "Alex Rivera",
        active: true,
        role: "implementation_engineer",
        customer_ids: ["acme"],
      }],
      customers: [{ id: "acme", name: "Acme Services" }],
      integrations: [{
        id: "int-acme-prod",
        customer_id: "acme",
        endpoint: "https://old.acme.example/deals",
        version: 7,
      }],
      tickets: [],
      policies: [],
    },
  });

  assert.equal(await operation("integration.get", { id: "int-acme-prod" }, 200, "other"), null);
  await operation("not.sql", {}, 404);

  const firstProposal = await operation("proposal.save", { proposal });
  const proposalRetry = await operation("proposal.save", {
    proposal: { ...proposal, id: "proposal-retry", created_at: "2026-09-19T12:01:00Z" },
  });
  assert.equal(firstProposal.wasCreated, true);
  assert.equal(proposalRetry.wasCreated, false);
  assert.equal(proposalRetry.proposal.id, proposal.id);

  await operation("approval.save", {
    approval: {
      id: "approval-one",
      proposal_id: proposal.id,
      approved_by_employee_id: "emp-priya",
      created_at: "2026-09-19T13:00:00Z",
    },
  });

  await operation("execution.apply", {
    execution: { ...execution, id: "failed-execution" },
    integrationId: "int-acme-prod",
    customerId: "acme",
    expectedVersion: 8,
    currentEndpoint: proposal.current_endpoint,
    proposedEndpoint: proposal.proposed_endpoint,
  }, 409);
  const unchanged = await operation("integration.get", { id: "int-acme-prod" });
  assert.equal(unchanged.version, 7);
  assert.equal(await operation("execution.get", { proposalId: proposal.id }), null);

  const applied = await operation("execution.apply", {
    execution,
    integrationId: "int-acme-prod",
    customerId: "acme",
    expectedVersion: 7,
    currentEndpoint: proposal.current_endpoint,
    proposedEndpoint: proposal.proposed_endpoint,
  });
  assert.equal(applied.wasCreated, true);
  assert.equal((await operation("integration.get", { id: "int-acme-prod" })).version, 8);
} else if (mode === "retry") {
  const retried = await operation("execution.apply", {
    execution: { ...execution, id: "execution-retry" },
    integrationId: "int-acme-prod",
    customerId: "acme",
    expectedVersion: 7,
    currentEndpoint: proposal.current_endpoint,
    proposedEndpoint: proposal.proposed_endpoint,
  });
  assert.equal(retried.wasCreated, false);
  assert.equal(retried.execution.id, execution.id);
  assert.equal((await operation("integration.get", { id: "int-acme-prod" })).version, 8);
} else {
  throw new Error("Use prepare or retry");
}
