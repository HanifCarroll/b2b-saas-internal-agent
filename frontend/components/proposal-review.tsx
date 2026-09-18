"use client";

import { useEffect, useState } from "react";
import { requestApi } from "@/lib/api";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Field, FieldLabel, FieldDescription } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

export function ProposalReview({
  runId,
  proposalId,
  employees,
}: {
  runId: string;
  proposalId: string;
  employees: { id: string; name: string; role: string }[];
}) {
  const [employee, setEmployee] = useState("emp-priya");
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const url = `/api/runs/${runId}/proposals/${proposalId}`;

  // 1. Reload with current reviewer access; ignore stale responses.
  useEffect(() => {
    const controller = new AbortController();
    requestApi<Review>(url, employee, { signal: controller.signal })
      .then(setReview)
      .catch((error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [url, employee, refresh]);

  // 2. Display only the receipt confirmed by the approval endpoint.
  async function approve() {
    setBusy(true);
    setError("");
    try {
      const approval = await requestApi<Approval>(`${url}/approval`, employee, {
        method: "POST",
      });
      setReview((current) => (current ? { ...current, approval } : null));
      setRefresh((value) => value + 1);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Approval could not be confirmed. Refresh before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="flex flex-col gap-4"
      aria-label="Proposal review"
      aria-live="polite"
    >
      <Field>
        <FieldLabel htmlFor="reviewer">Review as</FieldLabel>
        <Select
          items={employees.map((item) => ({
            value: item.id,
            label: `${item.name} · ${item.role.replaceAll("_", " ")}`,
          }))}
          disabled={busy}
          value={employee}
          onValueChange={(value) => {
            if (!value) return;
            setEmployee(value);
            setReview(null);
            setError("");
          }}
        >
          <SelectTrigger id="reviewer" className="w-full">
            <SelectValue placeholder="Select an option" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {employees.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name} · {item.role.replaceAll("_", " ")}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <FieldDescription>
          Simulated identity. Current customer access and approval authority are
          checked by the server.
        </FieldDescription>
      </Field>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>Review unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          setReview(null);
          setError("");
          setRefresh((value) => value + 1);
        }}
      >
        Refresh proposal
      </Button>
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
              {review.proposal.customer_id} · {review.proposal.integration_id} ·{" "}
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
                    {new Date(review.approval.created_at).toLocaleString()}
                  </p>
                  <p className="break-all">Receipt: {review.approval.id}</p>
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
              Records approval of this saved proposal. Does not execute the
              change. Execution and recovery planning are not implemented.
            </p>
          </CardFooter>
        </Card>
      )}
    </section>
  );
}
