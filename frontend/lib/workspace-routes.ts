export const workspacePaths = {
  work: "/work",
  approvals: "/approvals",
} as const;

export function requestPath(ticketId: string) {
  return `/requests/${encodeURIComponent(ticketId)}`;
}

export function approvalPath({ proposalId, runId }: { proposalId: string; runId: string }) {
  const query = new URLSearchParams({ run: runId });
  return `/approvals/${encodeURIComponent(proposalId)}?${query}`;
}
