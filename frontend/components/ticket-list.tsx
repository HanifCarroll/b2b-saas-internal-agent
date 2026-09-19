import type { Ticket } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function TicketList({
  tickets,
  selectedTicketId,
  busy,
  onSelect,
}: {
  tickets: Ticket[];
  selectedTicketId: string | null;
  busy: boolean;
  onSelect: (ticketId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Assigned tickets</CardTitle>
        <CardDescription>Customer requests available to your employee account.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {tickets.map((ticket) => (
          <Button
            key={ticket.id}
            variant={selectedTicketId === ticket.id ? "secondary" : "outline"}
            className="h-auto min-w-0 justify-start whitespace-normal px-4 py-3 text-left"
            disabled={busy}
            onClick={() => onSelect(ticket.id)}
          >
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <span className="font-semibold">{ticket.id}</span>
                <Badge variant="outline">{ticket.status}</Badge>
              </span>
              <span className="mt-1 block text-sm font-normal text-muted-foreground">
                {ticket.subject}
              </span>
            </span>
          </Button>
        ))}
        {!tickets.length && <p className="text-sm text-muted-foreground">No accessible tickets.</p>}
      </CardContent>
    </Card>
  );
}
