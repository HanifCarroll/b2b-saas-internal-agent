import { ChevronRight } from "lucide-react";
import type { AssignedRequestSummary } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export function TicketList({
  tickets,
  selectedTicketId,
  busy,
  onSelect,
}: {
  tickets: AssignedRequestSummary[];
  selectedTicketId: string | null;
  busy: boolean;
  onSelect: (ticketId: string) => void;
}) {
  if (!tickets.length) {
    return (
      <div className="grid min-h-64 place-items-center border-t text-center">
        <div>
          <p className="font-medium">No assigned requests</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Requests available to this employee will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t" aria-label="Assigned requests">
      <div className="hidden grid-cols-[110px_minmax(0,1fr)_170px_120px_28px] gap-4 border-b bg-slate-50/70 px-5 py-3 text-xs font-medium text-muted-foreground md:grid">
        <span>ID</span>
        <span>Request</span>
        <span>Stage</span>
        <span>Created</span>
        <span />
      </div>
      {tickets.map((ticket) => (
        <button
          key={ticket.id}
          type="button"
          className={`grid w-full min-w-0 grid-cols-[1fr_24px] items-center gap-4 border-b px-5 py-4 text-left transition-colors md:grid-cols-[110px_minmax(0,1fr)_170px_120px_28px] ${
            selectedTicketId === ticket.id ? "bg-blue-50/80" : "bg-white hover:bg-slate-50"
          }`}
          disabled={busy}
          onClick={() => onSelect(ticket.id)}
        >
          <span className="hidden font-medium text-slate-700 md:block">{ticket.id}</span>
          <span className="min-w-0">
            <span className="flex items-center gap-2 md:hidden">
              <span className="font-medium">{ticket.id}</span>
              <Badge variant="outline" className="capitalize">
                {ticket.workflow_status.title}
              </Badge>
            </span>
            <span className="block truncate font-medium text-slate-950">{ticket.subject}</span>
            <span className="mt-1 block truncate text-sm text-muted-foreground">
              {ticket.customer_id} · {ticket.integration_id}
            </span>
          </span>
          <span className="hidden min-w-0 md:block">
            <Badge variant="secondary" className="max-w-full truncate">
              {ticket.workflow_status.title}
            </Badge>
          </span>
          <span className="hidden text-sm text-muted-foreground md:block">
            {new Date(ticket.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </span>
          <ChevronRight className="size-4 text-muted-foreground" aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
