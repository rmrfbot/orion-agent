import unittest
from unittest.mock import Mock, patch

from backend.fast_commands import search_command
from backend.request_policy import RequestPolicy, verification
from backend.universal_agent import UniversalBrowser, run_agent
from backend.browser_worker import BrowserWorker


class RequestPolicyTests(unittest.TestCase):
    @patch('backend.universal_agent.generate')
    def test_challenge_arriving_during_inference_overrides_model_success(self, generate):
        browser = Mock()
        browser.page.return_value.url = 'https://www.youtube.com'
        browser.observe_page.return_value = {'observation': 'fixture'}
        browser.list_tabs.return_value = {'tabs': []}
        browser.verification_state.side_effect = [None, {
            'human_intervention_required': True,
            'error': 'Human verification required. Complete it manually.',
            'verification': {'site': 'youtube.com', 'evidence': 'fixture'},
        }]
        generate.return_value = Mock(text='Everything completed!', function_calls=[])
        result = run_agent(browser, 'Inspect this page and explain its state')
        self.assertEqual(result['outcome'], 'paused')
        self.assertTrue(result['human_intervention_required'])
        browser.execute.assert_not_called()

    @patch('backend.universal_agent.generate')
    def test_planner_cannot_repeat_network_action(self, generate):
        from google.genai import types
        browser = Mock()
        browser.page.return_value.url = 'https://www.youtube.com'
        browser.observe_page.return_value = {'observation': 'fixture'}
        browser.list_tabs.return_value = {'tabs': []}
        browser.execute.return_value = {'results': []}
        content = types.Content(role='model', parts=[types.Part.from_function_call(
            name='youtube_search', args={'query': 'jazz'})])
        response = Mock(candidates=[Mock(content=content)], function_calls=[content.parts[0].function_call])
        generate.side_effect = [response, response]
        result = run_agent(browser, 'Inspect this page and compare the available playlists')
        self.assertEqual(result['outcome'], 'incomplete')
        self.assertIn('loop', result['message'])
        browser.execute.assert_called_once()

    def test_repeated_network_attempts_are_rejected_without_sleeping(self):
        policy = RequestPolicy()
        with patch('backend.request_policy.time.monotonic', return_value=100):
            self.assertIsNone(policy.begin('https://www.google.com/search?q=a'))
            self.assertIn('error', policy.begin('https://www.google.com/search?q=a'))
            self.assertIsNone(policy.begin('https://www.google.com/search?q=b'))
        with patch('backend.request_policy.time.monotonic', return_value=103):
            self.assertIsNone(policy.begin('https://www.google.com/search?q=a'))

    def test_worker_keeps_human_verification_paused(self):
        worker = BrowserWorker()
        worker.running = True
        task = worker.submit('find jazz')
        worker._ensure_browser = Mock(return_value=Mock())
        worker._browser_alive = Mock(return_value=True)
        worker._execute_task(task['task_id'], Mock(), Mock(),
                             lambda *_: {'outcome': 'paused', 'human_intervention_required': True}, '')
        self.assertEqual(worker.get_task(task['task_id'])['status'], 'paused')


class VerificationBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.chrome = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.chrome.new_context()
        self.page = self.context.new_page()
        self.browser = UniversalBrowser(self.context)
        self.browser.active_page = self.page
        self.requests = []
        self.html = '<html><body><div id="search">Search results</div></body></html>'
        def route(request):
            self.requests.append(request.request.url)
            request.fulfill(content_type='text/html', body=self.html)
        self.context.route('**/*', route)

    def tearDown(self):
        self.context.close()

    def test_google_url_and_visible_captcha_evidence(self):
        self.page.goto('https://www.google.com/sorry/index')
        self.assertTrue(verification(self.page)['human_intervention_required'])
        self.page.goto('https://www.google.com/search?q=jazz')
        self.page.set_content('<form id="captcha-form"><input name="captcha"></form>')
        self.assertIn('CAPTCHA', verification(self.page)['verification']['evidence'])

    def test_unusual_traffic_and_youtube_signin_wall(self):
        self.page.goto('https://www.google.com/search?q=jazz')
        self.page.set_content('<p>Our systems have detected unusual traffic from your computer network.</p>')
        self.assertIsNotNone(verification(self.page))
        self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')
        self.page.set_content('<div class="yt-playability-error-supported-renderers">Sign in to confirm you’re not a bot</div>')
        self.assertIsNotNone(verification(self.page))

    def test_ordinary_search_mentions_and_hidden_controls_are_not_challenges(self):
        self.page.goto('https://www.youtube.com/results?search_query=captcha')
        self.page.set_content('<a>How to verify you are human: CAPTCHA tutorials</a><form id="captcha-form" style="display:none"></form>')
        self.assertIsNone(verification(self.page))
        self.page.goto('https://www.google.com/search?q=unusual+traffic')
        self.page.set_content('<div id="search">Tutorial: our systems have detected unusual traffic</div>')
        self.assertIsNone(verification(self.page))
        self.page.goto('https://www.wikipedia.org')
        self.page.set_content('<form id="captcha-form"></form>')
        self.assertIsNone(verification(self.page))

    @patch('backend.universal_agent.generate')
    def test_verification_pauses_without_navigation_or_model_and_manual_recovery(self, generate):
        self.page.goto('https://www.google.com/sorry/index')
        self.requests.clear()
        result = run_agent(self.browser, 'find jazz on Google')
        self.assertEqual(result['outcome'], 'paused')
        self.assertTrue(result['human_intervention_required'])
        self.assertEqual(self.requests, [])
        # Repeating the command while blocked must not refresh or solve the challenge.
        self.assertEqual(run_agent(self.browser, 'find jazz on Google')['outcome'], 'paused')
        self.assertEqual(self.requests, [])
        generate.assert_not_called()
        # Simulate a human completing verification and returning to the results.
        self.page.goto('https://www.google.com/search?q=jazz')
        self.requests.clear()
        recovered = run_agent(self.browser, 'find jazz on Google')
        self.assertEqual(recovered['outcome'], 'finished')
        self.assertEqual(self.requests, [])

    def test_identical_searches_reuse_live_results_and_existing_tabs(self):
        self.page.goto('https://www.google.com')
        command = search_command('find jazz on Google', self.page.url)
        self.requests.clear()
        first = self.browser.quick_search(command)
        second = self.browser.quick_search(command)
        self.assertTrue(first['ready'])
        self.assertTrue(second['reused'])
        self.assertEqual(len(self.requests), 1)
        other = self.context.new_page()
        other.goto('https://www.wikipedia.org')
        self.browser.active_page = other
        self.requests.clear()
        self.assertTrue(self.browser.quick_search(command)['reused'])
        self.assertIs(self.browser.active_page, self.page)
        self.assertEqual(self.requests, [])

    def test_cached_page_becoming_a_challenge_is_not_replayed(self):
        self.page.goto('https://www.google.com')
        command = search_command('find jazz on Google', self.page.url)
        self.browser.quick_search(command)
        self.page.set_content('<form id="captcha-form"><input name="captcha"></form>')
        self.requests.clear()
        self.assertTrue(self.browser.quick_search(command)['human_intervention_required'])
        self.assertEqual(self.requests, [])
        self.page.set_content('<div id="search">Search results after manual verification</div>')
        self.assertTrue(self.browser.quick_search(command)['ready'])
        self.assertEqual(self.requests, [])

    def test_closed_or_navigated_result_tabs_invalidate_cache(self):
        self.page.goto('https://www.google.com')
        command = search_command('find jazz on Google', self.page.url)
        self.browser.quick_search(command)
        self.page.goto('https://www.wikipedia.org')
        self.assertIsNone(self.browser.request_policy.cached(command['url'], self.context.pages))

    def test_same_url_reload_invalidates_cache(self):
        self.page.goto('https://www.google.com')
        command = search_command('find jazz on Google', self.page.url)
        self.browser.quick_search(command)
        self.page.reload()
        self.assertIsNone(self.browser.request_policy.cached(command['url'], self.context.pages))

    def test_youtube_duplicate_search_reuses_verified_video_list(self):
        self.html = '<a id="video-title" href="/watch?v=abcdefghijk" title="Jazz">Jazz</a>'
        self.page.goto('https://www.youtube.com')
        self.requests.clear()
        first = self.browser.youtube_search('jazz')
        second = self.browser.youtube_search('jazz')
        self.assertEqual(first['results'], second['results'])
        self.assertTrue(second['reused'])
        self.assertEqual(len(self.requests), 1)

    def test_local_controls_are_not_throttled_by_recent_search(self):
        self.page.goto('https://www.google.com')
        self.browser.quick_search(search_command('find jazz on Google', self.page.url))
        with patch.object(self.browser.request_policy, 'begin', side_effect=AssertionError('local action must not throttle')):
            self.assertNotIn('error', self.browser.execute('scroll_page', {'direction': 'down'}))
            self.assertNotIn('error', self.browser.execute('list_tabs', {}))

    def test_repeated_enter_does_not_resubmit_identical_search_form(self):
        self.html = '<form action="https://www.google.com/search"><input type="search" name="q" value="jazz"><button>Search</button></form>'
        self.page.goto('https://www.google.com')
        self.browser.observe_page()
        self.requests.clear()
        self.assertNotIn('error', self.browser.execute('press_enter', {'index': 0}))
        self.assertEqual(len(self.requests), 1)
        self.assertIn('suppressed', self.browser.execute('press_enter', {'index': 0})['error'])
        self.assertEqual(len(self.requests), 1)

    def test_repeated_link_click_does_not_navigate_again(self):
        self.html = '<a href="https://www.google.com/search?q=jazz">Jazz results</a>'
        self.page.goto('https://www.google.com')
        self.browser.observe_page()
        self.requests.clear()
        self.assertNotIn('error', self.browser.execute('click_element', {'index': 0}))
        self.assertEqual(len(self.requests), 1)
        self.assertIn('suppressed', self.browser.execute('click_element', {'index': 0})['error'])
        self.assertEqual(len(self.requests), 1)

    def test_challenge_never_receives_automated_click_or_enter(self):
        self.page.goto('https://www.google.com/search?q=jazz')
        self.page.set_content('<form id="captcha-form" onsubmit="window.submitted=true"><input name="captcha"></form>')
        self.assertTrue(self.browser.execute('press_enter', {})['human_intervention_required'])
        self.assertTrue(self.browser.execute('click_element', {'index': 0})['human_intervention_required'])
        self.assertFalse(self.page.evaluate('Boolean(window.submitted)'))
        self.assertTrue(self.browser.execute('close_tab', {'index': 0})['human_intervention_required'])
        self.assertFalse(self.page.is_closed())
