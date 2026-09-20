import { WorkspaceRoute } from "@/components/workspace-route";

export default async function RequestPage({
  params,
  searchParams,
}: PageProps<"/requests/[ticketId]">) {
  const { ticketId } = await params;
  const { run, evidence } = await searchParams;
  return (
    <WorkspaceRoute
      route={{
        kind: "request",
        ticketId,
        runId: typeof run === "string" ? run : undefined,
        evidenceId: typeof evidence === "string" ? evidence : undefined,
      }}
    />
  );
}
