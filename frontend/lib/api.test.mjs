import assert from "node:assert/strict";
import { test } from "node:test";
import { QueryClient } from "@tanstack/react-query";
import { historyQuery, investigationQuery, investigationKeys } from "./api.ts";

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
