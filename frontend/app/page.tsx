"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, CheckCircle2, Layers, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";

type Approval = {
  id: string;
  approved_by_employee_id: string;
  created_at: string;
};
type Review = {
  proposal: {
    id: string;
    ticket_id: string;
    customer_id: string;
    integration_id: string;
    environment: string;
    current_endpoint: string;
    proposed_endpoint: string;
    expected_configuration_version: number;
    proposed_by_employee_id: string;
  };
  approval: Approval | null;
};

export default function Home() {
  const [runId, setRunId] = useState("");
  const [proposalId, setProposalId] = useState("");
  const [employee, setEmployee] = useState("emp-priya");
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const url = `/api/runs/${encodeURIComponent(runId.trim())}/proposals/${encodeURIComponent(proposalId.trim())}`;

  async function readReview(): Promise<Review> {
    const response = await fetch(url, {
      headers: { "X-Employee-Id": employee },
      cache: "no-store",
    });
    if (!response.ok)
      throw new Error(
        response.status === 404
          ? "Proposal unavailable. Check the IDs and this employee’s customer access."
          : "Unable to load the proposal. Check the run ID and that the API is running.",
      );
    return response.json();
  }

  async function load(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setReview(null);
    try {
      setReview(await readReview());
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to load proposal.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${url}/approval`, {
        method: "POST",
        headers: { "X-Employee-Id": employee },
      });
      if (!response.ok)
        throw new Error(
          response.status === 403
            ? "Approval denied. An active, assigned technical lead other than the proposer is required."
            : "Approval could not be confirmed. Reload the proposal before retrying.",
        );
      const approval: Approval = await response.json();
      // Keep the confirmed receipt even if the following refresh fails.
      setReview((current) => (current ? { ...current, approval } : null));
      setReview(await readReview());
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to confirm approval. Reload before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }

  function changeInput(setter: (value: string) => void, value: string) {
    setter(value);
    setReview(null);
    setError("");
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3 font-semibold">
            <Layers className="size-5" />
            Switchboard
          </div>
          <Badge variant="outline">Local demo</Badge>
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-12">
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-muted-foreground">
            CHANGE MANAGEMENT / REVIEW
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">
            A deliberate step before change.
          </h1>
          <p className="max-w-2xl text-muted-foreground">
            Review the saved endpoint change and record an independent approval.
            Configuration stays unchanged.
          </p>
        </div>
        <div className="grid items-start gap-6 lg:grid-cols-[340px_1fr]">
          <Card>
            <CardHeader>
              <CardTitle>Open a proposal</CardTitle>
              <CardDescription>
                Use the IDs printed by an investigation.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form id="review-form" onSubmit={load}>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="run">Run ID</FieldLabel>
                    <Input
                      id="run"
                      required
                      disabled={busy}
                      value={runId}
                      placeholder="Investigation run UUID"
                      onChange={(e) => changeInput(setRunId, e.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="proposal">Proposal ID</FieldLabel>
                    <Input
                      id="proposal"
                      required
                      disabled={busy}
                      value={proposalId}
                      placeholder="Saved proposal UUID"
                      onChange={(e) =>
                        changeInput(setProposalId, e.target.value)
                      }
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="employee">
                      Simulated employee
                    </FieldLabel>
                    <NativeSelect
                      id="employee"
                      disabled={busy}
                      value={employee}
                      onChange={(e) => changeInput(setEmployee, e.target.value)}
                    >
                      <NativeSelectOption value="emp-priya">
                        Priya · Technical lead
                      </NativeSelectOption>
                      <NativeSelectOption value="emp-alex">
                        Alex · Proposing engineer
                      </NativeSelectOption>
                      <NativeSelectOption value="emp-ben">
                        Ben · Different customer
                      </NativeSelectOption>
                    </NativeSelect>
                    <FieldDescription>
                      Demo identity only. This is not sign-in. Permissions use
                      the run’s current employee records.
                    </FieldDescription>
                  </Field>
                </FieldGroup>
              </form>
            </CardContent>
            <CardFooter>
              <Button
                form="review-form"
                type="submit"
                disabled={busy}
                className="w-full"
              >
                {busy ? "Working…" : "Load proposal"}
              </Button>
            </CardFooter>
          </Card>
          <section
            className="flex flex-col gap-5"
            aria-live="polite"
            aria-busy={busy}
          >
            {error && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>Request needs attention</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            {!review && (
              <Card>
                <CardHeader>
                  <ShieldCheck className="mb-3 size-8 text-muted-foreground" />
                  <CardTitle>
                    {busy ? "Checking access…" : "Ready for review"}
                  </CardTitle>
                  <CardDescription>
                    Open a proposal to inspect the exact change, configuration
                    version, and approval record.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    Only employees assigned to the customer can view its
                    proposals. Approval requires an independent technical lead.
                  </p>
                </CardContent>
              </Card>
            )}
            {review && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>{review.proposal.ticket_id}</CardTitle>
                    <Badge variant={review.approval ? "default" : "secondary"}>
                      {review.approval
                        ? "Approval recorded"
                        : review.proposal.environment === "sandbox"
                          ? "Independent approval not required"
                          : "Awaiting approval"}
                    </Badge>
                  </div>
                  <CardDescription>
                    {review.proposal.customer_id} ·{" "}
                    {review.proposal.integration_id} ·{" "}
                    {review.proposal.environment}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3 rounded-lg border p-5">
                    <p className="text-xs font-medium uppercase text-muted-foreground">
                      Current endpoint
                    </p>
                    <p className="break-all font-mono text-sm">
                      {review.proposal.current_endpoint}
                    </p>
                    <ArrowRight className="size-5 text-muted-foreground" />
                    <p className="text-xs font-medium uppercase text-muted-foreground">
                      Proposed endpoint
                    </p>
                    <p className="break-all font-mono text-sm">
                      {review.proposal.proposed_endpoint}
                    </p>
                  </div>
                  <dl className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <dt className="text-muted-foreground">
                        Expected configuration version
                      </dt>
                      <dd className="mt-1 font-medium">
                        {review.proposal.expected_configuration_version}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Proposed by</dt>
                      <dd className="mt-1 font-medium">
                        {review.proposal.proposed_by_employee_id}
                      </dd>
                    </div>
                  </dl>
                  {review.approval && (
                    <Alert>
                      <CheckCircle2 />
                      <AlertTitle>Stored approval</AlertTitle>
                      <AlertDescription>
                        <p>
                          {review.approval.approved_by_employee_id} ·{" "}
                          {new Date(
                            review.approval.created_at,
                          ).toLocaleString()}
                        </p>
                        <p className="break-all">
                          Receipt: {review.approval.id}
                        </p>
                      </AlertDescription>
                    </Alert>
                  )}
                </CardContent>
                <CardFooter className="flex flex-col items-start gap-3">
                  <Button
                    onClick={approve}
                    disabled={
                      busy ||
                      !!review.approval ||
                      review.proposal.environment !== "production" ||
                      employee === review.proposal.proposed_by_employee_id
                    }
                  >
                    Approve this proposal
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Records approval of this saved proposal. Does not execute
                    the change. Execution and recovery planning are not
                    implemented.
                  </p>
                </CardFooter>
              </Card>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
