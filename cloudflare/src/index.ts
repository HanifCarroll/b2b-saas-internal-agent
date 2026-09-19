import { Container, getContainer } from "@cloudflare/containers";

export { ContainerProxy } from "@cloudflare/containers";

import { handleStorageRequest, type StorageEnvironment } from "./storage";

interface Env extends StorageEnvironment {
  SWITCHBOARD_CONTAINER: DurableObjectNamespace<SwitchboardContainer>;
  DEEPSEEK_API_KEY: string;
  SWITCHBOARD_AUTH_MODE: string;
  NEXT_PUBLIC_AUTH_MODE: string;
  STORAGE_BRIDGE_URL: string;
  ENTRA_TENANT_ID?: string;
  ENTRA_API_CLIENT_ID?: string;
  ENTRA_WEB_CLIENT_ID?: string;
  ENTRA_EMPLOYEE_MAPPING?: string;
  NEXT_PUBLIC_ENTRA_TENANT_ID?: string;
  NEXT_PUBLIC_ENTRA_API_CLIENT_ID?: string;
  NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID?: string;
  NEXT_PUBLIC_ENTRA_SCOPE?: string;
}

export class SwitchboardContainer extends Container<Env> {
  defaultPort = 3000;
  requiredPorts = [3000, 8000];
  sleepAfter = "2m";
  enableInternet = true;

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    this.envVars = containerEnvironment(env);
  }
}

SwitchboardContainer.outboundByHost = {
  "switchboard.storage": (request, env: Env) => handleStorageRequest(request, env),
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const container = getContainer(env.SWITCHBOARD_CONTAINER, "shared");
    const port = new URL(request.url).pathname.startsWith("/api/") ? 8000 : 3000;
    return container.containerFetch(request, port);
  },
};

function containerEnvironment(env: Env): Record<string, string> {
  const values: Record<string, string | undefined> = {
    DEEPSEEK_API_KEY: env.DEEPSEEK_API_KEY,
    SWITCHBOARD_AUTH_MODE: env.SWITCHBOARD_AUTH_MODE,
    NEXT_PUBLIC_AUTH_MODE: env.NEXT_PUBLIC_AUTH_MODE,
    STORAGE_BRIDGE_URL: env.STORAGE_BRIDGE_URL,
    ENTRA_TENANT_ID: env.ENTRA_TENANT_ID,
    ENTRA_API_CLIENT_ID: env.ENTRA_API_CLIENT_ID,
    ENTRA_WEB_CLIENT_ID: env.ENTRA_WEB_CLIENT_ID,
    ENTRA_EMPLOYEE_MAPPING: env.ENTRA_EMPLOYEE_MAPPING,
    NEXT_PUBLIC_ENTRA_TENANT_ID: env.NEXT_PUBLIC_ENTRA_TENANT_ID,
    NEXT_PUBLIC_ENTRA_API_CLIENT_ID: env.NEXT_PUBLIC_ENTRA_API_CLIENT_ID,
    NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID: env.NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID,
    NEXT_PUBLIC_ENTRA_SCOPE: env.NEXT_PUBLIC_ENTRA_SCOPE,
  };
  return Object.fromEntries(
    Object.entries(values).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
}
