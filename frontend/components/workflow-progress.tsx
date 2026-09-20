import { Check, LockKeyhole } from "lucide-react";
import type { WorkflowStatus } from "@/lib/api";

type StageState = "complete" | "current" | "ready" | "locked";

export function WorkflowProgress({
  hasInvestigation,
  hasProposal,
  investigationInProgress = false,
  status,
}: {
  hasInvestigation: boolean;
  hasProposal: boolean;
  investigationInProgress?: boolean;
  status: WorkflowStatus | null;
}) {
  const stages: { label: string; state: StageState }[] = [
    { label: "Request", state: "complete" },
    {
      label: "Investigate",
      state: hasInvestigation ? "complete" : investigationInProgress ? "current" : "ready",
    },
    {
      label: "Propose",
      state: hasProposal ? "complete" : hasInvestigation ? "current" : "locked",
    },
    {
      label: "Review",
      state: reviewState({ hasProposal, status }),
    },
    {
      label: "Execute",
      state: executionState(status),
    },
    {
      label: "Verify",
      state: verificationState(status),
    },
  ];

  return (
    <ol className="grid grid-cols-6 border-b bg-white" aria-label="Change lifecycle">
      {stages.map((stage, index) => (
        <li
          key={stage.label}
          className="relative flex min-w-0 items-center gap-3 px-3 py-4 sm:px-5"
        >
          {index > 0 && (
            <span className="absolute top-1/2 right-full h-px w-4 bg-border sm:w-7" aria-hidden />
          )}
          <span
            className={`grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ${
              stage.state === "complete"
                ? "bg-emerald-600 text-white"
                : stage.state === "current" || stage.state === "ready"
                  ? "bg-amber-500 text-white"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {stage.state === "complete" ? (
              <Check className="size-4" aria-hidden />
            ) : stage.state === "locked" ? (
              <LockKeyhole className="size-3.5" aria-hidden />
            ) : (
              index + 1
            )}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-semibold sm:text-sm">{stage.label}</span>
            <span className="hidden text-xs text-muted-foreground md:block">
              {stage.state === "complete"
                ? "Complete"
                : stage.state === "current"
                  ? "In progress"
                  : stage.state === "ready"
                    ? "Ready"
                    : "Locked"}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function reviewState({
  hasProposal,
  status,
}: {
  hasProposal: boolean;
  status: WorkflowStatus | null;
}): StageState {
  if (
    [
      "approval_recorded",
      "approval_not_required",
      "configuration_updated",
      "delivery_verified",
      "manual_intervention_required",
    ].includes(status?.code ?? "")
  )
    return "complete";
  return hasProposal ? "current" : "locked";
}

function executionState(status: WorkflowStatus | null): StageState {
  if (
    ["configuration_updated", "delivery_verified", "manual_intervention_required"].includes(
      status?.code ?? "",
    )
  )
    return "complete";
  if (["approval_recorded", "approval_not_required"].includes(status?.code ?? "")) return "current";
  return "locked";
}

function verificationState(status: WorkflowStatus | null): StageState {
  if (status?.code === "delivery_verified") return "complete";
  if (["configuration_updated", "manual_intervention_required"].includes(status?.code ?? ""))
    return "current";
  return "locked";
}
