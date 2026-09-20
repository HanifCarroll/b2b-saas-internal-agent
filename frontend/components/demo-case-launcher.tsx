"use client";

import type { DemoCaseSummary } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

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
      <div className="mt-2 flex flex-col gap-2">
        {cases.map((item) => (
          <AlertDialog key={item.id}>
            <AlertDialogTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  className="h-auto w-full items-start justify-start whitespace-normal bg-white/5 px-3 py-2 text-left text-slate-200 hover:bg-white/10 hover:text-white"
                />
              }
            >
              <span>
                <span className="block text-xs font-medium">{item.title}</span>
                <span className="mt-1 block text-[11px] leading-4 text-slate-400">
                  {item.description}
                </span>
              </span>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Prepare this demo case?</AlertDialogTitle>
                <AlertDialogDescription>
                  Your current demo workspace history will be replaced with{" "}
                  {item.title.toLowerCase()}.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => onPrepare(item.id)}>
                  Prepare case
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ))}
      </div>
    </details>
  );
}
