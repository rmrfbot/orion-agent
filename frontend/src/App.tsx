
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  Activity,
  Maximize2, Minimize2, Minus,
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
import { desktopCore, apiRequest, listenNative } from "./desktop";
import { CommandSession, delay, statusLabels } from "./commands";
import type { Request } from "./commands";
import { VoiceSession } from './voice';
import { browserVoiceIO } from './voice-browser';
import { VoiceControls } from './VoiceControls';
import { WindowSession } from './window-session';

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
  const [voiceAvailable,setVoiceAvailable]=useState(false);
  const [voice]=useState(()=>{
    let muted=false;try{muted=localStorage.getItem('orion.voice-muted')==='true';}catch{/* Optional preference. */}
    return new VoiceSession({io:browserVoiceIO(),muted,canSubmit:()=>!session.getSnapshot().busy,
      submit:text=>session.submit(text,'voice')});
  });
  const voiceState=useSyncExternalStore(voice.subscribe,voice.getSnapshot);
  const [shell]=useState(()=>{
    let storage:Storage|undefined;try{storage=localStorage;}catch{/* Optional preference. */}
    return new WindowSession({native:!!desktopCore(),storage,invoke:(command,args)=>{
      const core=desktopCore();if(!core)return Promise.reject(new Error('Desktop window unavailable'));
      return core.invoke(command,args);
    }});
  });
  const windowState=useSyncExternalStore(shell.subscribe,shell.getSnapshot);
  const [shortcutInput,setShortcutInput]=useState<string|null>(null);
  const compactRef=useRef<HTMLDivElement>(null);
  const voiceBusy=voiceState.phase!=='idle';
  const commandDisabled=busy||voiceBusy;
  const focusCommand=()=>document.querySelector<HTMLInputElement>('[aria-label="Browser command"]')?.focus();
  const mute=()=>{const value=!voiceState.muted;voice.setMuted(value);try{localStorage.setItem('orion.voice-muted',String(value));}catch{/* Optional preference. */}};
  const voiceControls=<VoiceControls voice={voice} state={voiceState} available={voiceAvailable}
    disabled={busy||!connected||(!desktop&&!token.trim())} onMute={mute}/>;

  useEffect(()=>{
    session.setResponseHandler((_text,task,source)=>{if(source==='voice')void voice.speak(task);else voice.stopSpeaking();});
    void shell.load();
    const cancel=()=>{if(document.hidden)voice.suspend();};
    const close=()=>voice.suspend();
    document.addEventListener('visibilitychange',cancel);window.addEventListener('pagehide',close);
    let active=true;const cleanups:(()=>void)[]=[];
    for(const [event,handler] of [['orion-inactive',()=>voice.suspend()],['orion-summoned',focusCommand]] as const){
      void listenNative(event,handler).then(cleanup=>{if(active)cleanups.push(cleanup);else cleanup();}).catch(()=>{});
    }
    return()=>{active=false;cleanups.forEach(fn=>fn());document.removeEventListener('visibilitychange',cancel);window.removeEventListener('pagehide',close);voice.dispose();session.setResponseHandler(undefined);};
  },[session,voice,shell]);

  useEffect(()=>{
    requestAnimationFrame(()=>document.querySelector<HTMLInputElement>('[aria-label="Browser command"]')?.focus());
    if(!windowState.compact||!compactRef.current)return;
    const observer=new ResizeObserver(entries=>{const height=entries[0]?.target.scrollHeight;if(height)void shell.setHeight(height+2);});
    observer.observe(compactRef.current);return()=>observer.disconnect();
  },[windowState.compact,shell]);


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
          const data = await apiRequest<{browser_worker: boolean; browser_state?: string;voice?:{transcription:boolean;speech:boolean}}>('/health');
          if (active) {
            setConnection(data.browser_worker ? 'connected' : 'disconnected');
            setBrowserState(data.browser_state ?? 'unknown');
            setVoiceAvailable(data.voice?.transcription??false);voice.setSpeechEnabled(data.voice?.speech??false);
          }
        } catch {
          if (active) setConnection('disconnected');
        }
        await delay(2000);
      }
    };
    void check();
    return () => { active = false; };
  }, [desktop,voice]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, task?.status]);

  const submit = async (instruction = input) => {
    if ((!desktop && !token.trim()) || !connected) return;
    if (!instruction.trim() || commandDisabled) return;
    voice.stopSpeaking();
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

  const latest=messages.filter(message=>message.role==='assistant'&&message.id!=='welcome').at(-1);
  if(windowState.compact)return <div className="floating-shell" ref={compactRef}>
    <header className="floating-header">
      <div className="floating-drag" onPointerDown={event=>{if(event.button===0&&desktop)void shell.action('drag');}}>
        <Orbit size={22}/><strong>ORION</strong><span className={`status-dot ${connected?'online':''}`}/>
        <span>{connected?'Connected':connection==='checking'?'Connecting':'Disconnected'}</span>
      </div>
      <button type="button" onClick={()=>void shell.setMode(false)} disabled={windowState.pending} aria-label="Expand Mission Control" title="Expand Mission Control"><Maximize2 size={17}/></button>
      <button type="button" onClick={()=>{voice.suspend();void shell.action('minimize');}} disabled={!desktop} aria-label="Minimize ORION" title="Minimize; summon with your global shortcut"><Minus size={18}/></button>
    </header>
    <div className="floating-body">
      <div className={`floating-task ${task?.status??''}`} role="status">{busy&&!task?'Sending command...':task?statusLabels[task.status]:'Ready for your command'}</div>
      {task?.instruction&&<p className="floating-command">{task.instruction}</p>}
      {latest&&<p className="floating-response" aria-live="polite">{latest.content}</p>}
      {!connected&&<p className="voice-notice">Start the FastAPI backend. ORION reconnects automatically.</p>}
      {notice&&<p className="voice-notice" role="status">{notice}</p>}
      {voiceControls}
      <form className="floating-composer" onSubmit={event=>{event.preventDefault();void submit();}}>
        <input aria-label="Browser command" placeholder="Or type a command..." value={input} onChange={event=>setInput(event.target.value)} maxLength={2000} disabled={commandDisabled}/>
        <button type="submit" aria-label="Send command" title="Send typed command" disabled={commandDisabled||!input.trim()||!connected||(!desktop&&!token.trim())}><ArrowUp size={18}/></button>
      </form>
      <div className="floating-footer"><span>{windowState.shortcut}</span><span>Click mic to record; 30s max</span></div>
      {windowState.shortcut_error&&<p className="voice-notice">{windowState.shortcut_error}</p>}
    </div>
  </div>;

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
                : connection === 'checking' ? "Connecting..." : "Disconnected"}
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
              { const value = e.target.value; session.setRequest((path, init) => apiRequest(path, init, value)); voice.setTransport(browserVoiceIO(value)); setToken(value); }
            }
            autoComplete="off"
          />

          <p className="hint">
            Stored in memory for this window only.
          </p>
          </>}
        </div>

        <form className="shortcut-settings" onSubmit={event=>{event.preventDefault();void shell.setShortcut(shortcutInput??windowState.shortcut).then(ok=>{if(ok)setShortcutInput(null);});}}>
          <label htmlFor="shortcut">Summon shortcut</label>
          <input id="shortcut" value={shortcutInput??windowState.shortcut} onChange={event=>setShortcutInput(event.target.value)} disabled={!desktop} maxLength={80}/>
          <button type="submit" disabled={!desktop}>Apply shortcut</button>
          <p className="hint">Active: {windowState.shortcut}</p>
          {windowState.shortcut_error&&<p className="voice-notice">{windowState.shortcut_error}</p>}
        </form>
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
            <button className="collapse-button" type="button" onClick={()=>void shell.setMode(true)} disabled={windowState.pending} aria-label="Collapse to floating mode" title="Collapse to floating copilot"><Minimize2 size={17}/></button>
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
            <button className="retry-button" disabled={commandDisabled || !connected || (!desktop && !token.trim())}
              onClick={() => void submit(lastInstruction)}>Retry last command</button>}
          {voiceControls}
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
              disabled={commandDisabled}
              aria-label="Browser command"
              autoComplete="off"
              maxLength={2000}
            />

            <button
              type="submit"
              disabled={commandDisabled || !input.trim() || !connected || (!desktop && !token.trim())}
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

        <div className="telemetry-card voice-timings">
          <p className="section-label">VOICE TIMING</p>
          <div className="metric-row"><span>Transcription</span><strong>{voiceState.transcriptionMs!=null?`${voiceState.transcriptionMs} ms`:'--'}</strong></div>
          <div className="metric-row"><span>Synthesis + transport</span><strong>{voiceState.synthesisMs!=null?`${voiceState.synthesisMs} ms`:'--'}</strong></div>
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
