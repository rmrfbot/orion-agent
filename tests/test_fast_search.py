import unittest
from unittest.mock import Mock, patch

from backend.fast_commands import search_command
from backend.universal_agent import UniversalBrowser, run_agent


class SearchRoutingTests(unittest.TestCase):
    def test_general_web_and_encoding(self):
        command = search_command('search for cats & dogs', 'https://example.com')
        self.assertEqual(command['url'], 'https://www.google.com/search?q=cats+%26+dogs')

    def test_site_context_and_override(self):
        self.assertEqual(search_command('find jazz', 'https://www.youtube.com/watch?v=x')['site'], 'youtube')
        self.assertEqual(search_command('find jazz on Wikipedia', 'https://youtube.com')['site'], 'wikipedia')
        self.assertEqual(search_command('search YouTube for jazz', 'https://github.com')['query'], 'jazz')

    def test_complex_commands_keep_planner(self):
        self.assertIsNone(search_command('find jazz then play it', 'https://youtube.com'))
        self.assertIsNone(search_command('summarize this video', 'https://youtube.com'))

    @patch('backend.universal_agent.generate')
    def test_search_avoids_model_and_observation(self, generate):
        browser = Mock()
        browser.page.return_value.url = 'https://www.youtube.com'
        browser.quick_search.return_value = {'results': [{'index': 0, 'title': 'Jazz'}]}
        result = run_agent(browser, 'search for jazz')
        self.assertEqual(result['outcome'], 'finished')
        self.assertIn('Jazz', result['message'])
        generate.assert_not_called()
        browser.observe_page.assert_not_called()

    def test_timeout_is_incomplete(self):
        browser = Mock()
        browser.page.return_value.url = 'https://google.com'
        browser.quick_search.return_value = {'error': 'Search timed out'}
        self.assertEqual(run_agent(browser, 'find cats')['outcome'], 'incomplete')


class BrowserIntegrationTests(unittest.TestCase):
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
        self.context.route('**/*', lambda route: route.fulfill(
            content_type='text/html', body=self.html))
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    html = '''<html><title>Fixture</title><body>
        <input type="search" placeholder="Find">
        <button style="display:none">Hidden</button>
        <a id="video-title" href="/watch?v=abcdefghijk" title="Jazz">Jazz</a>
        <div class="html5-video-player ad-showing"><video></video></div>
        <button class="ytp-ad-skip-button" onclick="this.remove()">Skip Ad</button>
        </body></html>'''

    def browser(self):
        browser = UniversalBrowser(self.context)
        browser.active_page = self.page
        # Fixture handles network responses after the production route is installed.
        self.context.route('**/*', lambda route: route.fulfill(
            content_type='text/html', body=self.html))
        return browser

    def test_restored_tab_skips_ad_and_observes_state(self):
        self.page.goto('https://www.youtube.com/watch?v=abcdefghijk')
        browser = self.browser()
        self.assertEqual(self.page.locator('.ytp-ad-skip-button').count(), 0)
        observation = browser.observe_page()
        self.assertTrue(observation['media']['auto_skip_enabled'])
        self.assertTrue(observation['media']['ad_playing'])
        self.assertNotIn('Hidden', observation['observation'].split('Interactive elements:')[1])
        self.assertEqual(browser.elements[0]['locator'].get_attribute('type'), 'search')
        # Newly available mid-roll controls are handled while the agent is idle.
        self.page.evaluate("""() => {
            const button = document.createElement('button');
            button.className = 'ytp-ad-skip-button';
            button.onclick = () => button.remove();
            document.body.append(button);
        }""")
        self.page.locator('.ytp-ad-skip-button').wait_for(state='detached', timeout=2000)

    def test_search_extracts_verified_video_results(self):
        self.page.goto('https://www.youtube.com')
        browser = self.browser()
        result = browser.youtube_search('jazz')
        self.assertEqual(result['results'][0]['title'], 'Jazz')
        self.assertEqual(len(browser.youtube_results), 1)
        browser.approved_domains.clear()
        self.assertIn('error', browser.quick_search(search_command('find cats', 'https://google.com')))

    def test_general_web_search(self):
        self.page.goto('https://www.google.com')
        browser = self.browser()
        result = browser.quick_search(search_command('find cats', self.page.url))
        self.assertTrue(result['ready'])
        self.assertIn('q=cats', result['url'])


if __name__ == '__main__':
    unittest.main()
