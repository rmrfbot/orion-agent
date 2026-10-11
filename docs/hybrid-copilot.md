# ORION hybrid copilot

ORION launches in one compact floating Tauri window. Its dedicated header drag region, always-on-top state, microphone controls, concise response and typed input remain available above Chrome. Expand opens the existing Mission Control dashboard; Collapse restores the floating view. Both views share history, tasks, transcription, connection, audio, mute preference and telemetry. Resizing restores dimensions and position without cumulative drift.

## Configure ElevenLabs

Replace the placeholders privately in the root `.env`:

```dotenv
ELEVENLABS_API_KEY=your_actual_account_key
ELEVENLABS_VOICE_ID=your_selected_voice_id
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
```

Enable both `text_to_speech` and `speech_to_text` permissions on the API key. Choose and preview a calm, natural voice in your ElevenLabs account's Voices/Voice Library, copy its voice ID, and restart FastAPI. ORION uses restrained voice settings, Scribe v2 for English transcription and Flash v2.5 for speech. No credentials belong in chat, React, frontend build variables or Git. Rust continues to embed only the existing local ORION token, a local-demo convenience rather than secure distribution.

## PowerShell startup

Backend terminal:

```powershell
Set-Location 'C:\Users\prana\OneDrive\Desktop\ORION\orion-agent'
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-voice.txt
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Desktop terminal:

```powershell
Set-Location 'C:\Users\prana\OneDrive\Desktop\ORION\orion-agent\frontend'
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npx.cmd tauri dev
```

Close an older desktop if Windows reports `app.exe` locked, and close any separate Vite server on port 5173. The normal Tauri command starts Vite itself. Closing the desktop never terminates FastAPI or Chrome. No installer is built.

## Chrome hands-free wake phrase

The launcher opens the Chrome-hosted ORION UI with wake mode requested. Once
ORION is connected and its local token is available, it starts **Hey Orion**
automatically. Allow microphone and speech-recognition access when Chrome asks;
if Chrome blocks automatic startup, select **Enable Hey Orion** in the UI.
Wake recognition stays on in the background for launcher-started wake mode and
pauses while ORION records or executes a command. Say
**“Hey Orion”**, then speak the command; Chrome speech recognition transcribes
the command and sends its text through ORION's normal task API. If both words
are spoken together, the recognized text after the wake phrase is used; if the
wake phrase is spoken alone, ORION listens for the next utterance. Hiding or
closing the page stops wake recognition.

Wake and command recognition use Chrome's Web Speech recognition API, which may
send microphone audio to an online recognition service. The separate desktop
bubble only uses its microphone stream to animate its audio visualizer; it does
not recognize or submit commands. Push to talk remains available as a fallback
and sends a recorded clip to ElevenLabs for transcription.

## End-to-end demo check

1. Launch compact ORION, confirm Connected and voice readiness, and drag the header above Chrome.
2. In Chrome, select **Enable Hey Orion**, allow microphone and speech-recognition access, and confirm the listening indicator. Say “Hey Orion, open YouTube.” Alternatively, say “Hey Orion,” wait for the command prompt, then say “open YouTube.”
3. Verify one task runs and the text result appears immediately. The wake phrase is removed from the recognized command before it enters the shared command pipeline.
4. With speech unmuted, listen for the same response shown on screen. The speaker button toggles mute; Stop speaking cancels current/pending audio. If autoplay is blocked, Play response uses the already-fetched audio without another synthesis request.
5. Expand Mission Control, inspect conversation/browser/voice telemetry, then Collapse. Pending tasks and transcript must remain intact.
6. Minimize and press Ctrl+Shift+Space to restore/focus ORION. Expanded mode's sidebar lets you change the shortcut; it must include Ctrl and Shift. Conflicts retain the previous working registration. Preferences are saved locally; registrations are released on exit.
7. Record again and click Cancel: nothing should be transcribed or executed. Check permission denial and device disconnection recovery. Minimizing/hiding cancels pending capture/transcription and stops wake recognition; already-submitted browser tasks continue normally.

Startup, showing the window and shortcuts never start wake recognition or command recording; the user must enable the wake phrase from the Chrome UI. Capture is capped at 30 seconds; exceeding the limit cancels rather than executing a partial instruction. Typed commands work when voice is unavailable. Both input paths use CommandSession.submit, without a separate Gemini workflow or speech-summary model call. Playback confirmation requires progress-verified, non-ad playback evidence from the actual browser result; model wording alone cannot claim success.

## Transport and limits

WebView2 MediaRecorder captures supported WebM/Opus or MP4. Web Audio converts it in memory to mono 16 kHz PCM16 WAV. Silent/empty/unsupported recordings fail without executing anything. Tauri transports WAV using raw Uint8Array IPC, never large JSON byte arrays. Rust sends authenticated bytes to a fixed localhost endpoint; synthesis returns binary audio through tauri::ipc::Response. Existing destination restrictions, sensitive token header, proxy bypass and disabled redirects remain intact. Browser-only Vite mode retains its proxy and manual local-token entry.

FastAPI voice endpoints require the existing token and localhost clients. WAV frame data validates duration and format, with a 1 MB input limit. TTS reads the actual response for typed and voice commands, with a 20,000-character input limit, a 2 MB output audio limit, concurrency to two requests and upstream work to bounded connect/read/total deadlines. Requests run asynchronously on FastAPI's loop, never the Playwright owner thread. Existing event pumping, direct browser commands, domain restrictions and ad monitoring are preserved. Separate voice transcription/synthesis PERF timings do not delay browser-result display.

ORION keeps recordings in memory, creates no recording files and logs timings rather than audio or credentials. ElevenLabs' provider retention follows the account policy; local memory-only handling is not provider zero retention. Canceling discards late native results and prevents execution/playback, but already-started provider work can continue until its deadline and may still be billed. Speech uses a complete bounded MP3 response rather than streaming.

## Dependencies and changed files

Python: existing HTTPX 0.28.1 is explicitly declared in requirements-voice.txt; direct REST integration adds no SDK dependency. Frontend: no new packages. Rust: official tauri-plugin-global-shortcut 2.4.1 and its Cargo-locked dependencies.

- backend/api.py: authenticated localhost voice endpoints and safe readiness flags.
- backend/voice_service.py: validation, async provider calls, concurrency/deadlines, sanitized errors and timing.
- backend/requirements-voice.txt: HTTPX dependency declaration.
- backend/universal_agent.py: exposes existing verified playback evidence without extra browser/model work.
- frontend/src/App.tsx and App.css: shared floating/expanded views, accessible controls, settings and lifecycle handling.
- frontend/src/commands.ts: shared command-origin tracking and response callback.
- frontend/src/desktop.ts: raw native audio transport, binary response handling and event subscriptions.
- frontend/src/voice.ts: push-to-talk recording/transcription/speech controller with cancellation, mute and stale-result protection.
- frontend/src/voice-browser.ts: browser/WebView2 microphone and Chrome speech-recognition adapters.
- frontend/src/wake-word.ts: opt-in Chrome wake-phrase and command-recognition lifecycle, restart handling and visible failure states.
- frontend/src/audio.ts: bounded in-memory WAV conversion.
- frontend/src/VoiceControls.tsx: accessible wake-phrase, recording/cancel/mute/playback controls.
- frontend/tests/wake-word.test.mjs: wake phrase detection, restart, permission and cancellation tests.
- frontend/src/window-session.ts: serialized mode transitions and shortcut preferences/conflict feedback.
- frontend/src-tauri/src/overlay.rs: window sizing/restoration, drag/minimize/focus and shortcut registration.
- frontend/src-tauri/src/voice.rs: scoped authenticated binary commands and size bounds.
- frontend/src-tauri/src/lib.rs: native command/plugin registration, inactivity events and shortcut cleanup.
- frontend/src-tauri/src/connection.rs: internal shared HTTP client; existing request restrictions remain.
- frontend/src-tauri/tauri.conf.json: compact initial dimensions, frameless dark appearance and always-on-top state.
- frontend/src-tauri/Cargo.toml and Cargo.lock: shortcut dependency and lockfile.
- tests/test_voice_service.py: provider contracts/errors, auth/binary/duration/concurrency and playback-evidence tests.
- frontend/tests/voice.test.mjs: permission/recording/cancel/audio/window/shortcut/shared-submission tests.
- README.md and docs/hybrid-copilot.md: launch/configuration instructions and this guide.
- Ignored root .env: missing voice model/setup defaults only; existing key and voice values were preserved. User-provided credentials remain private and ignored by Git.

## Validation and remaining demo risks

Validation passed: 64 Python tests, 21 frontend controller tests, eight Rust tests, TypeScript/Vite production build, changed-file ESLint and Git whitespace checks. Cargo compilation also validated Tauri configuration. Automated ElevenLabs requests are mocked. Native Windows checks confirmed compact visibility/always-on-top, expansion with normal decorations, repeated switches with stable dimensions, minimizing, and actual Ctrl+Shift+Space restoration. The normal npx.cmd tauri dev command launched Vite and the native executable. No physical microphone was activated in GUI testing.

Headless UI checks used a synthetic Web Audio microphone with real MediaRecorder and WAV conversion, mocked native speech APIs and mocked playback. They verified one submission, transcript preservation, response-before-audio behavior, focus and compact/expanded continuity. This is not a live microphone/provider/speaker test.

Live configuration check: the user-provided key and voice ID were loaded by restarting FastAPI. Both authenticated localhost voice routes reached ElevenLabs, which returned HTTP 401 `missing_permissions`: the key lacks `text_to_speech` and `speech_to_text`. Enable both permissions in ElevenLabs, or replace the key with one that has both, then restart FastAPI if its value changes. No physical microphone or speaker was activated. Successful provider audio generation, transcription, voice/model access and physical microphone permissions remain unverified until these permissions are corrected. WebView2 codec/autoplay behavior can vary; failures retain typed-command access. Network, Chrome startup and speech-provider latency can exceed the existing warm-session five-second browser target. The existing local-demo credential/CSP setup remains unchanged; no installer or production security review is implied.

Official contracts checked: [Scribe transcription](https://elevenlabs.io/docs/api-reference/speech-to-text/convert), [speech synthesis](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Tauri IPC](https://v2.tauri.app/develop/calling-rust/), [global shortcuts](https://v2.tauri.app/plugin/global-shortcut/).

## Repeat the integration checks

With FastAPI and Vite running, run these from the repository root:

```powershell
.\.venv\Scripts\python.exe tests/check_hybrid_ui.py
.\tests\check_native_hybrid.ps1
```

The UI check uses a synthetic microphone, real recording/WAV conversion, mocked native services and playback, and checks that the exact displayed response is synthesized. The Windows check requires the native desktop to be open; it normalizes expanded/compact mode before checking dimensions, always-on-top, minimize and the default global shortcut. It moves the window and pointer during testing. Neither check activates the physical microphone or sends paid speech requests.

The refreshed responsiveness benchmark records 30 CSS-visibility skip trials, with 26 ms median, 42.7 ms p95 and 52.7 ms maximum eligibility-to-click latency. Routed browser requests completed in 111.9 ms p95 while simulated model calls were pumped, versus 399.9 ms with a blocking model wait. These are local fixtures measured alongside other checks, not live YouTube ad latency.
