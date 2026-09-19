import { handleStorageRequest, type StorageEnvironment } from "./storage";

interface Env extends StorageEnvironment {
  LOCAL_STORAGE_BRIDGE_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const authorization = request.headers.get("Authorization");
    if (authorization !== `Bearer ${env.LOCAL_STORAGE_BRIDGE_TOKEN}`) {
      return Response.json({ error: "Storage bridge unavailable" }, { status: 404 });
    }
    return handleStorageRequest(request, env);
  },
};
