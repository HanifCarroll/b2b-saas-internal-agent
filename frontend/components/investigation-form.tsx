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
  options,
  employee,
  busy,
  onEmployeeChange,
  onInvestigate,
}: {
  options: DemoOptions | null;
  employee: string;
  busy: boolean;
  onEmployeeChange: (employee: string) => void;
  onInvestigate: (scenario: string) => void;
}) {
  const [scenario, setScenario] = useState("baseline");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Start an investigation</CardTitle>
        <CardDescription>Each run uses isolated fictional business records.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onInvestigate(scenario);
          }}
          className="flex flex-col gap-5"
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="scenario">Scenario</FieldLabel>
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
          <Button type="submit" disabled={busy || !options}>
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
