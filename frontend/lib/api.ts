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
export type CriterionStatus = "verified" | "unverified" | "unavailable" | "failed" | "deferred";
export type WorkflowStage = "proposal" | "review" | "execution" | "verification";
export type DecisionCriterion = {
  name: string;
  status: CriterionStatus;
  required_before: WorkflowStage;
  explanation: string;
  policy_id: string | null;
  evidence_ids: string[];
};
export type InvestigationBlocker = {
  kind: "missing_evidence" | "confirmed_violation";
  summary: string;
  resolution: string;
};
export type InvestigationRun = {
  current_status: WorkflowStatus;
  run_id: string;
  ticket_id: string;
  scenario_id: string | null;
  result: {
    investigation: {
      outcome: string;
      findings: {
        overview: string;
        decision_criteria: DecisionCriterion[];
        recommendation: string;
      };
      blockers: InvestigationBlocker[];
      evidence_ids: string[];
    };
    report_validation: {
      policy_ids: string[];
      evaluation_count: number;
      revision_count: number;
    };
    evidence: EvidenceSnapshot[];
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

export type EvidenceKind = "ticket" | "customer" | "integration" | "policy";
export type EvidenceSnapshot = {
  id: string;
  kind: EvidenceKind;
  captured_at: string;
  document: Record<string, unknown>;
};
export type InvestigationEvidenceDetail = {
  snapshot: EvidenceSnapshot;
  current_document: Record<string, unknown> | null;
  has_changed: boolean | null;
};

export type RequestIdentity =
  | { mode: "demo"; employeeId: string }
  | { mode: "entra"; accountId: string; getAccessToken: () => Promise<string> };

class ApiRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const RETRYABLE_READ_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);

/** Retry temporary failures for idempotent queries while a hosted service starts. */
export function shouldRetryReadRequest(failureCount: number, error: Error) {
  if (failureCount >= 3) return false;

  return (
    error instanceof TypeError ||
    (error instanceof ApiRequestError && RETRYABLE_READ_STATUSES.has(error.status))
  );
}

export function readRetryDelay(attemptIndex: number) {
  return Math.min(500 * 2 ** attemptIndex, 2_000);
}

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
    throw new ApiRequestError(
      typeof body?.detail === "string"
        ? body.detail
        : "The service is temporarily unavailable. Try again.",
      response.status,
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
  evidence: (identity: RequestIdentity, runId: string, evidenceId: string) =>
    ["investigation-evidence", ...identityKey(identity), runId, evidenceId] as const,
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
  staleTime: Infinity,
});

export const demoCasesQuery = (identity: RequestIdentity) => ({
  queryKey: ["demo-cases"],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<DemoCaseSummary[]>({
      path: "/api/demo/cases",
      identity,
      options: { signal },
    }),
  staleTime: Infinity,
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

export function investigationEvidenceQuery(
  identity: RequestIdentity,
  runId: string,
  evidenceId: string,
) {
  return {
    queryKey: investigationKeys.evidence(identity, runId, evidenceId),
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      requestApi<InvestigationEvidenceDetail>({
        path: `/api/investigations/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(evidenceId)}`,
        identity,
        options: { signal },
      }),
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
