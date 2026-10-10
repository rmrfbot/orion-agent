# Orion — PLAN.md

Voice-controlled study assistant that lives in Chrome. The student talks, Orion navigates their real Canvas (or any site), reads the material, explains it, and quizzes them.

**Paste this whole file into every AI coding session.** It is the single source of truth. If you change an interface, change it here first and tell the team.

---

## 1. The one demo flow (everything else is optional)

1. Student holds the mic button and says: *"Open my binary search tree notes."*
2. Orion narrates as it works: *"Opening your Data Structures course… found Module 5… opening the notes."*
3. The notes page opens in the student's own browser tab.
4. Orion says a short spoken summary of the page.
5. Student says: *"Quiz me on this."* Orion asks a question out loud, the student answers by voice, Orion gives feedback.

If this works reliably 10 times in a row, we win. Do not add features until it does.

**Tracks we are targeting:** Best Overall, Best Pitch/Demo, Best Use of Gemini, Best Use of ElevenLabs. (Not Vultr, Backboard, Solana, Tiger Data.)

---

## 2. Architecture

```
Chrome extension
  Side panel (UI + mic + agent loop)
     │  chrome.tabs.sendMessage         ┌──────────────────────────┐
     ├───────────────────────────────►  │ Content script (in tab)  │
     │  {observe | click | readText}    │ lists/clicks/reads DOM   │
     │                                  └──────────────────────────┘
     │  HTTP (fetch)
     ▼
FastAPI backend (localhost:8000)   ← holds ALL API keys
  POST /transcribe  audio  → text            (ElevenLabs STT)
  POST /plan        state  → next tool call  (Gemini function calling)
  POST /speak       text   → audio           (ElevenLabs TTS)
  POST /study       page text + request → summary / quiz Q / feedback (Gemini)
```

Key decisions:
- **The agent loop runs in the side panel**, not the service worker (MV3 service workers sleep after ~30s idle).
- **The backend is stateless.** The side panel sends the full state each call. No database.
- **API keys live only in the backend `.env`.** Never in extension code.
- **No Docker, no cloud deploy.** Backend runs on a laptop for the live demo. We also submit a recorded demo video and a repo.
- **Fallback:** if the extension spike (see milestone 0) fails, we switch to Playwright driving a mock portal. Decide at the 45-minute mark, not later.

---

## 3. Tech stack

| Layer | Tech |
|---|---|
| Extension | Chrome Manifest V3, side panel, content script, plain JS (React only if one teammate is already fast with it) |
| Backend | Python 3.11+, FastAPI, uvicorn |
| LLM | Gemini via `google-genai` (function calling) |
| Voice | ElevenLabs Python SDK (speech-to-text and text-to-speech) |
| Config | `python-dotenv`, `.env` (in `.gitignore`) |

Install:
```
pip install fastapi uvicorn google-genai elevenlabs python-dotenv python-multipart
```
SDK method names change often. **Check each official quickstart and paste it into the AI prompt as the reference.** Get one hello-world call per API working before building around it.

`.env` (backend only):
```
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

---

## 4. Repo layout

```
orion/
├── PLAN.md
├── README.md
├── .gitignore            (.env, node_modules, __pycache__)
├── backend/
│   ├── main.py           FastAPI app + CORS + routes
│   ├── agent.py          /plan logic: Gemini tool declarations + call
│   ├── study.py          /study logic: summary, quiz, feedback prompts
│   ├── voice.py          ElevenLabs STT/TTS wrappers
│   ├── requirements.txt
│   └── .env.example
└── extension/
    ├── manifest.json
    ├── background.js     opens the side panel on icon click, nothing else
    ├── content.js        observe / click / readText
    ├── sidepanel.html
    ├── sidepanel.js      mic, agent loop, UI, audio playback
    └── sidepanel.css
```

Rule: **one owner per file**. Nobody edits a file they don't own without asking.

---

## 5. Interfaces (the contracts everyone codes against)

### 5.1 Extension messages (side panel → content script)

```js
// observe: returns the clickable elements and a text excerpt
{ type: "observe" }
→ { url, title, elements: [{ index: 0, tag: "a", text: "Modules" }, ...], textExcerpt: "first ~1500 chars" }

// click an element by its index from the LAST observe
{ type: "click", index: 7 }
→ { ok: true } | { ok: false, error: "..." }

// full visible text of the page (for study features)
{ type: "readText" }
→ { text: "..." }   // truncate to ~15,000 chars
```

Content script rules:
- Number only visible, clickable elements (`a`, `button`, `[role=button]`, `[role=link]`, `input[type=submit]`). Keep text under ~80 chars. Cap at ~60 elements.
- Re-observe after every click. The page may navigate and reload the content script; wait ~1s and retry once on connection error.
- Canvas may use iframes. Test on a real Canvas page early.

### 5.2 Backend routes

```
POST /transcribe     multipart: audio file            → { text }
POST /speak          { text }                         → audio/mpeg bytes
POST /plan           { request, history, observation } → one of:
                       { action: "click", index: 7, narration: "Opening Modules" }
                       { action: "done", reply: "I opened your BST notes." }
                       { action: "fail", reply: "I couldn't find that page." }
POST /study          { mode, pageText, userInput? }   → { reply }
                       mode: "summarize" | "quiz_question" | "grade_answer" | "explain"
```

`history` is a list of `{ action, index, narration, resultUrl }` from this task so far.
Enable CORS in FastAPI (`CORSMiddleware`, allow origins `*` is fine for the hackathon).

### 5.3 Agent tools Gemini can call (declared in `agent.py`)

- `click(index)`: click an element from the current observation
- `done(reply)`: task finished; `reply` is one or two spoken sentences
- `fail(reply)`: could not complete

Keep the tool set tiny. Gemini picks by **index from the numbered list**, never by writing selectors.

### 5.4 Agent loop (side panel)

```
for step in range(10):                       # hard cap
    observation = content.observe()
    plan = POST /plan {request, history, observation}
    speak/show plan.narration
    if plan.action == "click": content.click(plan.index); wait ~1s; record history
    else: break
```
Add a timeout per step. Ask for explicit confirmation before anything irreversible (submitting, sending, deleting). Our demo flow never needs it, but the check should exist.

---

## 6. Ownership (team of 4)

| Person | Owns | Done when |
|---|---|---|
| **A: Agent** | `backend/agent.py`, `/plan`, loop logic in `sidepanel.js` with P-C | Typed command opens the right page in 8/10 runs |
| **B: Voice** | `backend/voice.py`, `/transcribe`, `/speak`, mic recording and playback in side panel | Hold button → speak → text appears; text → audio plays |
| **C: Extension/UI** | `manifest.json`, `content.js`, side panel UI (mic button, transcript, action log) | Side panel opens, content script lists and clicks elements on Canvas |
| **D: Study + Pitch** | `backend/study.py`, `/study`, README, architecture diagram, demo script, recorded video | Summary, quiz and grading work on real notes text; submission ready |

Everyone **stubs** the other pieces at first (fake `/plan` response, hardcoded observation, canned audio) so no one is blocked.

---

## 7. Milestones (counted from kickoff, adjust to your real deadline)

| Time | Goal |
|---|---|
| 0:00–0:30 | Repo, folders, `.env`, everyone installs deps. Hello-world per API (Gemini, ElevenLabs). |
| 0:30–1:15 | **Extension spike:** side panel button → content script lists and clicks a link on Canvas → one round trip to a FastAPI route. **If not working at 1:15, switch to Playwright + mock portal plan.** Also test `getUserMedia` (mic) in the side panel now. |
| 1:15–3:30 | Typed command works end to end through the agent loop (no voice yet). |
| 3:30–5:00 | Voice in and out wired to the same loop. Push-to-talk. Narration spoken as the agent works. |
| 5:00–6:30 | Study features: spoken summary, quiz question, answer grading by voice. |
| 6:30–7:30 | Full integration run of the demo flow, bug fixing, reliability testing (10 runs). |
| 7:30–8:30 | UI polish, README with setup steps and architecture diagram. **Feature freeze at 8:30.** |
| 8:30–10:00 | Record backup demo video, rehearse the live script 3 times, submit. |

---

## 8. Known risks and mitigations

| Risk | Mitigation |
|---|---|
| Mic permission is awkward in extension side panels | Test in the first hour. Workarounds: grant permission via a small extension tab page, or an offscreen document. |
| Agent clicks wrong element or loops | Numbered element list (not raw HTML), 10-step cap, clear tool descriptions, test the same command 10 times. |
| Voice latency makes silent gaps | Narrate each step aloud ("opening Modules…"). Keep replies short. |
| Content script dies on navigation | Re-observe after every action, wait ~1s, retry once. |
| Canvas uses iframes or dynamic content | Test early on the real page. Keep a mock page as a fallback demo. |
| API rate limits or network trouble during demo | Test with real keys. Keep the recorded video and a scripted fallback path for the one demo flow. |
| SDK method names are outdated in AI output | Paste the official quickstart into the prompt. Fix import/attribute errors from the docs, not by guessing. |
| Keys leak | Backend `.env` only, `.gitignore` it, share keys privately, never in extension code. |

---

## 9. Working rules

1. **Run it after every small change.** Never accept 300+ lines you haven't executed.
2. **Commit every time something works**, push often, pull before starting a new chunk.
3. **One owner per file.** Interface changes go through this document.
4. **Give the AI specifics**: file name, function signature, inputs/outputs, "no extra features", and paste the real traceback when something fails.
5. **Debug bottom-up**: content script alone → backend route alone → loop with typed text → voice.
6. **Don't add features after the freeze.** Reliability and the demo are the only goals after 8:30.

---

## 10. Definition of done

- [ ] Extension loads unpacked and the side panel opens
- [ ] Typed *and* spoken command opens the right notes page on Canvas
- [ ] Orion narrates steps and speaks a summary aloud
- [ ] "Quiz me" works: spoken question, spoken answer, spoken feedback
- [ ] Demo flow succeeds 10/10 times in rehearsal
- [ ] Repo has README with setup steps, `.env.example`, and an architecture diagram
- [ ] Recorded demo video exists as a backup
- [ ] Hosted site / submission page links to the repo and video
- [ ] Pitch rehearsed: problem (studying shouldn't mean hunting through menus), who it helps (students, accessibility), why Orion (works in your own logged-in browser, voice-first, transparent action log)

## 11. Pitch notes

- **Problem:** Students lose focus navigating LMS menus, and people who can't easily use a mouse are shut out.
- **Why us vs. generic browser agents:** it's a study companion, not just a clicker. Find the notes, explain them, quiz you, all by voice.
- **Trust:** narrated actions, a visible action log, confirmation before irreversible steps.
- **Honest limits:** say what is mocked or scripted. Judges respect that more than a demo that falls over.
