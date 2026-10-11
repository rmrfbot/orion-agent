# ORION desktop presentation

The existing native Tauri window is titled `ORION | Mission Control`, initially 1200 × 680 with a 900 × 560 minimum. Telemetry stays accessible at smaller sizes. System fonts avoid an external font dependency. Product name is ORION and the existing application identifier remains unchanged.

## Windows launch

Start or restart the backend in one PowerShell terminal:

```powershell
Set-Location 'C:\Users\prana\OneDrive\Desktop\ORION\orion-agent'
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

Open another terminal:

```powershell
Set-Location 'C:\Users\prana\OneDrive\Desktop\ORION\orion-agent\frontend'
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npx.cmd tauri dev
```

Close any separate Vite server occupying port 5173 first. Tauri starts its own server. Keep the backend terminal running when closing ORION; the desktop never owns or terminates Python or Chrome. Startup/health checks do not open Chrome. Browser commands and event callbacks remain on the existing Playwright owner thread.

## Communication and recovery

React invokes Rust's `orion_request`. Rust sends directly to `http://127.0.0.1:8000`, attaches the build-time local token in a sensitive `X-ORION-Token` header, bypasses proxies, disables redirects and applies a ten-second timeout. Only health GET, task POST and safe task-ID GET routes are allowed. The existing build script embeds only `ORION_LOCAL_TOKEN`; no Gemini or other credentials reach React. Embedded credentials are recoverable from a binary: this method is for a matching local development/demo backend, not secure distribution. Rebuild/restart Tauri after changing the token.

Browser-only Vite mode retains its proxy and manual token entry, kept in memory. Local storage saves only a pending task ID, never a token or prompt. Restarting the desktop restores GET polling. Health automatically reconnects; task polling uses 250 ms intervals and two-second reconnect backoff while retaining the duplicate-submission lock. POST is never replayed automatically. Unknown submission outcomes and lost task records are explained before explicit retry. Completed, incomplete and failed results have distinct labels and colors.

`CommandSession.submit(text)` is reusable by typed input and future speech transcription. Optional `onResponse(text, task)` exposes terminal responses for text-to-speech; consumer errors cannot restart polling. No microphone, speech recognition, wake word, ElevenLabs dependency or placeholder button was added.

## Modified files

- `frontend/src/App.tsx`: shared controller, accurate connection/task/browser states, retry and accessible input/conversation.
- `frontend/src/App.css`: responsive telemetry, compact spacing, status colors, focus outlines and offline system fonts.
- `frontend/src/commands.ts`: reusable command submission, polling, duplicate prevention, pending-ID restoration and response callback.
- `frontend/src/desktop.ts`: common native/browser request interface and structured errors.
- `frontend/src-tauri/tauri.conf.json`: window title, dimensions, dark theme and product identity.
- `frontend/src-tauri/src/connection.rs`: structured transport/authentication errors while retaining request restrictions.
- `backend/api.py`: cached browser state in health.
- `backend/browser_worker.py`: cached launching/ready/closed/unavailable browser state updated on the owner thread.
- `tests/test_api_workflow.py`: health regression verifying that it does not launch Chrome.
- `frontend/tests/commands.test.mjs`: six behavioral controller tests.
- `README.md`: native launch guide and embedded-token limits.
- `docs/desktop-presentation.md`: this runbook.

## Validation

- Python unittest discovery: **32 passed**, including local headless browser fixtures; no Gemini calls.
- `node --test tests/commands.test.mjs` from frontend: **six passed** (Node 24).
- `npm.cmd run build`: TypeScript and Vite production build passed.
- Changed-file ESLint passed for `App.tsx`, `desktop.ts`, and `commands.ts`.
- Offline Cargo compilation and **four Rust tests passed**. Compilation validated Tauri configuration.
- Headless UI fixtures passed for native-mode token-free input, single submission, incomplete result, 1366 × 768 and 900 × 560 layouts, disconnect/reconnect and no JavaScript errors. The native bridge was simulated in these fixtures.
- Native `npx.cmd tauri dev` compiled and started the executable. An existing Vite server occupied 5173, so validation used a temporary configuration overriding only `beforeDevCommand`. Windows enumeration confirmed a **visible native window with the exact required title**. Python screen capture was unavailable because Pillow is not installed.

No installer was built, and nothing was committed or pushed. Existing optimization diff files were preserved.

## Remaining demo checks

Restart an older backend process to expose the new health field; otherwise browser state displays unavailable. Before presenting, send `list tabs` through the actual native window, then a direct search and `skip the ad` on YouTube. Live native task execution against Chrome/Gemini was not verified in this pass; the window was verified visible and task/recovery behavior was tested with fixtures.

Chrome startup, networks and Gemini can exceed the existing five-second warm-session target. Unskippable ads play normally. A POST failure before the task ID arrives leaves completion uncertain; check Chrome before explicit retry. Restricted local storage disables restart restoration but does not interrupt a live task. The existing development CSP remains unchanged; this is a local demo configuration, not a production security review.
