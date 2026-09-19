import { ChevronRight } from "lucide-react";
import type { ApprovalInboxItem } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export function ApprovalInbox({
  items,
  selectedProposalId,
  busy,
  onSelect,
}: {
  items: ApprovalInboxItem[];
  selectedProposalId: string | null;
  busy: boolean;
  onSelect: (item: ApprovalInboxItem) => void;
}) {
  if (!items.length) {
    return (
      <div className="grid min-h-64 place-items-center border-t text-center">
        <div>
          <p className="font-medium">No proposals awaiting your review</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Eligible proposals will appear here when another employee submits them.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t" aria-label="Approval inbox">
      <div className="hidden grid-cols-[110px_minmax(0,1fr)_150px_130px_28px] gap-4 border-b bg-slate-50/70 px-5 py-3 text-xs font-medium text-muted-foreground md:grid">
        <span>Request</span>
        <span>Proposed change</span>
        <span>Proposed by</span>
        <span>Submitted</span>
        <span />
      </div>
      {items.map((item) => (
        <button
          key={item.proposal.id}
          type="button"
          className={`grid w-full min-w-0 grid-cols-[1fr_24px] items-center gap-4 border-b px-5 py-4 text-left transition-colors md:grid-cols-[110px_minmax(0,1fr)_150px_130px_28px] ${
            selectedProposalId === item.proposal.id ? "bg-blue-50/80" : "bg-white hover:bg-slate-50"
          }`}
          disabled={busy}
          onClick={() => onSelect(item)}
        >
          <span className="font-medium text-slate-700">{item.proposal.ticket_id}</span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">
              {item.proposal.integration_id}
            </span>
            <span className="mt-1 block truncate text-xs text-muted-foreground">
              {item.proposal.current_endpoint} → {item.proposal.proposed_endpoint}
            </span>
            <Badge variant="secondary" className="mt-2 md:hidden">
              Awaiting review
            </Badge>
          </span>
          <span className="hidden text-sm md:block">{item.proposal.proposed_by_employee_id}</span>
          <span className="hidden text-sm text-muted-foreground md:block">
            {new Date(item.proposal.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
          <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Awaiting review</span>
        </button>
      ))}
    </div>
  );
}
