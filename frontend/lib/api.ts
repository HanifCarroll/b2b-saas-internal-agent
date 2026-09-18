export type WorkflowStatus = {
  code:
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

/** Send the explicitly simulated identity to the local Python application. */
export async function requestApi<T>(
  path: string,
  employee: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-Employee-Id": employee,
      ...options.headers,
    },
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
    requestApi<DemoOptions>("/api/demo-options", "", { signal }),
};

export function historyQuery(employee: string) {
  return {
    queryKey: investigationKeys.history(employee),
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      requestApi<InvestigationHistoryItem[]>("/api/investigations", employee, { signal }),
  };
}

export function investigationQuery(employee: string, runId: string | null) {
  return {
    queryKey: investigationKeys.run(employee, runId),
    enabled: runId !== null,
    queryFn: ({ signal }: { signal: AbortSignal }) => {
      if (!runId) throw new Error("Select an investigation first.");
      return requestApi<InvestigationRun>(`/api/investigations/${runId}`, employee, { signal });
    },
  };
}
