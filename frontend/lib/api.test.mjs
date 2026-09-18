import assert from "node:assert/strict";
import { test } from "node:test";
import { QueryClient } from "@tanstack/react-query";
import {
  clearDemoQueries,
  historyQuery,
  investigationQuery,
  investigationKeys,
  proposalReviewQuery,
  proposalReviewKeys,
} from "./api.ts";

test("employee-scoped history is fetched and invalidated independently", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const employee = options.headers["X-Employee-Id"];
    calls.push(employee);
    return Response.json([{ run_id: employee, scenario_id: "baseline", outcome: "blocked" }]);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  t.after(() => client.clear());

  const alex = await client.fetchQuery(historyQuery("emp-alex"));
  const priya = await client.fetchQuery(historyQuery("emp-priya"));
  assert.notDeepEqual(alex, priya);
  assert.deepEqual(calls, ["emp-alex", "emp-priya"]);

  await client.invalidateQueries({ queryKey: investigationKeys.history("emp-alex") });
  assert.equal(client.getQueryState(investigationKeys.history("emp-alex")).isInvalidated, true);
  assert.equal(client.getQueryState(investigationKeys.history("emp-priya")).isInvalidated, false);
});

test("canceling a run query aborts its network request", async (t) => {
  let requestSignal;
  t.mock.method(globalThis, "fetch", (_url, options) => {
    requestSignal = options.signal;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () =>
        reject(new DOMException("Aborted", "AbortError")),
      );
    });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  t.after(() => client.clear());
  const query = investigationQuery("emp-alex", "run-1");
  const pending = client.fetchQuery(query).catch(() => undefined);
  await client.cancelQueries({ queryKey: query.queryKey });
  await pending;
  assert.equal(requestSignal.aborted, true);
  assert.equal(client.getQueryData(query.queryKey), undefined);
});

test("unselected runs stay disabled; inaccessible runs surface errors", async (t) => {
  assert.equal(investigationQuery("emp-alex", null).enabled, false);
  assert.notDeepEqual(
    investigationKeys.run("emp-alex", "run-1"),
    investigationKeys.run("emp-priya", "run-1"),
  );
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Record unavailable" }, { status: 403 }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  t.after(() => client.clear());
  await assert.rejects(
    client.fetchQuery(investigationQuery("emp-alex", "run-1")),
    /Record unavailable/,
  );
});

test("proposal reviews isolate reviewers and invalidate together after approval", async (t) => {
  let approved = false;
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    if (options.headers["X-Employee-Id"] === "emp-ben") {
      return Response.json({ detail: "Proposal unavailable" }, { status: 404 });
    }
    return Response.json({ approval: approved ? { id: "approval-1" } : null });
  });
  const client = new QueryClient();
  t.after(() => client.clear());
  const alex = proposalReviewQuery({
    employee: "emp-alex",
    runId: "run-1",
    proposalId: "proposal-1",
  });
  const priya = proposalReviewQuery({
    employee: "emp-priya",
    runId: "run-1",
    proposalId: "proposal-1",
  });
  const ben = proposalReviewQuery({
    employee: "emp-ben",
    runId: "run-1",
    proposalId: "proposal-1",
  });
  assert.notDeepEqual(alex.queryKey, priya.queryKey);
  assert.equal((await client.fetchQuery(alex)).approval, null);
  assert.equal((await client.fetchQuery(priya)).approval, null);
  await assert.rejects(client.fetchQuery(ben), /Proposal unavailable/);
  assert.equal(client.getQueryData(ben.queryKey), undefined);
  approved = true;
  await client.invalidateQueries({ queryKey: proposalReviewKeys.proposal("run-1", "proposal-1") });
  assert.equal(client.getQueryState(alex.queryKey).isInvalidated, true);
  assert.equal(client.getQueryState(priya.queryKey).isInvalidated, true);
  assert.equal((await client.fetchQuery(priya)).approval.id, "approval-1");
});

test("reset clears saved-work caches across investigators and reviewers", async () => {
  const client = new QueryClient();
  try {
    for (const employee of ["emp-alex", "emp-priya"]) {
      client.setQueryData(investigationKeys.history(employee), [{ run_id: "old-run" }]);
      client.setQueryData(investigationKeys.run(employee, "old-run"), { result: "old" });
      client.setQueryData([...proposalReviewKeys.proposal("old-run", "proposal"), employee], {
        approval: "old",
      });
    }
    client.setQueryData(["demo-options"], { scenarios: ["baseline"] });
    await clearDemoQueries(client);
    assert.equal(client.getQueriesData({ queryKey: ["investigations"] }).length, 0);
    assert.equal(client.getQueriesData({ queryKey: ["investigation"] }).length, 0);
    assert.equal(client.getQueriesData({ queryKey: ["proposal-review"] }).length, 0);
    assert.deepEqual(client.getQueryData(["demo-options"]), { scenarios: ["baseline"] });
  } finally {
    client.clear();
  }
});
