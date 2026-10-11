import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from google.genai import types

from backend import api
from backend.browser_worker import BrowserWorker
from backend.universal_agent import run_agent


class APICompatibilityTests(unittest.TestCase):
    def test_submission_polling_and_authentication(self):
        worker = BrowserWorker()
        worker.running = True
        with patch.object(api, 'worker', worker), patch.object(api, 'LOCAL_TOKEN', 'fixture-token'):
            # No lifespan context: the test exercises endpoints without launching Chrome.
            client = TestClient(api.app)
            self.assertEqual(client.post('/api/tasks', json={'instruction': 'find jazz'}).status_code, 401)
            headers = {'X-ORION-Token': 'fixture-token'}
            response = client.post('/api/tasks', json={'instruction': 'find jazz'}, headers=headers)
            self.assertEqual(response.status_code, 202)
            task = response.json()
            self.assertEqual(task['status'], 'queued')
            self.assertIsNone(task['result'])
            worker.update_task(task['task_id'], status='finished', result={'outcome': 'finished', 'message': 'fixture'})
            polled = client.get('/api/tasks/' + task['task_id'], headers=headers)
            self.assertEqual(polled.json()['result']['message'], 'fixture')
            self.assertEqual(client.get('/api/tasks/missing', headers=headers).status_code, 404)
            self.assertEqual(client.post('/api/tasks', json={'instruction': ''}, headers=headers).status_code, 422)

    def test_queue_and_browser_timings_are_additive(self):
        worker = BrowserWorker()
        worker.running = True
        task = worker.submit('fixture')
        worker._ensure_browser = Mock(return_value=Mock())
        worker._browser_alive = Mock(return_value=True)
        owner = threading.get_ident()

        def agent(browser, instruction):
            self.assertEqual(threading.get_ident(), owner)
            return {'outcome': 'finished', 'message': 'fixture', 'tabs': {'tabs': []}, 'elapsed_ms': 1}

        worker._execute_task(task['task_id'], Mock(), Mock(), agent, 'https://www.youtube.com')
        result = worker.get_task(task['task_id'])['result']
        self.assertIn('workflow_timings', result)
        self.assertGreaterEqual(result['total_elapsed_ms'], 0)
        self.assertNotIn(task['task_id'], worker.submitted_at)

    @patch('backend.universal_agent.generate')
    def test_manual_function_calls_keep_model_content_and_response(self, generate):
        browser = Mock()
        browser.page.return_value.url = 'https://youtube.com'
        browser.observe_page.return_value = {'observation': 'fixture'}
        browser.list_tabs.return_value = {'tabs': []}
        browser.execute.return_value = {'playing': False, 'state': 'buffering'}
        content = types.Content(role='model', parts=[types.Part.from_function_call(
            name='youtube_play', args={})])
        call = content.parts[0].function_call
        first = Mock(candidates=[Mock(content=content)], function_calls=[call])
        final = Mock(candidates=[Mock(content=types.Content(role='model', parts=[
            types.Part.from_text(text='Video is buffering.')]))], function_calls=[], text='Video is buffering.')
        generate.side_effect = [first, final]
        result = run_agent(browser, 'play the current video')
        self.assertEqual(result['message'], 'Video is buffering.')
        self.assertEqual(result['actions_taken'], 1)
        self.assertEqual(result['tool_errors'], [])
        conversation = generate.call_args.kwargs['contents']
        self.assertIs(conversation[1], content)
        self.assertEqual(conversation[2].parts[0].function_response.name, 'youtube_play')
        self.assertEqual(conversation[2].parts[0].function_response.response['state'], 'buffering')


if __name__ == '__main__':
    unittest.main()
