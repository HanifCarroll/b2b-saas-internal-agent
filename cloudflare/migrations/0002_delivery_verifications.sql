CREATE TABLE delivery_verifications (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    verified_by_employee_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('delivered', 'failed', 'inconclusive')),
    test_event_id TEXT NOT NULL,
    destination TEXT NOT NULL,
    evidence TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, execution_id),
    FOREIGN KEY (workspace_id, execution_id) REFERENCES executions(workspace_id, id),
    FOREIGN KEY (workspace_id, proposal_id) REFERENCES proposals(workspace_id, id)
);
