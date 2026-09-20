import type { ReactNode } from "react";
import { CheckSquare2, Inbox, Layers3, LogIn, LogOut, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DemoPersonaAvatar, DemoPersonaIndicator } from "@/components/demo-persona";
import type { AccountActions } from "@/components/authentication-gate";
import type { DemoPersona } from "@/lib/api";

export function WorkspaceSidebar({
  activeView,
  employee,
  role,
  accountControls,
  demoPersona,
  demoPersonaSwitcher,
  onOpenWork,
  onOpenApprovals,
}: {
  activeView: "work" | "approvals";
  employee: string;
  role: string | null;
  accountControls: AccountActions;
  demoPersona?: DemoPersona | null;
  demoPersonaSwitcher?: ReactNode;
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
    <aside className="flex min-h-0 w-full flex-col border-b border-sidebar-border bg-sidebar text-sidebar-foreground lg:fixed lg:inset-y-0 lg:left-0 lg:min-h-screen lg:w-60 lg:border-r lg:border-b-0">
      <div className="flex h-20 items-center gap-3 px-6 text-lg font-semibold tracking-tight">
        <span className="grid size-8 place-items-center">
          <SwitchboardMark />
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
                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
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
        <div className="border-t border-sidebar-border pt-3">
          <div className="flex items-center gap-3 rounded-lg px-2 py-2">
            {demoPersona !== undefined ? (
              <DemoPersonaAvatar persona={demoPersona} size="lg" />
            ) : (
              <Avatar size="lg">
                <AvatarFallback>{initials(employee)}</AvatarFallback>
              </Avatar>
            )}
            <span className="min-w-0 flex-1">
              {demoPersona !== undefined ? (
                <DemoPersonaIndicator persona={demoPersona} />
              ) : (
                <>
                  <span className="block truncate text-sm font-medium text-foreground">
                    {employee}
                  </span>
                  <span className="block truncate text-xs capitalize text-muted-foreground">
                    {role?.replaceAll("_", " ") ?? "Employee"}
                  </span>
                </>
              )}
            </span>
          </div>
          {demoPersonaSwitcher}
          {(accountControls.onUseDemo ||
            accountControls.onUseMicrosoft ||
            accountControls.onSwitchAccount ||
            accountControls.onSignOut) && (
            <div className="mt-2 flex flex-wrap gap-2">
              {accountControls.onUseDemo && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
                  onClick={accountControls.onUseDemo}
                >
                  <Layers3 className="size-4" />
                  Use demo
                </Button>
              )}
              {accountControls.onUseMicrosoft && demoPersona !== undefined && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
                  onClick={accountControls.onUseMicrosoft}
                >
                  <LogIn className="size-4" />
                  Sign in with Microsoft
                </Button>
              )}
              {accountControls.onSwitchAccount && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
                  onClick={accountControls.onSwitchAccount}
                >
                  <UserRound className="size-4" />
                  Switch
                </Button>
              )}
              {accountControls.onSignOut && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="justify-start text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
                  onClick={accountControls.onSignOut}
                >
                  <LogOut className="size-4" />
                  Sign out
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

function SwitchboardMark() {
  return (
    <svg
      viewBox="0 0 32 32"
      className="size-8 text-blue-600"
      fill="none"
      stroke="currentColor"
      strokeWidth="3.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M25 7H12a5 5 0 0 0 0 10h8a5 5 0 0 1 0 10H7" />
      <circle cx="25" cy="7" r="2.25" fill="currentColor" stroke="none" />
      <circle cx="7" cy="27" r="2.25" fill="currentColor" stroke="none" />
    </svg>
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
