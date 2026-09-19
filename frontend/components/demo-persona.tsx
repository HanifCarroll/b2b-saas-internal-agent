"use client";

import type { DemoPersona } from "@/lib/api";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function DemoPersonaIndicator({ persona }: { persona: DemoPersona | null }) {
  return (
    <div>
      <span className="block text-[11px] font-medium tracking-wide text-slate-500 uppercase">
        Demo persona
      </span>
      <span className="block truncate text-sm font-medium text-white">
        {persona?.name ?? "Loading persona…"}
      </span>
      <span className="block truncate text-xs capitalize text-slate-400">
        {persona?.role.replaceAll("_", " ") ?? ""}
      </span>
    </div>
  );
}

export function DemoPersonaSwitcher({
  personas,
  selectedPersonaId,
  busy,
  onChange,
}: {
  personas: DemoPersona[];
  selectedPersonaId: string;
  busy: boolean;
  onChange: (personaId: string) => void;
}) {
  return (
    <Select
      items={personas.map((persona) => ({ value: persona.id, label: persona.name }))}
      value={selectedPersonaId}
      disabled={busy || personas.length === 0}
      onValueChange={(value) => {
        if (value) onChange(value);
      }}
    >
      <SelectTrigger aria-label="Act as demo persona" className="mt-2 w-full border-white/10">
        <SelectValue placeholder="Choose a persona" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {personas.map((persona) => (
            <SelectItem key={persona.id} value={persona.id}>
              {persona.name}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
