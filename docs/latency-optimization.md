# ORION latency audit

## Execution path and causes

The desktop posts a command to FastAPI, which queues it in `BrowserWorker`.
One owning thread launches or reuses Chrome and calls `run_agent`. Simple
explicit searches retain their existing deterministic route. Other instructions
go through an initial page observation, Gemini manual function calls, browser
tools, and a final Gemini response. The desktop polls every 250 ms.

The YouTube monitor is an init script on new documents and is explicitly
installed on restored pages. Its JavaScript runs in the browser process without
a Gemini call, Python task, network request, or extension service worker per ad.
The extension remains a future browser bridge, rather than the active skipper.
[Playwright evaluation documentation](https://playwright.dev/python/docs/evaluating)
describes the separate browser execution context used here.

The previous monitor used a document-wide mutation observer, repeated selector
queries, a 250 ms interval, and one global 500 ms cooldown. A mutation arriving
during the cooldown could be discarded; timer boundaries could then extend the
delay past 500 ms. Its first-match queries also missed available controls when
a hidden duplicate appeared first. It did not respect `aria-disabled`, keep
confirmation records, or provide explicit cleanup. The supplied local benchmark
exercises the cooldown with rapid successive controls and exercises CSS-only
visibility separately. It does **not** reproduce a five-second live delay.

Separately, video opening allowed serial waits of 30 seconds for navigation,
12 seconds for attachment, and 8 seconds for a video locator. The subsequent
`play()` promise had no local bound. Playback success meant only `!paused`,
which can also describe a stalled or buffering video.

Remaining general-tool waits include 25-second navigation limits, 8-second
element actions, 5-second DOM readiness checks, and a 400 ms scroll settle.
Gemini requests and transient-error retries can dominate multi-step tasks;
retry sleeps are 1.5–2.5 seconds on the first retry. These are outside ad
skipping and have not been removed indiscriminately or benchmarked against live
Gemini. Chrome startup still opens the existing approved start page, preserving
session and contextual-search behavior. Sequential model-dependent actions
cannot safely overlap. No concurrent Playwright calls were introduced.

## Changes and measurement definitions

- One idempotent monitor per document caches candidates and reacts to relevant
  DOM mutations. It checks all matching controls, including `aria-disabled`,
  disabled fieldsets, hidden/inert controls, opacity, and pointer eligibility.
  It uses a 100 ms fallback for CSS changes without an observed DOM mutation,
  and a full selector refresh at most once a second during fallback operation.
- Per-control retries replace the global cooldown. An unconfirmed unchanged
  control has a one-second retry interval and a maximum of three attempts until
  it becomes unavailable. A different eligible control can be clicked immediately.
- SPA navigation refreshes candidates; full navigation installs a new document
  monitor. `stop()`, pagehide, and document destruction clean up observers,
  timers, listeners, and candidate references. A restored back/forward-cache
  document reinstalls one monitor. Samples are bounded to the latest 100 clicks.
- `performance.now()` records first observation, time waiting for observed
  eligibility, eligibility-check cost, click dispatch, synchronous click-handler
  cost, and confirmation. Confirmation distinguishes removed/unavailable control
  from an ended ad. Dispatch alone is not proof that an advertisement ended.
- True eligibility-change time is known only in the fixture, where its producer
  timestamps the change. Live `eligible_observed_at_ms` records when ORION saw
  eligibility; it cannot measure browser scheduling delay before observation.
- Playback checks use the HTMLVideoElement API and a 350 ms observation of
  `currentTime`. They distinguish opened, loading, paused, buffering, playing,
  ended, error, and advertisement states. Source/video/ad replacement or seeking
  invalidates progress evidence. Playback requests have a 500 ms promise bound;
  a buffering, already unpaused player is never toggled or clicked again.
- A general page observation reports playback as `unverified` without a fixed
  wait. Explicit `media_state` and `youtube_play` checks verify progress. Only
  verified progress reports `playing: true`; an ad is separately identified.
- YouTube video navigation and attachment now share an eight-second budget.
  A watch page whose video has not attached reports opened/loading, not playing.
- Monotonic Python stage timings cover API submission, queueing, browser ensure,
  agent execution, Gemini requests/turns, searches, video readiness, playback,
  tools, and final tabs. Additive `timings`, `workflow_timings`, and
  `total_elapsed_ms` fields preserve existing task fields. Desktop console timing
  covers submission through observed completion, including polling delivery.
- Browser reuse removes one redundant renderer probe but retains the initial
  probe, browser connectivity check, closed-tab reselection, and recovery.

## Benchmarks

Results are generated by `tests/benchmark_latency.py` with a frozen copy of the
pre-change methods and monitor in `tests/fixtures/latency_baseline.py`. Both
implementations use the same local HTML fixture and native muted audio playback
through an HTMLVideoElement. The native progress check uses
[HTMLMediaElement.currentTime](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/currentTime). All browser requests are intercepted by the test
fixture; no live YouTube, Google, Gemini, passwords, tokens, or cookies are used.
The fixture intentionally represents only a small player page, not YouTube's
actual network, DOM workload, ad delivery, or video selection quality.

**30 runs per operation; values are p50 / p95 / maximum in milliseconds.**

| Operation | Before | After |
| --- | ---: | ---: |
| Skip: enabled/inserted control | 721.900 / 729.200 / 742.000 | 0.100 / 1.200 / 1.700 |
| Skip: CSS-only visibility | 222.400 / 229.900 / 231.600 | 73.300 / 81.800 / 82.200 |
| YouTube search completion | 107.881 / 138.131 / 138.783 | 111.766 / 119.434 / 120.097 |
| Video open plus playback check | 237.825 / 474.573 / 491.384 | 483.728 / 511.374 / 512.813 |
| Explicit playback check | 72.043 / 86.341 / 146.395 | 356.983 / 368.436 / 368.518 |
| General page observation | 2.574 / 3.910 / 6.446 | 2.739 / 3.688 / 3.911 |
| Warm browser reuse (3 runs) | 6.232 / 7.075 / 7.075 | 3.535 / 3.823 / 3.823 |
| Cold launch/recovery (3 runs) | 665.126 / 709.889 / 709.889 | 703.163 / 723.615 / 723.615 |

**Additional after-only phase measurements, 30 runs each:**

| Phase | p50 / p95 / maximum (ms) |
| --- | ---: |
| Eligibility change to observed eligibility | 0.100 / 1.000 / 1.700 |
| Observed eligibility to click dispatch | 0.000 / 0.100 / 0.100 |
| Click dispatch to monitor confirmation | 5.800 / 6.800 / 7.000 |
| search.navigate | 42.645 / 51.109 / 57.504 |
| search.results_ready | 52.104 / 57.451 / 58.624 |
| search.extract | 15.112 / 17.343 / 17.534 |
| video.navigate | 38.547 / 58.857 / 61.281 |
| video.attach | 74.880 / 80.483 / 89.864 |
| video.playback_verify | 370.707 / 379.024 / 382.668 |

The after monitor dispatched exactly 30 clicks for the 30 rapid-control trials;
its counters recorded one full scan, 50 cached eligibility checks, and 135
mutation records during that scenario. These counts exclude the separate CSS
trials and subsequent navigation benchmarks.


Raw values, Chrome version, and sample counts are in
[latency-benchmark.json](latency-benchmark.json). p95 uses nearest rank; for the
three recovery runs, p95 equals the maximum. Headless fixture results do not
establish a live or background-tab SLA. Browser timer throttling, main-thread
work, changed YouTube selectors, and network/model latency remain risks.

Playback opening/checks intentionally spend time verifying progress that the
previous implementation never verified. These measurements are a correctness
tradeoff, not an equivalent-operation speedup. No end-to-end Gemini speedup or
guaranteed five-second search response is claimed.

## Validation and reproduction

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/benchmark_latency.py --runs 30
cd frontend
npm.cmd run build
node node_modules/eslint/bin/eslint.js src/App.tsx
```

The tests cover API authentication/submission/polling, additive workflow timing,
manual Gemini function-call round trips, search routes, enabled/hidden/disabled
controls, CSS fallback, click confirmation timeout, repeated SPA/full navigation,
stop/pagehide/back-forward-cache lifecycle, real media progress, stalled/paused/
loading/error/ad playback, domain rejection, and real headless Chrome recovery.
Recovery and closed-tab reselection run on the owning thread. All 22 tests pass. The final frontend
build and changed-file ESLint check pass. Native Tauri packaging and live YouTube
have not been exercised. The installed Starlette TestClient emits an httpx
deprecation warning; no dependency changes are required for these tests to pass.

Restart the backend to install the new scripts on the current session. The JS
assets must remain alongside `universal_agent.py` when distributing the Python
backend. The existing Tauri shell and MV3 manifest/service worker are unchanged.

## Changed files

| File | Purpose |
| --- | --- |
| `backend/youtube_monitor.js` | Candidate-based skip detection, lifecycle, bounded metrics and confirmation |
| `backend/youtube_playback.js` | Bounded native playback request and progress verification |
| `backend/universal_agent.py` | Script integration, shared YouTube wait budgets, playback states and stage timing |
| `backend/performance.py` | Monotonic stage timing and performance-only logs |
| `backend/browser_worker.py` | Queue/startup/total timing and one fewer warm-session renderer probe |
| `backend/api.py` | Submission timing with the existing endpoints/authentication |
| `frontend/src/App.tsx` | Overall server execution time and observed command-to-result timing |
| `tests/test_youtube_monitor.py` | Browser, watcher, playback, safety and recovery regressions |
| `tests/test_api_workflow.py` | API/task compatibility and manual function calling |
| `tests/fixtures/player.py` | Repeatable local ad DOM and native playback fixture |
| `tests/fixtures/latency_baseline.py` | Frozen pre-change methods for comparison only |
| `tests/benchmark_latency.py` | Before/after distributions and recovery benchmark |
| `docs/latency-benchmark.json` | Measured results |
| `docs/latency-optimization.md` | Audit, definitions, results and limitations |
| `README.md` | Telemetry semantics and audit/reproduction link |
