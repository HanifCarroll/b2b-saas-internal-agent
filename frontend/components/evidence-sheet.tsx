"use client";

import { LoaderCircle } from "lucide-react";
import { EvidenceDocument } from "@/components/evidence-document";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { EvidenceKind, InvestigationEvidenceDetail } from "@/lib/api";

const evidenceTitles: Record<EvidenceKind, string> = {
  ticket: "Ticket evidence",
  customer: "Customer evidence",
  integration: "Integration evidence",
  policy: "Policy evidence",
};

export function EvidenceSheet({
  detail,
  error,
  ticketId,
  runId,
  onClose,
  onRetry,
}: {
  detail?: InvestigationEvidenceDetail;
  error?: string;
  ticketId: string;
  runId: string;
  onClose: () => void;
  onRetry: () => void;
}) {
  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="gap-0 overflow-hidden p-0 data-[side=right]:w-full data-[side=right]:sm:max-w-2xl data-[side=right]:xl:max-w-4xl">
        <SheetHeader className="shrink-0 border-b p-5 pr-14 sm:p-6 sm:pr-14">
          <div className="flex flex-wrap items-center gap-2">
            <SheetTitle className="text-xl font-semibold">
              {detail ? evidenceTitles[detail.snapshot.kind] : "Evidence"}
            </SheetTitle>
            {detail && <Badge variant="secondary">{detail.snapshot.id}</Badge>}
          </div>
          <SheetDescription>
            {ticketId} · Run {runId.slice(0, 8)} · Exact record saved with this investigation.
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {detail ? (
            <EvidenceDocument detail={detail} />
          ) : error ? (
            <div className="p-5 sm:p-6">
              <Alert variant="destructive">
                <AlertTitle>Evidence unavailable</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <Button className="mt-4" variant="outline" onClick={onRetry}>
                Try again
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-3 p-5 text-sm text-muted-foreground sm:p-6">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
              Loading evidence…
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
