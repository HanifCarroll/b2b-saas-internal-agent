PRAGMA foreign_keys = ON;

CREATE TABLE workspaces (
    id TEXT PRIMARY KEY NOT NULL,
    identity_mode TEXT NOT NULL CHECK(identity_mode IN ('demo', 'entra', 'cli', 'eval')),
    scenario_id TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE employees (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    role TEXT NOT NULL CHECK(role IN ('support_specialist', 'implementation_engineer', 'technical_lead')),
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE assignments (
    workspace_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    PRIMARY KEY (workspace_id, employee_id, customer_id),
    FOREIGN KEY (workspace_id, employee_id) REFERENCES employees(workspace_id, id) ON DELETE CASCADE
);

CREATE TABLE customers (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    body_json TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE integrations (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    body_json TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE tickets (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    body_json TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE policies (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE TABLE proposals (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    proposed_by_employee_id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    requester_contact_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    integration_id TEXT NOT NULL,
    environment TEXT NOT NULL CHECK(environment IN ('sandbox', 'production')),
    current_endpoint TEXT NOT NULL,
    proposed_endpoint TEXT NOT NULL,
    expected_configuration_version INTEGER NOT NULL CHECK(expected_configuration_version >= 1),
    recovery_plan TEXT NOT NULL CHECK(recovery_plan = 'manual_intervention'),
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'pending_approval'),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (
        workspace_id,
        proposed_by_employee_id,
        ticket_id,
        requester_contact_id,
        customer_id,
        integration_id,
        environment,
        current_endpoint,
        proposed_endpoint,
        expected_configuration_version,
        recovery_plan,
        status
    )
);

CREATE TABLE approvals (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    approved_by_employee_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, proposal_id)
);

CREATE TABLE executions (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    executed_by_employee_id TEXT NOT NULL,
    approval_id TEXT,
    executed_at TEXT NOT NULL,
    previous_configuration_version INTEGER NOT NULL CHECK(previous_configuration_version >= 1),
    resulting_configuration_version INTEGER NOT NULL CHECK(resulting_configuration_version = previous_configuration_version + 1),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, proposal_id)
);

CREATE TABLE investigation_runs (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    ticket_id TEXT NOT NULL,
    scenario_id TEXT,
    requester_employee_id TEXT NOT NULL,
    requester_role TEXT NOT NULL,
    customer_ids_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    policy_review_json TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id)
);

CREATE INDEX investigation_runs_ticket_created
    ON investigation_runs(workspace_id, ticket_id, created_at DESC);
