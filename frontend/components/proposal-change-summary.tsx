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
      className="grid overflow-hidden rounded-xl border bg-background md:grid-cols-2"
    >
      <div className="min-w-0 bg-muted/15 p-5">
        <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Current endpoint
        </p>
        <p className="mt-3 rounded-lg border bg-background px-4 py-3 font-mono text-sm leading-6 break-all">
          {currentEndpoint}
        </p>
      </div>

      <div className="min-w-0 border-t bg-emerald-50/60 p-5 md:border-t-0 md:border-l">
        <p className="text-xs font-medium tracking-wide text-emerald-800 uppercase">
          Proposed endpoint
        </p>
        <p className="mt-3 rounded-lg border border-emerald-200 bg-white/80 px-4 py-3 font-mono text-sm leading-6 text-emerald-950 break-all">
          {proposedEndpoint}
        </p>
      </div>

      <dl className="grid border-t bg-muted/20 text-sm sm:grid-cols-2 sm:divide-x md:col-span-2">
        <div className="p-4">
          <dt className="text-xs text-muted-foreground">Expected current version</dt>
          <dd className="mt-1 font-medium tabular-nums">{expectedVersion}</dd>
        </div>
        <div className="border-t p-4 sm:border-t-0">
          <dt className="text-xs text-muted-foreground">Proposed by</dt>
          <dd className="mt-1 font-medium">{proposerName}</dd>
        </div>
      </dl>
    </section>
  );
}
