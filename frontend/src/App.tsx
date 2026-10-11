
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowUp,
  Bot,
  CheckCircle2,
  CircleAlert,
  Globe2,
  LoaderCircle,
  Orbit,
  Radio,
  Settings2,
  Terminal,
  UserRound,
  Mic,
} from "lucide-react";
import "./App.css";
import { desktopCore, desktopRequest } from "./desktop";

type TaskStatus =
  | "queued"
  | "running"
  | "finished"
  | "incomplete"
  | "failed";

type TaskResult = {
  elapsed_ms?: number;
  total_elapsed_ms?: number;
  outcome?: string;
  message?: string;
  actions_taken?: number;
  tool_errors?: {
    tool: string;
    message: string;
  }[];
  tabs?: {
    tabs: {
      index: number;
      title: string;
      url: string;
      active: boolean;
    }[];
  };
};

type BrowserTask = {
  task_id: string;
  instruction: string;
  status: TaskStatus;
  result: TaskResult | null;
  error: string | null;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const wait = (ms: number) =>
  new Promise<void>((resolve) => setTimeout(resolve, ms));

const initialMessage: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "ORION online. All systems nominal. Standing by for your command, boss.",
};

function App() {
  const [desktop, setDesktop] = useState(() => !!desktopCore());
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    initialMessage,
  ]);
  const [task, setTask] = useState<BrowserTask | null>(null);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [notice, setNotice] = useState("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);

  useEffect(() => {
    const detect = () => setDesktop(!!desktopCore());
    window.addEventListener("load", detect, { once: true });
    return () => window.removeEventListener("load", detect);
  }, []);

  // ======================================================
  // BACKEND HEALTH MONITOR
  // ======================================================

  useEffect(() => {
    let active = true;

    const check = async () => {
      try {
        const response = desktop ? null : await fetch("/health");
        const data = desktop
          ? await desktopRequest("/health") as { browser_worker?: boolean }
          : await response!.json();

        if (active) {
          setConnected(
            (desktop || response?.ok === true) && data.browser_worker === true
          );
        }
      } catch {
        if (active) setConnected(false);
      }
    };

    void check();

    const interval = window.setInterval(check, 5000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [desktop]);

  // Auto-scroll chat
  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, task?.status]);

  // ======================================================
  // CHAT MESSAGE HANDLING
  // ======================================================

  const addMessage = (
    role: Message["role"],
    content: string
  ) => {
    setMessages((old) => [
      ...old,
      {
        id: crypto.randomUUID(),
        role,
        content,
      },
    ]);
  };

  // ======================================================
  // API REQUEST WRAPPER
  // ======================================================

  const request = async (
    url: string,
    init?: RequestInit
  ) => {
    if (desktop) return desktopRequest(url, init);
    const response = await fetch(url, {
      ...init,
      headers: {
        "X-ORION-Token": token.trim(),
        ...(init?.headers || {}),
      },
    });

    if (!response.ok) {
      const body = await response.text();

      throw new Error(
        `HTTP ${response.status}: ${body.slice(0, 350)}`
      );
    }

    return response.json();
  };

  // ======================================================
  // SUBMIT BROWSER COMMAND
  // ======================================================

  const submit = async () => {
    const instruction = input.trim();

    if (!instruction || busyRef.current) return;

    if (!desktop && !token.trim()) {
      setNotice(
        "Enter your local ORION API token to connect."
      );
      return;
    }

    busyRef.current = true;
    setBusy(true);
    setNotice("");
    setInput("");
    setTask(null);

    addMessage("user", instruction);

    try {
      const submittedAt = performance.now();
      const created = (await request("/api/tasks", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ instruction }),
      })) as BrowserTask;

      setTask(created);

      const deadline = Date.now() + 180_000;
      let finalTask = created;

      // Poll task status until complete.
      while (Date.now() < deadline) {
        await wait(250);

        finalTask = (await request(
          `/api/tasks/${created.task_id}`
        )) as BrowserTask;

        setTask(finalTask);

        if (
          ["finished", "failed", "incomplete"].includes(
            finalTask.status
          )
        ) {
          break;
        }
      }

      if (
        finalTask.status === "queued" ||
        finalTask.status === "running"
      ) {
        addMessage(
          "assistant",
          "Mission is still running. The dashboard stopped waiting, but the browser worker may continue executing it."
        );
      } else {
        console.debug('[PERF] command_to_result_ms', performance.now() - submittedAt);
        addMessage(
          "assistant",
          finalTask.result?.message ||
            finalTask.error ||
            `Task ended with status: ${finalTask.status}`
        );
      }
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Unknown request error.";

      addMessage(
        "assistant",
        `Mission error: ${message}`
      );

      setNotice(message);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const activeTabs =
    task?.result?.tabs?.tabs?.filter(
      (tab) => tab.url !== "about:blank"
    ) || [];

  // ======================================================
  // DASHBOARD
  // ======================================================

  return (
    <div className="app">

      {/* LEFT SIDEBAR */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Orbit size={28} />
          </div>
          <div>
            <h1>ORION</h1>
            <span>AUTONOMOUS SYSTEMS</span>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="section-label">
            SYSTEM STATUS
          </p>

          <div className="system-status">
            <span
              className={`status-dot ${
                connected ? "online" : ""
              }`}
            />

            <span>
              {connected
                ? "Browser worker online"
                : "Backend offline"}
            </span>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="section-label">
            CONNECTION
          </p>

          {desktop ? <p className="hint">Desktop connection configured automatically.</p> : <>
          <label htmlFor="api-token">
            Local API token
          </label>

          <input
            id="api-token"
            className="token-input"
            type="password"
            placeholder="Paste local token"
            value={token}
            onChange={(e) =>
              setToken(e.target.value)
            }
            autoComplete="off"
          />

          <p className="hint">
            Stored in memory for this window only.
          </p>
          </>}
        </div>

        <div className="sidebar-bottom">
          <Settings2 size={16} />
          <span>ORION Development Build</span>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main">
        <header className="topbar">
          <div className="topbar-title">
            <Radio size={17} />
            MISSION CONTROL
          </div>

          <div className="topbar-right">
            <Activity size={15} />
            <span>Browser Automation</span>
          </div>
        </header>

        <section className="conversation">
          <div className="hero">
            <div className="hero-symbol">
              <Orbit size={31} />
            </div>

            <h2>Your mission starts here.</h2>

            <p>
              Give ORION a command. Gemini plans it,
              and Playwright executes it in Chrome.
            </p>
          </div>

          <div className="messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message ${message.role}`}
              >
                <div className="message-avatar">
                  {message.role === "assistant" ? (
                    <Bot size={18} />
                  ) : (
                    <UserRound size={18} />
                  )}
                </div>

                <div className="message-content">
                  <strong>
                    {message.role === "assistant"
                      ? "ORION"
                      : "YOU"}
                  </strong>

                  <p>{message.content}</p>
                </div>
              </div>
            ))}

            {busy && (
              <div className="working">
                <LoaderCircle
                  size={16}
                  className="spin"
                />
                ORION is processing your command...
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </section>

        {/* COMMAND INPUT */}
        <section className="composer-area">
          {notice && (
            <div className="notice">
              <CircleAlert size={16} />
              {notice}
            </div>
          )}

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <input
              value={input}
              onChange={(e) =>
                setInput(e.target.value)
              }
              placeholder="Enter your command, Commander..."
              disabled={busy}
              maxLength={2000}
            />

            {/* Voice activation is coming later */}
            <span
              className="voice-placeholder"
              title="Voice integration coming soon"
            >
              <Mic size={19} />
            </span>

            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Send command"
            >
              <ArrowUp size={21} />
            </button>
          </form>

          <p className="composer-note">
            ORION operates in your dedicated
            Chrome automation session.
          </p>
        </section>
      </main>

      {/* RIGHT ACTIVITY PANEL */}
      <aside className="activity-panel">
        <div className="panel-heading">
          <Terminal size={17} />
          <span>MISSION TELEMETRY</span>
        </div>

        <div className="telemetry-card">
          <p className="section-label">
            CURRENT TASK
          </p>

          <h3>
            {task?.instruction || "Awaiting orders"}
          </h3>

          <div className="task-status">
            {task?.status === "finished" ? (
              <CheckCircle2 size={17} />
            ) : task ? (
              <LoaderCircle size={17} />
            ) : (
              <Radio size={17} />
            )}

            <span>
              {task?.status?.toUpperCase() ||
                "STANDBY"}
            </span>
          </div>
        </div>

        <div className="telemetry-card">
          <p className="section-label">
            BROWSER TABS
          </p>

          {activeTabs.length === 0 ? (
            <p className="empty-state">
              Tab information will appear after
              a completed task.
            </p>
          ) : (
            activeTabs.map((tab) => (
              <div
                className="tab-item"
                key={tab.index}
              >
                <Globe2 size={16} />

                <div>
                  <strong>
                    {tab.title || "Untitled"}
                  </strong>
                  <span>{tab.url}</span>
                </div>

                {tab.active && (
                  <span className="active-indicator" />
                )}
              </div>
            ))
          )}
        </div>

        <div className="telemetry-card">
          <p className="section-label">
            EXECUTION
          </p>

          <div className="metric-row">
            <span>Execution time</span>
            <strong>
              {(task?.result?.total_elapsed_ms ?? task?.result?.elapsed_ms) != null
                ? `${((task?.result?.total_elapsed_ms ?? task?.result?.elapsed_ms ?? 0) / 1000).toFixed(1)}s`
                : "—"}
            </strong>
          </div>

          <div className="metric-row">
            <span>Actions performed</span>
            <strong>
              {task?.result?.actions_taken ?? "—"}
            </strong>
          </div>

          <div className="metric-row">
            <span>Tool errors</span>
            <strong>
              {task?.result?.tool_errors?.length ??
                "—"}
            </strong>
          </div>
        </div>

        <div className="panel-footer">
          <span className="status-dot online" />
          GEMINI + PLAYWRIGHT
        </div>
      </aside>

    </div>
  );
}

export default App;
