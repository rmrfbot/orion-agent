import threading
import time
import unittest
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

from backend.browser_io import call_with_browser_events, pump_context
from backend.fast_commands import direct_command
from backend.universal_agent import run_agent


class DirectCommandTests(unittest.TestCase):
    def test_explicit_commands_and_indices(self):
        self.assertEqual(direct_command('skip the ad'), ('youtube_skip_ad', {}))
        self.assertEqual(direct_command('pause the video'), ('youtube_pause', {}))
        self.assertEqual(direct_command('switch to tab 2'), ('switch_tab', {'index': 1}))
        self.assertEqual(direct_command('open result 3'), ('youtube_open_video', {'index': 2}))
        self.assertEqual(direct_command('open YouTube in a new tab'), ('open_tab', {'url': 'https://www.youtube.com/'}))
        for text in ['skip ad then buy this', 'open YouTube and send a message', 'switch tab 0', 'play best jazz video']:
            self.assertIsNone(direct_command(text))

    @patch('backend.universal_agent.generate')
    def test_skip_does_not_wait_for_inference(self, generate):
        browser = Mock()
        browser.execute.return_value = {'skipped': True, 'message': 'Click dispatched.'}
        browser.list_tabs.return_value = {'tabs': []}
        self.assertEqual(run_agent(browser, 'skip the ad')['message'], 'Click dispatched.')
        browser.execute.assert_called_once_with('youtube_skip_ad', {})
        browser.observe_page.assert_not_called()
        generate.assert_not_called()

    @patch('backend.universal_agent.generate')
    def test_direct_path_keeps_domain_rejection(self, generate):
        browser = Mock()
        browser.execute.return_value = {'error': 'Website not approved.'}
        self.assertEqual(run_agent(browser, 'open https://unapproved.example')['outcome'], 'incomplete')
        generate.assert_not_called()

    def test_buffering_is_not_reported_as_success(self):
        browser = Mock()
        browser.execute.return_value = {'playing': False, 'state': 'buffering'}
        result = run_agent(browser, 'play the video')
        self.assertEqual(result['outcome'], 'incomplete')
        self.assertIn('buffering', result['message'])

    @patch('backend.universal_agent.generate')
    def test_video_selection_needs_only_one_model_call(self, generate):
        from google.genai import types
        browser = Mock()
        browser.page.return_value.url = 'https://youtube.com'
        browser.execute.side_effect = [
            {'results': [{'index': 0, 'title': 'Fixture jazz'}]},
            {'selected_title': 'Fixture jazz', 'playback': {'playing': True, 'state': 'playing'}},
        ]
        content = types.Content(role='model', parts=[types.Part.from_function_call(
            name='youtube_open_video', args={'index': 0})])
        generate.return_value = Mock(candidates=[Mock(content=content)],
                                     function_calls=[content.parts[0].function_call])
        result = run_agent(browser, 'play jazz on YouTube')
        self.assertEqual(result['outcome'], 'finished')
        self.assertIn('Fixture jazz', result['message'])
        self.assertEqual(generate.call_count, 1)
        browser.observe_page.assert_not_called()


class EventPumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.chrome = cls.playwright.chromium.launch(channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()
        cls.playwright.stop()

    def setUp(self):
        self.owner = threading.get_ident()
        self.callbacks = []
        self.context = self.chrome.new_context()
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()
        self.page.goto('https://www.youtube.com/')

    def route(self, route):
        self.callbacks.append(threading.get_ident())
        route.fulfill(content_type='text/html', body='<html><body>Fixture</body></html>')

    def tearDown(self):
        self.context.close()

    def begin_fetch(self):
        self.page.evaluate('''() => {
            window.finishedAt = null;
            window.beganAt = performance.now();
            fetch('/fixture').then(r => r.text()).then(() => window.finishedAt = performance.now());
        }''')

    def test_routing_runs_during_remote_call_on_owner_thread(self):
        self.begin_fetch()
        remote_owner = []
        def remote():
            remote_owner.append(threading.get_ident())
            time.sleep(.25)
            return 'fixture response'
        self.assertEqual(call_with_browser_events(remote, self.context), 'fixture response')
        self.page.wait_for_function('() => window.finishedAt !== null')
        elapsed = self.page.evaluate('() => window.finishedAt - window.beganAt')
        self.assertLess(elapsed, 150)
        self.assertTrue(all(thread == self.owner for thread in self.callbacks))
        self.assertNotEqual(remote_owner[0], self.owner)

    def test_idle_pump_services_requests(self):
        self.begin_fetch()
        for _ in range(4):
            pump_context(self.context)
        self.assertTrue(self.page.evaluate('() => window.finishedAt !== null'))

    def test_remote_errors_propagate(self):
        def remote():
            raise RuntimeError('fixture error')
        with self.assertRaisesRegex(RuntimeError, 'fixture error'):
            call_with_browser_events(remote, self.context)


if __name__ == '__main__':
    unittest.main()
