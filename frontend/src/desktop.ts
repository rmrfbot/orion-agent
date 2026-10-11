import { RequestError } from "./commands";
type NativeCore = {
  invoke<T>(command: string, args: Record<string, unknown>): Promise<T>;
};

export function desktopCore(): NativeCore | undefined {
  return (window as Window & { __TAURI__?: { core: NativeCore } }).__TAURI__?.core;
}

export async function desktopRequest(path: string, init?: RequestInit): Promise<unknown> {
  const core = desktopCore();
  if (!core) throw new Error("Desktop connection is unavailable");
  try {
    return await core.invoke("orion_request", {
      path, method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : null,
    });
  } catch (error) {
    const detail = error as { message?: string; status?: number };
    throw new RequestError(detail?.message ?? "Cannot connect to the local ORION backend.", detail?.status);
  }
}



export async function apiRequest<T>(path: string, init?: RequestInit, token = ""): Promise<T> {
  if (desktopCore()) return await desktopRequest(path, init) as T;
  const response = await fetch(path, {
    ...init, signal: AbortSignal.timeout(10_000),
    headers: { ...init?.headers, "X-ORION-Token": token.trim() },
  });
  if (!response.ok) {
    const message = response.status === 401
      ? "ORION authentication failed. Check the local token used by the backend and app."
      : `ORION returned HTTP ${response.status}.`;
    throw new RequestError(message, response.status);
  }
  return response.json() as Promise<T>;
}
