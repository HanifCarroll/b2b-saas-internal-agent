"use client";

import type { DemoCaseSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function DemoCaseLauncher({
  cases,
  busy,
  onPrepare,
}: {
  cases: DemoCaseSummary[];
  busy: boolean;
  onPrepare: (caseId: string) => void;
}) {
  return (
    <details className="rounded-lg border border-white/10 bg-white/5 p-2">
      <summary className="cursor-pointer px-1 text-xs font-medium text-slate-300">
        Try a demo case
      </summary>
      <div className="mt-2 space-y-2">
        {cases.map((item) => (
          <Button
            key={item.id}
            type="button"
            variant="ghost"
            disabled={busy}
            className="h-auto w-full items-start justify-start whitespace-normal bg-white/5 px-3 py-2 text-left text-slate-200 hover:bg-white/10 hover:text-white"
            onClick={() => {
              if (
                window.confirm(
                  "Prepare this case? Your current demo workspace history will be replaced.",
                )
              ) {
                onPrepare(item.id);
              }
            }}
          >
            <span>
              <span className="block text-xs font-medium">{item.title}</span>
              <span className="mt-1 block text-[11px] leading-4 text-slate-400">
                {item.description}
              </span>
            </span>
          </Button>
        ))}
      </div>
    </details>
  );
}
