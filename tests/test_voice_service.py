import asyncio
import io
import json
import threading
import unittest
import wave
from unittest.mock import Mock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import api
from backend.voice_service import VoiceService, validate_recording, MAX_AUDIO_BYTES
from backend.voice_service import configuration
from backend.universal_agent import run_agent


def wav(seconds=0.2):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as file:
        file.setnchannels(1);file.setsampwidth(2);file.setframerate(16000)
        file.writeframes(b'\x01\x00'*int(16000*seconds))
    return stream.getvalue()


class RecordingValidationTests(unittest.TestCase):
    def test_placeholder_credentials_are_not_reported_as_ready(self):
        with patch.dict('os.environ',{'ELEVENLABS_API_KEY':'your_api_key_here','ELEVENLABS_VOICE_ID':'your_voice_id_here'}):
            self.assertFalse(configuration()['transcription'])
            self.assertFalse(configuration()['speech'])

    def test_spoken_playback_proof_requires_verified_progress_and_no_ad(self):
        for progress,ad,expected in [(True,False,True),(False,False,False),(True,True,False)]:
            browser=Mock()
            browser.execute.return_value={'playing':True,'state':'playing','progress_verified':progress,'ad_playing':ad}
            browser.list_tabs.return_value={'tabs':[]}
            result=run_agent(browser,'play the video')
            self.assertEqual(result['verified_playback'],expected)

    def test_duration_and_binary_validation(self):
        self.assertAlmostEqual(validate_recording(wav()),0.2)
        for data in [b'',b'not audio',wav(0.01),wav(30.1),wav()[:-20],b'x'*(MAX_AUDIO_BYTES+1)]:
            with self.assertRaises(HTTPException):validate_recording(data)


class VoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env=patch.dict('os.environ',{'ELEVENLABS_API_KEY':'fixture-secret','ELEVENLABS_VOICE_ID':'fixture-voice',
                                         'ELEVENLABS_MODEL_ID':'eleven_flash_v2_5'})
        self.env.start();self.addCleanup(self.env.stop)

    async def test_transcription_contract_and_no_audio_logging(self):
        def handle(request):
            self.assertEqual(str(request.url),'https://api.elevenlabs.io/v1/speech-to-text')
            self.assertEqual(request.headers['xi-api-key'],'fixture-secret')
            self.assertIn(b'scribe_v2',request.content)
            self.assertIn(b'language_code',request.content)
            self.assertIn(b'recording.wav',request.content)
            return httpx.Response(200,json={'text':'ORION, open YouTube.'})
        service=VoiceService(httpx.MockTransport(handle))
        with self.assertLogs('orion.performance',level='INFO') as logs:
            result=await service.transcribe(wav())
        self.assertEqual(result['text'],'ORION, open YouTube.')
        self.assertGreaterEqual(result['elapsed_ms'],0)
        self.assertNotIn('fixture-secret',' '.join(logs.output))
        self.assertNotIn('RIFF',' '.join(logs.output))

    async def test_speech_contract_binary_and_bounds(self):
        def handle(request):
            body=json.loads(request.content)
            self.assertEqual(body['model_id'],'eleven_flash_v2_5')
            self.assertEqual(body['text'],'Playback confirmed.')
            self.assertIn('/text-to-speech/fixture-voice',str(request.url))
            return httpx.Response(200,content=b'ID3fixture-audio',headers={'Content-Type':'audio/mpeg'})
        service=VoiceService(httpx.MockTransport(handle))
        audio,elapsed=await service.speak('Playback confirmed.')
        self.assertEqual(audio,b'ID3fixture-audio');self.assertGreaterEqual(elapsed,0)
        with self.assertRaises(HTTPException):await service.speak('x'*20001)

    async def test_upstream_errors_are_sanitized_and_never_retried(self):
        for status,expected in [(401,503),(403,503),(429,429),(500,502),(302,502)]:
            requests=[]
            def handle(request):
                requests.append(request)
                return httpx.Response(status,content=b'fixture-secret raw provider error')
            service=VoiceService(httpx.MockTransport(handle))
            with self.assertRaises(HTTPException) as caught:await service.transcribe(wav())
            self.assertEqual(caught.exception.status_code,expected)
            self.assertNotIn('fixture-secret',caught.exception.detail)
            self.assertEqual(len(requests),1)

    async def test_timeout_empty_and_invalid_transcripts(self):
        def timeout(request):raise httpx.ReadTimeout('fixture-secret',request=request)
        with self.assertRaises(HTTPException) as caught:
            await VoiceService(httpx.MockTransport(timeout)).transcribe(wav())
        self.assertEqual(caught.exception.status_code,504)
        for body in [{'text':''},{'text':None},{'wrong':'value'}]:
            with self.assertRaises(HTTPException):
                await VoiceService(httpx.MockTransport(lambda _:httpx.Response(200,json=body))).transcribe(wav())

    async def test_missing_permission_reports_only_safe_actionable_details(self):
        for status in (401, 403):
            requests = []
            def handle(request):
                requests.append(request)
                return httpx.Response(status, json={'detail': {
                    'status': 'missing_permissions', 'message': 'fixture-secret untrusted provider text'}})
            service = VoiceService(httpx.MockTransport(handle))
            for operation, permission in ((lambda: service.transcribe(wav()), 'speech_to_text'),
                                          (lambda: service.speak('Hello.'), 'text_to_speech')):
                with self.assertRaises(HTTPException) as caught:
                    await operation()
                self.assertEqual(caught.exception.status_code, 503)
                self.assertIn(permission, caught.exception.detail)
                self.assertIn('API key settings', caught.exception.detail)
                self.assertNotIn('fixture-secret', caught.exception.detail)
            self.assertEqual(len(requests), 2)

    async def test_slow_voice_request_leaves_event_loop_and_browser_worker_free(self):
        started=asyncio.Event();release=asyncio.Event();ticks=[]
        async def handle(_):
            started.set();await release.wait()
            return httpx.Response(200,json={'text':'open YouTube'})
        service=VoiceService(httpx.MockTransport(handle))
        with patch.object(api.worker,'submit',side_effect=AssertionError('voice must not touch worker')):
            pending=asyncio.create_task(service.transcribe(wav()))
            await started.wait()
            for _ in range(3):ticks.append(threading.get_ident());await asyncio.sleep(0)
            self.assertEqual(len(ticks),3);self.assertFalse(pending.done())
            release.set();await pending

    async def test_voice_concurrency_is_bounded_without_waiting(self):
        release=asyncio.Event();started=asyncio.Event();count=0
        async def handle(_):
            nonlocal count
            count+=1
            if count==2:started.set()
            await release.wait();return httpx.Response(200,json={'text':'fixture'})
        service=VoiceService(httpx.MockTransport(handle))
        pending=[asyncio.create_task(service.transcribe(wav())) for _ in range(2)]
        await started.wait()
        with self.assertRaises(HTTPException) as caught:await service.transcribe(wav())
        self.assertEqual(caught.exception.status_code,429)
        release.set();await asyncio.gather(*pending)


class VoiceEndpointTests(unittest.TestCase):
    def test_authentication_localhost_and_binary_endpoints(self):
        env={'ELEVENLABS_API_KEY':'fixture-secret','ELEVENLABS_VOICE_ID':'fixture-voice'}
        def handle(request):return httpx.Response(200,json={'text':'open YouTube'}) if request.url.path.endswith('speech-to-text') else httpx.Response(200,content=b'ID3fixture')
        service=VoiceService(httpx.MockTransport(handle))
        with patch.dict('os.environ',env),patch.object(api,'LOCAL_TOKEN','fixture-token'),patch.object(api,'voice_service',service),patch.object(api.worker,'submit',Mock()) as submit:
            client=TestClient(api.app,client=('127.0.0.1',50000))
            headers={'X-ORION-Token':'fixture-token','Content-Type':'audio/wav'}
            self.assertEqual(client.post('/api/voice/transcribe',content=wav()).status_code,401)
            response=client.post('/api/voice/transcribe',content=wav(),headers=headers)
            self.assertEqual(response.status_code,200);self.assertEqual(response.json()['text'],'open YouTube')
            self.assertEqual(client.post('/api/voice/transcribe',content=b'',headers=headers).status_code,422)
            self.assertEqual(client.post('/api/voice/transcribe',content=wav(),headers={**headers,'Content-Type':'audio/webm'}).status_code,415)
            self.assertEqual(client.post('/api/voice/transcribe',content=b'x'*(MAX_AUDIO_BYTES+1),headers=headers).status_code,413)
            response=client.post('/api/voice/speak',json={'text':'Playback confirmed.'},headers={'X-ORION-Token':'fixture-token'})
            self.assertEqual(response.content,b'ID3fixture');self.assertIn('audio/mpeg',response.headers['content-type'])
            self.assertEqual(response.headers['cache-control'],'no-store')
            external=TestClient(api.app,client=('192.0.2.1',50000))
            self.assertEqual(external.post('/api/voice/transcribe',content=wav(),headers=headers).status_code,403)
            submit.assert_not_called()

