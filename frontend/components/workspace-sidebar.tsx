import type { ReactNode } from "react";
import { CheckSquare2, ChevronRight, Inbox, Layers3, LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";

export function WorkspaceSidebar({
  activeView,
  employee,
  role,
  accountControls,
  demoControls,
  onOpenWork,
  onOpenApprovals,
}: {
  activeView: "work" | "approvals";
  employee: string;
  role: string | null;
  accountControls: { onSwitchAccount: () => void; onSignOut: () => void } | null;
  demoControls?: ReactNode;
  onOpenWork: () => void;
  onOpenApprovals: () => void;
}) {
  const navigation = [
    { label: "My work", icon: Inbox, active: activeView === "work", onClick: onOpenWork },
    {
      label: "Approvals",
      icon: CheckSquare2,
      active: activeView === "approvals",
      onClick: onOpenApprovals,
    },
  ];

  return (
    <aside className="flex min-h-0 w-full flex-col bg-[#121a28] text-slate-300 lg:fixed lg:inset-y-0 lg:left-0 lg:min-h-screen lg:w-60">
      <div className="flex h-20 items-center gap-3 px-6 text-lg font-semibold text-white">
        <span className="grid size-8 place-items-center rounded-lg bg-blue-600">
          <Layers3 className="size-4" aria-hidden="true" />
        </span>
        Switchboard
      </div>

      <nav className="flex flex-col gap-1 px-3" aria-label="Workspace navigation">
        {navigation.map(({ label, icon: Icon, active, onClick }) => (
          <button
            key={label}
            type="button"
            className={`flex h-11 items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors ${
              active
                ? "bg-blue-600/25 font-medium text-white"
                : "text-slate-300 hover:bg-white/5 hover:text-white"
            }`}
            aria-current={active ? "page" : undefined}
            onClick={onClick}
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-3 p-3">
        {demoControls}
        <div className="border-t border-white/10 pt-3">
          <div className="flex items-center gap-3 rounded-lg px-2 py-2">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-slate-200 text-xs font-semibold text-slate-800">
              {initials(employee)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-white">{employee}</span>
              <span className="block truncate text-xs capitalize text-slate-400">
                {role?.replaceAll("_", " ") ?? "Employee"}
              </span>
            </span>
            <ChevronRight className="size-4 text-slate-500" aria-hidden="true" />
          </div>
          {accountControls && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Button
                variant="ghost"
                size="sm"
                className="justify-start text-slate-300 hover:bg-white/10 hover:text-white"
                onClick={accountControls.onSwitchAccount}
              >
                <UserRound className="size-4" />
                Switch
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="justify-start text-slate-300 hover:bg-white/10 hover:text-white"
                onClick={accountControls.onSignOut}
              >
                <LogOut className="size-4" />
                Sign out
              </Button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function initials(employee: string) {
  return employee
    .replace(/^emp-/, "")
    .split(/[-\s]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
