import { ArrowLeft, FileCheck2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import type { EvidenceKind, InvestigationEvidenceDetail } from "@/lib/api";
import { requestPath } from "@/lib/workspace-routes";

const evidenceTitles: Record<EvidenceKind, string> = {
  ticket: "Ticket evidence",
  customer: "Customer evidence",
  integration: "Integration evidence",
  policy: "Policy evidence",
};

export function EvidenceDocument({
  detail,
  ticketId,
  runId,
}: {
  detail: InvestigationEvidenceDetail;
  ticketId: string;
  runId: string;
}) {
  const { snapshot, current_document: currentDocument, has_changed: hasChanged } = detail;

  return (
    <main className="min-h-screen bg-white">
      <header className="border-b px-5 py-6 sm:px-8">
        <div className="mx-auto max-w-5xl">
          <a
            href={requestPath(ticketId, runId)}
            className="inline-flex items-center gap-2 text-sm font-medium hover:underline"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to investigation
          </a>
          <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm text-muted-foreground">
                {ticketId} · Run {runId.slice(0, 8)}
              </p>
              <h1 className="mt-1 text-3xl font-semibold tracking-tight">
                {evidenceTitles[snapshot.kind]}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Exact record saved with this investigation.
              </p>
            </div>
            <Badge variant="secondary">{snapshot.id}</Badge>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8">
        {hasChanged === true && (
          <Alert className="mb-6 border-amber-300 bg-amber-50/70">
            <FileCheck2 className="text-amber-700" />
            <AlertTitle>This record changed after the investigation.</AlertTitle>
            <AlertDescription>
              The captured evidence remains unchanged below. The current record is shown separately.
            </AlertDescription>
          </Alert>
        )}

        <div className={currentDocument ? "grid gap-6 xl:grid-cols-2" : "grid gap-6"}>
          <EvidencePanel
            title="Captured during investigation"
            description={`Captured ${formatDateTime(snapshot.captured_at)}`}
            kind={snapshot.kind}
            document={snapshot.document}
          />
          {currentDocument && (
            <EvidencePanel
              title="Current record"
              description={hasChanged ? "Latest accessible version" : "Unchanged since capture"}
              kind={snapshot.kind}
              document={currentDocument}
            />
          )}
        </div>

        {!currentDocument && (
          <p className="mt-6 text-sm text-muted-foreground">
            The current record is no longer available to this employee. The captured evidence is
            preserved.
          </p>
        )}
      </div>
    </main>
  );
}

function EvidencePanel({
  title,
  description,
  kind,
  document,
}: {
  title: string;
  description: string;
  kind: EvidenceKind;
  document: Record<string, unknown>;
}) {
  return (
    <section className="overflow-hidden rounded-xl border bg-white shadow-sm">
      <div className="border-b bg-slate-50/70 px-5 py-4">
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="p-5">
        <EvidenceFields kind={kind} document={document} />
      </div>
    </section>
  );
}

function EvidenceFields({
  kind,
  document,
}: {
  kind: EvidenceKind;
  document: Record<string, unknown>;
}) {
  if (kind === "policy") {
    return (
      <div>
        <EvidenceRow label="Policy ID" value={document.id} />
        <div className="mt-5 border-t pt-5">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Policy text
          </p>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-7">{String(document.content)}</p>
        </div>
      </div>
    );
  }

  if (kind === "integration") {
    return (
      <EvidenceRows
        rows={[
          ["Integration ID", document.id],
          ["Name", document.name],
          ["Customer", document.customer_id],
          ["Environment", document.environment],
          ["Endpoint", document.endpoint],
          ["Configuration version", document.version],
        ]}
      />
    );
  }

  if (kind === "ticket") {
    return (
      <EvidenceRows
        rows={[
          ["Ticket ID", document.id],
          ["Subject", document.subject],
          ["Status", document.status],
          ["Customer", document.customer_id],
          ["Integration", document.integration_id],
          ["Requester", document.requester_contact_id],
          ["Assigned employee", document.assigned_employee_id],
          ["Requested endpoint", document.requested_endpoint],
          ["Created", formatDateTime(String(document.created_at))],
          ["Request body", document.body],
        ]}
      />
    );
  }

  const authorizedContacts = Array.isArray(document.authorized_contacts)
    ? document.authorized_contacts
        .map((contact) => String((contact as Record<string, unknown>).name))
        .join(", ")
    : "";
  const registeredDestinations = Array.isArray(document.registered_destinations)
    ? document.registered_destinations
        .map((destination) => {
          const item = destination as Record<string, unknown>;
          return `${String(item.environment)}: ${String(item.url)}`;
        })
        .join("\n")
    : "";
  const changeWindow = document.production_change_window as Record<string, unknown>;

  return (
    <EvidenceRows
      rows={[
        ["Customer ID", document.id],
        ["Name", document.name],
        ["Authorized contacts", authorizedContacts],
        [
          "Production change window",
          `${String(changeWindow.weekday)} ${String(changeWindow.start)}–${String(changeWindow.end)} ${String(changeWindow.timezone)}`,
        ],
        ["Registered destinations", registeredDestinations],
      ]}
    />
  );
}

function EvidenceRows({ rows }: { rows: [string, unknown][] }) {
  return (
    <dl className="divide-y">
      {rows.map(([label, value]) => (
        <EvidenceRow key={label} label={label} value={value} />
      ))}
    </dl>
  );
}

function EvidenceRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[160px_1fr] sm:gap-5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap break-words text-sm font-medium">{String(value)}</dd>
    </div>
  );
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
