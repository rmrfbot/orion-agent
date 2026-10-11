
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
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
} from "lucide-react";
import "./App.css";
import { desktopCore, apiRequest } from "./desktop";
import { CommandSession, delay, statusLabels } from "./commands";
import type { Request } from "./commands";

function App() {
  const [desktop, setDesktop] = useState(() => !!desktopCore());
  const [token, setToken] = useState("");
  const [input, setInput] = useState("");
  const [connection, setConnection] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const [browserState, setBrowserState] = useState('not_started');
  const bottomRef = useRef<HTMLDivElement>(null);
  const [session] = useState(() => {
    let storage: Storage | undefined;
    try { storage = window.localStorage; } catch { /* Storage is optional. */ }
    const request: Request = (path, init) => apiRequest(path, init);
    return new CommandSession({ request, storage });
  });
  const { messages, task, busy, notice, lastInstruction } = useSyncExternalStore(session.subscribe, session.getSnapshot);
  const connected = connection === 'connected';

  useEffect(() => {
    session.start();
    return () => session.stop();
  }, [session]);

  useEffect(() => {
    const detect = () => setDesktop(!!desktopCore());
    window.addEventListener("load", detect, { once: true });
    return () => window.removeEventListener("load", detect);
  }, []);

  useEffect(() => {
    let active = true;
    const check = async () => {
      while (active) {
        try {
          const data = await apiRequest<{browser_worker: boolean; browser_state?: string}>('/health');
          if (active) {
            setConnection(data.browser_worker ? 'connected' : 'disconnected');
            setBrowserState(data.browser_state ?? 'unknown');
          }
        } catch {
          if (active) setConnection('disconnected');
        }
        await delay(2000);
      }
    };
    void check();
    return () => { active = false; };
  }, [desktop]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, task?.status]);

  const submit = async (instruction = input) => {
    if ((!desktop && !token.trim()) || !connected) return;
    if (!instruction.trim() || busy) return;
    setInput('');
    await session.submit(instruction);
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
                ? "Connected"
                : connection === 'checking' ? "Connecting?" : "Disconnected"}
            </span>
          </div>
        </div>

        <div className="sidebar-section">
          <p className="section-label">
            CONNECTION
          </p>

          {desktop ? <p className="hint">Desktop connection ready. No token entry needed.</p> : <>
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
              { const value = e.target.value; session.setRequest((path, init) => apiRequest(path, init, value)); setToken(value); }
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
            <span className={`connection-label ${connected ? 'connected' : ''}`}>{connected ? 'Connected' : connection === 'checking' ? 'Connecting' : 'Disconnected'}</span>
          </div>
        </header>

        <section className="conversation" aria-label="Conversation">
          <div className={`hero ${messages.length > 1 ? 'compact' : ''}`}>
            <div className="hero-symbol">
              <Orbit size={31} />
            </div>

            <h2>Your mission starts here.</h2>

            <p>
              Give ORION a command. Gemini plans it,
              and Playwright executes it in Chrome.
            </p>
          </div>

          <div className="messages" role="log" aria-live="polite" aria-relevant="additions">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message ${message.role} ${message.status ?? ''}`}
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

                  {message.status && <span className={`result-label ${message.status}`}>{statusLabels[message.status]}</span>}
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
                {notice ? 'Waiting to reconnect...' : task?.status === 'queued' ? 'Command queued...' : task?.status === 'running' ? 'ORION is working in Chrome...' : 'Sending command...'}
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </section>

        {/* COMMAND INPUT */}
        <section className="composer-area">
          {!connected && (
            <div className="notice connection-notice" role="status">
              <Radio size={16} />
              {connection === 'checking' ? 'Connecting to ORION?' : 'Start the ORION backend. Mission Control reconnects automatically.'}
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              <CircleAlert size={16} />
              {notice}
            </div>
          )}

          {!busy && lastInstruction && (task?.status === 'failed' || task?.status === 'incomplete' || task?.status === 'paused' || notice) &&
            <button className="retry-button" disabled={!connected || (!desktop && !token.trim())}
              onClick={() => void submit(lastInstruction)}>Retry last command</button>}
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
              aria-label="Browser command"
              autoComplete="off"
              maxLength={2000}
            />

            <button
              type="submit"
              disabled={busy || !input.trim() || !connected || (!desktop && !token.trim())}
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
            {task?.instruction || lastInstruction || "Awaiting orders"}
          </h3>

          <div className={`task-status ${task?.status ?? 'standby'}`} role="status">
            {task?.status === "finished" ? (
              <CheckCircle2 size={17} />
            ) : task?.status === 'failed' || task?.status === 'incomplete' || task?.status === 'paused' ? (
              <CircleAlert size={17} />
            ) : task ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <Radio size={17} />
            )}

            <span>
              {task ? statusLabels[task.status] : busy ? 'Waiting for task status' : notice ? 'Status unavailable' : 'Standby'}
            </span>
          </div>
        </div>

        <div className="telemetry-card">
          <p className="section-label">BROWSER SESSION</p>
          <p className="browser-state">{!connected ? 'Status unavailable' :
            ({not_started: 'Chrome opens with your first command', launching: 'Launching Chrome...', ready: 'Chrome session ready', closed: 'Chrome closed; reopens on command', unavailable: 'Chrome needs recovery'}[browserState] ?? 'Chrome status unavailable')}</p>

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
          <span className={`status-dot ${connected ? 'online' : ''}`} />
          GEMINI + PLAYWRIGHT
        </div>
      </aside>

    </div>
  );
}

export default App;
