# Browser request handling

ORION checks approved Google and YouTube pages for Google `/sorry` URLs, visible CAPTCHA controls, unusual-traffic challenge text outside search-result containers, and YouTube player messages requiring human sign-in verification. Ordinary search results mentioning CAPTCHA or hidden controls do not trigger a pause. Evidence includes the challenge URL, site and detection reason in the task result.

A detected challenge produces task status `paused` and `human_intervention_required: true`. The desktop stops polling that task, shows an amber human-verification state and offers explicit retry. Complete verification manually in the Playwright-managed Chrome window, then retry. ORION does not click, submit, dismiss, solve or navigate away from the challenge. Repeated requests while it remains active are refused; there is no automatic task replay or resume. Switching/listing tabs and local scrolling remain available. Verification tabs cannot be automatically closed; ordinary tab closing remains available. A challenge on another tab blocks requests to the same protected site.

Successful identical searches can reuse cached results for five seconds, provided the tab, URL and document identity still match. Navigated, reloaded, closed or challenged tabs invalidate the cache. Existing result tabs with recognizable result elements can be reused without refreshing; YouTube video lists are extracted again when appropriate. Failed searches are never cached as successful results.

Identical network attempts within two seconds are rejected immediately rather than delayed. Navigation, link navigation and search-form submissions receive this protection. Distinct search URLs can proceed immediately. Repeated explicit network actions in one AI task are stopped to prevent planner loops. Playback, ad skipping, typing, scrolling and other local UI actions receive no artificial sleeps or cooldowns. Existing inference event pumping, direct-command routing, domain restrictions and API authentication remain intact.

## Changed files

- `backend/request_policy.py`: evidence detection, short-lived success cache and network-only duplicate suppression.
- `backend/universal_agent.py`: guarded search/navigation/interactions, result-tab reuse, planner loop prevention and paused results with evidence.
- `backend/browser_worker.py`: paused status propagation and verification guards around API-mode clicks.
- `frontend/src/commands.ts`: paused tasks stop polling and require explicit retry.
- `frontend/src/App.tsx`, `frontend/src/App.css`: human-intervention status, warning icon/color and retry action.
- `tests/test_request_policy.py`: 17 policy/browser regression tests using local page fixtures, including manual-verification recovery, duplicate Google/YouTube searches, stale caches, form/link submissions and local controls.
- `frontend/tests/commands.test.mjs`: paused-task polling and explicit-retry regression.
- `docs/request-handling.md`: this guide.

## Validation and limits

Python regression suite: **49 passed**. Frontend controller suite: **seven passed**. TypeScript/Vite build, changed-file ESLint and Git whitespace checks passed. Existing playback, ad-monitor, event-pump and domain/authentication regressions remain covered.

Tests use local headless Chrome fixtures and mocked model calls; they do not solve or exercise live CAPTCHA services. Detection depends on known URL/DOM evidence and English challenge messages, so changed layouts, localization or new verification providers may require additional evidence rules. A challenge arriving after an already-completed task is detected on the next relevant operation. Google detection currently covers the approved `google.com` domain family, without expanding the existing allowlist to regional domains. Existing domain restrictions can block third-party verification iframe origins; ORION does not automatically approve them. Cached search results may be up to five seconds old.

Manual retry starts a new task and can repeat previously completed actions in a complex instruction; inspect Chrome first. Paused tasks are not resumed midway. This work adds no stealth libraries, spoofing, CAPTCHA solvers, proxy rotation, installers or credential changes. No changes were committed or pushed.
