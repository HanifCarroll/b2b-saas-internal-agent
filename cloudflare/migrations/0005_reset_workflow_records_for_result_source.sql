-- Saved demo workflows use a strict result schema. Remove obsolete synthetic runs
-- instead of carrying compatibility logic for the new model/fixture source field.
DELETE FROM delivery_verifications;
DELETE FROM executions;
DELETE FROM approvals;
DELETE FROM investigation_runs;
DELETE FROM proposals;
