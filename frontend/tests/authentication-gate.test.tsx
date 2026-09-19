import assert from "node:assert/strict";
import { mock, test, type TestContext } from "node:test";
import { JSDOM } from "jsdom";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost:3000",
});
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Element: dom.window.Element,
  Node: dom.window.Node,
  getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
});
const { render, screen, cleanup, fireEvent, waitFor } = await import("@testing-library/react");
let account: object | null = null;
let loginCalls = 0;
let logoutCalls = 0;
mock.module("@azure/msal-browser", {
  namedExports: {
    CacheLookupPolicy: { AccessTokenAndRefreshToken: 3 },
    createStandardPublicClientApplication: async () => ({
      handleRedirectPromise: async () => null,
      getActiveAccount: () => account,
      acquireTokenSilent: async () => ({ accessToken: "token" }),
      loginRedirect: async () => {
        loginCalls++;
      },
      logoutRedirect: async () => {
        logoutCalls++;
      },
    }),
  },
});
process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
process.env.NEXT_PUBLIC_ENTRA_TENANT_ID = "b1338704-8cc0-43f7-846c-d930c917b905";
process.env.NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID = "28093c48-1122-403b-b63f-99717ddf5e4c";
process.env.NEXT_PUBLIC_ENTRA_API_CLIENT_ID = "78e83c6d-0b97-47ee-aa39-114da2139341";
const { AuthenticationGate } = await import("../components/authentication-gate");

function mount(t: TestContext) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  t.after(() => {
    cleanup();
    client.clear();
  });
  render(
    <QueryClientProvider client={client}>
      <AuthenticationGate>
        {({ employee }, { onSignOut }) => (
          <>
            <p>Workspace {employee?.employee_id}</p>
            {employee && <button onClick={onSignOut}>Sign out</button>}
          </>
        )}
      </AuthenticationGate>
    </QueryClientProvider>,
  );
}

test("signed-out users see sign-in without fetching business data", async (t) => {
  account = null;
  t.mock.method(globalThis, "fetch", () => assert.fail("No request before sign-in"));
  mount(t);
  fireEvent.click(await screen.findByRole("button", { name: "Sign in with Microsoft" }));
  await waitFor(() => assert.equal(loginCalls, 1));
  assert.equal(screen.queryByText(/Workspace/), null);
});

test("recognized employee opens the workspace; sign-out immediately hides it", async (t) => {
  account = { tenantId: "tenant", homeAccountId: "alex" };
  t.mock.method(globalThis, "fetch", async (path: string, options: RequestInit) => {
    assert.equal(path, "/api/me");
    assert.equal(new Headers(options.headers).get("Authorization"), "Bearer token");
    return Response.json({ employee_id: "emp-alex", role: "implementation_engineer" });
  });
  mount(t);
  await screen.findByText("Workspace emp-alex");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => assert.equal(screen.queryByText(/Workspace/), null));
  assert.equal(logoutCalls, 1);
});

test("Microsoft account without employee access cannot open the workspace", async (t) => {
  account = { tenantId: "tenant", homeAccountId: "unknown" };
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ detail: "Employee unavailable" }, { status: 403 }),
  );
  mount(t);
  assert.match((await screen.findByRole("alert")).textContent!, /couldn.t sign you in/);
  assert.equal(screen.queryByText(/Workspace/), null);
});

test("demo mode opens the workspace without Microsoft or employee API calls", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
  t.after(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
  });
  t.mock.method(globalThis, "fetch", () =>
    assert.fail("Demo gate needs no authentication request"),
  );
  mount(t);
  await screen.findByText("Workspace");
  assert.equal(screen.queryByRole("button", { name: "Sign out" }), null);
});

test("sign-in screen gives a clear purpose and hides sign-out without an account", async (t) => {
  account = null;
  mount(t);
  await screen.findByRole("heading", { name: "Sign in to Switchboard" });
  assert.equal(screen.queryByRole("button", { name: "Sign out" }), null);
  assert.ok(screen.getByText(/Investigate customer requests/));
});

const { ProposalReview } = await import("../components/proposal-review");
test("Entra review uses the signed-in employee and disables self-approval", async (t) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  t.after(() => {
    cleanup();
    client.clear();
  });
  t.mock.method(globalThis, "fetch", async (_path: string, options: RequestInit) => {
    assert.equal(new Headers(options.headers).get("Authorization"), "Bearer token");
    assert.equal(new Headers(options.headers).has("X-Employee-Id"), false);
    return Response.json({
      proposal: {
        id: "proposal",
        ticket_id: "CHG-1042",
        customer_id: "acme",
        integration_id: "production",
        environment: "production",
        current_endpoint: "https://old.example",
        proposed_endpoint: "https://new.example",
        expected_configuration_version: 1,
        proposed_by_employee_id: "emp-alex",
        created_at: "2026-09-22T13:30:00Z",
      },
      approval: null,
      execution: null,
      current_status: { code: "awaiting_approval", title: "Awaiting approval" },
    });
  });
  render(
    <QueryClientProvider client={client}>
      <ProposalReview
        runId="run"
        proposalId="proposal"
        identity={{ mode: "entra", accountId: "alex", getAccessToken: async () => "token" }}
        currentEmployee={{ employee_id: "emp-alex", role: "technical_lead" }}
        employees={[]}
        onStatusRefresh={async () => {}}
      />
    </QueryClientProvider>,
  );
  const button = await screen.findByRole("button", { name: "Approve this proposal" });
  assert.equal((button as HTMLButtonElement).disabled, true);
  assert.equal(screen.queryByText("Review or execute as"), null);
});

const { default: Home } = await import("../app/page");
test("signed-in workspace puts account controls in the application sidebar", async (t) => {
  account = { tenantId: "tenant", homeAccountId: "alex" };
  t.after(cleanup);
  t.mock.method(globalThis, "fetch", async (path: string) => {
    if (path === "/api/me")
      return Response.json({ employee_id: "emp-alex", role: "implementation_engineer" });
    if (path === "/api/demo-options") return Response.json({ employees: [], scenarios: [] });
    if (path === "/api/demo") return Response.json({ scenario_id: "baseline" });
    return Response.json([]);
  });
  render(<Home />);
  const sidebar = await screen.findByRole("complementary");
  await waitFor(() => assert.match(sidebar.textContent!, /emp-alex/));
  assert.ok(sidebar.contains(screen.getByRole("button", { name: "Switch" })));
  assert.ok(sidebar.contains(screen.getByRole("button", { name: "Sign out" })));
  assert.ok(screen.getByRole("heading", { name: "My work" }));
  fireEvent.click(screen.getByRole("button", { name: "Approvals" }));
  assert.ok(screen.getByRole("heading", { name: "Approvals" }));
});
