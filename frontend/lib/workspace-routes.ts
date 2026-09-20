export const workspacePaths = {
  work: "/work",
  approvals: "/approvals",
} as const;

export function requestPath(ticketId: string, runId?: string) {
  const path = `/requests/${encodeURIComponent(ticketId)}`;
  return runId ? `${path}?run=${encodeURIComponent(runId)}` : path;
}

export function evidencePath({
  ticketId,
  runId,
  evidenceId,
}: {
  ticketId: string;
  runId: string;
  evidenceId: string;
}) {
  return `/requests/${encodeURIComponent(ticketId)}/investigations/${encodeURIComponent(runId)}/evidence/${encodeURIComponent(evidenceId)}`;
}

export function approvalPath({ proposalId, runId }: { proposalId: string; runId: string }) {
  const query = new URLSearchParams({ run: runId });
  return `/approvals/${encodeURIComponent(proposalId)}?${query}`;
}
