import type { InvestigationRun } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
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
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>Investigation report</CardTitle>
          <Badge variant="secondary">
            {investigation.outcome === "blocked" ? "Blocked" : "Investigation complete"}
          </Badge>
        </div>
        <CardDescription>
          Ticket {run.ticket_id} · Run {run.run_id.slice(0, 8)}
          <span className="mt-1 block">
            Findings reflect what was known at investigation time. Current status is shown above.
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          {findings.overview}
        </p>
        {[
          { title: "Evidence checks", items: findings.checks },
          { title: "Policy requirements", items: findings.policy_requirements },
          { title: "Unknown at investigation time", items: findings.gaps },
        ].map(({ title, items }) =>
          items.length > 0 ? (
            <section key={title} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{title}</h3>
              <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed break-words">
                {items.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null,
        )}
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Investigator’s recommendation</h3>
          <p className="text-sm leading-relaxed break-words">{findings.recommendation}</p>
        </section>
        {investigation.blockers.length > 0 && (
          <Alert variant="destructive">
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
        <p className="text-sm text-muted-foreground">
          Evidence: {investigation.evidence_ids.join(", ") || "No records retrieved"}
        </p>
        {run.result.proposal && (
          <Alert>
            <AlertTitle>
              {run.result.was_created ? "Proposal saved" : "Existing proposal reused"}
            </AlertTitle>
            <AlertDescription>
              {run.result.was_created
                ? "Review the saved change below."
                : "An identical proposal already exists. No duplicate was created during this run."}
            </AlertDescription>
          </Alert>
        )}
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            Tool calls ({toolCalls.length})
          </summary>
          {toolCalls.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">
              No tool calls were recorded for this run.
            </p>
          )}
          <ul className="mt-3 flex flex-col gap-2 text-sm">
            {toolCalls.map((call) => (
              <li className="break-all" key={call.id}>
                <code>
                  {call.name} {JSON.stringify(call.args)}
                </code>
              </li>
            ))}
          </ul>
        </details>
        <Button variant="outline" disabled={busy} onClick={onEvaluatePolicy}>
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
  );
}
