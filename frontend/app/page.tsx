"use client";

import { useState } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Layers, LoaderCircle } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ProposalReview } from "@/components/proposal-review";
import {
  requestApi,
  demoOptionsQuery,
  historyQuery,
  investigationQuery,
  investigationKeys,
  type InvestigationRun,
  type PolicyReview,
} from "@/lib/api";
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
  const [employee, setEmployee] = useState("emp-alex");

  return (
    <QueryClientProvider client={queryClient}>
      <InvestigationWorkspace key={employee} employee={employee} onEmployeeChange={setEmployee} />
    </QueryClientProvider>
  );
}

function InvestigationWorkspace({
  employee,
  onEmployeeChange,
}: {
  employee: string;
  onEmployeeChange: (employee: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // 1. Query keys isolate each employee's data; Query manages cancellation and loading.
  const optionsQuery = useQuery(demoOptionsQuery);
  const histories = useQuery(historyQuery(employee));
  const selectedRun = useQuery(investigationQuery(employee, selectedRunId));
  const options = optionsQuery.data ?? null;
  const history = histories.data ?? [];
  const run = selectedRun.isError ? null : (selectedRun.data ?? null);

  // 2. Mutations run only on explicit user actions and never retry paid calls.
  const investigation = useMutation({
    mutationFn: (scenario: string) =>
      requestApi<InvestigationRun>("/api/investigations", employee, {
        method: "POST",
        body: JSON.stringify({ scenario_id: scenario }),
      }),
    onSuccess: (savedRun) => {
      queryClient.setQueryData(investigationKeys.run(employee, savedRun.run_id), savedRun);
      setSelectedRunId(savedRun.run_id);
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: investigationKeys.history(employee) }),
  });
  const policyEvaluation = useMutation({
    mutationFn: (runId: string) =>
      requestApi<PolicyReview>(`/api/investigations/${runId}/policy-review`, employee, {
        method: "POST",
      }),
    onSuccess: (policy_review, runId) => {
      queryClient.setQueryData<InvestigationRun>(
        investigationKeys.run(employee, runId),
        (current) => (current ? { ...current, policy_review } : current),
      );
    },
  });

  function investigate(scenario: string) {
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
  }

  function evaluatePolicy() {
    if (run) policyEvaluation.mutate(run.run_id);
  }

  // 3. Derive presentation from query and mutation state, rather than copying it.
  const pendingMessage = investigation.isPending
    ? "Investigating records and validating the result…"
    : policyEvaluation.isPending
      ? "Reviewing policy claims…"
      : selectedRun.isLoading
        ? "Loading saved investigation…"
        : "";
  const isPending = pendingMessage !== "";
  const error = (
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
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3 font-semibold">
            <Layers className="size-5" />
            Switchboard
          </div>
          <Badge variant="outline">Local demo · Simulated identities</Badge>
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-muted-foreground">
            INVESTIGATE → PROPOSE → REVIEW
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">
            From request to a reviewed change.
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            Investigate a customer request, inspect the evidence, and review the saved proposal as a
            different employee. Approval does not execute a change.
          </p>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="flex flex-col gap-5">
            <InvestigationForm
              options={options}
              employee={employee}
              busy={isPending}
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
                <AlertDescription>
                  Results appear when the operation completes. Configuration is not being changed.
                </AlertDescription>
              </Alert>
            )}
            {!run && !isPending && (
              <Card>
                <CardHeader>
                  <CardTitle>Choose a scenario to begin</CardTitle>
                  <CardDescription>
                    Try baseline for a valid proposal, then unregistered destination to see a
                    blocked request. No CLI or copied IDs needed.
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
                    employees={options.employees}
                    onStatusRefresh={() => {
                      void queryClient.invalidateQueries({
                        queryKey: investigationKeys.run(employee, run.run_id),
                      });
                    }}
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
