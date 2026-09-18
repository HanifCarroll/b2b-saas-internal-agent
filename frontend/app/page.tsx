"use client";

import { FormEvent, useEffect, useState } from "react";
import { Layers, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ProposalReview } from "@/components/proposal-review";
import { requestApi } from "@/lib/api";

type DemoOptions = {
  scenarios: { id: string; expected: string[] }[];
  employees: { id: string; name: string; role: string }[];
};
type HistoryItem = { run_id: string; scenario_id: string; outcome: string };
type PolicyReview = {
  issues: {
    claim: string;
    policy_id: string;
    policy_excerpt: string;
    explanation: string;
  }[];
  limitation: string;
};
type Run = {
  run_id: string;
  scenario_id: string;
  policy_review: PolicyReview | null;
  result: {
    investigation: {
      outcome: string;
      summary: string;
      blockers: string[];
      evidence_ids: string[];
    };
    proposal: { id: string } | null;
    was_created: boolean | null;
    messages: {
      tool_calls?: {
        id: string;
        name: string;
        args: Record<string, unknown>;
      }[];
    }[];
  };
};

export default function Home() {
  const [options, setOptions] = useState<DemoOptions | null>(null);
  const [scenario, setScenario] = useState("baseline");
  const [employee, setEmployee] = useState("emp-alex");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  // 1. Load demo choices and this employee's accessible completed runs.
  useEffect(() => {
    const controller = new AbortController();
    requestApi<DemoOptions>("/api/demo-options", "", {
      signal: controller.signal,
    })
      .then(setOptions)
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    requestApi<HistoryItem[]>("/api/investigations", employee, {
      signal: controller.signal,
    })
      .then(setHistory)
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [employee, refresh]);

  // 2. Run a scenario and display the workflow's confirmed storage outcome.
  async function investigate(event: FormEvent) {
    event.preventDefault();
    setBusy("Investigating records and validating the result…");
    setError("");
    setRun(null);
    try {
      setRun(
        await requestApi<Run>("/api/investigations", employee, {
          method: "POST",
          body: JSON.stringify({ scenario_id: scenario }),
        }),
      );
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Investigation could not complete.",
      );
    } finally {
      setBusy("");
      setRefresh((value) => value + 1);
    }
  }

  async function openRun(id: string) {
    if (!id) return;
    setBusy("Loading saved investigation…");
    setError("");
    setRun(null);
    try {
      setRun(await requestApi<Run>(`/api/investigations/${id}`, employee));
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Investigation unavailable.",
      );
    } finally {
      setBusy("");
    }
  }

  // 3. Keep optional model judgment separate from deterministic approval.
  async function evaluatePolicy() {
    if (!run) return;
    setBusy("Reviewing policy claims…");
    setError("");
    try {
      const policy_review = await requestApi<PolicyReview>(
        `/api/investigations/${run.run_id}/policy-review`,
        employee,
        { method: "POST" },
      );
      setRun({ ...run, policy_review });
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Policy review could not complete.",
      );
    } finally {
      setBusy("");
    }
  }

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
            Investigate a customer request, inspect the evidence, and review the
            saved proposal as a different employee. Approval does not execute a
            change.
          </p>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="flex flex-col gap-5">
            <Card>
              <CardHeader>
                <CardTitle>Start an investigation</CardTitle>
                <CardDescription>
                  Each run uses isolated fictional business records.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={investigate} className="flex flex-col gap-5">
                  <FieldGroup>
                    <Field>
                      <FieldLabel htmlFor="scenario">Scenario</FieldLabel>
                      <NativeSelect
                        id="scenario"
                        value={scenario}
                        disabled={!!busy || !options}
                        onChange={(event) => setScenario(event.target.value)}
                      >
                        {options?.scenarios.map((item) => (
                          <NativeSelectOption key={item.id} value={item.id}>
                            {item.id.replaceAll("-", " ")}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="employee">Investigate as</FieldLabel>
                      <NativeSelect
                        id="employee"
                        value={employee}
                        disabled={!!busy || !options}
                        onChange={(event) => {
                          setEmployee(event.target.value);
                          setRun(null);
                          setHistory([]);
                          setError("");
                        }}
                      >
                        {options?.employees.map((item) => (
                          <NativeSelectOption key={item.id} value={item.id}>
                            {item.name}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                      <FieldDescription>
                        Demo identity only, not sign-in. Customer access is
                        enforced in Python.
                      </FieldDescription>
                    </Field>
                  </FieldGroup>
                  <Button type="submit" disabled={!!busy || !options}>
                    Start investigation
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Uses your configured model API. May take a minute; avoid
                    starting duplicate runs.
                  </p>
                </form>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Saved investigations</CardTitle>
                <CardDescription>
                  Completed runs for the selected investigator.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <Field>
                  <FieldLabel htmlFor="history">Open a previous run</FieldLabel>
                  <NativeSelect
                    id="history"
                    disabled={!!busy}
                    value={run?.run_id ?? ""}
                    onChange={(event) => openRun(event.target.value)}
                  >
                    <NativeSelectOption value="">
                      Choose a run
                    </NativeSelectOption>
                    {history.map((item) => (
                      <NativeSelectOption key={item.run_id} value={item.run_id}>
                        {item.scenario_id.replaceAll("-", " ")} ·{" "}
                        {item.outcome === "blocked" ? "Blocked" : "Proposal"} ·{" "}
                        {item.run_id.slice(0, 8)}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
                </Field>
                <Button
                  variant="outline"
                  disabled={!!busy}
                  onClick={() => {
                    setError("");
                    setRefresh((value) => value + 1);
                  }}
                >
                  Refresh history
                </Button>
                {!history.length && (
                  <p className="text-sm text-muted-foreground">
                    No accessible completed runs yet.
                  </p>
                )}
              </CardContent>
            </Card>
          </aside>
          <section
            className="flex min-w-0 flex-col gap-5"
            aria-live="polite"
            aria-busy={!!busy}
          >
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Request needs attention</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {busy && (
              <Alert>
                <LoaderCircle className="animate-spin" />
                <AlertTitle>{busy}</AlertTitle>
                <AlertDescription>
                  Results appear when the operation completes. Configuration is
                  not being changed.
                </AlertDescription>
              </Alert>
            )}
            {!run && !busy && (
              <Card>
                <CardHeader>
                  <CardTitle>Choose a scenario to begin</CardTitle>
                  <CardDescription>
                    Try baseline for a valid proposal, then unregistered
                    destination to see a blocked request. No CLI or copied IDs
                    needed.
                  </CardDescription>
                </CardHeader>
              </Card>
            )}
            {run && (
              <>
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle>Investigation findings</CardTitle>
                      <Badge variant="secondary">
                        {run.result.investigation.outcome === "blocked"
                          ? "Blocked"
                          : "Investigation complete"}
                      </Badge>
                    </div>
                    <CardDescription>
                      {run.scenario_id.replaceAll("-", " ")} · Run{" "}
                      {run.run_id.slice(0, 8)}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-5">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {run.result.investigation.summary}
                    </p>
                    {run.result.investigation.blockers.length > 0 && (
                      <Alert variant="destructive">
                        <AlertTitle>Blockers — no proposal saved</AlertTitle>
                        <AlertDescription>
                          <ul className="list-disc pl-5">
                            {run.result.investigation.blockers.map(
                              (item, index) => (
                                <li key={index}>{item}</li>
                              ),
                            )}
                          </ul>
                        </AlertDescription>
                      </Alert>
                    )}
                    <p className="text-sm text-muted-foreground">
                      Evidence:{" "}
                      {run.result.investigation.evidence_ids.join(", ") ||
                        "No records retrieved"}
                    </p>
                    {run.result.proposal && (
                      <Alert>
                        <AlertTitle>
                          {run.result.was_created
                            ? "Proposal saved"
                            : "Existing proposal reused"}
                        </AlertTitle>
                        <AlertDescription>
                          {run.result.was_created
                            ? "Review the saved change below."
                            : "An identical proposal already exists. No duplicate was created; its current approval is shown below."}
                        </AlertDescription>
                      </Alert>
                    )}
                    <details>
                      <summary className="cursor-pointer text-sm font-medium">
                        Tool calls
                      </summary>
                      <ul className="mt-3 flex flex-col gap-2 text-sm">
                        {run.result.messages
                          .flatMap((message) => message.tool_calls ?? [])
                          .map((call) => (
                            <li className="break-all" key={call.id}>
                              <code>
                                {call.name} {JSON.stringify(call.args)}
                              </code>
                            </li>
                          ))}
                      </ul>
                    </details>
                    <details>
                      <summary className="cursor-pointer text-sm font-medium">
                        Expected outcomes for manual comparison
                      </summary>
                      <ul className="mt-3 list-disc pl-5 text-sm">
                        {options?.scenarios
                          .find((item) => item.id === run.scenario_id)
                          ?.expected.map((item, index) => (
                            <li key={index}>{item}</li>
                          ))}
                      </ul>
                    </details>
                    <Button
                      variant="outline"
                      disabled={!!busy}
                      onClick={evaluatePolicy}
                    >
                      Evaluate policy claims · extra model call
                    </Button>
                    {run.policy_review && (
                      <Alert>
                        <AlertTitle>
                          Policy review:{" "}
                          {run.policy_review.issues.length
                            ? `${run.policy_review.issues.length} issue(s)`
                            : "No issues identified"}
                        </AlertTitle>
                        <AlertDescription>
                          <p>{run.policy_review.limitation}</p>
                          {run.policy_review.issues.map((issue, index) => (
                            <div key={index} className="flex flex-col gap-1">
                              <p>{issue.claim}</p>
                              <p>{issue.explanation}</p>
                              <p>
                                Source {issue.policy_id}: {issue.policy_excerpt}
                              </p>
                            </div>
                          ))}
                        </AlertDescription>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
                {run.result.proposal && options && (
                  <ProposalReview
                    key={run.run_id}
                    runId={run.run_id}
                    proposalId={run.result.proposal.id}
                    employees={options.employees}
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
