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
  requestAnimationFrame: (callback: FrameRequestCallback) =>
    dom.window.setTimeout(() => callback(Date.now()), 0),
  cancelAnimationFrame: (handle: number) => dom.window.clearTimeout(handle),
});
const { render, screen, cleanup, fireEvent, waitFor, within } =
  await import("@testing-library/react");
let account: object | null = null;
let loginCalls = 0;
let logoutCalls = 0;
let pushedPath = "";
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
mock.module("next/navigation", {
  namedExports: {
    useRouter: () => ({
      push: (path: string) => {
        pushedPath = path;
      },
      replace: () => {},
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
        {({ employee }, { onUseDemo, onSignOut }) => (
          <>
            <p>Workspace {employee?.employee_id}</p>
            {onUseDemo && <button onClick={onUseDemo}>Use demo</button>}
            {employee && onSignOut && <button onClick={onSignOut}>Sign out</button>}
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
    return Response.json({
      employee_id: "emp-alex",
      name: "Alex Rivera",
      role: "implementation_engineer",
    });
  });
  mount(t);
  await screen.findByText("Workspace emp-alex");
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(screen.queryByText(/Workspace/), null);
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

test("hybrid mode lets a visitor enter the demo without contacting Microsoft", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
  window.sessionStorage.clear();
  t.after(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
    window.sessionStorage.clear();
  });
  t.mock.method(globalThis, "fetch", () => assert.fail("Demo gate needs no API request"));
  const loginCallsBefore = loginCalls;

  mount(t);
  fireEvent.click(await screen.findByRole("button", { name: "Try the demo" }));

  await screen.findByText("Workspace");
  assert.equal(loginCalls, loginCallsBefore);
  assert.equal(window.sessionStorage.getItem("switchboard-session-mode"), "demo");
});

test("hybrid mode starts Microsoft sign-in when selected", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
  window.sessionStorage.clear();
  t.after(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
    window.sessionStorage.clear();
  });
  const loginCallsBefore = loginCalls;

  mount(t);
  fireEvent.click(await screen.findByRole("button", { name: "Sign in with Microsoft" }));

  await waitFor(() => assert.equal(loginCalls, loginCallsBefore + 1));
  assert.equal(window.sessionStorage.getItem("switchboard-session-mode"), "entra");
});

test("hybrid mode restores the selected demo for the browser tab", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
  window.sessionStorage.setItem("switchboard-session-mode", "demo");
  t.after(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
    window.sessionStorage.clear();
  });
  t.mock.method(globalThis, "fetch", () => assert.fail("Demo gate needs no API request"));

  mount(t);

  await screen.findByText("Workspace");
  assert.equal(screen.queryByRole("heading", { name: "Choose how to continue" }), null);
});

test("hybrid mode switches from Microsoft to demo without signing out", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
  window.sessionStorage.setItem("switchboard-session-mode", "entra");
  account = { tenantId: "tenant", homeAccountId: "alex" };
  const logoutCallsBefore = logoutCalls;
  t.after(() => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
    window.sessionStorage.clear();
  });
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({
      employee_id: "emp-alex",
      name: "Alex Rivera",
      role: "implementation_engineer",
    }),
  );

  mount(t);
  fireEvent.click(await screen.findByRole("button", { name: "Use demo" }));

  await screen.findByText("Workspace");
  assert.equal(logoutCalls, logoutCallsBefore);
  assert.equal(window.sessionStorage.getItem("switchboard-session-mode"), "demo");
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
    assert.equal(new Headers(options.headers).has("X-Demo-Persona-Id"), false);
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
        currentEmployee={{ employee_id: "emp-alex", name: "Alex Rivera", role: "technical_lead" }}
        employees={[]}
        onStatusRefresh={async () => {}}
      />
    </QueryClientProvider>,
  );
  const button = await screen.findByRole("button", { name: "Approve this proposal" });
  assert.equal((button as HTMLButtonElement).disabled, true);
  assert.equal(screen.queryByText("Review or execute as"), null);
});

test("proposal execution requires confirmation in an alert dialog", async (t) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let executionRequests = 0;
  t.after(() => {
    cleanup();
    client.clear();
  });
  t.mock.method(globalThis, "fetch", async (path: string, options: RequestInit = {}) => {
    if (options.method === "POST" && path.endsWith("/execution")) {
      executionRequests++;
      return Response.json({
        execution: {
          id: "execution",
          proposal_id: "proposal",
          executed_by_employee_id: "emp-alex",
          executed_at: "2026-09-22T14:15:00Z",
          approval_id: "approval",
          previous_configuration_version: 1,
          resulting_configuration_version: 2,
        },
        was_created: true,
      });
    }
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
        recovery_plan: "manual_intervention",
        proposed_by_employee_id: "emp-alex",
        created_at: "2026-09-22T13:30:00Z",
      },
      approval: {
        id: "approval",
        proposal_id: "proposal",
        approved_by_employee_id: "emp-priya",
        created_at: "2026-09-22T14:00:00Z",
      },
      execution: null,
      verification: null,
      current_status: { code: "approval_recorded", title: "Approval recorded" },
    });
  });
  render(
    <QueryClientProvider client={client}>
      <ProposalReview
        runId="run"
        proposalId="proposal"
        identity={{ mode: "entra", accountId: "alex", getAccessToken: async () => "token" }}
        currentEmployee={{
          employee_id: "emp-alex",
          name: "Alex Rivera",
          role: "implementation_engineer",
        }}
        employees={[]}
        onStatusRefresh={async () => {}}
      />
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: "Execute change" }));

  const dialog = await screen.findByRole("alertdialog");
  assert.ok(within(dialog).getByRole("heading", { name: "Execute CHG-1042?" }));
  assert.equal(executionRequests, 0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Execute change" }));
  await waitFor(() => assert.equal(executionRequests, 1));
});

test("executed proposal can be verified without repeating execution", async (t) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  let verified = false;
  let verificationRequests = 0;
  const verification = {
    id: "verification",
    execution_id: "execution",
    proposal_id: "proposal",
    verified_by_employee_id: "emp-alex",
    outcome: "delivered",
    test_event_id: "test-event",
    destination: "https://new.example/",
    evidence: "Synthetic event accepted.",
    verified_at: "2026-09-22T14:16:00Z",
  };
  const approval = {
    id: "approval",
    proposal_id: "proposal",
    approved_by_employee_id: "emp-priya",
    created_at: "2026-09-22T14:14:00Z",
  };
  t.after(() => {
    cleanup();
    client.clear();
  });
  t.mock.method(globalThis, "fetch", async (path: string, options: RequestInit) => {
    if (options.method === "POST" && path.endsWith("/verification")) {
      verificationRequests++;
      verified = true;
      return Response.json({ verification, was_created: true });
    }
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
        recovery_plan: "manual_intervention",
        proposed_by_employee_id: "emp-alex",
        created_at: "2026-09-22T13:30:00Z",
      },
      approval,
      execution: {
        id: "execution",
        proposal_id: "proposal",
        executed_by_employee_id: "emp-alex",
        executed_at: "2026-09-22T14:15:00Z",
        approval_id: approval.id,
        previous_configuration_version: 1,
        resulting_configuration_version: 2,
      },
      verification: verified ? verification : null,
      current_status: verified
        ? { code: "delivery_verified", title: "Delivery verified" }
        : { code: "configuration_updated", title: "Configuration updated" },
    });
  });
  render(
    <QueryClientProvider client={client}>
      <ProposalReview
        runId="run"
        proposalId="proposal"
        identity={{ mode: "entra", accountId: "alex", getAccessToken: async () => "token" }}
        currentEmployee={{
          employee_id: "emp-alex",
          name: "Alex Rivera",
          role: "implementation_engineer",
        }}
        employees={[{ id: "emp-priya", name: "Priya Shah", role: "technical_lead" }]}
        onStatusRefresh={async () => {}}
      />
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: "Verify delivery" }));

  assert.equal((await screen.findAllByText("Delivery verified")).length, 1);
  assert.equal(verificationRequests, 1);
  assert.ok(screen.getByText("Synthetic event accepted."));
  assert.equal(screen.queryByText("Independent approval required"), null);
  const auditDetails = screen.getByText("Approval and recovery details").closest("details");
  assert.equal(auditDetails?.open, false);
  assert.match(auditDetails?.textContent ?? "", /Approved by Priya Shah/);
  assert.match(auditDetails?.textContent ?? "", /Test event: test-event/);
  assert.equal(screen.queryByRole("button", { name: "Execute change" }), null);
});

const { WorkspaceProvider } = await import("../components/workspace-provider");
const { WorkspaceRoute } = await import("../components/workspace-route");
test("signed-in workspace puts account controls in the application sidebar", async (t) => {
  account = { tenantId: "tenant", homeAccountId: "alex" };
  pushedPath = "";
  t.after(cleanup);
  t.mock.method(globalThis, "fetch", async (path: string) => {
    if (path === "/api/me")
      return Response.json({
        employee_id: "emp-alex",
        name: "Alex Rivera",
        role: "implementation_engineer",
      });
    if (path === "/api/tickets")
      return Response.json([
        {
          id: "CHG-1042",
          customer_id: "acme",
          integration_id: "int-acme-prod",
          requester_contact_id: "contact-jordan",
          assigned_employee_id: "emp-alex",
          requester: { id: "contact-jordan", name: "Jordan Lee" },
          assigned_employee: { id: "emp-alex", name: "Alex Rivera" },
          requested_endpoint: "https://events.acme.example/deals",
          created_at: "2026-09-22T13:30:00Z",
          status: "open",
          subject: "Update production CRM event delivery endpoint",
          body: "Please move the production CRM sync.",
          workflow_status: {
            code: "ready_to_investigate",
            title: "Ready to investigate",
            next_action: "Run an investigation.",
          },
          needs_attention: true,
        },
      ]);
    return Response.json([]);
  });
  render(
    <WorkspaceProvider>
      <WorkspaceRoute route={{ kind: "work" }} />
    </WorkspaceProvider>,
  );
  const sidebar = await screen.findByRole("complementary");
  await waitFor(() => assert.match(sidebar.textContent!, /Alex Rivera/));
  assert.ok(sidebar.contains(screen.getByRole("button", { name: "Switch" })));
  assert.ok(sidebar.contains(screen.getByRole("button", { name: "Sign out" })));
  assert.ok(screen.getByRole("heading", { name: "My work" }));
  fireEvent.click(await screen.findByRole("button", { name: /CHG-1042/ }));
  assert.equal(pushedPath, "/requests/CHG-1042");
  fireEvent.click(screen.getByRole("button", { name: "Approvals" }));
  assert.equal(pushedPath, "/approvals");
});

test("public demo shows persistent requests with workflow filters", async (t) => {
  process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
  pushedPath = "";
  t.after(() => {
    cleanup();
    process.env.NEXT_PUBLIC_AUTH_MODE = "entra";
  });
  t.mock.method(globalThis, "fetch", async (path: string) => {
    if (path === "/api/demo/personas") {
      return Response.json([
        { id: "emp-alex", name: "Alex Rivera", role: "implementation_engineer" },
        { id: "emp-priya", name: "Priya Shah", role: "technical_lead" },
      ]);
    }
    if (path === "/api/tickets") {
      return Response.json([
        {
          id: "CHG-1042",
          customer_id: "acme",
          integration_id: "int-acme-prod",
          requester_contact_id: "contact-jordan",
          assigned_employee_id: "emp-alex",
          requester: { id: "contact-jordan", name: "Jordan Lee" },
          assigned_employee: { id: "emp-alex", name: "Alex Rivera" },
          requested_endpoint: "https://events.acme.example/deals",
          created_at: "2026-09-22T13:30:00Z",
          status: "open",
          subject: "Investigate CRM delivery",
          body: "Please update the endpoint.",
          workflow_status: {
            code: "ready_to_investigate",
            title: "Ready to investigate",
            next_action: "Run an investigation.",
          },
          needs_attention: true,
        },
        {
          id: "CHG-1045",
          customer_id: "acme",
          integration_id: "int-acme-orders-prod",
          requester_contact_id: "contact-jordan",
          assigned_employee_id: "emp-alex",
          requester: { id: "contact-jordan", name: "Jordan Lee" },
          assigned_employee: { id: "emp-alex", name: "Alex Rivera" },
          requested_endpoint: "https://events.acme.example/orders",
          created_at: "2026-09-22T13:45:00Z",
          status: "open",
          subject: "Update order delivery",
          body: "Please update the endpoint.",
          workflow_status: {
            code: "awaiting_approval",
            title: "Awaiting approval",
            next_action: "Obtain approval.",
          },
          needs_attention: false,
        },
      ]);
    }
    return Response.json([]);
  });

  render(
    <WorkspaceProvider>
      <WorkspaceRoute route={{ kind: "work" }} />
    </WorkspaceProvider>,
  );

  const sidebar = await screen.findByRole("complementary");
  await waitFor(() => assert.match(sidebar.textContent!, /Demo persona/));
  assert.match(sidebar.textContent!, /Alex Rivera/);
  assert.equal(sidebar.querySelector(".lucide-chevron-right"), null);
  assert.equal(within(sidebar).getByText("implementation engineer").tabIndex, -1);
  assert.equal(screen.queryByText("Try a demo case"), null);
  assert.equal(
    screen.queryByText("Open a request to inspect it and start an investigation."),
    null,
  );
  assert.equal((await screen.findAllByText("Ready to investigate")).length, 2);
  assert.equal(screen.getAllByText("Awaiting approval").length, 2);
  fireEvent.click(screen.getByRole("button", { name: "Needs attention 1" }));
  assert.ok(screen.getByText("Investigate CRM delivery"));
  assert.equal(screen.queryByText("Update order delivery"), null);
});
