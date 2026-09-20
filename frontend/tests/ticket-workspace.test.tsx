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
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: (handle: number) => clearTimeout(handle),
});
const { render, screen, cleanup, fireEvent } = await import("@testing-library/react");
const { TicketList } = await import("../components/ticket-list");
const { TicketDetail } = await import("../components/ticket-detail");
const { WorkflowProgress } = await import("../components/workflow-progress");
const { InvestigationFindings } = await import("../components/investigation-findings");
const { EvidenceDocument } = await import("../components/evidence-document");
const { EvidenceSheet } = await import("../components/evidence-sheet");
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

test("workflow distinguishes a ready investigation from one in progress", (t) => {
  t.after(cleanup);
  const { rerender } = render(
    <WorkflowProgress
      hasInvestigation={false}
      hasProposal={false}
      investigationInProgress={false}
      status={null}
    />,
  );

  let lifecycle = screen.getByRole("list", { name: "Change lifecycle" });
  assert.match(lifecycle.textContent!, /InvestigateReady/);

  rerender(
    <WorkflowProgress
      hasInvestigation={false}
      hasProposal={false}
      investigationInProgress
      status={null}
    />,
  );
  lifecycle = screen.getByRole("list", { name: "Change lifecycle" });
  assert.match(lifecycle.textContent!, /InvestigateIn progress/);
});

test("investigation report shows structured criteria and actionable blockers", (t) => {
  t.after(cleanup);
  render(
    <InvestigationFindings
      run={{
        run_id: "run-1",
        ticket_id: "CHG-1042",
        scenario_id: null,
        current_status: {
          code: "blocked",
          title: "Investigation blocked",
          next_action: "Resolve the blockers.",
        },
        result: {
          source: "fixture",
          investigation: {
            outcome: "blocked",
            findings: {
              overview: "The destination record could not be retrieved.",
              decision_criteria: [
                {
                  name: "Destination registration",
                  status: "unavailable",
                  required_before: "proposal",
                  explanation: "The integration record was unavailable.",
                  policy_id: "endpoint-change-v2",
                  evidence_ids: [],
                },
                {
                  name: "Independent approval",
                  status: "deferred",
                  required_before: "execution",
                  explanation: "A different technical lead must approve it.",
                  policy_id: "endpoint-change-v2",
                  evidence_ids: [],
                },
              ],
              recommendation: "Restore access and investigate again.",
            },
            blockers: [
              {
                kind: "missing_evidence",
                summary: "Integration evidence is unavailable.",
                resolution: "Restore access to the integration record.",
              },
            ],
            evidence_ids: ["CHG-1042", "endpoint-change-v2"],
          },
          report_validation: {
            policy_ids: ["endpoint-change-v2"],
            evaluation_count: 2,
            revision_count: 1,
          },
          evidence: [
            {
              id: "CHG-1042",
              kind: "ticket",
              captured_at: "2026-09-22T14:00:00Z",
              document: { id: "CHG-1042" },
            },
            {
              id: "endpoint-change-v2",
              kind: "policy",
              captured_at: "2026-09-22T14:00:00Z",
              document: { id: "endpoint-change-v2" },
            },
          ],
          proposal: null,
          was_created: null,
          messages: [],
        },
      }}
    />,
  );

  assert.ok(screen.getByRole("heading", { name: "Decision criteria" }));
  assert.ok(screen.getByText("Fixture result"));
  assert.ok(screen.getByText("Unavailable"));
  assert.ok(screen.getByText("Required before execution"));
  assert.ok(screen.getByRole("heading", { name: "What needs attention" }));
  assert.equal(screen.queryByText("Passed"), null);
  assert.equal(screen.queryByRole("button", { name: /Evaluate policy claims/ }), null);
  const technicalDetails = screen.getByText("Technical details").closest("details");
  assert.equal(technicalDetails?.open, false);
  fireEvent.click(screen.getByText("Technical details"));
  assert.ok(screen.getByText("Prevalidated local fixture; no model evaluation was run."));
  assert.equal(
    screen.getAllByRole("link", { name: "endpoint-change-v2" })[0].getAttribute("href"),
    "/requests/CHG-1042?run=run-1&evidence=endpoint-change-v2",
  );
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

test("evidence document distinguishes the captured integration from the current record", (t) => {
  t.after(cleanup);
  render(
    <EvidenceDocument
      detail={{
        snapshot: {
          id: "int-acme-prod",
          kind: "integration",
          captured_at: "2026-09-22T14:00:00Z",
          document: {
            id: "int-acme-prod",
            customer_id: "acme",
            name: "Acme production CRM sync",
            environment: "production",
            endpoint: "https://old.acme.example/deals",
            version: 7,
          },
        },
        current_document: {
          id: "int-acme-prod",
          customer_id: "acme",
          name: "Acme production CRM sync",
          environment: "production",
          endpoint: "https://events.acme.example/deals",
          version: 8,
        },
        has_changed: true,
      }}
    />,
  );

  assert.ok(screen.getByText("This record changed after the investigation."));
  assert.ok(screen.getByText("Captured during investigation"));
  assert.ok(screen.getByText("Current record"));
  assert.ok(screen.getByText("https://old.acme.example/deals"));
  assert.ok(screen.getByText("https://events.acme.example/deals"));
  assert.equal(
    screen
      .getByText("https://events.acme.example/deals")
      .closest("[data-changed]")
      ?.getAttribute("data-changed"),
    "true",
  );
});

test("unchanged evidence is shown once", (t) => {
  t.after(cleanup);
  const unchangedTicket = {
    id: "CHG-1042",
    subject: "Update production CRM event delivery endpoint",
    status: "open",
    created_at: "2026-09-22T13:30:00Z",
  };

  render(
    <EvidenceDocument
      detail={{
        snapshot: {
          id: "CHG-1042",
          kind: "ticket",
          captured_at: "2026-09-22T14:00:00Z",
          document: unchangedTicket,
        },
        current_document: unchangedTicket,
        has_changed: false,
      }}
    />,
  );

  assert.ok(screen.getByText("Unchanged since capture"));
  assert.equal(screen.queryByText("Current record"), null);
  assert.equal(screen.getAllByText("CHG-1042").length, 1);
});

test("evidence opens in a dismissible sheet", (t) => {
  t.after(cleanup);
  let closed = false;

  render(
    <EvidenceSheet
      ticketId="CHG-1042"
      runId="run-1"
      detail={{
        snapshot: {
          id: "int-acme-prod",
          kind: "integration",
          captured_at: "2026-09-22T14:00:00Z",
          document: {
            id: "int-acme-prod",
            name: "Acme production CRM sync",
            customer_id: "acme",
            environment: "production",
            endpoint: "https://events.acme.example/deals",
            version: 8,
          },
        },
        current_document: null,
        has_changed: null,
      }}
      onClose={() => {
        closed = true;
      }}
      onRetry={() => {}}
    />,
  );

  const sheet = screen.getByRole("dialog");
  assert.ok(sheet.className.includes("data-[side=right]:w-full"));
  assert.ok(screen.getByRole("heading", { name: "Integration evidence" }));
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  assert.equal(closed, true);
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
