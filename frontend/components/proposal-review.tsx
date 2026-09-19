"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import {
  requestApi,
  proposalReviewQuery,
  proposalReviewKeys,
  type Approval,
  type RequestIdentity,
  type CurrentEmployee,
  type ExecuteProposalResult,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
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
  identity,
  currentEmployee,
  employees,
  onStatusRefresh,
}: {
  runId: string;
  proposalId: string;
  identity: RequestIdentity;
  currentEmployee: CurrentEmployee | null;
  employees: { id: string; name: string; role: string }[];
  onStatusRefresh: () => Promise<void>;
}) {
  const [demoEmployee, setEmployee] = useState("emp-priya");
  const employee = identity.mode === "demo" ? demoEmployee : currentEmployee!.employee_id;
  const reviewerIdentity: RequestIdentity =
    identity.mode === "demo" ? { mode: "demo", employeeId: employee } : identity;
  const role =
    identity.mode === "demo"
      ? employees.find((item) => item.id === employee)?.role
      : currentEmployee?.role;
  const queryClient = useQueryClient();
  const url = `/api/runs/${runId}/proposals/${proposalId}`;

  // 1. Fetch with reviewer-scoped caching and cancellation.
  const reviewQuery = useQuery(
    proposalReviewQuery({ identity: reviewerIdentity, runId, proposalId }),
  );

  // 2. Refresh confirmed records after success or an uncertain failure; never retry writes.
  const approval = useMutation({
    mutationFn: () =>
      requestApi<Approval>({
        path: `${url}/approval`,
        identity: reviewerIdentity,
        options: { method: "POST" },
      }),
    retry: false,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: proposalReviewKeys.proposal(runId, proposalId) }),
        queryClient.invalidateQueries({ queryKey: proposalReviewKeys.inbox(reviewerIdentity) }),
        onStatusRefresh(),
      ]),
  });
  const execution = useMutation({
    mutationFn: () =>
      requestApi<ExecuteProposalResult>({
        path: `${url}/execution`,
        identity: reviewerIdentity,
        options: { method: "POST" },
      }),
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
    <section className="py-7" aria-label="Proposal review" aria-live="polite">
      <div className="flex flex-wrap items-end justify-between gap-4">
        {identity.mode === "demo" && (
          <Field className="w-full max-w-sm">
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
              Simulated identity. Access and action permissions are checked by the server.
            </FieldDescription>
          </Field>
        )}
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => {
            approval.reset();
            execution.reset();
            void reviewQuery.refetch();
            void onStatusRefresh();
          }}
        >
          <RefreshCw className="size-4" />
          Refresh proposal
        </Button>
      </div>

      {error && (
        <Alert variant="destructive" className="mt-5">
          <AlertTitle>Review unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {review && (
        <div className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Proposed change</h2>
            <Badge variant={review.approval ? "default" : "secondary"}>
              {review.current_status.title}
            </Badge>
          </div>

          {review.execution && (
            <Alert className="mt-5 border-emerald-200 bg-emerald-50/70">
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

          <div className="mt-4 grid items-center gap-3 rounded-lg border bg-slate-50/60 p-5 md:grid-cols-[1fr_auto_1fr]">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Before
              </p>
              <p className="mt-2 break-all rounded-md bg-white p-3 font-mono text-xs">
                {review.proposal.current_endpoint}
              </p>
            </div>
            <ArrowRight className="size-5 rotate-90 text-muted-foreground md:rotate-0" />
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                After
              </p>
              <p className="mt-2 break-all rounded-md border border-emerald-200 bg-emerald-50 p-3 font-mono text-xs text-emerald-950">
                {review.proposal.proposed_endpoint}
              </p>
            </div>
          </div>

          <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Expected configuration version</dt>
              <dd className="mt-1 font-medium">{review.proposal.expected_configuration_version}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Proposed by</dt>
              <dd className="mt-1 font-medium">{review.proposal.proposed_by_employee_id}</dd>
            </div>
          </dl>

          <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50/70 p-4">
            <div className="flex gap-3">
              <ShieldCheck className="mt-0.5 size-5 text-amber-700" aria-hidden="true" />
              <div>
                <p className="font-semibold text-amber-950">Independent approval required</p>
                <p className="mt-1 text-sm leading-6 text-amber-900">
                  Production changes require an authorized reviewer who is different from the
                  proposer. Approval records the decision; it does not execute the change.
                </p>
              </div>
            </div>
          </div>

          <Alert className="mt-5">
            <AlertTitle>Recovery plan: manual intervention</AlertTitle>
            <AlertDescription>
              If delivery verification fails, stop and request manual intervention. No automatic
              rollback is authorized.
            </AlertDescription>
          </Alert>

          {review.approval && (
            <Alert className="mt-5 border-emerald-200 bg-emerald-50/70">
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

          <div className="mt-6 flex flex-wrap items-center gap-3 border-t pt-5">
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
            {!review.execution && (
              <Button
                variant="outline"
                disabled={
                  busy ||
                  !["approval_recorded", "approval_not_required"].includes(
                    review.current_status.code,
                  ) ||
                  !["implementation_engineer", "technical_lead"].includes(role ?? "")
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
            )}
            <p className="max-w-xl text-xs leading-5 text-muted-foreground">
              Execution uses the server’s UTC time and requires a valid change window. Delivery
              verification remains a separate step.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
