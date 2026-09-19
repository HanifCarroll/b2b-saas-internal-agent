import { WorkspaceRoute } from "@/components/workspace-route";

export default async function ApprovalPage({
  params,
  searchParams,
}: PageProps<"/approvals/[proposalId]">) {
  const [{ proposalId }, query] = await Promise.all([params, searchParams]);
  const runId = typeof query.run === "string" ? query.run : undefined;
  return <WorkspaceRoute route={{ kind: "approvals", proposalId, runId }} />;
}
