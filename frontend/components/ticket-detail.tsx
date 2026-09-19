import type { Ticket } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>{ticket.subject}</CardTitle>
          <Badge variant="secondary">{ticket.status}</Badge>
        </div>
        <CardDescription>
          {ticket.id} · Customer {ticket.customer_id} · Integration {ticket.integration_id}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{ticket.body}</p>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Requested endpoint</dt>
            <dd className="break-all">{ticket.requested_endpoint}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Requester</dt>
            <dd>{ticket.requester_contact_id}</dd>
          </div>
        </dl>
        <Button disabled={busy} onClick={() => onInvestigate(ticket.id)}>
          Investigate ticket
        </Button>
        <p className="text-xs text-muted-foreground">
          Uses the configured model and current business records. It may take a minute.
        </p>
      </CardContent>
    </Card>
  );
}
