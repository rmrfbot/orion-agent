"""Repeatable before/after benchmark. All network responses are local fixtures.

Run from root: .venv/Scripts/python.exe tests/benchmark_latency.py --runs 30
"""
import argparse
import json
import logging
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from backend.browser_worker import BrowserWorker
from backend.universal_agent import UniversalBrowser
from fixtures.latency_baseline import BaselineBrowser, BaselineWorker
from fixtures.player import fulfill_player


def distribution(values):
    values = sorted(values)
    return {'n': len(values), 'p50_ms': round(statistics.median(values), 3),
            'p95_ms': round(values[math.ceil(len(values) * .95) - 1], 3),
            'max_ms': round(max(values), 3)}


def fixture_browser(base):
    class FixtureBrowser(base):
        def __init__(self, context):
            super().__init__(context)
            context.route('**/*', fulfill_player)
    return FixtureBrowser


def benchmark(playwright, chrome, base, runs):
    context = chrome.new_context()
    browser = fixture_browser(base)(context)
    page = context.new_page()
    browser.active_page = page
    page.goto('https://www.youtube.com/watch?v=abcdefghijk')
    results = {}
    try:
        # Rapid successive controls stress the original global cooldown.
        skips = [page.evaluate('opts => window.runSkipTrial(opts)',
                 {'mode': 'enable' if i % 2 else 'insert', 'delay': 10 + i % 5})
                 for i in range(runs)]
        assert not any(sample['early'] for sample in skips)
        results['skip_eligible_to_click'] = distribution([s['eligible_to_click_ms'] for s in skips])
        results['fixture_click_to_control_removed'] = distribution([s['confirmation_ms'] for s in skips])
        results['fixture_eligibility_wait'] = distribution([s['eligibility_wait_ms'] for s in skips])
        if base is UniversalBrowser:
            page.wait_for_function('() => window.__orionSkipWatcher.snapshot().samples.every(s => s.confirmation)')
            monitor = page.evaluate('() => window.__orionSkipWatcher.snapshot()')
            samples = monitor['samples']
            results['skip_detection'] = distribution([
                s['eligible_observed_at_ms'] - fixture['ready_at_ms'] for s, fixture in zip(samples, skips)])
            results['skip_detection_to_dispatch'] = distribution([s['dispatch_ms'] for s in samples])
            results['skip_dispatch_to_confirm'] = distribution([s['confirmation_ms'] for s in samples])
            results['monitor_counters'] = monitor['counters']
        css = []
        for _ in range(runs):
            page.goto('https://www.youtube.com/watch?v=abcdefghijk')
            sample = page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'stylesheet'})
            assert not sample['early']
            css.append(sample['eligible_to_click_ms'])
        results['skip_css_fallback'] = distribution(css)
        for name, operation in [
            ('youtube_search', lambda: browser.youtube_search('fixture video')),
            ('video_open_and_play', lambda: browser.youtube_open_video(0)),
            ('playback_verify', browser.youtube_play),
            ('page_observation', browser.observe_page),
        ]:
            measurements = []
            stages = {}
            for _ in range(runs):
                started = time.perf_counter()
                result = operation()
                measurements.append((time.perf_counter() - started) * 1000)
                assert 'error' not in result, result
                for timing in result.get('timings', []):
                    stages.setdefault(timing['stage'], []).append(timing['elapsed_ms'])
                if name in ('video_open_and_play', 'playback_verify') and base is UniversalBrowser:
                    playback = result.get('playback', result)
                    assert playback['progress_verified'], playback
            results[name] = distribution(measurements)
            if stages:
                results[name + '_stages'] = {stage: distribution(values) for stage, values in stages.items()}
    finally:
        context.close()
    return results


def recovery_benchmark(playwright, worker_class=BrowserWorker, runs=3):
    timings = []
    warm = []
    launcher = Mock()
    def launch(**kwargs):
        kwargs['headless'] = True
        return playwright.chromium.launch_persistent_context(**kwargs)
    launcher.chromium.launch_persistent_context.side_effect = launch
    worker = worker_class()
    try:
        with tempfile.TemporaryDirectory(dir='tests') as profile:
            with patch('backend.browser_worker.PROFILE', Path(profile)), patch('fixtures.latency_baseline.PROFILE', Path(profile)):
                for _ in range(runs):
                    started = time.perf_counter()
                    worker._ensure_browser(launcher, fixture_browser(UniversalBrowser), 'https://www.youtube.com')
                    timings.append((time.perf_counter() - started) * 1000)
                    started = time.perf_counter()
                    worker._ensure_browser(launcher, fixture_browser(UniversalBrowser), 'https://www.youtube.com')
                    warm.append((time.perf_counter() - started) * 1000)
                    worker.context.close()  # Force recovery on the next iteration.
                worker._close_browser()
    finally:
        worker._close_browser()
    return {'cold_or_recovery': distribution(timings), 'warm_reuse': distribution(warm)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=30)
    parser.add_argument('--output', default='docs/latency-benchmark.json')
    args = parser.parse_args()
    if not 2 <= args.runs <= 100:
        parser.error('--runs must be between 2 and 100')
    logging.getLogger('orion.performance').setLevel(logging.WARNING)
    with sync_playwright() as playwright:
        chrome = playwright.chromium.launch(channel='chrome', headless=True)
        report = {'environment': {'chrome': chrome.version, 'mode': 'headless',
                  'network': 'local route.fulfill fixtures, no live YouTube or Gemini',
                  'clock': 'performance.now in-page; perf_counter in Python',
                  'runs': args.runs, 'skip_scenario': 'rapid successive inserted/enabled controls'},
                  'before': benchmark(playwright, chrome, BaselineBrowser, args.runs),
                  'after': benchmark(playwright, chrome, UniversalBrowser, args.runs),
                  'recovery_before': recovery_benchmark(playwright, BaselineWorker),
                  'recovery_after': recovery_benchmark(playwright)}
        chrome.close()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
