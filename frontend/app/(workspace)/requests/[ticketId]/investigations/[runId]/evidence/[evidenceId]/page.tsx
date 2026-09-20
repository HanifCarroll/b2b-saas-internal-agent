import { WorkspaceRoute } from "@/components/workspace-route";

export default async function EvidencePage({
  params,
}: PageProps<"/requests/[ticketId]/investigations/[runId]/evidence/[evidenceId]">) {
  const { ticketId, runId, evidenceId } = await params;
  return <WorkspaceRoute route={{ kind: "evidence", ticketId, runId, evidenceId }} />;
}
