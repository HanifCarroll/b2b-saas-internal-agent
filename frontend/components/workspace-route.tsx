"use client";

import { useState } from "react";
import { useMutation, useIsMutating, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  CircleAlert,
  Database,
  LoaderCircle,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ApprovalInbox } from "@/components/approval-inbox";
import { ProposalReview } from "@/components/proposal-review";
import {
  approvalInboxQuery,
  clearDemoQueries,
  demoCasesQuery,
  demoPersonasQuery,
  historyQuery,
  investigationQuery,
  investigationKeys,
  type InvestigationRun,
  prepareDemoCase,
  requestApi,
  ticketsQuery,
  proposalReviewKeys,
} from "@/lib/api";
import { DemoCaseLauncher } from "@/components/demo-case-launcher";
import { DemoPersonaSwitcher } from "@/components/demo-persona";
import { InvestigationHistory } from "@/components/investigation-history";
import { InvestigationFindings } from "@/components/investigation-findings";
import { TicketDetail } from "@/components/ticket-detail";
import { TicketList } from "@/components/ticket-list";
import { WorkflowProgress } from "@/components/workflow-progress";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";
import { useWorkspaceSession } from "@/components/workspace-provider";
import { approvalPath, requestPath, workspacePaths } from "@/lib/workspace-routes";

export type WorkspaceRouteDescriptor =
  | { kind: "work" }
  | { kind: "request"; ticketId: string }
  | { kind: "approvals"; proposalId?: string; runId?: string };

export function WorkspaceRoute({ route }: { route: WorkspaceRouteDescriptor }) {
  const { identity, currentEmployee, accountActions, onEmployeeChange } = useWorkspaceSession();
  const router = useRouter();
  const employee = identity.mode === "demo" ? identity.employeeId : currentEmployee!.employee_id;
  const queryClient = useQueryClient();
  const selectedTicketId = route.kind === "request" ? route.ticketId : null;
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const activeView = route.kind === "approvals" ? "approvals" : "work";
  const [ticketSearch, setTicketSearch] = useState("");

  // 1. Query keys isolate each employee's data; Query manages cancellation and loading.
  const personasQuery = useQuery({
    ...demoPersonasQuery(identity),
    enabled: identity.mode === "demo",
  });
  const casesQuery = useQuery({
    ...demoCasesQuery(identity),
    enabled: identity.mode === "demo",
  });
  const ticketsQueryResult = useQuery(ticketsQuery(identity));
  const approvalsQueryResult = useQuery({
    ...approvalInboxQuery(identity),
    enabled: activeView === "approvals",
  });
  const mutationsInProgress = useIsMutating();
  const historyQueryResult = useQuery(historyQuery(identity, selectedTicketId));
  const selectedRun = useQuery(investigationQuery(identity, selectedRunId));
  const personas = personasQuery.data ?? [];
  const cases = casesQuery.data ?? [];
  const tickets = ticketsQueryResult.data ?? [];
  const approvals = approvalsQueryResult.data ?? [];
  const selectedProposalId = route.kind === "approvals" ? (route.proposalId ?? null) : null;
  const selectedApproval =
    approvals.find((item) => item.proposal.id === selectedProposalId) ?? null;
  const selectedApprovalRunId =
    route.kind === "approvals" ? (route.runId ?? selectedApproval?.run_id ?? null) : null;
  const normalizedTicketSearch = ticketSearch.trim().toLowerCase();
  const visibleTickets = normalizedTicketSearch
    ? tickets.filter((ticket) =>
        [ticket.id, ticket.subject, ticket.customer_id, ticket.integration_id].some((value) =>
          value.toLowerCase().includes(normalizedTicketSearch),
        ),
      )
    : tickets;
  const selectedTicket = tickets.find((ticket) => ticket.id === selectedTicketId) ?? null;
  const history = historyQueryResult.data ?? [];
  const run = selectedRun.isError ? null : (selectedRun.data ?? null);
  const employeeRecord = personas.find((item) => item.id === employee);
  const employeeName = employeeRecord?.name ?? currentEmployee?.name ?? employee;
  const employeeRole = employeeRecord?.role ?? currentEmployee?.role ?? null;

  // 2. Mutations run only on explicit user actions and never retry paid calls.
  const investigation = useMutation({
    mutationFn: (ticketId: string) =>
      requestApi<InvestigationRun>({
        path: "/api/investigations",
        identity,
        options: {
          method: "POST",
          body: JSON.stringify({ ticket_id: ticketId }),
        },
      }),
    onSuccess: (savedRun) => {
      queryClient.setQueryData(investigationKeys.run(identity, savedRun.run_id), savedRun);
      router.replace(requestPath(savedRun.ticket_id));
      setSelectedRunId(savedRun.run_id);
    },
    onSettled: (_data, _error, ticketId) =>
      queryClient.invalidateQueries({ queryKey: investigationKeys.history(identity, ticketId) }),
  });
  const casePreparation = useMutation({
    mutationFn: (caseId: string) => prepareDemoCase({ identity, caseId }),
    onMutate: () => {
      setSelectedRunId(null);
      investigation.reset();
    },
    onSuccess: async (prepared) => {
      await clearDemoQueries(queryClient);
      onEmployeeChange(prepared.persona_id);
      router.push(prepared.path);
    },
  });

  function startTicketInvestigation(ticketId: string) {
    casePreparation.reset();
    setSelectedRunId(null);
    investigation.mutate(ticketId);
  }

  function selectTicket(ticketId: string) {
    investigation.reset();
    setSelectedRunId(null);
    router.push(requestPath(ticketId));
  }

  function changePersona(personaId: string) {
    setSelectedRunId(null);
    investigation.reset();
    onEmployeeChange(personaId);
    router.push(workspacePaths.work);
  }

  function clearSelection() {
    setSelectedRunId(null);
    router.push(workspacePaths.work);
  }

  function openApprovals() {
    setSelectedRunId(null);
    investigation.reset();
    router.push(workspacePaths.approvals);
  }

  function openRun(id: string) {
    investigation.reset();
    setSelectedRunId(id);
  }

  function refreshHistory() {
    void historyQueryResult.refetch();
  }

  // 3. Derive presentation from query and mutation state, rather than copying it.
  const pendingMessage = casePreparation.isPending
    ? "Preparing the demo case…"
    : investigation.isPending
      ? "Investigating records and validating the result…"
      : selectedRun.isLoading
        ? "Loading saved investigation…"
        : "";
  const isPending = pendingMessage !== "";
  const operationError = (casePreparation.error ?? investigation.error)?.message;
  const readError = (
    selectedRun.error ??
    ticketsQueryResult.error ??
    approvalsQueryResult.error ??
    personasQuery.error ??
    casesQuery.error ??
    historyQueryResult.error
  )?.message;
  const error = operationError ?? readError;

  function retryWorkspaceReads() {
    void queryClient.refetchQueries({ type: "active" });
  }
  const sidebarDemoControls =
    identity.mode === "demo" ? (
      <DemoCaseLauncher
        cases={cases}
        busy={isPending || mutationsInProgress > 0 || casesQuery.isFetching}
        onPrepare={(caseId) => casePreparation.mutate(caseId)}
      />
    ) : undefined;
  const demoPersonaSwitcher =
    identity.mode === "demo" ? (
      <DemoPersonaSwitcher
        personas={personas}
        selectedPersonaId={employee}
        busy={isPending || mutationsInProgress > 0}
        onChange={changePersona}
      />
    ) : undefined;

  return (
    <div className="min-h-screen bg-[#f7f8fa] lg:pl-60">
      <WorkspaceSidebar
        activeView={activeView}
        employee={employeeName}
        role={employeeRole}
        accountControls={accountActions}
        demoControls={sidebarDemoControls}
        demoPersona={identity.mode === "demo" ? (employeeRecord ?? null) : undefined}
        demoPersonaSwitcher={demoPersonaSwitcher}
        onOpenWork={clearSelection}
        onOpenApprovals={openApprovals}
      />

      {activeView === "approvals" ? (
        <main className="min-h-screen">
          <div className="border-b bg-white px-5 py-7 sm:px-8">
            <div className="mx-auto max-w-6xl">
              <h1 className="text-3xl font-semibold tracking-tight">Approvals</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Production changes waiting for your independent review.
              </p>
            </div>
          </div>
          <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
            {error && (
              <WorkspaceError
                message={error}
                onRetry={operationError ? undefined : retryWorkspaceReads}
              />
            )}
            <section className="overflow-hidden rounded-xl border bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 px-5 py-4">
                <div>
                  <h2 className="font-semibold">Awaiting review</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Only proposals you are currently authorized to approve appear here.
                  </p>
                </div>
                <Badge variant="secondary">{approvals.length} pending</Badge>
              </div>
              <ApprovalInbox
                items={approvals}
                selectedProposalId={selectedProposalId}
                busy={approvalsQueryResult.isFetching}
                onSelect={(item) =>
                  router.push(
                    approvalPath({
                      proposalId: item.proposal.id,
                      runId: item.run_id,
                    }),
                  )
                }
              />
            </section>

            {selectedProposalId && selectedApprovalRunId && (
              <section className="mt-8 rounded-xl border bg-white px-6 shadow-sm">
                <ProposalReview
                  key={selectedProposalId}
                  runId={selectedApprovalRunId}
                  proposalId={selectedProposalId}
                  identity={identity}
                  currentEmployee={currentEmployee}
                  employees={personas}
                  onStatusRefresh={async () => {
                    await queryClient.invalidateQueries({
                      queryKey: proposalReviewKeys.inbox(identity),
                    });
                  }}
                />
              </section>
            )}
          </div>
        </main>
      ) : !selectedTicket ? (
        <main className="min-h-screen">
          <div className="border-b bg-white px-5 py-7 sm:px-8">
            <div className="mx-auto max-w-6xl">
              <div className="flex flex-wrap items-end justify-between gap-5">
                <div>
                  <h1 className="text-3xl font-semibold tracking-tight">My work</h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Customer requests assigned to your employee account.
                  </p>
                </div>
                <div className="relative w-full max-w-sm">
                  <Search
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <input
                    type="search"
                    aria-label="Search assigned requests"
                    placeholder="Search requests"
                    value={ticketSearch}
                    onChange={(event) => setTicketSearch(event.target.value)}
                    className="h-10 w-full rounded-lg border bg-white pr-3 pl-9 text-sm outline-none focus:ring-2 focus:ring-ring/30"
                  />
                </div>
              </div>
              <div className="mt-6 flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-md bg-blue-50 px-3 py-1.5 font-medium text-blue-700">
                  All {tickets.length}
                </span>
                <span className="rounded-md px-3 py-1.5 text-muted-foreground">
                  Needs attention {tickets.length}
                </span>
              </div>
            </div>
          </div>
          <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
            {error && (
              <WorkspaceError
                message={error}
                onRetry={operationError ? undefined : retryWorkspaceReads}
              />
            )}
            {isPending && <PendingOperation message={pendingMessage} />}
            <section className="overflow-hidden rounded-xl border bg-white shadow-sm">
              <div className="flex items-center justify-between gap-3 px-5 py-4">
                <div>
                  <h2 className="font-semibold">Assigned requests</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Open a request to inspect it and start an investigation.
                  </p>
                </div>
                <Badge variant="secondary">{tickets.length} open</Badge>
              </div>
              <TicketList
                tickets={visibleTickets}
                selectedTicketId={selectedTicketId}
                busy={ticketsQueryResult.isFetching}
                onSelect={selectTicket}
              />
            </section>
          </div>
        </main>
      ) : (
        <main className="min-h-screen bg-white" aria-live="polite" aria-busy={isPending}>
          <header className="border-b px-5 py-6 sm:px-8">
            <div className="mx-auto max-w-7xl">
              <Button variant="ghost" size="sm" className="-ml-3" onClick={clearSelection}>
                <ArrowLeft className="size-4" />
                My work
              </Button>
              <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">{selectedTicket.id}</p>
                  <h1 className="mt-1 text-3xl font-semibold tracking-tight">
                    {selectedTicket.subject}
                  </h1>
                  <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                    <span className="flex items-center gap-2">
                      <Building2 className="size-4" aria-hidden="true" />
                      {selectedTicket.customer_id}
                    </span>
                    <span className="flex items-center gap-2">
                      <Database className="size-4" aria-hidden="true" />
                      {selectedTicket.integration_id}
                    </span>
                    <span>Owner: {selectedTicket.assigned_employee.name}</span>
                    <Badge variant="secondary" className="capitalize">
                      {run?.current_status.title ?? selectedTicket.status}
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
          </header>

          <div className="mx-auto max-w-7xl px-5 sm:px-8">
            <WorkflowProgress
              hasInvestigation={run !== null}
              hasProposal={run?.result.proposal !== null && run?.result.proposal !== undefined}
              investigationInProgress={investigation.isPending}
              status={run?.current_status ?? null}
            />

            {error && (
              <WorkspaceError
                message={error}
                onRetry={operationError ? undefined : retryWorkspaceReads}
              />
            )}
            {isPending && <PendingOperation message={pendingMessage} />}

            <div className="grid items-start gap-10 py-8 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="min-w-0">
                <TicketDetail
                  ticket={selectedTicket}
                  busy={investigation.isPending}
                  onInvestigate={startTicketInvestigation}
                />
                {run && (
                  <>
                    <InvestigationFindings run={run} />
                    {run.result.proposal && (
                      <ProposalReview
                        key={run.run_id}
                        runId={run.run_id}
                        proposalId={run.result.proposal.id}
                        identity={identity}
                        currentEmployee={currentEmployee}
                        employees={personas}
                        onStatusRefresh={() =>
                          queryClient.invalidateQueries({
                            queryKey: investigationKeys.run(identity, run.run_id),
                          })
                        }
                      />
                    )}
                  </>
                )}
              </div>

              <aside className="flex flex-col gap-6 xl:sticky xl:top-6">
                <section aria-labelledby="current-stage-title">
                  <h2 id="current-stage-title" className="font-semibold">
                    Current stage
                  </h2>
                  <div className="mt-3 flex gap-3 rounded-lg border p-4">
                    {run?.current_status.code === "blocked" && !investigation.isPending ? (
                      <CircleAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
                    ) : (
                      <ShieldCheck className="mt-0.5 size-5 shrink-0 text-amber-600" />
                    )}
                    <div>
                      <p className="font-medium">
                        {investigation.isPending
                          ? "Investigation in progress"
                          : (run?.current_status.title ?? "Ready to investigate")}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {investigation.isPending
                          ? "Reviewing records and validating the report."
                          : (run?.current_status.next_action ??
                            "Run an investigation to gather evidence and determine the next action.")}
                      </p>
                    </div>
                  </div>
                </section>

                <section className="border-t pt-6" aria-labelledby="request-details-title">
                  <h2 id="request-details-title" className="font-semibold">
                    Request details
                  </h2>
                  <dl className="mt-4 grid grid-cols-[100px_1fr] gap-x-4 gap-y-3 text-sm">
                    <dt className="text-muted-foreground">Customer</dt>
                    <dd>{selectedTicket.customer_id}</dd>
                    <dt className="text-muted-foreground">Integration</dt>
                    <dd>{selectedTicket.integration_id}</dd>
                    <dt className="text-muted-foreground">Assigned to</dt>
                    <dd>{selectedTicket.assigned_employee.name}</dd>
                  </dl>
                </section>

                <InvestigationHistory
                  history={history}
                  selectedRunId={selectedRunId}
                  busy={isPending || historyQueryResult.isFetching}
                  onOpenRun={openRun}
                  onRefresh={refreshHistory}
                />
              </aside>
            </div>
          </div>
        </main>
      )}
    </div>
  );
}

export function WorkspaceError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert variant="destructive" role="alert" className="my-5">
      <AlertTitle>Request needs attention</AlertTitle>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <AlertDescription>{message}</AlertDescription>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )}
      </div>
    </Alert>
  );
}

function PendingOperation({ message }: { message: string }) {
  return (
    <Alert className="my-5">
      <LoaderCircle className="animate-spin" />
      <AlertTitle>{message}</AlertTitle>
      <AlertDescription>Results appear when the operation completes.</AlertDescription>
    </Alert>
  );
}
