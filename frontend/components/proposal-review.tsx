"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  requestApi,
  proposalReviewQuery,
  proposalReviewKeys,
  type Approval,
  type ExecuteProposalResult,
} from "@/lib/api";
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

export function ProposalReview({
  runId,
  proposalId,
  employees,
  onStatusRefresh,
}: {
  runId: string;
  proposalId: string;
  employees: { id: string; name: string; role: string }[];
  onStatusRefresh: () => Promise<void>;
}) {
  const [employee, setEmployee] = useState("emp-priya");
  const queryClient = useQueryClient();
  const url = `/api/runs/${runId}/proposals/${proposalId}`;

  // 1. Fetch with reviewer-scoped caching and cancellation.
  const reviewQuery = useQuery(proposalReviewQuery({ employee, runId, proposalId }));

  // 2. Refresh confirmed records after success or an uncertain failure; never retry approval automatically.
  const approval = useMutation({
    mutationFn: () => requestApi<Approval>(`${url}/approval`, employee, { method: "POST" }),
    retry: false,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: proposalReviewKeys.proposal(runId, proposalId) }),
        onStatusRefresh(),
      ]),
  });
  const execution = useMutation({
    mutationFn: () =>
      requestApi<ExecuteProposalResult>(`${url}/execution`, employee, { method: "POST" }),
    retry: false,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ["proposal-review"] }),
        queryClient.invalidateQueries({ queryKey: ["investigation"] }),
        onStatusRefresh(),
      ]),
  });
  const busy = approval.isPending || execution.isPending || reviewQuery.isFetching;
  const error =
    approval.error?.message || execution.error?.message || reviewQuery.error?.message || "";
  const review = !error && !busy ? reviewQuery.data : undefined;

  return (
    <section className="flex flex-col gap-4" aria-label="Proposal review" aria-live="polite">
      <Field>
        <FieldLabel htmlFor="reviewer">Review or execute as</FieldLabel>
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
            approval.reset();
            execution.reset();
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
          Simulated identity. Current customer access and action permissions are checked by the
          server.
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
          approval.reset();
          execution.reset();
          void reviewQuery.refetch();
          void onStatusRefresh();
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
                {review.current_status.title}
              </Badge>
            </div>
            <CardDescription>
              {review.proposal.customer_id} · {review.proposal.integration_id} ·{" "}
              {review.proposal.environment}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            {review.execution && (
              <Alert>
                <CheckCircle2 />
                <AlertTitle>Configuration updated — delivery not yet verified</AlertTitle>
                <AlertDescription>
                  <p>
                    {review.execution.executed_by_employee_id} ·{" "}
                    {new Date(review.execution.executed_at).toLocaleString()}
                  </p>
                  <p>
                    Version {review.execution.previous_configuration_version} →{" "}
                    {review.execution.resulting_configuration_version}
                  </p>
                  <p className="break-all">Receipt: {review.execution.id}</p>
                  {execution.data && (
                    <p>
                      {execution.data.was_created
                        ? "This request updated the configuration."
                        : "Already executed; no change repeated."}
                    </p>
                  )}
                </AlertDescription>
              </Alert>
            )}
            <div className="flex flex-col gap-3 rounded-lg border p-5">
              <p className="text-xs font-medium uppercase text-muted-foreground">
                Endpoint when proposed
              </p>
              <p className="break-all font-mono text-sm">{review.proposal.current_endpoint}</p>
              <ArrowRight className="size-5 text-muted-foreground" />
              <p className="text-xs font-medium uppercase text-muted-foreground">
                Proposed endpoint
              </p>
              <p className="break-all font-mono text-sm">{review.proposal.proposed_endpoint}</p>
            </div>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Expected configuration version</dt>
                <dd className="mt-1 font-medium">
                  {review.proposal.expected_configuration_version}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Proposed by</dt>
                <dd className="mt-1 font-medium">{review.proposal.proposed_by_employee_id}</dd>
              </div>
            </dl>
            <Alert>
              <AlertTitle>Recovery plan: manual intervention</AlertTitle>
              <AlertDescription>
                If delivery verification fails, stop and request manual intervention. No automatic
                rollback is authorized.
              </AlertDescription>
            </Alert>
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
              onClick={() => approval.mutate()}
              disabled={
                busy ||
                review.current_status.code !== "awaiting_approval" ||
                employee === review.proposal.proposed_by_employee_id
              }
            >
              Approve this proposal
            </Button>
            <p className="text-xs text-muted-foreground">
              Records approval of this saved proposal, including its recovery plan. Does not execute
              the change. Delivery verification is a separate step.
            </p>
            {!review.execution && (
              <>
                <Button
                  disabled={
                    busy ||
                    !["approval_recorded", "approval_not_required"].includes(
                      review.current_status.code,
                    ) ||
                    !["implementation_engineer", "technical_lead"].includes(
                      employees.find((item) => item.id === employee)?.role ?? "",
                    )
                  }
                  onClick={() => {
                    if (
                      window.confirm(
                        `Execute ${review.proposal.ticket_id}? Change ${review.proposal.integration_id} (${review.proposal.environment}) from ${review.proposal.current_endpoint} to ${review.proposal.proposed_endpoint}. Recovery requires manual intervention. This does not verify delivery.`,
                      )
                    ) {
                      execution.mutate();
                    }
                  }}
                >
                  Execute change
                </Button>
                <p className="text-xs text-muted-foreground">
                  Execution uses the server’s actual UTC time. Production changes must be inside the
                  registered change window.
                </p>
              </>
            )}
          </CardFooter>
        </Card>
      )}
    </section>
  );
}
