#!/usr/bin/env python3
"""ORION hands-free voice client (no browser or Tauri needed).

Listens on your mic, and when you speak inside a listening window it sends the
audio to the ORION backend (ElevenLabs speech-to-text), then submits the text as
a browser task - the same as typing it. Prints every step in this terminal.

  python orion_voice.py --check      test token, backend, ElevenLabs key and mic
  python orion_voice.py              listening window opens now and on each hotkey
  python orion_voice.py --mode always   listen continuously (see warning below)

Needs only what the bubble already uses: numpy + sounddevice (in your .venv).
"""
import argparse, collections, ctypes, io, json, os, queue, re, statistics, sys
import threading, time, urllib.error, urllib.request, wave
from pathlib import Path

import numpy as np

VERSION = "v1"
ROOT = Path(__file__).resolve().parent
RATE = 16000
BLOCK_MS = 100
BLOCK = RATE * BLOCK_MS // 1000
MIN_THRESHOLD = 0.012  # RMS (0..1) below which audio is treated as silence


def say(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- .env / API
def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip("\"'")
    return values


class ApiError(Exception):
    pass


class Api:
    def __init__(self, base, token):
        self.base, self.token = base.rstrip("/"), token

    def _call(self, method, path, body=None, headers=None, timeout=30):
        h = {"X-Orion-Token": self.token}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            try:
                detail = json.loads(raw).get("detail", raw)
            except ValueError:
                detail = raw
            raise ApiError(f"HTTP {e.code}: {detail}") from None
        except (urllib.error.URLError, OSError) as e:
            raise ApiError(f"cannot reach backend at {self.base}: {e}") from None

    def health(self):
        return self._call("GET", "/health", timeout=5)

    def transcribe(self, wav_bytes):
        return self._call("POST", "/api/voice/transcribe", wav_bytes,
                          {"Content-Type": "audio/wav"}, timeout=30)

    def submit(self, text):
        return self._call("POST", "/api/tasks", json.dumps({"instruction": text}).encode(),
                          {"Content-Type": "application/json"}, timeout=10)

    def task(self, task_id):
        return self._call("GET", f"/api/tasks/{task_id}", timeout=10)


def to_wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.astype("<i2").tobytes())
    return buf.getvalue()


# ------------------------------------------------------------- text cleanup
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9, "ten": 10}
WAKE = re.compile(r"^\s*(?:hey\s+)?orion\b[\s,.:!-]*", re.I)


def clean(text):
    text = WAKE.sub("", text).strip().rstrip(" .!?,")
    text = re.sub(r"\b(tab|video|result)\s+(" + "|".join(NUMBERS) + r")\b",
                  lambda m: f"{m.group(1)} {NUMBERS[m.group(2).lower()]}", text, flags=re.I)
    return text


# --------------------------------------------------------------- speech VAD
def rms(block):
    return float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))


class Segmenter:
    """Turns a stream of 100 ms blocks into utterances. Pure logic, no audio I/O."""

    def __init__(self, silence_s=0.9, preroll_blocks=4, min_voiced_s=0.3, max_s=28.0):
        self.silence_s, self.min_voiced_s, self.max_s = silence_s, min_voiced_s, max_s
        self.preroll = collections.deque(maxlen=preroll_blocks)
        self.floor, self._calib = None, []
        self._reset()

    def _reset(self):
        self.state, self.loud, self.quiet, self.voiced, self.buf = "idle", 0, 0, 0, []

    def threshold(self):
        return max(MIN_THRESHOLD, (self.floor or 0) * 3.0)

    def feed(self, block, armed):
        level = rms(block)
        self.preroll.append(block)
        step = BLOCK_MS / 1000.0
        if self.state == "idle":
            if self.floor is None:  # learn room noise from the first ~0.8 s
                self._calib.append(level)
                if len(self._calib) >= 8:
                    self.floor = min(statistics.median(self._calib), 0.02)
                return None, None
            if level < self.threshold():
                self.floor = 0.97 * self.floor + 0.03 * level
                self.loud = 0
                return None, None
            self.loud = self.loud + 1 if armed else 0
            if self.loud >= 2:  # two loud blocks in a row = speech started
                self.state, self.buf = "speech", list(self.preroll)
                self.voiced, self.quiet = self.loud, 0
                return "start", None
            return None, None
        self.buf.append(block)
        if level >= self.threshold() * 0.7:
            self.voiced, self.quiet = self.voiced + 1, 0
        else:
            self.quiet += 1
        if self.quiet * step >= self.silence_s or len(self.buf) * step >= self.max_s:
            audio, voiced = np.concatenate(self.buf), self.voiced * step
            self._reset()
            return ("end", audio) if voiced >= self.min_voiced_s else ("discard", None)
        return None, None


# ------------------------------------------------------------------ hotkey
def parse_hotkey(spec):
    mods = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}
    code, vk = 0x4000, None  # MOD_NOREPEAT
    for part in spec.lower().split("+"):
        part = part.strip()
        if part in mods:
            code |= mods[part]
        elif part == "space":
            vk = 0x20
        elif re.fullmatch(r"f([1-9]|1[0-2])", part):
            vk = 0x70 + int(part[1:]) - 1
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
    if vk is None:
        raise ValueError(f"unsupported hotkey: {spec}")
    return code, vk


def start_hotkey(spec, event):
    if os.name != "nt":
        say("[VOICE] global hotkey is Windows-only; the window opens at start only.")
        return
    from ctypes import wintypes
    mods, vk = parse_hotkey(spec)

    def loop():
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, mods, vk):
            say(f"[VOICE] could not register {spec} (another app uses it). Use --hotkey.")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:
                event.set()

    threading.Thread(target=loop, daemon=True).start()


def beep(freq):
    try:
        import winsound
        threading.Thread(target=winsound.Beep, args=(freq, 70), daemon=True).start()
    except Exception:
        pass


# ------------------------------------------------------------- send command
def handle_utterance(api, audio, args):
    t0 = time.monotonic()
    try:
        heard = api.transcribe(to_wav(audio))["text"].strip()
    except ApiError as e:
        say(f"[VOICE] transcription failed - {e}")
        return
    t1 = time.monotonic()
    command = clean(heard)
    say(f'[VOICE] heard: "{heard}"  ({(t1 - t0) * 1000:.0f} ms transcribe)')
    if not command:
        say("[VOICE] nothing to send.")
        return
    if args.mode == "always" and args.wake and not WAKE.match(heard):
        say('[VOICE] ignored (no "ORION" at the start).')
        return
    try:
        task = api.submit(command)
    except ApiError as e:
        say(f"[VOICE] submit failed - {e}")
        return
    say(f"[VOICE] sent: {command}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            task = api.task(task["id"])
        except (ApiError, KeyError):
            continue
        if task.get("status") in ("finished", "incomplete", "failed", "paused"):
            result = (task.get("result") or {}).get("message") or task.get("error") or ""
            say(f"[ORION] {task['status']}: {result}  ({(time.monotonic() - t1) * 1000:.0f} ms)")
            return
    say("[ORION] still running after 120 s; check the browser.")


# --------------------------------------------------------------------- main
def open_stream(device, q):
    import sounddevice as sd

    def cb(indata, frames, t, status):
        q.put(indata[:, 0].copy())

    return sd.InputStream(samplerate=RATE, channels=1, dtype="int16",
                          blocksize=BLOCK, device=device, callback=cb)


def listen(api, args):
    q, event = queue.Queue(), threading.Event()
    seg = Segmenter(silence_s=args.silence)
    if args.mode == "hotkey":
        start_hotkey(args.hotkey, event)
    window_until = time.monotonic() + args.window if args.mode == "hotkey" and args.start_window else 0
    ignore_until = 0.0
    if args.mode == "always":
        say("[VOICE] ALWAYS mode: every utterance near your mic is sent to ElevenLabs"
            " and may run in your browser. Use --wake to require saying 'ORION' first.")
    with open_stream(args.device, q):
        say(f"[VOICE] ready ({args.mode}). Room-noise calibration takes ~1 s.")
        if window_until:
            say(f"[VOICE] listening window open for {args.window:.0f} s - speak now.")
        while True:
            block = q.get()
            now = time.monotonic()
            if event.is_set():
                event.clear()
                window_until, ignore_until = now + args.window, now + 0.25
                beep(880)
                say(f"[VOICE] listening window open for {args.window:.0f} s - speak now.")
            armed = (args.mode == "always" or now < window_until) and now >= ignore_until
            kind, audio = seg.feed(block, armed)
            if kind == "start":
                say("[VOICE] hearing you...")
            elif kind == "discard":
                say("[VOICE] too short, ignored.")
            elif kind == "end":
                window_until = 0
                beep(660)
                threading.Thread(target=handle_utterance, args=(api, audio, args), daemon=True).start()
            if args.mode == "hotkey" and window_until and now > window_until and seg.state == "idle":
                window_until = 0
                say(f"[VOICE] window closed - press {args.hotkey} to talk again.")


def check(api, args, env):
    ok = True
    say(f"[CHECK] orion_voice {VERSION}")
    say(f"[CHECK] .env: {args.env} {'found' if args.env.exists() else 'NOT FOUND'}")
    if not api.token:
        say("[FAIL] ORION_LOCAL_TOKEN is missing from .env - backend and this script need it.")
        return
    say("[ OK ] ORION_LOCAL_TOKEN found")
    key = env.get("ELEVENLABS_API_KEY", "")
    say(f"[CHECK] ELEVENLABS_API_KEY in .env: {'present' if key else 'MISSING'}")
    try:
        voice = api.health().get("voice", {})
    except ApiError as e:
        say(f"[FAIL] {e}")
        return
    say(f"[ OK ] backend reachable; voice flags: {voice}")
    if not voice.get("transcription"):
        say("[FAIL] backend says speech-to-text is NOT configured (this is why the UI shows"
            " 'Voice setup required').\n"
            f"       Add this line to {args.env} then restart the backend:\n"
            "       ELEVENLABS_API_KEY=your_key_here\n"
            "       The key must have the speech_to_text permission enabled.")
        return
    try:
        import sounddevice as sd
        dev = sd.query_devices(args.device, "input")
        say(f"[ OK ] microphone: {dev['name']}")
    except Exception as e:
        say(f"[FAIL] no usable microphone via sounddevice: {e}")
        return
    q = queue.Queue()
    say('[CHECK] recording 5 s - say: "open YouTube"')
    blocks = []
    with open_stream(args.device, q):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            blocks.append(q.get())
    audio = np.concatenate(blocks)
    peak = max(rms(b) for b in blocks)
    say(f"[CHECK] loudest level {peak:.3f} (speech is usually above 0.02)")
    if peak < 0.01:
        say("[WARN] very quiet - wrong input device or mic muted? Try --device N.")
    t0 = time.monotonic()
    try:
        text = api.transcribe(to_wav(audio))["text"]
    except ApiError as e:
        say(f"[FAIL] transcription error - {e}")
        return
    say(f'[ OK ] ElevenLabs heard: "{text}"  ({(time.monotonic() - t0) * 1000:.0f} ms)')
    say("[ OK ] speech-to-text works. Run without --check to go hands-free.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--check", action="store_true", help="diagnose token, key, mic, transcription")
    ap.add_argument("--mode", choices=("hotkey", "always"), default="hotkey")
    ap.add_argument("--window", type=float, default=8.0, help="seconds to wait for speech")
    ap.add_argument("--silence", type=float, default=0.9, help="seconds of quiet that ends a command")
    ap.add_argument("--hotkey", default="ctrl+alt+space")
    ap.add_argument("--no-start-window", dest="start_window", action="store_false")
    ap.add_argument("--wake", action="store_true", help="always mode: require leading 'ORION'")
    ap.add_argument("--device", type=int, default=None, help="input device index")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--env", type=Path, default=ROOT / ".env")
    args = ap.parse_args()
    env = read_env(args.env)
    api = Api(args.url, env.get("ORION_LOCAL_TOKEN", ""))
    say(f"[VOICE] orion_voice {VERSION}")
    if args.check:
        check(api, args, env)
    else:
        try:
            listen(api, args)
        except KeyboardInterrupt:
            say("[VOICE] stopped.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        input("[VOICE] Press Enter to close...")
