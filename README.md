# ORION

ORION runs browser commands in a dedicated Chrome session through the local API.

Desktop builds automatically read `ORION_LOCAL_TOKEN` from the project-root
`.env` (or the build environment when it is absent there). Only this local token
is embedded in the native executable; Gemini and other `.env` credentials are
not bundled. Rust attaches the token to requests to `http://127.0.0.1:8000`, so
the desktop app needs no token entry and does not rely on the Vite dev proxy.
The backend must be running with the same token. Rebuild the desktop app after
changing it. This embedded credential is for local development/demo builds,
not secure distribution. Browser-only development retains manual token entry.

For the native presentation window, backend startup commands, reconnect behavior,
and validation results, see [the hybrid copilot guide](docs/hybrid-copilot.md).
Run `npx.cmd tauri dev` from `frontend`; no installer is needed.

Simple searches use a direct route without model calls:

- `search for jazz on YouTube`
- `find Python tutorials on Google`
- `search GitHub for playwright`
- `find orbital mechanics on Wikipedia`

Without a named site, searches use the current YouTube, Wikipedia, or GitHub
page, or Google otherwise. Instructions that include additional actions stay
with the AI planner.

The direct route uses a shared 4.5-second navigation/readiness budget and the
dashboard polls every 250 ms. If the page is not ready within that budget, ORION
reports an incomplete search. Five seconds is a warm-session target, not a
guarantee: Chrome startup, queue delays, network latency, and complex AI tasks
can take longer. API-mode execution telemetry includes queue and browser startup
time. Per-stage monotonic timings are available in task results and `[PERF]` logs.

On YouTube, a page-local watcher clicks visible, enabled Skip Ad controls as
they become available, including on restored tabs and during idle playback.
Unskippable ads still play normally. The agent can inspect the player, playback,
ad status, and skip availability through `media_state`.

Run the focused tests from the project root with:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_fast_search.py -v
```

These tests use local page fixtures in headless Chrome; they do not contact
Gemini or validate live YouTube latency.

The ad monitor uses mutation-driven detection with a 100 ms visibility fallback.
Explicit playback checks require the video position to advance; a general page
observation labels active playback as unverified to avoid adding a fixed wait.

See [the latency audit and measured benchmarks](docs/latency-optimization.md)
for the execution path, measurement limits, validation, and changed files.

The latest [responsiveness fixes](docs/responsiveness.md) keep routed browser
requests moving while the worker is idle or waiting on Gemini. Explicit commands
such as `skip the ad`, `pause`, `play`, `scroll down`, `switch to tab 2`, and
`open YouTube` run locally. `play jazz on YouTube` searches locally, uses one
model call to choose a result, and verifies playback locally. Tab/video numbers
in these explicit commands start at 1.


ORION now launches as a floating copilot. Expand opens Mission Control;
Ctrl+Shift+Space restores the desktop window. See the [hybrid copilot and voice
guide](docs/hybrid-copilot.md) for ElevenLabs setup, microphone controls,
startup commands, the optional “Hey Orion” wake phrase, validation and demo
limitations. Chrome wake-phrase and command recognition may use an online
speech service; it is off until explicitly enabled in the UI.
