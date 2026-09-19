import { WorkspaceRoute } from "@/components/workspace-route";

export default async function RequestPage({ params }: PageProps<"/requests/[ticketId]">) {
  const { ticketId } = await params;
  return <WorkspaceRoute route={{ kind: "request", ticketId }} />;
}
