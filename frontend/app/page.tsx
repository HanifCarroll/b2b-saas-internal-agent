"use client";

import { useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useIsMutating,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
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
  requestApi,
  demoOptionsQuery,
  demoStateQuery,
  clearDemoQueries,
  type DemoState,
  historyQuery,
  investigationQuery,
  investigationKeys,
  type InvestigationRun,
  type PolicyReview,
  ticketsQuery,
  identityKey,
  type RequestIdentity,
  type CurrentEmployee,
  type ApprovalInboxItem,
  proposalReviewKeys,
} from "@/lib/api";
import {
  AuthenticationGate,
  type AuthenticatedSession,
  type AccountActions,
} from "@/components/authentication-gate";
import { DemoControls } from "@/components/demo-controls";
import { InvestigationHistory } from "@/components/investigation-history";
import { InvestigationFindings } from "@/components/investigation-findings";
import { TicketDetail } from "@/components/ticket-detail";
import { TicketList } from "@/components/ticket-list";
import { WorkflowProgress } from "@/components/workflow-progress";
import { WorkspaceSidebar } from "@/components/workspace-sidebar";

export default function Home() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, refetchOnWindowFocus: false },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthenticationGate>
        {(session, accountActions) => (
          <TicketWorkspaceSession
            key={JSON.stringify(identityKey(session.identity))}
            session={session}
            accountActions={accountActions}
          />
        )}
      </AuthenticationGate>
    </QueryClientProvider>
  );
}

function TicketWorkspaceSession({
  session,
  accountActions,
}: {
  session: AuthenticatedSession;
  accountActions: AccountActions;
}) {
  // A fresh cache per session prevents late responses from reaching another account.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, refetchOnWindowFocus: false },
          mutations: { retry: false },
        },
      }),
  );
  const [demoEmployee, setDemoEmployee] = useState("emp-alex");
  const identity: RequestIdentity =
    session.identity.mode === "demo"
      ? { mode: "demo", employeeId: demoEmployee }
      : session.identity;
  return (
    <QueryClientProvider client={queryClient}>
      <TicketWorkspace
        key={JSON.stringify(identityKey(identity))}
        identity={identity}
        currentEmployee={session.employee}
        accountActions={accountActions}
        onEmployeeChange={setDemoEmployee}
      />
    </QueryClientProvider>
  );
}

function TicketWorkspace({
  identity,
  currentEmployee,
  accountActions,
  onEmployeeChange,
}: {
  identity: RequestIdentity;
  currentEmployee: CurrentEmployee | null;
  accountActions: AccountActions;
  onEmployeeChange: (employee: string) => void;
}) {
  const employee = identity.mode === "demo" ? identity.employeeId : currentEmployee!.employee_id;
  const queryClient = useQueryClient();
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<"work" | "approvals">("work");
  const [selectedApproval, setSelectedApproval] = useState<ApprovalInboxItem | null>(null);
  const [ticketSearch, setTicketSearch] = useState("");

  // 1. Query keys isolate each employee's data; Query manages cancellation and loading.
  const optionsQuery = useQuery({
    ...demoOptionsQuery(identity),
    enabled: identity.mode === "demo",
  });
  const demo = useQuery({ ...demoStateQuery(identity), enabled: identity.mode === "demo" });
  const ticketsQueryResult = useQuery(ticketsQuery(identity));
  const approvalsQueryResult = useQuery({
    ...approvalInboxQuery(identity),
    enabled: activeView === "approvals",
  });
  const mutationsInProgress = useIsMutating();
  const historyQueryResult = useQuery(historyQuery(identity, selectedTicketId));
  const selectedRun = useQuery(investigationQuery(identity, selectedRunId));
  const options = optionsQuery.data ?? null;
  const tickets = ticketsQueryResult.data ?? [];
  const approvals = approvalsQueryResult.data ?? [];
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
  const employeeRecord = options?.employees.find((item) => item.id === employee);
  const employeeName = employeeRecord?.name ?? employee;
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
      setSelectedTicketId(savedRun.ticket_id);
      setSelectedRunId(savedRun.run_id);
    },
    onSettled: (_data, _error, ticketId) =>
      queryClient.invalidateQueries({ queryKey: investigationKeys.history(identity, ticketId) }),
  });
  const policyEvaluation = useMutation({
    mutationFn: (runId: string) =>
      requestApi<PolicyReview>({
        path: `/api/investigations/${runId}/policy-review`,
        identity,
        options: { method: "POST" },
      }),
    onSuccess: (policyReview, runId) => {
      queryClient.setQueryData<InvestigationRun>(
        investigationKeys.run(identity, runId),
        (current) => (current ? { ...current, policy_review: policyReview } : current),
      );
    },
  });
  const reset = useMutation({
    mutationFn: (scenario: string) =>
      requestApi<DemoState>({
        path: "/api/demo/reset",
        identity,
        options: {
          method: "POST",
          body: JSON.stringify({ scenario_id: scenario, confirm: true }),
        },
      }),
    onMutate: async () => {
      clearSelection();
      investigation.reset();
      policyEvaluation.reset();
      await queryClient.cancelQueries();
    },
    onSettled: async () => {
      await clearDemoQueries(queryClient);
      await queryClient.invalidateQueries();
    },
  });

  function startTicketInvestigation(ticketId: string) {
    reset.reset();
    policyEvaluation.reset();
    setSelectedRunId(null);
    investigation.mutate(ticketId);
  }

  function selectTicket(ticketId: string) {
    setActiveView("work");
    setSelectedApproval(null);
    investigation.reset();
    policyEvaluation.reset();
    setSelectedRunId(null);
    setSelectedTicketId(ticketId);
  }

  function clearSelection() {
    setActiveView("work");
    setSelectedApproval(null);
    setSelectedTicketId(null);
    setSelectedRunId(null);
  }

  function openApprovals() {
    setActiveView("approvals");
    setSelectedTicketId(null);
    setSelectedRunId(null);
    investigation.reset();
    policyEvaluation.reset();
  }

  function openRun(id: string) {
    investigation.reset();
    policyEvaluation.reset();
    setSelectedRunId(id);
  }

  function refreshHistory() {
    void historyQueryResult.refetch();
  }

  function evaluatePolicy() {
    if (run) policyEvaluation.mutate(run.run_id);
  }

  // 3. Derive presentation from query and mutation state, rather than copying it.
  const pendingMessage = reset.isPending
    ? "Resetting demo records…"
    : investigation.isPending
      ? "Investigating records and validating the result…"
      : policyEvaluation.isPending
        ? "Reviewing policy claims…"
        : selectedRun.isLoading
          ? "Loading saved investigation…"
          : "";
  const isPending = pendingMessage !== "";
  const error = (
    reset.error ??
    demo.error ??
    investigation.error ??
    policyEvaluation.error ??
    selectedRun.error ??
    ticketsQueryResult.error ??
    approvalsQueryResult.error ??
    optionsQuery.error ??
    historyQueryResult.error
  )?.message;
  const sidebarDemoControls =
    identity.mode === "demo" ? (
      <details className="rounded-lg border border-white/10 bg-white/5 p-2">
        <summary className="cursor-pointer px-1 text-xs font-medium text-slate-300">
          Demo controls
        </summary>
        <div className="mt-2 overflow-hidden rounded-lg bg-white text-slate-950">
          <DemoControls
            options={options}
            employee={employee}
            busy={isPending || mutationsInProgress > 0 || demo.isFetching}
            activeScenario={demo.isError ? null : (demo.data?.scenario_id ?? null)}
            onReset={(scenario) => reset.mutate(scenario)}
            onEmployeeChange={onEmployeeChange}
          />
        </div>
      </details>
    ) : undefined;

  return (
    <div className="min-h-screen bg-[#f7f8fa] lg:pl-60">
      <WorkspaceSidebar
        activeView={activeView}
        employee={employeeName}
        role={employeeRole}
        accountControls={identity.mode === "entra" ? accountActions : null}
        demoControls={sidebarDemoControls}
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
            {error && <WorkspaceError message={error} />}
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
                selectedProposalId={selectedApproval?.proposal.id ?? null}
                busy={approvalsQueryResult.isFetching}
                onSelect={setSelectedApproval}
              />
            </section>

            {selectedApproval && (
              <section className="mt-8 rounded-xl border bg-white px-6 shadow-sm">
                <ProposalReview
                  key={selectedApproval.proposal.id}
                  runId={selectedApproval.run_id}
                  proposalId={selectedApproval.proposal.id}
                  identity={identity}
                  currentEmployee={currentEmployee}
                  employees={options?.employees ?? []}
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
            {error && <WorkspaceError message={error} />}
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
                    <span>Owner: {employeeName}</span>
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
              status={run?.current_status ?? null}
            />

            {error && <WorkspaceError message={error} />}
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
                    <InvestigationFindings
                      run={run}
                      busy={isPending}
                      onEvaluatePolicy={evaluatePolicy}
                    />
                    {run.result.proposal && (
                      <ProposalReview
                        key={run.run_id}
                        runId={run.run_id}
                        proposalId={run.result.proposal.id}
                        identity={identity}
                        currentEmployee={currentEmployee}
                        employees={options?.employees ?? []}
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
                    {run?.current_status.code === "blocked" ? (
                      <CircleAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
                    ) : (
                      <ShieldCheck className="mt-0.5 size-5 shrink-0 text-amber-600" />
                    )}
                    <div>
                      <p className="font-medium">
                        {run?.current_status.title ?? "Ready to investigate"}
                      </p>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {run?.current_status.next_action ??
                          "Run an investigation to gather evidence and determine the next action."}
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
                    <dd>{selectedTicket.assigned_employee_id}</dd>
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

function WorkspaceError({ message }: { message: string }) {
  return (
    <Alert variant="destructive" role="alert" className="my-5">
      <AlertTitle>Request needs attention</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
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
