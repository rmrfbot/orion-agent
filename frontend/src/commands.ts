export type TaskStatus = "queued" | "running" | "finished" | "incomplete" | "failed";
export type TaskResult = {
  elapsed_ms?: number;
  total_elapsed_ms?: number;
  outcome?: string;
  message?: string;
  actions_taken?: number;
  tool_errors?: { tool: string; message: string }[];
  tabs?: { tabs: { index: number; title: string; url: string; active: boolean }[] };
};
export type BrowserTask = {
  task_id: string;
  instruction: string;
  status: TaskStatus;
  result: TaskResult | null;
  error: string | null;
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: TaskStatus;
};
export type Request = <T>(path: string, init?: RequestInit) => Promise<T>;
export class RequestError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}
export const statusLabels: Record<TaskStatus, string> = {
  queued: "Queued", running: "Running", finished: "Completed", incomplete: "Incomplete", failed: "Failed",
};
const terminal = (status: TaskStatus) => ["finished", "failed", "incomplete"].includes(status);
export const delay = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));

type Snapshot = { messages: Message[]; task: BrowserTask | null; busy: boolean; notice: string; lastInstruction: string };
type Options = {
  request: Request;
  storage?: Pick<Storage, "getItem" | "setItem" | "removeItem">;
  wait?: typeof delay;
  onResponse?: (text: string, task: BrowserTask) => void;
};
const pendingKey = "orion.pending-task";

/** Shared submission path for typed commands and future speech transcriptions. */
export class CommandSession {
  private state: Snapshot = {
    messages: [{ id: "welcome", role: "assistant", content: "Mission Control ready. Connect to ORION and give your browser a command." }],
    task: null, busy: false, notice: "", lastInstruction: "",
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private options: Options;
  constructor(options: Options) { this.options = options; }
  setRequest(request: Request) { this.options.request = request; }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private update(changes: Partial<Snapshot>) {
    this.state = { ...this.state, ...changes };
    this.listeners.forEach(listener => listener());
  }
  private message(role: Message["role"], content: string, status?: TaskStatus) {
    this.update({ messages: [...this.state.messages, { id: crypto.randomUUID(), role, content, status }] });
  }
  private remember(id: string | null) {
    try {
      if (id) this.options.storage?.setItem(pendingKey, id);
      else this.options.storage?.removeItem(pendingKey);
    } catch { /* Restricted storage must not interrupt a live task. */ }
  }
  start() {
    const generation = ++this.generation;
    let id: string | null = null;
    try { id = this.options.storage?.getItem(pendingKey) ?? null; } catch { /* Storage is optional. */ }
    if (id && /^[a-zA-Z0-9-]{1,64}$/.test(id)) {
      this.update({ busy: true, notice: "Reconnecting to the last task…" });
      void this.poll(id, generation);
    }
  }
  stop() { ++this.generation; } // Stop UI tracking only; never stop backend/Chrome.
  async submit(instruction: string): Promise<boolean> {
    instruction = instruction.trim();
    if (!instruction || this.state.busy) return false;
    if (instruction.length > 2000) {
      this.update({ notice: "Keep commands under 2,000 characters." });
      return false;
    }
    const generation = this.generation;
    this.update({ busy: true, notice: "", task: null, lastInstruction: instruction });
    this.message("user", instruction);
    try {
      // POST is deliberately never replayed automatically after a connection error.
      const task = await this.options.request<BrowserTask>("/api/tasks", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ instruction }),
      });
      this.remember(task.task_id);
      if (generation !== this.generation) return true;
      this.update({ task });
      await this.poll(task.task_id, generation);
    } catch (error) {
      if (generation !== this.generation) return true;
      const detail = error instanceof Error ? error.message : "Cannot reach ORION.";
      const message = error instanceof RequestError && error.status
        ? detail
        : `${detail} The command may have reached the backend. Check Chrome before retrying; it was not resent.`;
      this.update({ busy: false, notice: message });
      this.message("assistant", message, "failed");
    }
    return true;
  }
  private async poll(id: string, generation: number) {
    const wait = this.options.wait ?? delay;
    while (generation === this.generation) {
      try {
        const task = await this.options.request<BrowserTask>(`/api/tasks/${id}`);
        if (generation !== this.generation) return;
        this.update({ task, notice: "", lastInstruction: task.instruction });
        if (terminal(task.status)) {
          this.remember(null);
          this.update({ busy: false });
          const text = task.result?.message || task.error || `Task ${statusLabels[task.status].toLowerCase()}.`;
          this.message("assistant", text, task.status);
          try { this.options.onResponse?.(text, task); } catch { /* Response consumers must not restart task polling. */ }
          return;
        }
        await wait(250);
      } catch (error) {
        if (generation !== this.generation) return;
        if (error instanceof RequestError && [401, 403, 404].includes(error.status ?? 0)) {
          this.remember(null);
          const text = error.status === 404
            ? "The backend no longer has this task, possibly after a restart. Its completion is unknown; it was not resent."
            : error.message;
          this.update({ busy: false, notice: text, task: null });
          this.message("assistant", text, "failed");
          return;
        }
        this.update({ notice: "Connection interrupted. Reconnecting to this task without resending it…" });
        await wait(2000);
      }
    }
  }
}
