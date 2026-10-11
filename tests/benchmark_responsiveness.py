"""Local routed-network and CSS-skip benchmarks; no live Gemini or YouTube calls."""
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from backend.browser_io import call_with_browser_events
from backend.universal_agent import YOUTUBE_SKIP_SCRIPT
from fixtures.player import fulfill_player


def summary(values):
    ordered = sorted(values)
    return {'n': len(values), 'p50_ms': round(statistics.median(values), 3),
            'p95_ms': round(ordered[math.ceil(.95 * len(values)) - 1], 3),
            'max_ms': round(max(values), 3)}


with sync_playwright() as playwright:
    chrome = playwright.chromium.launch(channel='chrome', headless=True)
    context = chrome.new_context()
    context.route('**/*', fulfill_player)
    page = context.new_page()
    page.goto('https://www.youtube.com/')
    report = {'environment': {'chrome': chrome.version, 'network': 'local mocked routes',
              'model': 'simulated 250ms HTTP wait; no live inference'}}
    for mode in ('blocking_before', 'pumped_after'):
        durations = []
        for _ in range(20):
            page.evaluate('''() => {
                window.done = null;
                window.started = performance.now();
                fetch('/fixture').then(r => r.text()).then(() => window.done = performance.now());
            }''')
            if mode == 'blocking_before':
                time.sleep(.25)
            else:
                call_with_browser_events(lambda: time.sleep(.25), context)
            page.wait_for_function('() => window.done !== null')
            durations.append(page.evaluate('() => window.done - window.started'))
        report[mode] = summary(durations)
    page.evaluate(YOUTUBE_SKIP_SCRIPT)
    skips = [page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'stylesheet'})
             for _ in range(30)]
    assert not any(s['early'] for s in skips)
    report['css_skip_after'] = summary([s['eligible_to_click_ms'] for s in skips])
    context.close()
    chrome.close()
output = Path('docs/responsiveness-benchmark.json')
output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
