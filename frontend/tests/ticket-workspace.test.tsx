import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import React from "react";

const dom = new JSDOM("<!doctype html><html><body></body></html>");
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Element: dom.window.Element,
  Node: dom.window.Node,
  getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
});
const { render, screen, cleanup, fireEvent } = await import("@testing-library/react");
const { TicketList } = await import("../components/ticket-list");
const { TicketDetail } = await import("../components/ticket-detail");
const { WorkflowProgress } = await import("../components/workflow-progress");
const { ApprovalInbox } = await import("../components/approval-inbox");
const { WorkspaceError } = await import("../components/workspace-route");

const ticket = {
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
};

test("failed workspace reads offer a manual retry", (t) => {
  t.after(cleanup);
  let retries = 0;
  render(
    <WorkspaceError
      message="The service is temporarily unavailable. Try again."
      onRetry={() => {
        retries += 1;
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  assert.equal(retries, 1);
});

test("ticket list selects an accessible work item", (t) => {
  t.after(cleanup);
  let selected = "";
  render(
    <TicketList
      tickets={[ticket]}
      selectedTicketId={null}
      busy={false}
      onSelect={(ticketId) => {
        selected = ticketId;
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /CHG-1042/ }));
  assert.equal(selected, "CHG-1042");
  assert.ok(screen.getByText("int-acme-prod"));
});

test("ticket detail starts an investigation for the displayed ticket", (t) => {
  t.after(cleanup);
  let investigated = "";
  render(
    <TicketDetail
      ticket={ticket}
      busy={false}
      onInvestigate={(ticketId) => {
        investigated = ticketId;
      }}
    />,
  );

  assert.ok(screen.getByRole("heading", { name: "Request summary" }));
  assert.ok(screen.getByText("Jordan Lee"));
  fireEvent.click(screen.getByRole("button", { name: "Start investigation" }));
  assert.equal(investigated, "CHG-1042");
});

test("workflow keeps human review separate from execution", (t) => {
  t.after(cleanup);
  render(
    <WorkflowProgress
      hasInvestigation
      hasProposal
      status={{
        code: "awaiting_approval",
        title: "Awaiting approval",
        next_action: "Review the proposal",
      }}
    />,
  );

  const lifecycle = screen.getByRole("list", { name: "Change lifecycle" });
  assert.match(lifecycle.textContent!, /ReviewIn progress/);
  assert.match(lifecycle.textContent!, /ExecuteLocked/);
});

test("workflow shows delivery verification after execution", (t) => {
  t.after(cleanup);
  render(
    <WorkflowProgress
      hasInvestigation
      hasProposal
      status={{
        code: "delivery_verified",
        title: "Delivery verified",
        next_action: "Request closed",
      }}
    />,
  );

  const lifecycle = screen.getByRole("list", { name: "Change lifecycle" });
  assert.match(lifecycle.textContent!, /ExecuteComplete/);
  assert.match(lifecycle.textContent!, /VerifyComplete/);
});

test("approval inbox opens a proposal awaiting independent review", (t) => {
  t.after(cleanup);
  let selected = "";
  render(
    <ApprovalInbox
      items={[
        {
          run_id: "run-1",
          proposal: {
            id: "proposal-1",
            ticket_id: "CHG-1042",
            customer_id: "acme",
            integration_id: "int-acme-prod",
            environment: "production",
            current_endpoint: "https://old.example/deals",
            proposed_endpoint: "https://new.example/deals",
            expected_configuration_version: 7,
            recovery_plan: "manual_intervention",
            proposed_by_employee_id: "emp-alex",
            created_at: "2026-09-22T13:30:00Z",
          },
        },
      ]}
      selectedProposalId={null}
      busy={false}
      onSelect={(item) => {
        selected = item.proposal.id;
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /CHG-1042/ }));
  assert.equal(selected, "proposal-1");
  assert.ok(screen.getAllByText("Awaiting review").length > 0);
});
