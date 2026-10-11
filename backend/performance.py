"""Monotonic stage timings; no prompts, page contents, or credentials in logs."""
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger('orion.performance')
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


@contextmanager
def measure(stage, timings=None):
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        logger.info('[PERF] %s %.3f ms', stage, elapsed)
        if timings is not None:
            timings.append({'stage': stage, 'elapsed_ms': elapsed})
