"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  AuthenticationGate,
  type AccountActions,
  type AuthenticatedSession,
} from "@/components/authentication-gate";
import { identityKey, type CurrentEmployee, type RequestIdentity } from "@/lib/api";

type WorkspaceSession = {
  identity: RequestIdentity;
  currentEmployee: CurrentEmployee | null;
  accountActions: AccountActions;
  onEmployeeChange: (employeeId: string) => void;
};

const WorkspaceSessionContext = createContext<WorkspaceSession | null>(null);

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [authenticationClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={authenticationClient}>
      <AuthenticationGate>
        {(session, accountActions) => (
          <AuthenticatedWorkspace
            key={JSON.stringify(identityKey(session.identity))}
            session={session}
            accountActions={accountActions}
          >
            {children}
          </AuthenticatedWorkspace>
        )}
      </AuthenticationGate>
    </QueryClientProvider>
  );
}

function AuthenticatedWorkspace({
  session,
  accountActions,
  children,
}: {
  session: AuthenticatedSession;
  accountActions: AccountActions;
  children: ReactNode;
}) {
  const [queryClient] = useState(createQueryClient);
  const [demoEmployee, setDemoEmployee] = useState("emp-alex");
  const identity = useMemo<RequestIdentity>(
    () =>
      session.identity.mode === "demo"
        ? { mode: "demo", employeeId: demoEmployee }
        : session.identity,
    [session.identity, demoEmployee],
  );
  const value = useMemo(
    () => ({
      identity,
      currentEmployee: session.employee,
      accountActions,
      onEmployeeChange: setDemoEmployee,
    }),
    [identity, session.employee, accountActions],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <WorkspaceSessionContext value={value}>
        <IdentityBoundary key={JSON.stringify(identityKey(identity))}>{children}</IdentityBoundary>
      </WorkspaceSessionContext>
    </QueryClientProvider>
  );
}

function IdentityBoundary({ children }: { children: ReactNode }) {
  return children;
}

export function useWorkspaceSession() {
  const session = useContext(WorkspaceSessionContext);
  if (!session) throw new Error("Workspace routes must be rendered inside WorkspaceProvider.");
  return session;
}
