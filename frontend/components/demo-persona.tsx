"use client";

import type { DemoPersona } from "@/lib/api";
import { useCallback, useState } from "react";
import { preload } from "react-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const personaAvatarPaths: Record<string, string> = {
  "emp-alex": "/personas/alex-rivera.webp",
  "emp-priya": "/personas/priya-shah.webp",
  "emp-ben": "/personas/ben-okafor.webp",
};

export function DemoPersonaAvatar({
  persona,
  size = "default",
}: {
  persona: DemoPersona | null;
  size?: "sm" | "default" | "lg";
}) {
  const name = persona?.name ?? "Demo persona";
  const avatarPath = persona ? personaAvatarPaths[persona.id] : undefined;

  return (
    <Avatar size={size}>
      {avatarPath && <AvatarImage src={avatarPath} alt={name} />}
      <AvatarFallback>{initials(name)}</AvatarFallback>
    </Avatar>
  );
}

export function DemoPersonaIndicator({ persona }: { persona: DemoPersona | null }) {
  const name = persona?.name ?? "Loading persona…";
  const role = persona?.role.replaceAll("_", " ") ?? "";

  return (
    <div className="min-w-0">
      <span className="block text-[11px] font-medium tracking-wide text-slate-500 uppercase">
        Demo persona
      </span>
      <TruncatedPersonaValue value={name} className="text-sm font-medium text-foreground" />
      {role && (
        <TruncatedPersonaValue value={role} className="text-xs text-muted-foreground capitalize" />
      )}
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
  for (const avatarPath of Object.values(personaAvatarPaths)) {
    preload(avatarPath, { as: "image", type: "image/webp" });
  }

  return (
    <Select
      items={personas.map((persona) => ({ value: persona.id, label: persona.name }))}
      value={selectedPersonaId}
      disabled={busy || personas.length === 0}
      onValueChange={(value) => {
        if (value) onChange(value);
      }}
    >
      <SelectTrigger aria-label="Act as demo persona" className="mt-2 w-full bg-white">
        <SelectValue placeholder="Choose a persona" />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          {personas.map((persona) => (
            <SelectItem key={persona.id} value={persona.id}>
              <DemoPersonaAvatar persona={persona} size="sm" />
              {persona.name}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

function TruncatedPersonaValue({ value, className }: { value: string; className: string }) {
  const [isTruncated, setIsTruncated] = useState(false);
  const measureOverflow = useCallback((element: HTMLElement | null) => {
    if (!element) return;

    const update = () => setIsTruncated(element.scrollWidth > element.clientWidth);
    update();

    if (typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  if (!isTruncated) {
    return (
      <span ref={measureOverflow} className={`block w-full truncate text-left ${className}`}>
        {value}
      </span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            ref={measureOverflow}
            type="button"
            aria-label={`${value}; show full value`}
            className={`block w-full cursor-help truncate text-left ${className}`}
          />
        }
      >
        {value}
      </TooltipTrigger>
      <TooltipContent>{value}</TooltipContent>
    </Tooltip>
  );
}

function initials(name: string) {
  return name
    .split(/[-\s]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
