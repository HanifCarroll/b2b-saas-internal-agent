import assert from "node:assert/strict";
import { mock, test } from "node:test";

const account = { homeAccountId: "alex", tenantId: "tenant", localAccountId: "object" };
let activeAccount = null;
let redirectAccount = account;
let tokenRequest;
let loginRequest;
let logoutRequest;
let tokenError;
let initializationCount = 0;
const client = {
  handleRedirectPromise: async () => redirectAccount && { account: redirectAccount },
  getActiveAccount: () => activeAccount,
  setActiveAccount: (value) => {
    activeAccount = value;
  },
  acquireTokenSilent: async (request) => {
    tokenRequest = request;
    if (tokenError) throw tokenError;
    return { accessToken: "api-token" };
  },
  loginRedirect: async (request) => {
    loginRequest = request;
  },
  logoutRedirect: async (request) => {
    logoutRequest = request;
  },
};
mock.module("@azure/msal-browser", {
  namedExports: {
    createStandardPublicClientApplication: async () => {
      initializationCount++;
      return client;
    },
    CacheLookupPolicy: { AccessTokenAndRefreshToken: 3 },
  },
});
process.env.NEXT_PUBLIC_ENTRA_TENANT_ID = "b1338704-8cc0-43f7-846c-d930c917b905";
process.env.NEXT_PUBLIC_ENTRA_WEB_CLIENT_ID = "28093c48-1122-403b-b63f-99717ddf5e4c";
process.env.NEXT_PUBLIC_ENTRA_API_CLIENT_ID = "78e83c6d-0b97-47ee-aa39-114da2139341";
globalThis.window = { location: { origin: "http://localhost:3000" } };
const auth = await import("./auth.ts");

test("restores the redirect account and acquires its API token", async () => {
  assert.equal(await auth.restoreSignedInAccount(), account);
  assert.equal(await auth.getAccessToken({ account }), "api-token");
  assert.equal(tokenRequest.account, account);
  assert.deepEqual(tokenRequest.scopes, [
    "api://78e83c6d-0b97-47ee-aa39-114da2139341/access_as_user",
  ]);
  assert.equal(initializationCount, 1);
});

test("signed-out restoration does not choose an arbitrary cached account", async () => {
  activeAccount = null;
  redirectAccount = null;
  assert.equal(await auth.restoreSignedInAccount(), null);
});

test("sign-in asks for account selection and sign-out targets the active account", async () => {
  await auth.signIn();
  assert.equal(loginRequest.prompt, "select_account");
  assert.deepEqual(loginRequest.scopes, [
    "api://78e83c6d-0b97-47ee-aa39-114da2139341/access_as_user",
  ]);
  activeAccount = account;
  await auth.signOut();
  assert.equal(logoutRequest.account, account);
});

test("token failures propagate without starting an interactive login", async () => {
  tokenError = new Error("Interaction required");
  loginRequest = undefined;
  await assert.rejects(auth.getAccessToken({ account }), /Interaction required/);
  assert.equal(loginRequest, undefined);
  tokenError = undefined;
});

test("authentication defaults to Entra and rejects unknown modes", () => {
  delete process.env.NEXT_PUBLIC_AUTH_MODE;
  assert.equal(auth.getAuthMode(), "entra");
  process.env.NEXT_PUBLIC_AUTH_MODE = "demo";
  assert.equal(auth.getAuthMode(), "demo");
  process.env.NEXT_PUBLIC_AUTH_MODE = "hybrid";
  assert.equal(auth.getAuthMode(), "hybrid");
  process.env.NEXT_PUBLIC_AUTH_MODE = "typo";
  assert.throws(() => auth.getAuthMode(), /NEXT_PUBLIC_AUTH_MODE/);
  delete process.env.NEXT_PUBLIC_AUTH_MODE;
});
