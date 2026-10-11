"""Keep routed Chrome requests moving; only the owner thread touches Playwright."""
import time
import weakref
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

_remote_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='orion-model-http')
_last_monitor_tick = weakref.WeakKeyDictionary()


def pump_context(context, milliseconds=25):
    try:
        pages = context.pages if context is not None else []
        for page in pages:
            if not page.is_closed():
                # This services the sync driver's callbacks, including navigation guards.
                # It is not a readiness delay attached to an individual browser action.
                page.wait_for_timeout(milliseconds)
                now = time.monotonic()
                if now - _last_monitor_tick.get(context, 0) >= .05:
                    _last_monitor_tick[context] = now
                    for watched in pages:
                        host = (urlparse(watched.url).hostname or '').lower()
                        if not watched.is_closed() and (host == 'youtube.com' or host.endswith('.youtube.com')):
                            watched.evaluate('() => window.__orionSkipWatcher?.tick?.()')
                return
    except Exception:
        pass
    time.sleep(milliseconds / 1000)


def call_with_browser_events(call, context):
    # Only network inference/retry work runs here. No browser object enters this thread.
    future = _remote_executor.submit(call)
    while not future.done():
        pump_context(context)
    return future.result()
