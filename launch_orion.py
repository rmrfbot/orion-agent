"""ORION launcher: frees ports 8000/5173, then opens backend, frontend and bubble
in three separate terminals (same as RUNBOOK.md).

Run from anywhere:  python launch_orion.py
Flags: --no-kill  skip port killer | --no-bubble | --no-frontend | --no-token-url
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
FRONTEND_URL = "http://127.0.0.1:5173"
WAKE_URL = FRONTEND_URL + "/?wake=1"  # page auto-enables "Hey Orion"

KILL_PS = r"""
foreach ($port in 8000, 5173) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
                     Write-Host "Stopped process on port $port" }
}
"""


def local_token():
    """ORION_LOCAL_TOKEN from the root .env, or empty."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("ORION_LOCAL_TOKEN") and "=" in line:
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def venv_python():
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        sys.exit(f"[ORION] {py} not found - create the .venv first.")
    return str(py)


def find_bubble():
    for p in (ROOT / "orion_bubble.py", ROOT.parent / "orion_bubble.py"):
        if p.exists():
            return p
    return None


def backend_ready():
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=1) as response:
            health = json.load(response)
    except (OSError, URLError, ValueError):
        return False
    return (
        health.get("service") == "ORION Desktop"
        and health.get("browser_worker") is True
    )


def frontend_ready():
    try:
        with urlopen(FRONTEND_URL, timeout=1) as response:
            page = response.read().decode("utf-8")
    except (OSError, URLError, UnicodeDecodeError):
        return False
    return '<div id="root"></div>' in page and "/src/main.tsx" in page


def wait_until(check, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.5)
    return False


def find_chrome():
    candidates = [
        shutil.which("chrome.exe"),
        shutil.which("chrome"),
        os.path.join(
            os.environ.get("ProgramFiles", ""),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
        os.path.join(
            os.environ.get("ProgramFiles(x86)", ""),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google",
            "Chrome",
            "Application",
            "chrome.exe",
        ),
    ]
    return next(
        (str(Path(candidate)) for candidate in candidates
         if candidate and Path(candidate).is_file()),
        None,
    )


def terminal(title, cmd, cwd):
    """Open a new PowerShell window that stays open after the command exits."""
    print(f"[ORION] {title}")
    ps = f"$Host.UI.RawUI.WindowTitle='{title}'; {cmd}"
    return subprocess.Popen(["powershell", "-NoExit", "-Command", ps],
                            cwd=str(cwd), creationflags=NEW_CONSOLE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kill", action="store_true")
    ap.add_argument("--no-bubble", action="store_true")
    ap.add_argument("--no-frontend", action="store_true")
    ap.add_argument("--no-token-url", action="store_true",
                    help="do not pass the local token to the page; type it in yourself")
    args = ap.parse_args()
    py = venv_python()

    if not args.no_kill:
        subprocess.run(["powershell", "-NoProfile", "-Command", KILL_PS])
        time.sleep(1)

    terminal("ORION Backend",
             f"& '{py}' -m uvicorn backend.api:app --host 127.0.0.1 --port 8000", ROOT)
    if not wait_until(backend_ready, 40):
        sys.exit(
            "[ORION] Desktop backend did not become healthy on :8000. "
            "Check the ORION Backend terminal."
        )

    if not args.no_frontend:
        terminal("ORION Frontend", "npm.cmd run dev", ROOT / "frontend")

    if not args.no_bubble:
        bubble = find_bubble()
        if bubble:
            terminal("ORION Bubble", f"& '{py}' '{bubble}'", bubble.parent)
        else:
            print("[ORION] orion_bubble.py not found in repo root or its parent folder.")

    if not wait_until(frontend_ready, 40):
        sys.exit(
            "[ORION] Frontend did not become ready at "
            f"{FRONTEND_URL}. Check the ORION Frontend terminal."
        )

    chrome = find_chrome()
    if not chrome:
        sys.exit(
            "[ORION] Could not find Google Chrome. Install Chrome, then "
            f"open {FRONTEND_URL}."
        )

    token = "" if args.no_token_url else local_token()
    url = WAKE_URL + (f"#token={token}" if token else "")
    subprocess.Popen([chrome, "--new-window", url])
    print(f"[ORION] Chrome opened at {WAKE_URL} (Hey Orion auto-enabled"
          f"{', token passed' if token else ''}).")


if __name__ == "__main__":
    main()
