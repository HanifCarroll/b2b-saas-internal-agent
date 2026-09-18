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
export type ProposalReviewResult = {
  execution: Execution | null;
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
  };
  approval: Approval | null;
};

export type WorkflowStatus = {
  code:
    | "configuration_updated"
    | "blocked"
    | "awaiting_approval"
    | "approval_recorded"
    | "approval_not_required"
    | "unavailable";
  title: string;
  next_action: string;
};

export type DemoOptions = {
  scenarios: { id: string; expected: string[] }[];
  employees: { id: string; name: string; role: string }[];
};
export type InvestigationHistoryItem = { run_id: string; scenario_id: string; outcome: string };
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
  scenario_id: string;
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
  if (headers.has("Authorization") || headers.has("X-Employee-Id")) {
    throw new Error("Do not supply identity headers through request options.");
  }
  headers.set("Content-Type", "application/json");

  // 2. Resolve exactly one identity mechanism before sending the request.
  if (identity.mode === "demo") {
    headers.set("X-Employee-Id", identity.employeeId);
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

// Include the simulated identity in every employee-scoped cache key.
export const investigationKeys = {
  history: (employee: string) => ["investigations", employee] as const,
  run: (employee: string, runId: string | null) => ["investigation", employee, runId] as const,
};

export const demoOptionsQuery = {
  queryKey: ["demo-options"],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<DemoOptions>({
      path: "/api/demo-options",
      identity: { mode: "demo", employeeId: "" },
      options: { signal },
    }),
};

export function historyQuery(employee: string) {
  return {
    queryKey: investigationKeys.history(employee),
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      requestApi<InvestigationHistoryItem[]>({
        path: "/api/investigations",
        identity: { mode: "demo", employeeId: employee },
        options: { signal },
      }),
  };
}

export function investigationQuery(employee: string, runId: string | null) {
  return {
    queryKey: investigationKeys.run(employee, runId),
    enabled: runId !== null,
    queryFn: ({ signal }: { signal: AbortSignal }) => {
      if (!runId) throw new Error("Select an investigation first.");
      return requestApi<InvestigationRun>({
        path: `/api/investigations/${runId}`,
        identity: { mode: "demo", employeeId: employee },
        options: { signal },
      });
    },
  };
}

export const proposalReviewKeys = {
  proposal: (runId: string, proposalId: string) => ["proposal-review", runId, proposalId] as const,
};

export function proposalReviewQuery({
  employee,
  runId,
  proposalId,
}: {
  employee: string;
  runId: string;
  proposalId: string;
}) {
  return {
    queryKey: [...proposalReviewKeys.proposal(runId, proposalId), employee],
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      requestApi<ProposalReviewResult>({
        path: `/api/runs/${runId}/proposals/${proposalId}`,
        identity: { mode: "demo", employeeId: employee },
        options: {
          signal,
        },
      }),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  };
}

export type DemoState = { scenario_id: string | null };

export const demoStateQuery = {
  queryKey: ["demo-state"],
  queryFn: ({ signal }: { signal: AbortSignal }) =>
    requestApi<DemoState>({
      path: "/api/demo",
      identity: { mode: "demo", employeeId: "" },
      options: { signal },
    }),
};

export async function clearDemoQueries(client: import("@tanstack/react-query").QueryClient) {
  await client.cancelQueries();
  for (const key of ["investigations", "investigation", "proposal-review"]) {
    client.removeQueries({ queryKey: [key] });
  }
}
