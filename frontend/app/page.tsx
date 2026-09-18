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
import { Layers, LoaderCircle } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ProposalReview } from "@/components/proposal-review";
import {
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
  identityKey,
  type RequestIdentity,
  type CurrentEmployee,
} from "@/lib/api";
import {
  AuthenticationGate,
  type AuthenticatedSession,
  type AccountActions,
} from "@/components/authentication-gate";
import { InvestigationForm } from "@/components/investigation-form";
import { InvestigationHistory } from "@/components/investigation-history";
import { InvestigationFindings } from "@/components/investigation-findings";

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
          <WorkspaceSession
            key={JSON.stringify(identityKey(session.identity))}
            session={session}
            accountActions={accountActions}
          />
        )}
      </AuthenticationGate>
    </QueryClientProvider>
  );
}

function WorkspaceSession({
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
      <InvestigationWorkspace
        key={JSON.stringify(identityKey(identity))}
        identity={identity}
        currentEmployee={session.employee}
        accountActions={accountActions}
        onEmployeeChange={setDemoEmployee}
      />
    </QueryClientProvider>
  );
}

function InvestigationWorkspace({
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
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // 1. Query keys isolate each employee's data; Query manages cancellation and loading.
  const optionsQuery = useQuery(demoOptionsQuery(identity));
  const demo = useQuery(demoStateQuery(identity));
  const mutationsInProgress = useIsMutating();
  const histories = useQuery(historyQuery(identity));
  const selectedRun = useQuery(investigationQuery(identity, selectedRunId));
  const options = optionsQuery.data ?? null;
  const history = histories.data ?? [];
  const run = selectedRun.isError ? null : (selectedRun.data ?? null);

  // 2. Mutations run only on explicit user actions and never retry paid calls.
  const investigation = useMutation({
    mutationFn: (scenario: string) =>
      requestApi<InvestigationRun>({
        path: "/api/investigations",
        identity,
        options: {
          method: "POST",
          body: JSON.stringify({ scenario_id: scenario }),
        },
      }),
    onSuccess: (savedRun) => {
      queryClient.setQueryData(investigationKeys.run(identity, savedRun.run_id), savedRun);
      setSelectedRunId(savedRun.run_id);
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: investigationKeys.history(identity) }),
  });
  const policyEvaluation = useMutation({
    mutationFn: (runId: string) =>
      requestApi<PolicyReview>({
        path: `/api/investigations/${runId}/policy-review`,
        identity,
        options: {
          method: "POST",
        },
      }),
    onSuccess: (policy_review, runId) => {
      queryClient.setQueryData<InvestigationRun>(
        investigationKeys.run(identity, runId),
        (current) => (current ? { ...current, policy_review } : current),
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
      setSelectedRunId(null);
      investigation.reset();
      policyEvaluation.reset();
      await queryClient.cancelQueries();
    },
    onSettled: async () => {
      await clearDemoQueries(queryClient);
      await queryClient.invalidateQueries();
    },
  });

  function investigate() {
    const scenario = demo.data?.scenario_id;
    if (!scenario) return;
    reset.reset();
    policyEvaluation.reset();
    setSelectedRunId(null);
    investigation.mutate(scenario);
  }

  function openRun(id: string) {
    investigation.reset();
    policyEvaluation.reset();
    setSelectedRunId(id);
  }

  function refreshHistory() {
    void histories.refetch();
    void demo.refetch();
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
    optionsQuery.error ??
    histories.error
  )?.message;
  const expectedOutcomes =
    options?.scenarios.find((item) => item.id === run?.scenario_id)?.expected ?? [];

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-5">
          <div className="flex items-center gap-3 font-semibold">
            <Layers className="size-5" />
            Switchboard
          </div>
          {identity.mode === "demo" ? (
            <Badge variant="outline">Local demo · Simulated identities</Badge>
          ) : (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span>Signed in as {employee}</span>
              <Button variant="outline" onClick={accountActions.onSwitchAccount}>
                Switch account
              </Button>
              <Button variant="ghost" onClick={accountActions.onSignOut}>
                Sign out
              </Button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-muted-foreground">
            INVESTIGATE → PROPOSE → REVIEW → EXECUTE
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">
            From request to a controlled change.
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            Investigate a customer request, inspect the evidence, and review the saved proposal as a
            different employee. Execute explicitly after review; delivery verification remains a
            separate step.
          </p>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="flex flex-col gap-5">
            <InvestigationForm
              authMode={identity.mode}
              options={options}
              employee={employee}
              busy={isPending || mutationsInProgress > 0 || demo.isFetching}
              activeScenario={demo.isError ? null : (demo.data?.scenario_id ?? null)}
              onReset={(scenario) => reset.mutate(scenario)}
              onEmployeeChange={onEmployeeChange}
              onInvestigate={investigate}
            />
            <InvestigationHistory
              history={history}
              selectedRunId={selectedRunId}
              busy={isPending || histories.isFetching}
              onOpenRun={openRun}
              onRefresh={refreshHistory}
            />
          </aside>
          <section className="flex min-w-0 flex-col gap-5" aria-live="polite" aria-busy={isPending}>
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Request needs attention</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {isPending && (
              <Alert>
                <LoaderCircle className="animate-spin" />
                <AlertTitle>{pendingMessage}</AlertTitle>
                <AlertDescription>Results appear when the operation completes.</AlertDescription>
              </Alert>
            )}
            {!run && !isPending && (
              <Card>
                <CardHeader>
                  <CardTitle>
                    {identity.mode === "demo"
                      ? "Initialize the demo, then investigate"
                      : "Investigate the active scenario"}
                  </CardTitle>
                  <CardDescription>
                    {identity.mode === "demo"
                      ? "Reset to baseline for a valid proposal. Reset explicitly to try another starting state."
                      : "If no scenario is active, prepare the synthetic data through the local CLI."}{" "}
                    Starting an investigation never resets business records.
                  </CardDescription>
                </CardHeader>
              </Card>
            )}
            {run && (
              <>
                <Alert
                  variant={run.current_status.code === "unavailable" ? "destructive" : "default"}
                >
                  <AlertTitle>
                    {selectedRun.isFetching
                      ? "Refreshing current status…"
                      : `Current status: ${run.current_status.title}`}
                  </AlertTitle>
                  <AlertDescription>
                    {selectedRun.isFetching
                      ? "Checking the latest saved records."
                      : run.current_status.next_action}
                  </AlertDescription>
                </Alert>
                <InvestigationFindings
                  run={run}
                  expectedOutcomes={expectedOutcomes}
                  busy={isPending}
                  onEvaluatePolicy={evaluatePolicy}
                />
                {run.result.proposal && options && (
                  <ProposalReview
                    key={run.run_id}
                    runId={run.run_id}
                    proposalId={run.result.proposal.id}
                    identity={identity}
                    currentEmployee={currentEmployee}
                    employees={options.employees}
                    onStatusRefresh={() =>
                      queryClient.invalidateQueries({
                        queryKey: investigationKeys.run(identity, run.run_id),
                      })
                    }
                  />
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
