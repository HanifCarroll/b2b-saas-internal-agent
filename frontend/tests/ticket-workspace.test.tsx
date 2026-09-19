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

const ticket = {
  id: "CHG-1042",
  customer_id: "acme",
  integration_id: "int-acme-prod",
  requester_contact_id: "contact-jordan",
  assigned_employee_id: "emp-alex",
  requested_endpoint: "https://events.acme.example/deals",
  created_at: "2026-09-22T13:30:00Z",
  status: "open",
  subject: "Update production CRM event delivery endpoint",
  body: "Please move the production CRM sync.",
};

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

  assert.ok(screen.getByText(ticket.subject));
  fireEvent.click(screen.getByRole("button", { name: "Investigate ticket" }));
  assert.equal(investigated, "CHG-1042");
});
