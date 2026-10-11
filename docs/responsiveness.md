# Browser responsiveness follow-up

The earlier skip benchmark isolated the page-local watcher. It did not exercise
the sync Playwright owner's blocking waits. The application routes every browser
request through that owner for its navigation guard. Blocking on `queue.get()`
while idle, or synchronous Gemini HTTP requests/retry sleeps, can leave routed
requests paused. This holds up resources needed by videos and advertisements.
[Playwright documents that blocking Python sleeps prevent its asynchronous work
from being processed](https://playwright.dev/python/docs/library).

`browser_io.py` now keeps driver callbacks flowing on the original Playwright
thread. Only Gemini network work runs on one separate thread. The worker pumps
events while idle; it picks queued work between short pumps. Tests assert that
route callbacks remain on the owning thread and that inference runs elsewhere.
No navigation restriction was removed. Routing still disables HTTP caching;
removing that guard would be a separate security-sensitive design change.

The owner also ticks cached YouTube skip candidates at most every 50 ms while
idle or waiting for inference. This complements mutation detection and the
50 ms in-page fallback, particularly when browser timers are throttled. It does
not make a busy renderer instantaneous. Confirmed controls are not clicked again
until they become unavailable, and unconfirmed controls retain bounded retries.
Only three recent skip samples enter model-facing results; the full bounded
100-sample history remains available in the page's monitor snapshot.

Explicit skip, pause/resume, scrolling, tab selection/closing, numbered video
opening, and website-opening commands no longer require inference. Existing
search fast paths remain. Natural-language requests such as `play jazz on
YouTube` use one inference to select a returned result, followed by local
playback verification, without another inference just to report success. Complex
instructions retain manual function calling and model content/metadata.

Other changes:

- Gemini HTTP timeout defaults to 10,000 ms, configurable through
  `ORION_MODEL_TIMEOUT_MS`. SDK retries and duplicate application retries are
  disabled; a configured fallback is attempted immediately on transient API
  errors. No backoff sleep blocks the browser owner.
- Responses are capped at 1,024 tokens. Truncated responses fail without
  executing a partial action. The agent stops requesting more steps after a
  30-second budget; an already running bounded request/action can overrun it.
- Ordinary navigation and element actions have four-second limits; post-click
  and post-Enter readiness checks have 1.2-second limits. These are failure
  limits, not fixed waits. Initial Chrome navigation waits for commit with a
  four-second limit instead of the previous 20-second DOM-ready limit.
- Typing returns a small result and preserves the observed index map instead
  of extracting another full page. Scrolling uses a synchronous native scroll
  without a 400 ms sleep or a potentially suspended animation-frame promise.
- Playback still requires measured progress. Buffering or advertisements are
  not reported as completed video playback.

## Measured results

The new benchmark uses real headless Chrome and local routed fixtures. A
simulated 250 ms remote call reproduces the Python blocking condition; it does
not measure live Gemini inference or YouTube's network/DOM behavior.

| Measurement | Runs | p50 | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Routed resource completion with blocked owner | 20 | 284.55 ms | 295.5 ms | 295.7 ms |
| Routed resource completion with event pumping | 20 | 30.55 ms | 35.8 ms | 42.1 ms |
| CSS-only Skip Ad eligibility to click | 30 | 27.45 ms | 44.5 ms | 45.5 ms |

Raw data: [responsiveness-benchmark.json](responsiveness-benchmark.json).
These resource measurements explain one application stall and do not constitute
an end-to-end speed guarantee. Live model latency, background page scheduling,
YouTube changes, and renderer workload remain outside these fixture results.
Shorter timeouts can report incomplete tasks on unusually slow pages.

## Validation and application

31 tests pass, including thread ownership, routing during inference and idle
periods, direct-command safety, single-call video selection, manual function-call
compatibility, real playback progress, ad lifecycle, recovery, and scrolling
with animation-frame callbacks suppressed. JavaScript syntax and Git whitespace
checks pass. No frontend/native bridge change is needed in this follow-up.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tests/benchmark_responsiveness.py
```

Restart the backend to load these Python and injected-script changes. The existing
desktop app can then use the updated backend without rebuilding its executable.

Changed runtime files: `backend/browser_io.py`, `backend/browser_worker.py`,
`backend/fast_commands.py`, `backend/universal_agent.py`,
`backend/youtube_monitor.js`, and `backend/youtube_playback.js`. Regression tests
and the benchmark are in `tests/test_responsiveness.py`,
`tests/test_api_workflow.py`, `tests/test_youtube_monitor.py`, and
`tests/benchmark_responsiveness.py`. README links this report and its JSON data.
