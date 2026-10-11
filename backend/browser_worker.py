import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from uuid import uuid4

from playwright.sync_api import sync_playwright
from backend.performance import measure, logger
from backend.browser_io import pump_context

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / ".orion_chrome_profile"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class APISafeBrowser:
    """Keep API mode noninteractive, with the existing site allowlist."""

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
            label = (item.get("label") or "").lower()

            if tag == "button" or role == "button":
                if "search" not in label and "find" not in label:
                    return {
                        "error": "Button requires approval; desktop approval UI is not implemented."
                    }

            href = item.get("href")
            if href:
                target = urljoin(self.base.page().url, href)
                if not self.base.domain_allowed(target):
                    return {"error": "Website is not approved."}

            return self.base.click_element(index)
        except Exception as exc:
            return {"error": str(exc)}

    def execute(self, name, args):
        if name in ("navigate", "open_tab"):
            url = args.get("url", "")
            if not self.base.domain_allowed(url):
                return {"error": "Website is not approved for this demo."}

        if name == "click_element":
            blocked = self.base.verification_state()
            if blocked:
                return blocked
            result = self.click_element(**args)
            return self.base.verification_state() or result

        # YouTube tools are scoped inside UniversalBrowser to youtube.com,
        # and youtube_open_video only accepts URLs from youtube_search.
        return self.base.execute(name, args)


class BrowserWorker:
    """Single-threaded Playwright owner; Chrome opens on demand."""

    def __init__(self):
        self.task_queue = queue.Queue(maxsize=20)
        self.tasks = {}
        self.lock = threading.Lock()
        self.thread = None
        self.ready = threading.Event()
        self.startup_error = None
        self.running = False
        self.context = None
        self.safe_browser = None
        self.submitted_at = {}
        self.browser_state = 'not_started'

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.ready.clear()
        self.startup_error = None
        self.thread = threading.Thread(
            target=self._run, name="orion-browser-worker", daemon=True
        )
        self.thread.start()
        if not self.ready.wait(timeout=30):
            raise RuntimeError("Browser worker startup timed out.")
        if self.startup_error:
            raise RuntimeError(self.startup_error)
        if not self.running:
            raise RuntimeError("Browser worker did not start.")

    def submit(self, instruction):
        if not self.running:
            raise RuntimeError("Browser worker is offline.")
        task_id = str(uuid4())
        now = timestamp()
        task = {
            "task_id": task_id,
            "instruction": instruction,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "result": None,
            "error": None,
        }
        with self.lock:
            self.tasks[task_id] = task
            self.submitted_at[task_id] = time.perf_counter()
        try:
            self.task_queue.put_nowait(task_id)
        except queue.Full:
            with self.lock:
                del self.tasks[task_id]
                self.submitted_at.pop(task_id, None)
            raise RuntimeError("Task queue is full.")
        return dict(task)

    def get_task(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            return dict(task) if task else None

    def update_task(self, task_id, **changes):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(changes)
                self.tasks[task_id]["updated_at"] = timestamp()

    def stop(self):
        self.running = False
        if not self.thread or not self.thread.is_alive():
            return
        try:
            self.task_queue.put(None, timeout=2)
        except queue.Full:
            print("[WORKER] Queue full during shutdown; running task must finish.")
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=10)

    def _browser_alive(self):
        if self.context is None or self.safe_browser is None:
            return False
        try:
            pages = [p for p in self.context.pages if not p.is_closed()]
            if not pages:
                return False
            if not self.context.browser or not self.context.browser.is_connected():
                return False
            pages[0].evaluate('1')  # Detect a crashed renderer, not only a disconnected browser.
            return True
        except Exception:
            return False

    def _close_browser(self):
        context = self.context
        self.context = None
        self.safe_browser = None
        if context is not None:
            self.browser_state = 'closed'
            try:
                context.close()
            except Exception:
                pass

    def _ensure_browser(self, playwright, UniversalBrowser, START_URL):
        if self._browser_alive():
            # The previously active tab can have been closed while
            # another approved tab remains open. Re-select one.
            base = self.safe_browser.base
            try:
                base.page()
            except Exception:
                valid = [
                    p for p in self.context.pages
                    if not p.is_closed() and (base.domain_allowed(p.url) or p.url == 'about:blank')
                ]
                if valid:
                    base.active_page = valid[-1]
                    base.reset_elements()
                else:
                    self._close_browser()
            if self.context is not None and self.safe_browser is not None:
                return self.safe_browser

        self._close_browser()
        self.browser_state = 'launching'
        print("[WORKER] Launching Google Chrome...")
        PROFILE.mkdir(parents=True, exist_ok=True)
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE),
                channel="chrome",
                headless=False,
                viewport={"width": 1440, "height": 900},
                accept_downloads=False,
            )
        except Exception:
            self.browser_state = "unavailable"
            raise
        self.context = context
        def closed(*_):
            if self.context is context and not any(not p.is_closed() for p in context.pages):
                self.browser_state = 'closed'
        context.on('page', lambda page: page.on('close', closed))
        for page in context.pages:
            page.on('close', closed)
        context.on('close', lambda *_: setattr(self, 'browser_state', 'closed') if self.context is context else None)
        try:
            base = UniversalBrowser(context)
            valid = [
                p for p in context.pages
                if not p.is_closed() and base.domain_allowed(p.url)
            ]
            if valid:
                base.active_page = valid[-1]
                base.active_page.bring_to_front()
            else:
                page = next((p for p in context.pages if not p.is_closed() and p.url == 'about:blank'), None)
                if page is None:
                    page = context.new_page()
                base.active_page = page

            # Reuse Chrome's initial empty tab for the requested destination.
            for page in list(context.pages):
                if page is not base.active_page and not page.is_closed() and page.url == 'about:blank':
                    page.close()

            self.safe_browser = APISafeBrowser(base)
            base.approve_domain = self.safe_browser.approve_domain
            self.browser_state = 'ready'
            print("[WORKER] Chrome ready.")
            return self.safe_browser
        except Exception:
            self._close_browser()
            self.browser_state = "unavailable"
            raise

    def _execute_task(self, task_id, playwright, UniversalBrowser, run_agent, START_URL):
        task = self.get_task(task_id)
        if task is None:
            return
        self.update_task(task_id, status="running")
        started = time.perf_counter()
        with self.lock:
            submitted = self.submitted_at.pop(task_id, started)
        timings = [{'stage': 'worker.queue', 'elapsed_ms': round((started - submitted) * 1000, 3)}]
        try:
            with measure('browser.ensure', timings):
                browser = self._ensure_browser(playwright, UniversalBrowser, START_URL)
            with measure('agent.run', timings):
                result = run_agent(browser, task["instruction"])
            if not isinstance(result, dict):
                raise RuntimeError("Agent returned an invalid result.")
            result['workflow_timings'] = timings
            result['total_elapsed_ms'] = round((time.perf_counter() - submitted) * 1000, 3)
            logger.info('[PERF] task.total %.3f ms', result['total_elapsed_ms'])
            outcome = result.get("outcome")
            status = (
                "finished" if outcome == "finished" else
                "incomplete" if outcome == "incomplete" else
                "paused" if outcome == "paused" else "failed"
            )
            self.update_task(task_id, status=status, result=result)
            if not self._browser_alive():
                self._close_browser()
        except Exception as exc:
            self.update_task(task_id, status="failed", error=str(exc))
            print("[WORKER ERROR]", exc)
            self._close_browser()
            # Never automatically replay a potentially partial operation.

    def _run(self):
        try:
            from backend.universal_agent import UniversalBrowser, run_agent, START_URL
            with sync_playwright() as playwright:
                self.running = True
                self.ready.set()
                print("[WORKER] Ready. Chrome will open with the first task.")
                try:
                    while True:
                        if self.context is None:
                            task_id = self.task_queue.get()
                        else:
                            try:
                                task_id = self.task_queue.get_nowait()
                            except queue.Empty:
                                pump_context(self.context, 25)
                                continue
                        try:
                            if task_id is None:
                                break
                            self._execute_task(
                                task_id, playwright, UniversalBrowser, run_agent, START_URL
                            )
                        finally:
                            self.task_queue.task_done()
                finally:
                    self._close_browser()
        except Exception as exc:
            self.startup_error = str(exc)
            print("[WORKER STARTUP ERROR]", exc)
        finally:
            self.running = False
            self.ready.set()
            print("[WORKER] Stopped.")
