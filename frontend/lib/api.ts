export type Approval = {
  id: string;
  approved_by_employee_id: string;
  created_at: string;
};
export type Execution = {
  id: string;
  proposal_id: string;
  executed_by_employee_id: string;
  executed_at: string;
  approval_id: string | null;
  previous_configuration_version: number;
  resulting_configuration_version: number;
};
export type ExecuteProposalResult = { execution: Execution; was_created: boolean };
export type DeliveryVerification = {
  id: string;
  execution_id: string;
  proposal_id: string;
  verified_by_employee_id: string;
  outcome: "delivered" | "failed" | "inconclusive";
  test_event_id: string;
  destination: string;
  evidence: string;
  verified_at: string;
};
export type VerifyDeliveryResult = {
  verification: DeliveryVerification;
  was_created: boolean;
};
export type ProposalReviewResult = {
  execution: Execution | null;
  verification: DeliveryVerification | null;
  current_status: WorkflowStatus;
  proposal: {
    id: string;
    ticket_id: string;
    customer_id: string;
    integration_id: string;
    environment: string;
    current_endpoint: string;
    proposed_endpoint: string;
    expected_configuration_version: number;
    recovery_plan: "manual_intervention";
    proposed_by_employee_id: string;
    created_at: string;
  };
  approval: Approval | null;
};

export type WorkflowStatus = {
  code:
    | "configuration_updated"
    | "delivery_verified"
    | "manual_intervention_required"
    | "blocked"
    | "awaiting_approval"
    | "approval_recorded"
    | "approval_not_required"
    | "unavailable";
  title: string;
  next_action: string;
};

export type DemoPersona = { id: string; name: string; role: string };
export type DemoCaseSummary = {
  id: string;
  title: string;
  description: string;
  recommended_persona_id: string;
};
export type PreparedDemoCase = { case_id: string; persona_id: string; path: string };
export type PersonReference = { id: string; name: string };
export type Ticket = {
  id: string;
  customer_id: string;
  integration_id: string;
  requester_contact_id: string;
  assigned_employee_id: string;
  requester: PersonReference;
  assigned_employee: PersonReference;
  requested_endpoint: string;
  created_at: string;
  status: string;
  subject: string;
  body: string;
};
export type InvestigationHistoryItem = {
  run_id: string;
  ticket_id: string;
  scenario_id: string | null;
  outcome: string;
};
export type PolicyReview = {
  issues: {
    claim: string;
    policy_id: string;
    policy_excerpt: string;
    explanation: string;
  }[];
  limitation: string;
};
export type InvestigationRun = {
  current_status: WorkflowStatus;
  run_id: string;
  ticket_id: string;
  scenario_id: string | null;
  policy_review: PolicyReview | null;
  result: {
    investigation: {
      outcome: string;
      findings: {
        overview: string;
        checks: string[];
        policy_requirements: string[];
        gaps: string[];
        recommendation: string;
      };
      blockers: string[];
      evidence_ids: string[];
    };
    proposal: { id: string } | null;
    was_created: boolean | null;
    messages: {
      tool_calls?: {
        id: string;
        name: string;
        args: Record<string, unknown>;
      }[];
    }[];
  };
};

export type RequestIdentity =
  | { mode: "demo"; employeeId: string }
  | { mode: "entra"; accountId: string; getAccessToken: () => Promise<string> };

/** Send an explicitly selected identity to the Python API. */
export async function requestApi<T>({
  path,
  identity,
  options = {},
}: {
  path: string;
  identity: RequestIdentity;
  options?: RequestInit;
}): Promise<T> {
  // 1. Keep identity headers under this helper's control.
  const headers = new Headers(options.headers);
  if (headers.has("Authorization") || headers.has("X-Demo-Persona-Id")) {
    throw new Error("Do not supply identity headers through request options.");
  }
  headers.set("Content-Type", "application/json");

  // 2. Resolve exactly one identity mechanism before sending the request.
  if (identity.mode === "demo") {
    headers.set("X-Demo-Persona-Id", identity.employeeId);
  } else {
    const accessToken = await identity.getAccessToken();
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  // 3. Send once and surface failures; never retry a business action here.
  const response = await fetch(path, {
    ...options,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Request failed. Check that the API is running and refresh before retrying.",
    );
  }
  return response.json();
}

export type CurrentEmployee = { employee_id: string; name: string; role: string };

export function identityKey(identity: RequestIdentity) {
  return identity.mode === "demo" ? ["demo", identity.employeeId] : ["entra", identity.accountId];
}

// Keep business caches separate for every mode and account.
export const investigationKeys = {
  tickets: (identity: RequestIdentity) => ["tickets", ...identityKey(identity)] as const,
  history: (identity: RequestIdentity, ticketId: string | null) =>
    ["investigations", ...identityKey(identity), ticketId] as const,
  run: (identity: RequestIdentity, runId: string | null) =>
    ["investigation", ...identityKey(identity), runId] as const,
};

export const ticketsQuery = (identity: RequestIdentity) => ({
  queryKey: investigationKeys.tickets(identity),
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<Ticket[]>({
      path: "/api/tickets",
      identity,
      options: { signal },
    }),
});

export const demoPersonasQuery = (identity: RequestIdentity) => ({
  queryKey: ["demo-personas", ...identityKey(identity)],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<DemoPersona[]>({
      path: "/api/demo/personas",
      identity,
      options: { signal },
    }),
});

export const demoCasesQuery = (identity: RequestIdentity) => ({
  queryKey: ["demo-cases"],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<DemoCaseSummary[]>({
      path: "/api/demo/cases",
      identity,
      options: { signal },
    }),
});

export function prepareDemoCase({
  identity,
  caseId,
}: {
  identity: RequestIdentity;
  caseId: string;
}) {
  return requestApi<PreparedDemoCase>({
    path: `/api/demo/cases/${encodeURIComponent(caseId)}/prepare`,
    identity,
    options: { method: "POST" },
  });
}

export function historyQuery(identity: RequestIdentity, ticketId: string | null) {
  return {
    queryKey: investigationKeys.history(identity, ticketId),
    enabled: ticketId !== null,
    queryFn: ({ signal }: { signal: AbortSignal }) => {
      if (!ticketId) throw new Error("Select a ticket first.");
      return requestApi<InvestigationHistoryItem[]>({
        path: `/api/investigations?ticket_id=${encodeURIComponent(ticketId)}`,
        identity,
        options: { signal },
      });
    },
  };
}

export function investigationQuery(identity: RequestIdentity, runId: string | null) {
  return {
    queryKey: investigationKeys.run(identity, runId),
    enabled: runId !== null,
    queryFn: ({ signal }: { signal: AbortSignal }) => {
      if (!runId) throw new Error("Select an investigation first.");
      return requestApi<InvestigationRun>({
        path: `/api/investigations/${runId}`,
        identity,
        options: { signal },
      });
    },
  };
}

export const proposalReviewKeys = {
  inbox: (identity: RequestIdentity) => ["approval-inbox", ...identityKey(identity)] as const,
  proposal: (runId: string, proposalId: string) => ["proposal-review", runId, proposalId] as const,
};

export type ApprovalInboxItem = {
  run_id: string;
  proposal: ProposalReviewResult["proposal"];
};

export const approvalInboxQuery = (identity: RequestIdentity) => ({
  queryKey: proposalReviewKeys.inbox(identity),
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<ApprovalInboxItem[]>({
      path: "/api/approvals",
      identity,
      options: { signal },
    }),
});

export function proposalReviewQuery({
  identity,
  runId,
  proposalId,
}: {
  identity: RequestIdentity;
  runId: string;
  proposalId: string;
}) {
  return {
    queryKey: [...proposalReviewKeys.proposal(runId, proposalId), ...identityKey(identity)],
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      requestApi<ProposalReviewResult>({
        path: `/api/runs/${runId}/proposals/${proposalId}`,
        identity,
        options: {
          signal,
        },
      }),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  };
}

export async function clearDemoQueries(client: import("@tanstack/react-query").QueryClient) {
  await client.cancelQueries();
  for (const key of [
    "tickets",
    "investigations",
    "investigation",
    "approval-inbox",
    "proposal-review",
  ]) {
    client.removeQueries({ queryKey: [key] });
  }
}
