# ORION

ORION runs browser commands in a dedicated Chrome session through the local API.

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
can take longer. Execution time is shown in telemetry; it excludes startup and
queue time.

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
