import type { InvestigationHistoryItem } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field, FieldLabel } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

export function InvestigationHistory({
  history,
  selectedRunId,
  busy,
  onOpenRun,
  onRefresh,
}: {
  history: InvestigationHistoryItem[];
  selectedRunId: string | null;
  busy: boolean;
  onOpenRun: (id: string) => void;
  onRefresh: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved investigations</CardTitle>
        <CardDescription>Completed runs for this ticket and employee.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Field>
          <FieldLabel htmlFor="history">Open a previous run</FieldLabel>
          <Select
            items={history.map((item) => ({
              value: item.run_id,
              label: `${item.outcome === "blocked" ? "Blocked" : "Proposal"} · ${item.run_id.slice(0, 8)}`,
            }))}
            disabled={busy}
            value={selectedRunId}
            onValueChange={(value) => {
              if (value) onOpenRun(value);
            }}
          >
            <SelectTrigger id="history" className="w-full">
              <SelectValue placeholder="Choose a run" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {history.map((item) => (
                  <SelectItem key={item.run_id} value={item.run_id}>
                    {item.outcome === "blocked" ? "Blocked" : "Proposal"} ·{" "}
                    {item.run_id.slice(0, 8)}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <Button variant="outline" disabled={busy} onClick={onRefresh}>
          Refresh history
        </Button>
        {!history.length && (
          <p className="text-sm text-muted-foreground">No accessible completed runs yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
