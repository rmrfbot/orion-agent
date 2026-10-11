type NativeCore = {
  invoke<T>(command: string, args: Record<string, unknown>): Promise<T>;
};

export function desktopCore(): NativeCore | undefined {
  return (window as Window & { __TAURI__?: { core: NativeCore } }).__TAURI__?.core;
}

export async function desktopRequest(path: string, init?: RequestInit): Promise<unknown> {
  const core = desktopCore();
  if (!core) throw new Error("Desktop connection is unavailable");
  return core.invoke("orion_request", {
    path,
    method: init?.method ?? "GET",
    body: typeof init?.body === "string" ? JSON.parse(init.body) : null,
  });
}
