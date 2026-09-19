import { Check, ChevronRight, FileCheck2, Sparkles } from "lucide-react";
import type { InvestigationRun } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

export function InvestigationFindings({
  run,
  busy,
  onEvaluatePolicy,
}: {
  run: InvestigationRun;
  busy: boolean;
  onEvaluatePolicy: () => void;
}) {
  const { investigation, messages } = run.result;
  const { findings } = investigation;
  const toolCalls = messages.flatMap((message) => message.tool_calls ?? []);

  return (
    <section className="border-b py-7" aria-labelledby="agent-conclusion-title">
      <div className="flex items-center justify-between gap-3">
        <h2 id="agent-conclusion-title" className="flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="size-5 text-emerald-700" aria-hidden="true" />
          Agent conclusion
        </h2>
        <Badge variant="secondary">
          {investigation.outcome === "blocked" ? "Blocked" : "Investigation complete"}
        </Badge>
      </div>

      <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/70 p-5">
        <p className="text-sm leading-6 text-slate-800">{findings.overview}</p>
        <p className="mt-3 text-sm font-medium text-emerald-900">{findings.recommendation}</p>
      </div>

      <div className="mt-7">
        <h3 className="flex items-center gap-2 font-semibold">
          <FileCheck2 className="size-4" aria-hidden="true" />
          Evidence reviewed
        </h3>
        <div className="mt-3 overflow-hidden rounded-lg border">
          {findings.checks.map((check, index) => (
            <details key={index} className="group border-b last:border-b-0">
              <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-sm hover:bg-slate-50">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                  <Check className="size-3.5" aria-hidden="true" />
                </span>
                <span className="min-w-0 flex-1 font-medium">{check}</span>
                <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                  Passed
                </Badge>
                <ChevronRight className="size-4 text-muted-foreground transition-transform group-open:rotate-90" />
              </summary>
              <div className="border-t bg-slate-50/60 px-13 py-3 text-sm text-muted-foreground">
                Recorded from evidence retrieved during this investigation.
              </div>
            </details>
          ))}
          {!findings.checks.length && (
            <p className="px-4 py-4 text-sm text-muted-foreground">No evidence checks recorded.</p>
          )}
        </div>
      </div>

      {(findings.policy_requirements.length > 0 || findings.gaps.length > 0) && (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <FindingList title="Policy requirements" items={findings.policy_requirements} />
          <FindingList title="Unknown at investigation time" items={findings.gaps} />
        </div>
      )}

      {investigation.blockers.length > 0 && (
        <Alert variant="destructive" className="mt-5">
          <AlertTitle>Blockers — no proposal saved</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {investigation.blockers.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

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

      <details className="mt-5 rounded-lg border px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium">
          Technical investigation details
        </summary>
        <div className="mt-4 flex flex-col gap-4 text-sm">
          <p className="text-muted-foreground">
            Evidence records: {investigation.evidence_ids.join(", ") || "None retrieved"}
          </p>
          <div>
            <p className="font-medium">Tool calls ({toolCalls.length})</p>
            {toolCalls.length === 0 ? (
              <p className="mt-2 text-muted-foreground">No tool calls were recorded.</p>
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

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Button variant="outline" disabled={busy} onClick={onEvaluatePolicy}>
          Evaluate policy claims · extra model call
        </Button>
        <span className="text-xs text-muted-foreground">Optional evaluation of the report.</span>
      </div>

      {run.policy_review && (
        <Alert className="mt-5">
          <AlertTitle>
            Policy review:{" "}
            {run.policy_review.issues.length
              ? `${run.policy_review.issues.length} issue(s)`
              : "No issues identified"}
          </AlertTitle>
          <AlertDescription>
            <p>{run.policy_review.limitation}</p>
            {run.policy_review.issues.map((issue, index) => (
              <div key={index} className="mt-3 flex flex-col gap-1">
                <p className="font-medium">{issue.claim}</p>
                <p>{issue.explanation}</p>
                <p>
                  Source {issue.policy_id}: {issue.policy_excerpt}
                </p>
              </div>
            ))}
          </AlertDescription>
        </Alert>
      )}
    </section>
  );
}

function FindingList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <section className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 list-disc space-y-2 pl-5 text-sm leading-6 text-slate-700">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
