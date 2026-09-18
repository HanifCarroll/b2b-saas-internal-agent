import {
  CacheLookupPolicy,
  createStandardPublicClientApplication,
  type AccountInfo,
  type IPublicClientApplication,
} from "@azure/msal-browser";

let msalClient: Promise<IPublicClientApplication> | undefined;

function getEntraConfiguration() {
  const tenantId = process.env.NEXT_PUBLIC_ENTRA_TENANT_ID;
  const webClientId = process.env.NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID;
  const apiClientId = process.env.NEXT_PUBLIC_ENTRA_API_CLIENT_ID;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  if (
    !tenantId ||
    !uuid.test(tenantId) ||
    !webClientId ||
    !uuid.test(webClientId) ||
    !apiClientId ||
    !uuid.test(apiClientId)
  ) {
    throw new Error("Set the three NEXT_PUBLIC_ENTRA_* IDs before enabling Microsoft sign-in.");
  }

  return { tenantId, webClientId, scope: `api://${apiClientId}/access_as_user` };
}

export function getMsalClient(): Promise<IPublicClientApplication> {
  if (!msalClient) {
    const configuration = getEntraConfiguration();
    msalClient = createStandardPublicClientApplication({
      auth: {
        clientId: configuration.webClientId,
        authority: `https://login.microsoftonline.com/${configuration.tenantId}`,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
      },
      cache: { cacheLocation: "sessionStorage" },
    }).catch((error) => {
      msalClient = undefined;
      throw error;
    });
  }

  return msalClient;
}

export async function restoreSignedInAccount(): Promise<AccountInfo | null> {
  const client = await getMsalClient();
  const response = await client.handleRedirectPromise();
  if (response?.account) client.setActiveAccount(response.account);

  return client.getActiveAccount();
}

export async function getAccessToken({ account }: { account: AccountInfo }): Promise<string> {
  const client = await getMsalClient();
  const response = await client.acquireTokenSilent({
    account,
    scopes: [getEntraConfiguration().scope],
    // Use cached tokens or refresh tokens; require explicit sign-in when both expire.
    cacheLookupPolicy: CacheLookupPolicy.AccessTokenAndRefreshToken,
  });
  return response.accessToken;
}

export function getAuthMode(): "demo" | "entra" {
  const mode = process.env.NEXT_PUBLIC_AUTH_MODE ?? "entra";
  if (mode !== "demo" && mode !== "entra") {
    throw new Error("NEXT_PUBLIC_AUTH_MODE must be demo or entra.");
  }

  return mode;
}

export async function signIn(): Promise<void> {
  const client = await getMsalClient();
  await client.loginRedirect({
    scopes: [getEntraConfiguration().scope],
    prompt: "select_account",
  });
}

export async function signOut(): Promise<void> {
  const client = await getMsalClient();
  await client.logoutRedirect({ account: client.getActiveAccount() });
}
