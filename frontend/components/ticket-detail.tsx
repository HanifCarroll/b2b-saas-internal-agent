import { CalendarClock, Contact, Link2 } from "lucide-react";
import type { Ticket } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function TicketDetail({
  ticket,
  busy,
  onInvestigate,
}: {
  ticket: Ticket;
  busy: boolean;
  onInvestigate: (ticketId: string) => void;
}) {
  return (
    <section className="border-b pb-7" aria-labelledby="request-summary-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="request-summary-title" className="text-lg font-semibold">
            Request summary
          </h2>
          <p className="mt-3 max-w-3xl whitespace-pre-wrap text-sm leading-6 text-slate-700">
            {ticket.body}
          </p>
        </div>
        <Button disabled={busy} onClick={() => onInvestigate(ticket.id)}>
          Start investigation
        </Button>
      </div>
      <dl className="mt-6 grid gap-5 text-sm sm:grid-cols-2 xl:grid-cols-3">
        <div className="flex gap-3">
          <Contact className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
          <div>
            <dt className="text-muted-foreground">Requester</dt>
            <dd className="mt-1 font-medium">{ticket.requester.name}</dd>
          </div>
        </div>
        <div className="flex gap-3">
          <Link2 className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0">
            <dt className="text-muted-foreground">Requested endpoint</dt>
            <dd className="mt-1 break-all font-mono text-xs">{ticket.requested_endpoint}</dd>
          </div>
        </div>
        <div className="flex gap-3">
          <CalendarClock className="mt-0.5 size-4 text-muted-foreground" aria-hidden="true" />
          <div>
            <dt className="text-muted-foreground">Requested</dt>
            <dd className="mt-1 font-medium">{new Date(ticket.created_at).toLocaleString()}</dd>
          </div>
        </div>
      </dl>
      <p className="mt-5 text-xs text-muted-foreground">
        The investigation uses the configured model and current business records. It may take a
        minute.
      </p>
    </section>
  );
}
