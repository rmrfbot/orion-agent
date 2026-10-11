import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

from backend.browser_worker import BrowserWorker
from backend.universal_agent import UniversalBrowser, YOUTUBE_SKIP_SCRIPT
from fixtures.player import fulfill_player


class FixtureBrowser(UniversalBrowser):
    def __init__(self, context):
        super().__init__(context)
        context.route('**/*', fulfill_player)


class MonitorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.chrome = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.chrome.new_context()
        self.browser = FixtureBrowser(self.context)
        self.page = self.context.new_page()
        self.browser.active_page = self.page
        self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')

    def tearDown(self):
        self.context.close()

    def test_new_controls_have_no_global_cooldown(self):
        for mode in ('insert', 'enable', 'aria'):
            result = self.page.evaluate('opts => window.runSkipTrial(opts)', {'mode': mode})
            self.assertFalse(result['early'])
            self.assertLess(result['eligible_to_click_ms'], 250)
        snapshot = self.page.evaluate('() => window.__orionSkipWatcher.snapshot()')
        self.assertEqual(snapshot['counters']['clicks'], 3)
        self.assertTrue(all(item['confirmed'] for item in snapshot['samples']))
        self.assertTrue(all(item['dispatch_ms'] >= 0 for item in snapshot['samples']))

    def test_css_visibility_fallback(self):
        result = self.page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'stylesheet'})
        self.assertFalse(result['early'])
        self.assertLess(result['eligible_to_click_ms'], 250)

    def test_disabled_hidden_and_first_hidden_match(self):
        self.page.evaluate('''() => {
          for (const attributes of [{disabled: true}, {hidden: true},
            {aria: true}, {inert: true}, {opacity: true}, {pointer: true}]) {
            const button = document.createElement('button');
            button.className = 'ytp-ad-skip-button';
            button.disabled = !!attributes.disabled;
            button.hidden = !!attributes.hidden;
            if (attributes.aria) button.setAttribute('aria-disabled', 'true');
            if (attributes.inert) button.inert = true;
            if (attributes.opacity) button.style.opacity = '0';
            if (attributes.pointer) button.style.pointerEvents = 'none';
            button.onclick = () => window.badClick = true;
            document.body.append(button);
          }
        }''')
        self.page.wait_for_timeout(150)
        self.assertFalse(self.page.evaluate('() => !!window.badClick'))
        result = self.page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'insert'})
        self.assertFalse(result['early'])
        self.assertLess(result['eligible_to_click_ms'], 250)

    def test_no_duplicates_across_spa_and_full_navigation(self):
        for _ in range(3):
            self.page.evaluate(YOUTUBE_SKIP_SCRIPT)
            self.page.evaluate("() => { history.pushState({}, '', '/watch?v=zyxwvutsrqp'); document.dispatchEvent(new Event('yt-navigate-finish')); }")
            self.page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'insert'})
        self.assertEqual(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().counters.clicks'), 3)
        self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')
        self.page.evaluate('opts => window.runSkipTrial(opts)', {'mode': 'insert'})
        self.assertEqual(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().counters.clicks'), 1)

    def test_stop_and_pagehide_cleanup(self):
        self.browser.stop_monitors()
        self.page.evaluate("() => { const b=document.createElement('button'); b.className='ytp-ad-skip-button'; b.onclick=()=>window.badClick=true; document.body.append(b); }")
        self.page.wait_for_timeout(150)
        self.assertFalse(self.page.evaluate('() => !!window.badClick'))
        self.assertFalse(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().enabled'))
        self.page.evaluate(YOUTUBE_SKIP_SCRIPT)
        self.page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pagehide'))")
        self.assertFalse(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().enabled'))
        self.page.evaluate("() => window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}))")
        self.assertTrue(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().enabled'))

    def test_confirm_timeout_does_not_spam(self):
        self.page.evaluate("() => { const b=document.createElement('button'); b.className='ytp-ad-skip-button'; document.body.append(b); }")
        self.page.wait_for_timeout(300)
        self.assertEqual(self.page.evaluate('() => window.__orionSkipWatcher.snapshot().counters.clicks'), 1)
        self.page.wait_for_timeout(900)
        sample = self.page.evaluate('() => window.__orionSkipWatcher.snapshot().samples[0]')
        self.assertFalse(sample['confirmed'])
        self.assertEqual(sample['confirmation'], 'not_confirmed')

    def test_progress_verified_with_real_media(self):
        self.page.locator('video').evaluate('v => v.play()')
        result = self.browser.youtube_play()
        self.assertTrue(result['progress_verified'])
        self.assertTrue(result['playing'])
        self.assertNotIn('error', result)
        self.assertGreater(result['advanced_seconds'], 0.02)
        self.assertGreaterEqual(result['observation_ms'], 300)

    def test_same_control_is_reused_for_a_later_ad(self):
        self.page.evaluate('''() => {
          const player = document.querySelector('#movie_player');
          const button = document.createElement('button');
          button.className = 'ytp-ad-skip-button';
          window.reusedSkipClicks = 0;
          button.onclick = () => { window.reusedSkipClicks++; player.classList.remove('ad-showing'); };
          player.classList.add('ad-showing');
          document.querySelector('#controls').append(button);
        }''')
        self.page.wait_for_function('window.reusedSkipClicks === 1')
        self.page.evaluate("() => document.querySelector('#movie_player').classList.add('ad-showing')")
        self.page.wait_for_function('window.reusedSkipClicks === 2', timeout=1500)
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.evaluate('window.reusedSkipClicks'), 2)
        samples = self.page.evaluate('window.__orionSkipWatcher.snapshot().samples')
        self.assertTrue(all(sample['confirmed'] for sample in samples))

    def set_media(self, **values):
        self.page.locator('video').evaluate('''(v, values) => {
          v.pause();
          for (const [key, value] of Object.entries(values)) {
            Object.defineProperty(v, key, {get: () => value, configurable:true});
          }
        }''', values)

    def test_playback_states(self):
        for values, state in [({'readyState': 0, 'paused': False}, 'loading'),
                              ({'readyState': 4, 'paused': True}, 'paused'),
                              ({'readyState': 4, 'paused': False, 'currentTime': 10}, 'buffering'),
                              ({'error': {'code': 3, 'message': 'fixture decode error'}}, 'error')]:
            self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')
            self.set_media(**values)
            result = self.browser.media_state()
            self.assertEqual(result['state'], state)
            self.assertFalse(result['playing'])
        self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')
        self.page.evaluate("() => document.querySelector('#movie_player').classList.add('ad-showing')")
        self.page.locator('video').evaluate('v => v.play()')
        result = self.browser.media_state()
        self.assertEqual(result['state'], 'advertisement')
        self.assertTrue(result['ad_playing'])
        self.page.locator('video').evaluate('v => v.remove()')
        self.assertEqual(self.browser.media_state()['state'], 'opened')

    def test_video_opening_verifies_playback(self):
        self.browser.youtube_results = [{'title': 'Fixture video', 'url': self.page.url}]
        result = self.browser.youtube_open_video(0)
        self.assertTrue(result['opened'])
        self.assertTrue(result['playback']['progress_verified'])
        self.assertIn('error', self.browser.youtube_open_video(1))

    def test_domain_guards(self):
        self.browser.youtube_results = [{'title': 'bad', 'url': 'https://unapproved.example/watch?v=abcdefghijk'}]
        self.assertIn('error', self.browser.youtube_open_video(0))
        route = Mock()
        route.request.is_navigation_request.return_value = True
        route.request.url = 'http://localhost/private'
        self.browser.guard_navigation(route)
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    def test_scroll_does_not_depend_on_animation_frames(self):
        self.page.evaluate("() => { document.body.style.minHeight = '5000px'; window.requestAnimationFrame = () => 0; }")
        self.assertNotIn('error', self.browser.scroll_page('down'))
        self.assertGreater(self.page.evaluate('() => window.scrollY'), 0)

    def test_browser_recovery_stays_on_owner_thread(self):
        worker = BrowserWorker()
        owner = threading.get_ident()
        launcher = Mock()
        calls = []

        def launch(**kwargs):
            calls.append(threading.get_ident())
            kwargs['headless'] = True
            return self.playwright.chromium.launch_persistent_context(**kwargs)

        launcher.chromium.launch_persistent_context.side_effect = launch
        with tempfile.TemporaryDirectory(dir='tests') as profile:
            with patch('backend.browser_worker.PROFILE', Path(profile)):
                browser = worker._ensure_browser(launcher, FixtureBrowser, 'https://www.youtube.com')
                first = worker.context
                self.assertEqual([page.url for page in first.pages], ['about:blank'])
                self.assertFalse(browser.base.domain_allowed('about:blank'))
                initial = browser.page()
                self.assertNotIn('error', browser.open_tab('https://www.youtube.com/watch?v=abcdefghijk'))
                self.assertIs(browser.page(), initial)
                self.assertEqual(len(first.pages), 1)
                self.assertNotIn('error', browser.open_tab('https://www.youtube.com/watch?v=lmnopqrstuv'))
                self.assertEqual(len(first.pages), 2)
                self.assertIs(worker._ensure_browser(launcher, FixtureBrowser, 'https://www.youtube.com'), browser)
                extra = worker.context.new_page()
                extra.goto('https://www.youtube.com/watch?v=abcdefghijk')
                browser.base.active_page.close()
                self.assertIs(worker._ensure_browser(launcher, FixtureBrowser, 'https://www.youtube.com').page(), extra)
                first.close()
                worker._ensure_browser(launcher, FixtureBrowser, 'https://www.youtube.com')
                self.assertIsNot(worker.context, first)
                worker._close_browser()
        self.assertEqual(calls, [owner, owner])


if __name__ == '__main__':
    unittest.main()
