
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / ".orion_chrome_profile"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class APISafeBrowser:
    """
    Wrap the existing UniversalBrowser.

    Denies new website permissions and uncertain clicks
    instead of asking questions through the terminal.
    """

    def __init__(self, base):
        self.base = base

    def __getattr__(self, name):
        return getattr(self.base, name)

    def approve_domain(self, url):
        return self.base.domain_allowed(url)

    def click_element(self, index):
        try:
            item = self.base.element(index)

            tag = item["tag"]
            role = item["role"]
            label = item["label"].lower()

            if tag == "button" or role == "button":
                if "search" not in label and "find" not in label:
                    return {
                        "error": (
                            "Button requires user approval. "
                            "Desktop approval UI not implemented."
                        )
                    }

            # The original click handler may prompt for
            # domain approval. Only permit approved URLs.
            href = item["href"]

            if href:
                from urllib.parse import urljoin

                target = urljoin(
                    self.base.page().url,
                    href
                )

                if not self.base.domain_allowed(target):
                    return {
                        "error": "Website not approved."
                    }

            return self.base.click_element(index)

        except Exception as exc:
            return {"error": str(exc)}

    def execute(self, name, args):
        if name in ("navigate", "open_tab"):
            url = args.get("url", "")

            if not self.base.domain_allowed(url):
                return {
                    "error": "Website is not approved for this demo."
                }

        if name == "click_element":
            return self.click_element(**args)

        if name in ("navigate", "open_tab"):
            # These have already been checked against
            # the currently approved domains.
            return self.base.execute(name, args)

        return self.base.execute(name, args)


class BrowserWorker:

    def __init__(self):
        self.task_queue = queue.Queue(maxsize=20)
        self.tasks = {}
        self.lock = threading.Lock()
        self.thread = None

        self.ready = threading.Event()
        self.startup_error = None
        self.running = False

    def start(self):
        self.thread = threading.Thread(
            target=self._run,
            name="orion-browser-worker",
            daemon=True,
        )

        self.thread.start()
        self.ready.wait(timeout=30)

        if self.startup_error:
            raise RuntimeError(self.startup_error)

        if not self.running:
            raise RuntimeError(
                "Browser worker did not start."
            )

    def submit(self, instruction):
        if not self.running:
            raise RuntimeError("Browser worker is offline.")

        task_id = str(uuid4())

        task = {
            "task_id": task_id,
            "instruction": instruction,
            "status": "queued",
            "created_at": timestamp(),
            "updated_at": timestamp(),
            "result": None,
            "error": None,
        }

        with self.lock:
            self.tasks[task_id] = task

        try:
            self.task_queue.put_nowait(task_id)
        except queue.Full:
            with self.lock:
                del self.tasks[task_id]
            raise RuntimeError("Task queue is full.")

        return dict(task)

    def get_task(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)

            return dict(task) if task else None

    def update_task(self, task_id, **changes):
        with self.lock:
            self.tasks[task_id].update(changes)
            self.tasks[task_id]["updated_at"] = timestamp()

    def stop(self):
        self.running = False
        self.task_queue.put(None)

        if self.thread:
            self.thread.join(timeout=10)

    def _run(self):
        try:
            # Import the existing agent in this thread.
            from backend.universal_agent import (
                UniversalBrowser,
                run_agent,
                START_URL,
            )

            with sync_playwright() as playwright:

                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILE),
                    channel="chrome",
                    headless=False,
                    viewport={
                        "width": 1440,
                        "height": 900,
                    },
                    accept_downloads=False,
                )

                try:
                    base_browser = UniversalBrowser(context)

                    existing = [
                        p for p in context.pages
                        if base_browser.domain_allowed(p.url)
                    ]

                    if existing:
                        base_browser.active_page = existing[0]
                    else:
                        page = context.new_page()
                        base_browser.active_page = page

                        page.goto(
                            START_URL,
                            wait_until="domcontentloaded",
                        )

                    # The existing agent expects browser.execute().
                    # Replace this instance method with safe dispatch.
                    safe_browser = APISafeBrowser(base_browser)

                    # Block terminal-based domain approval.
                    base_browser.approve_domain = (
                        safe_browser.approve_domain
                    )

                    self.running = True
                    self.ready.set()

                    print("[WORKER] Chrome ready.")

                    while True:
                        task_id = self.task_queue.get()

                        if task_id is None:
                            self.task_queue.task_done()
                            break

                        task = self.get_task(task_id)

                        self.update_task(
                            task_id,
                            status="running",
                        )

                        try:
                            result = run_agent(
                                safe_browser,
                                task["instruction"],
                            )

                            if result is None:
                                raise RuntimeError(
                                    "Agent returned no result."
                                )

                            outcome = result.get("outcome")

                            status = (
                                "finished"
                                if outcome == "finished"
                                else "incomplete"
                                if outcome == "incomplete"
                                else "failed"
                            )

                            self.update_task(
                                task_id,
                                status=status,
                                result=result,
                            )

                        except Exception as exc:
                            self.update_task(
                                task_id,
                                status="failed",
                                error=str(exc),
                            )

                            print("[WORKER ERROR]", exc)

                        finally:
                            self.task_queue.task_done()

                finally:
                    context.close()

        except Exception as exc:
            self.startup_error = str(exc)
            print("[WORKER STARTUP ERROR]", exc)

        finally:
            self.running = False
            self.ready.set()
