import { FileCheck2 } from "lucide-react";
import { PolicyEvidenceDocument } from "@/components/policy-evidence-document";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { EvidenceKind, InvestigationEvidenceDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

export function EvidenceDocument({ detail }: { detail: InvestigationEvidenceDetail }) {
  const { snapshot, current_document: currentDocument, has_changed: hasChanged } = detail;

  return (
    <div className="flex flex-col gap-6 p-5 sm:p-6">
      {hasChanged === true && (
        <Alert className="border-amber-300 bg-amber-50/70">
          <FileCheck2 className="text-amber-700" />
          <AlertTitle>This record changed after the investigation.</AlertTitle>
          <AlertDescription>
            The captured evidence remains unchanged below. The current record is shown separately.
          </AlertDescription>
        </Alert>
      )}

      <div
        className={cn(
          "grid",
          hasChanged &&
            "divide-y rounded-xl border xl:grid-cols-2 xl:divide-x xl:divide-y-0 [&>section]:p-5 sm:[&>section]:p-6",
        )}
      >
        <EvidencePanel
          title="Captured during investigation"
          description={`Captured ${formatDateTime(snapshot.captured_at)}`}
          kind={snapshot.kind}
          document={snapshot.document}
          comparisonDocument={hasChanged ? currentDocument : null}
        />
        {hasChanged && currentDocument && (
          <EvidencePanel
            title="Current record"
            description={hasChanged ? "Latest accessible version" : "Unchanged since capture"}
            kind={snapshot.kind}
            document={currentDocument}
            comparisonDocument={snapshot.document}
          />
        )}
      </div>

      {hasChanged === false && (
        <p className="text-sm text-muted-foreground">Unchanged since capture</p>
      )}

      {!currentDocument && (
        <p className="text-sm text-muted-foreground">
          The current record is no longer available to this employee. The captured evidence is
          preserved.
        </p>
      )}
    </div>
  );
}

function EvidencePanel({
  title,
  description,
  kind,
  document,
  comparisonDocument,
}: {
  title: string;
  description: string;
  kind: EvidenceKind;
  document: Record<string, unknown>;
  comparisonDocument: Record<string, unknown> | null;
}) {
  return (
    <section className="min-w-0">
      <div className="border-b pb-4">
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="pt-5">
        <EvidenceFields kind={kind} document={document} comparisonDocument={comparisonDocument} />
      </div>
    </section>
  );
}

function EvidenceFields({
  kind,
  document,
  comparisonDocument,
}: {
  kind: EvidenceKind;
  document: Record<string, unknown>;
  comparisonDocument: Record<string, unknown> | null;
}) {
  if (kind === "policy") {
    return (
      <PolicyEvidenceDocument
        content={String(document.content)}
        changed={fieldChanged("content", document, comparisonDocument)}
      />
    );
  }

  if (kind === "integration") {
    return (
      <EvidenceRows
        document={document}
        comparisonDocument={comparisonDocument}
        rows={[
          ["id", "Integration ID", document.id],
          ["name", "Name", document.name],
          ["customer_id", "Customer", document.customer_id],
          ["environment", "Environment", document.environment],
          ["endpoint", "Endpoint", document.endpoint],
          ["version", "Configuration version", document.version],
        ]}
      />
    );
  }

  if (kind === "ticket") {
    return (
      <EvidenceRows
        document={document}
        comparisonDocument={comparisonDocument}
        rows={[
          ["id", "Ticket ID", document.id],
          ["subject", "Subject", document.subject],
          ["status", "Status", document.status],
          ["customer_id", "Customer", document.customer_id],
          ["integration_id", "Integration", document.integration_id],
          ["requester_contact_id", "Requester", document.requester_contact_id],
          ["assigned_employee_id", "Assigned employee", document.assigned_employee_id],
          ["requested_endpoint", "Requested endpoint", document.requested_endpoint],
          ["created_at", "Created", formatDateTime(String(document.created_at))],
          ["body", "Request body", document.body],
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
      document={document}
      comparisonDocument={comparisonDocument}
      rows={[
        ["id", "Customer ID", document.id],
        ["name", "Name", document.name],
        ["authorized_contacts", "Authorized contacts", authorizedContacts],
        [
          "production_change_window",
          "Production change window",
          `${String(changeWindow.weekday)} ${String(changeWindow.start)}–${String(changeWindow.end)} ${String(changeWindow.timezone)}`,
        ],
        ["registered_destinations", "Registered destinations", registeredDestinations],
      ]}
    />
  );
}

function EvidenceRows({
  rows,
  document,
  comparisonDocument,
}: {
  rows: [string, string, unknown][];
  document: Record<string, unknown>;
  comparisonDocument: Record<string, unknown> | null;
}) {
  return (
    <dl className="divide-y">
      {rows.map(([key, label, value]) => (
        <EvidenceRow
          key={key}
          label={label}
          value={value}
          changed={fieldChanged(key, document, comparisonDocument)}
        />
      ))}
    </dl>
  );
}

function EvidenceRow({
  label,
  value,
  changed,
}: {
  label: string;
  value: unknown;
  changed: boolean;
}) {
  return (
    <div
      data-changed={changed}
      className={cn(
        "grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[160px_1fr] sm:gap-5",
        changed && "bg-amber-50 px-3",
      )}
    >
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap break-words text-sm font-medium">{String(value)}</dd>
    </div>
  );
}

function fieldChanged(
  key: string,
  document: Record<string, unknown>,
  comparisonDocument: Record<string, unknown> | null,
) {
  return (
    comparisonDocument !== null &&
    JSON.stringify(document[key]) !== JSON.stringify(comparisonDocument[key])
  );
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
