import {
  CheckCircle2,
  CircleAlert,
  CircleHelp,
  Clock3,
  FileCheck2,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import type {
  CriterionStatus,
  DecisionCriterion,
  InvestigationBlocker,
  InvestigationRun,
} from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { evidencePath } from "@/lib/workspace-routes";

export function InvestigationFindings({ run }: { run: InvestigationRun }) {
  const { investigation, messages, report_validation: validation } = run.result;
  const { findings } = investigation;
  const toolCalls = messages.flatMap((message) => message.tool_calls ?? []);

  return (
    <section className="border-b py-7" aria-labelledby="agent-conclusion-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="agent-conclusion-title" className="flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="size-5 text-blue-700" aria-hidden="true" />
          Agent conclusion
        </h2>
        <Badge variant="secondary">
          {investigation.outcome === "blocked" ? "Blocked" : "Investigation complete"}
        </Badge>
      </div>

      <div className="mt-4 rounded-lg border bg-slate-50/70 p-5">
        <p className="text-sm leading-6 text-slate-800">{findings.overview}</p>
        <p className="mt-3 text-sm font-medium text-slate-900">{findings.recommendation}</p>
      </div>

      <DecisionCriteria criteria={findings.decision_criteria} run={run} />
      <AttentionItems blockers={investigation.blockers} />

      {run.result.proposal && (
        <Alert className="mt-5 border-amber-200 bg-amber-50/60">
          <AlertTitle>
            {run.result.was_created ? "Proposal saved" : "Existing proposal reused"}
          </AlertTitle>
          <AlertDescription>
            {run.result.was_created
              ? "The proposed change is ready for independent review."
              : "An identical proposal already exists. No duplicate was created during this run."}
          </AlertDescription>
        </Alert>
      )}

      <details id="technical-investigation-details" className="mt-5 rounded-lg border px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
        <div className="mt-4 flex flex-col gap-4 text-sm text-muted-foreground">
          <div>
            <p className="font-medium text-foreground">Evidence records</p>
            {investigation.evidence_ids.length ? (
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-2">
                {investigation.evidence_ids.map((evidenceId) => (
                  <EvidenceReference key={evidenceId} evidenceId={evidenceId} run={run} />
                ))}
              </div>
            ) : (
              <p className="mt-2">None retrieved</p>
            )}
          </div>
          <p>Governing policies: {validation.policy_ids.join(", ")}</p>
          <p>
            Policy claims validated automatically with {validation.evaluation_count} evaluation
            {validation.evaluation_count === 1 ? "" : "s"} and {validation.revision_count} revision
            {validation.revision_count === 1 ? "" : "s"}.
          </p>
          <div>
            <p className="font-medium text-foreground">Tool calls ({toolCalls.length})</p>
            {toolCalls.length === 0 ? (
              <p className="mt-2">No tool calls were recorded.</p>
            ) : (
              <ul className="mt-2 space-y-2">
                {toolCalls.map((call) => (
                  <li className="break-all font-mono text-xs" key={call.id}>
                    {call.name} {JSON.stringify(call.args)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </details>
    </section>
  );
}

function DecisionCriteria({
  criteria,
  run,
}: {
  criteria: DecisionCriterion[];
  run: InvestigationRun;
}) {
  if (!criteria.length) return null;

  return (
    <section className="mt-7" aria-labelledby="decision-criteria-title">
      <h3 id="decision-criteria-title" className="flex items-center gap-2 font-semibold">
        <FileCheck2 className="size-4" aria-hidden="true" />
        Decision criteria
      </h3>
      <div className="mt-3 overflow-hidden rounded-lg border">
        {criteria.map((criterion) => {
          const presentation = criterionPresentation(criterion.status);
          const StatusIcon = presentation.icon;
          const sourceIds = Array.from(
            new Set([
              ...(criterion.policy_id ? [criterion.policy_id] : []),
              ...criterion.evidence_ids,
            ]),
          );

          return (
            <div
              key={`${criterion.name}-${criterion.required_before}`}
              className="flex items-start gap-3 border-b px-4 py-3 last:border-b-0"
            >
              <StatusIcon className={`mt-0.5 size-5 shrink-0 ${presentation.iconClass}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{criterion.name}</p>
                  <Badge variant="secondary" className={presentation.badgeClass}>
                    {presentation.label}
                  </Badge>
                  {criterion.status === "deferred" && (
                    <span className="text-xs text-muted-foreground">
                      Required before {criterion.required_before}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {criterion.explanation}
                </p>
                {sourceIds.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span>Sources:</span>
                    {sourceIds.map((evidenceId) => (
                      <EvidenceReference key={evidenceId} evidenceId={evidenceId} run={run} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EvidenceReference({ evidenceId, run }: { evidenceId: string; run: InvestigationRun }) {
  const captured = run.result.evidence.some((item) => item.id === evidenceId);
  if (!captured) return <span>{evidenceId}</span>;

  return <EvidenceLink evidenceId={evidenceId} run={run} />;
}

export function EvidenceLink({ evidenceId, run }: { evidenceId: string; run: InvestigationRun }) {
  return (
    <a
      href={evidencePath({
        ticketId: run.ticket_id,
        runId: run.run_id,
        evidenceId,
      })}
      className="font-medium text-blue-700 underline-offset-4 hover:underline"
    >
      {evidenceId}
    </a>
  );
}

function AttentionItems({ blockers }: { blockers: InvestigationBlocker[] }) {
  if (!blockers.length) return null;

  return (
    <section className="mt-5" aria-labelledby="attention-title">
      <h3 id="attention-title" className="font-semibold">
        What needs attention
      </h3>
      <div className="mt-3 space-y-3">
        {blockers.map((blocker) => (
          <Alert
            key={`${blocker.kind}-${blocker.summary}`}
            variant={blocker.kind === "confirmed_violation" ? "destructive" : "default"}
            className={blocker.kind === "missing_evidence" ? "border-amber-300 bg-amber-50/70" : ""}
          >
            <TriangleAlert
              className={blocker.kind === "missing_evidence" ? "text-amber-700" : ""}
            />
            <AlertTitle>{blocker.summary}</AlertTitle>
            <AlertDescription>{blocker.resolution}</AlertDescription>
          </Alert>
        ))}
      </div>
    </section>
  );
}

function criterionPresentation(status: CriterionStatus) {
  switch (status) {
    case "verified":
      return {
        label: "Verified",
        icon: CheckCircle2,
        iconClass: "text-emerald-700",
        badgeClass: "bg-emerald-100 text-emerald-800",
      };
    case "failed":
      return {
        label: "Failed",
        icon: CircleAlert,
        iconClass: "text-destructive",
        badgeClass: "bg-red-100 text-red-800",
      };
    case "deferred":
      return {
        label: "Required later",
        icon: Clock3,
        iconClass: "text-blue-700",
        badgeClass: "bg-blue-100 text-blue-800",
      };
    case "unavailable":
      return {
        label: "Unavailable",
        icon: CircleHelp,
        iconClass: "text-amber-700",
        badgeClass: "bg-amber-100 text-amber-800",
      };
    case "unverified":
      return {
        label: "Unverified",
        icon: CircleHelp,
        iconClass: "text-amber-700",
        badgeClass: "bg-amber-100 text-amber-800",
      };
  }
}
