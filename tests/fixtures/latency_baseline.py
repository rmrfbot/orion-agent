# Frozen pre-optimization implementation for local before/after benchmarks only.
from urllib.parse import quote_plus, urlparse, urljoin, parse_qs
import time
from backend.universal_agent import UniversalBrowser, get_host, host_matches, INITIAL_DOMAINS

YOUTUBE_SKIP_SCRIPT = "\n(() => {\n  if (!/(^|\\.)youtube\\.com$/.test(location.hostname)) return;\n  if (window.__orionSkipWatcher) return;\n  window.__orionSkipWatcher = true;\n\n  const selectors = [\n    '.ytp-ad-skip-button',\n    '.ytp-ad-skip-button-modern',\n    '.ytp-skip-ad-button',\n    'button.ytp-ad-skip-button',\n    '.ytp-ad-skip-button-container button'\n  ];\n  let lastClick = 0;\n  const trySkip = () => {\n    if (Date.now() - lastClick < 500) return;\n    for (const selector of selectors) {\n      const button = document.querySelector(selector);\n      if (!button || button.disabled) continue;\n      const style = getComputedStyle(button);\n      const visible = button.getClientRects().length > 0 &&\n        style.visibility !== 'hidden' && style.display !== 'none';\n      if (visible) {\n        lastClick = Date.now();\n        button.click();\n        break;\n      }\n    }\n  };\n  const start = () => {\n    trySkip();\n    new MutationObserver(trySkip).observe(document.documentElement, {\n      childList: true, subtree: true, attributes: true,\n      attributeFilter: ['class', 'style', 'disabled']\n    });\n    setInterval(trySkip, 250);\n  };\n  if (document.readyState === 'loading') {\n    document.addEventListener('DOMContentLoaded', start, {once:true});\n  } else { start(); }\n})();\n"

class BaselineBrowser(UniversalBrowser):
    def __init__(self, context):
    
            self.context = context
    
            self.active_page = None
    
            self.elements = []
    
            self.observed_page = None
    
            self.approved_domains = set(INITIAL_DOMAINS)
    
    
    
            context.route("**/*", self.guard_navigation)
            context.add_init_script(script=YOUTUBE_SKIP_SCRIPT)
            self.youtube_results = []
            for existing_page in context.pages:
                try:
                    existing_page.evaluate(YOUTUBE_SKIP_SCRIPT)
                except Exception:
                    pass

    def observe_page(self):
            page = self.page()
            self.reset_elements()
            # A single browser round trip replaces hundreds of locator calls.
            snapshot = page.evaluate("""selector => {
                const elements = Array.from(document.querySelectorAll(selector))
                  .slice(0, 350).map((el, position) => {
                    const style = getComputedStyle(el);
                    if (!el.getClientRects().length || style.visibility === 'hidden' ||
                        style.display === 'none') return null;
                    return {position, tag: el.tagName.toLowerCase(),
                      label: (el.innerText || el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') || el.getAttribute('title') ||
                        el.getAttribute('value') || '').trim().slice(0, 100),
                      href: el.getAttribute('href') || '', type: el.getAttribute('type') || '',
                      role: el.getAttribute('role') || '', name: el.getAttribute('name') || '',
                      editable: el.getAttribute('contenteditable') === 'true'};
                  }).filter(Boolean).slice(0, 70);
                return {elements, title: document.title,
                  body: (document.body?.innerText || '').slice(0, 3500)};
            }""", self.SELECTOR)
            candidates = page.locator(self.SELECTOR)
            lines = []
            for details in snapshot['elements']:
                position = details.pop('position')
                index = len(self.elements)
                self.elements.append({'locator': candidates.nth(position), **details})
                lines.append(f"{index}: [{details['tag']}] {details['label'] or '(unlabeled)'} "
                             f"name={details['name']} type={details['type']} href={details['href'][:120]}")
            self.observed_page = page
            return {'observation': f"URL: {page.url}\nTitle: {snapshot['title']}\n"
                    f"Visible text:\n{snapshot['body']}\nInteractive elements:\n" + '\n'.join(lines),
                    'media': self.media_state()}

    def youtube_search(self, query):
            if not isinstance(query, str) or not query.strip():
                return {'error': 'Provide a YouTube search query.'}
            url = 'https://www.youtube.com/results?search_query=' + quote_plus(query.strip()[:200])
            if not self.domain_allowed(url):
                return {'error': 'YouTube is not approved.'}
            self.youtube_results = []
            self.reset_elements()
            deadline = time.monotonic() + 4.5
            try:
                page = self.page()
                response = page.goto(url, wait_until='commit', timeout=4500)
                if response and response.status >= 400:
                    return {'error': f'YouTube returned HTTP {response.status}.'}
                page.locator('a#video-title[href*="/watch?"]').first.wait_for(
                    state='attached', timeout=max(1, int((deadline - time.monotonic()) * 1000)))
                raw = page.locator('a#video-title').evaluate_all("""links => links.slice(0, 40)
                    .map(a => ({url: a.href, title: (a.title || a.innerText || '').trim()}))""")
                seen = set()
                for item in raw:
                    parsed = urlparse(item['url'])
                    video_id = parse_qs(parsed.query).get('v', [''])[0]
                    if (parsed.hostname not in ('youtube.com', 'www.youtube.com') or
                        parsed.path != '/watch' or len(video_id) != 11 or video_id in seen):
                        continue
                    seen.add(video_id)
                    self.youtube_results.append({'index': len(self.youtube_results),
                        'title': item['title'][:160], 'url': item['url']})
                    if len(self.youtube_results) >= 12:
                        break
                if not self.youtube_results:
                    return {'error': 'No video results are available yet.'}
                return {'query': query, 'results': self.youtube_results, 'url': page.url}
            except Exception as exc:
                return {'error': f'YouTube search unavailable: {exc}'}

    def youtube_open_video(self, index):
            """Open one of the numbered results from youtube_search."""
            if not isinstance(index, int) or not 0 <= index < len(self.youtube_results):
                return {"error": "Invalid YouTube result index. Search again first."}
            selected = self.youtube_results[index]
            url = selected["url"]
            if not self.domain_allowed(url):
                return {"error": "YouTube video URL is not approved."}
            try:
                page = self.page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self.reset_elements()
                page.locator("video").first.wait_for(state="attached", timeout=12000)
                return {
                    "opened": True,
                    "selected_title": selected["title"],
                    "page_title": page.title(),
                    "url": page.url,
                    "playback": self.youtube_play(),
                    "ads": "Watching for YouTube's normal Skip Ad button when available."
                }
            except Exception as exc:
                return {"error": f"Could not open video: {exc}"}

    def youtube_play(self):
            """Attempt playback, but never claim success without player state."""
            try:
                page = self.page()
                if get_host(page.url) not in ("youtube.com", "www.youtube.com"):
                    return {"error": "Not on YouTube."}
                video = page.locator("video").first
                video.wait_for(state="attached", timeout=8000)
                result = video.evaluate('''async (v) => {
                    try { await v.play(); }
                    catch (e) { return {playing: !v.paused, reason: String(e)}; }
                    return {playing: !v.paused, paused: v.paused};
                }''')
                return result
            except Exception as exc:
                return {"playing": False, "reason": str(exc)}

    def media_state(self):
            page = self.page()
            if not host_matches(get_host(page.url), 'youtube.com'):
                return {'site': get_host(page.url)}
            return page.evaluate("""() => {
                const video = document.querySelector('video');
                const ad = !!document.querySelector('.html5-video-player.ad-showing');
                const skip = Array.from(document.querySelectorAll(
                  '.ytp-ad-skip-button,.ytp-ad-skip-button-modern,.ytp-skip-ad-button'))
                  .some(el => el.getClientRects().length && !el.disabled &&
                    getComputedStyle(el).visibility !== 'hidden');
                return {site: 'youtube', video_present: !!video,
                  playing: !!video && !video.paused && !video.ended,
                  ad_playing: ad, skip_available: skip,
                  auto_skip_enabled: !!window.__orionSkipWatcher};
            }""")

from backend.browser_worker import BrowserWorker, APISafeBrowser, PROFILE

class BaselineWorker(BrowserWorker):
    def _browser_alive(self):
            if self.context is None or self.safe_browser is None:
                return False
            try:
                pages = [p for p in self.context.pages if not p.is_closed()]
                if not pages:
                    return False
                pages[0].evaluate("1")
                return True
            except Exception:
                return False

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
                        if not p.is_closed() and base.domain_allowed(p.url)
                    ]
                    if valid:
                        base.active_page = valid[-1]
                        base.reset_elements()
                    else:
                        self._close_browser()
                if self._browser_alive():
                    return self.safe_browser
    
            self._close_browser()
            print("[WORKER] Launching Google Chrome...")
            PROFILE.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE),
                channel="chrome",
                headless=False,
                viewport={"width": 1440, "height": 900},
                accept_downloads=False,
            )
            self.context = context
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
                    page = context.new_page()
                    base.active_page = page
                    page.goto(START_URL, wait_until="domcontentloaded", timeout=20000)
    
                self.safe_browser = APISafeBrowser(base)
                base.approve_domain = self.safe_browser.approve_domain
                print("[WORKER] Chrome ready.")
                return self.safe_browser
            except Exception:
                self._close_browser()
                raise
