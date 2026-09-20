export function ProposalChangeSummary({
  currentEndpoint,
  proposedEndpoint,
  expectedVersion,
  proposerName,
}: {
  currentEndpoint: string;
  proposedEndpoint: string;
  expectedVersion: number;
  proposerName: string;
}) {
  return (
    <section
      aria-label="Proposed change"
      className="overflow-hidden rounded-xl border bg-background"
    >
      <div className="grid min-w-0 gap-2 px-5 py-4 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-center">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Current endpoint
        </p>
        <p className="font-mono text-sm leading-6 break-all text-muted-foreground">
          {currentEndpoint}
        </p>
      </div>

      <div className="grid min-w-0 gap-2 border-t px-5 py-4 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-center">
        <p className="text-xs font-medium tracking-wide text-emerald-800 uppercase">
          Proposed endpoint
        </p>
        <p className="font-mono text-sm font-medium leading-6 break-all text-emerald-900">
          {proposedEndpoint}
        </p>
      </div>

      <p className="border-t bg-muted/15 px-5 py-3 text-xs text-muted-foreground">
        Version {expectedVersion} · Proposed by {proposerName}
      </p>
    </section>
  );
}
