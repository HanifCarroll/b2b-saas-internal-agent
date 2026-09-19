import assert from "node:assert/strict";
import { test } from "node:test";
import { approvalPath, requestPath } from "./workspace-routes.ts";

test("request paths preserve ticket identifiers", () => {
  assert.equal(requestPath("CHG-1042"), "/requests/CHG-1042");
  assert.equal(requestPath("change/with spaces"), "/requests/change%2Fwith%20spaces");
});

test("approval paths preserve both identifiers needed to refresh a review", () => {
  assert.equal(
    approvalPath({ proposalId: "proposal/1", runId: "run 1" }),
    "/approvals/proposal%2F1?run=run+1",
  );
});
