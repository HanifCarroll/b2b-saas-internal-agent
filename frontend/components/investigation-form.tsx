"use client";

import { useState } from "react";
import type { DemoOptions } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Field, FieldGroup, FieldLabel, FieldDescription } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

export function InvestigationForm({
  authMode,
  options,
  employee,
  busy,
  onEmployeeChange,
  onInvestigate,
  onReset,
  activeScenario,
}: {
  authMode: "demo" | "entra";
  options: DemoOptions | null;
  employee: string;
  busy: boolean;
  onEmployeeChange: (employee: string) => void;
  onInvestigate: () => void;
  onReset: (scenario: string) => void;
  activeScenario: string | null;
}) {
  const [scenario, setScenario] = useState("baseline");
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {authMode === "demo" ? "Demo setup and investigation" : "Investigation"}
        </CardTitle>
        <CardDescription>
          Active scenario: {activeScenario?.replaceAll("-", " ") ?? "Not initialized"}.
          Investigations use the current shared records.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onInvestigate();
          }}
          className="flex flex-col gap-5"
        >
          {authMode === "demo" && (
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="scenario">Reset to scenario</FieldLabel>
                <Select
                  items={options?.scenarios.map((item) => ({
                    value: item.id,
                    label: item.id.replaceAll("-", " "),
                  }))}
                  value={scenario}
                  disabled={busy || !options}
                  onValueChange={(value) => {
                    if (value) setScenario(value);
                  }}
                >
                  <SelectTrigger id="scenario" className="w-full">
                    <SelectValue placeholder="Select an option" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {options?.scenarios.map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.id.replaceAll("-", " ")}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Button
                type="button"
                variant="outline"
                disabled={busy || !options}
                onClick={() => {
                  if (
                    window.confirm(
                      "Reset the demo? This permanently deletes all saved investigations, proposals, approvals, and execution receipts, and restores the selected scenario.",
                    )
                  )
                    onReset(scenario);
                }}
              >
                Reset demo to scenario
              </Button>
              <p className="text-xs text-muted-foreground">
                Reset clears all saved demo work. Changing this selection alone does nothing.
              </p>
              <Field>
                <FieldLabel htmlFor="employee">Investigate as</FieldLabel>
                <Select
                  items={options?.employees.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                  value={employee}
                  disabled={busy || !options}
                  onValueChange={(value) => {
                    if (!value) return;
                    onEmployeeChange(value);
                  }}
                >
                  <SelectTrigger id="employee" className="w-full">
                    <SelectValue placeholder="Select an option" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {options?.employees.map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldDescription>
                  Demo identity only, not sign-in. Customer access is enforced in Python.
                </FieldDescription>
              </Field>
            </FieldGroup>
          )}
          <Button type="submit" disabled={busy || !options || !activeScenario}>
            Start investigation
          </Button>
          <p className="text-xs text-muted-foreground">
            Uses your configured model API. May take a minute; avoid starting duplicate runs.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
