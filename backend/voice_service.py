"""Bounded, asynchronous ElevenLabs REST calls. Recordings stay in memory."""
import asyncio
import io
import json
import os
import re
import time
import wave

import httpx
from fastapi import HTTPException

from backend.performance import logger

MAX_AUDIO_BYTES = 1_000_000
MAX_SECONDS = 30
MAX_TEXT = 500
MAX_SPEECH_BYTES = 2_000_000


def configured_value(name, default=''):
    value = os.getenv(name, default).strip()
    return '' if value.lower().startswith(('your_', 'replace_', 'paste_')) or value.lower() == 'changeme' else value


def configuration():
    key = bool(configured_value('ELEVENLABS_API_KEY'))
    return {'transcription': key, 'speech': key and bool(configured_value('ELEVENLABS_VOICE_ID')),
            'max_seconds': MAX_SECONDS}


def validate_recording(data):
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413 if data else 422, 'Recording is empty or exceeds the 1 MB limit.')
    try:
        with wave.open(io.BytesIO(data), 'rb') as recording:
            frames, rate = recording.getnframes(), recording.getframerate()
            if (recording.getnchannels() != 1 or recording.getsampwidth() != 2 or
                    rate != 16000 or recording.getcomptype() != 'NONE'):
                raise ValueError('format')
            duration = frames / rate
            if not 0.1 <= duration <= MAX_SECONDS:
                raise ValueError('duration')
            samples = recording.readframes(frames)
            if len(samples) != frames * 2:
                raise ValueError('truncated')
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise HTTPException(422, 'Use a complete mono 16 kHz PCM16 WAV recording between 0.1 and 30 seconds.') from None
    return duration


class VoiceService:
    def __init__(self, transport=None):
        self.transport = transport  # MockTransport in tests; never a browser worker.
        self.slots = asyncio.Semaphore(2)

    async def _call(self, path, *, limit, **kwargs):
        key = configured_value('ELEVENLABS_API_KEY')
        if not key:
            raise HTTPException(503, 'Voice is not configured. Set ELEVENLABS_API_KEY in the backend .env.')
        if self.slots.locked():
            raise HTTPException(429, 'Voice service is busy. Try again when the current request finishes.')
        async with self.slots:
            try:
                async with asyncio.timeout(25):
                    async with httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(20, connect=5),
                                                 follow_redirects=False, trust_env=False) as client:
                        async with client.stream('POST', 'https://api.elevenlabs.io/v1/' + path,
                                                 headers={'xi-api-key': key}, **kwargs) as response:
                            if not response.is_success:
                                if response.status_code == 429:
                                    raise HTTPException(429, 'ElevenLabs quota or rate limit reached. No automatic retry was sent.')
                                if response.status_code in (401, 403):
                                    error_body = bytearray()
                                    async for chunk in response.aiter_bytes():
                                        if len(error_body) + len(chunk) > 8192:
                                            break
                                        error_body.extend(chunk)
                                    try:
                                        detail = json.loads(error_body).get('detail', {})
                                        missing_permission = isinstance(detail, dict) and detail.get('status') == 'missing_permissions'
                                    except (ValueError, AttributeError):
                                        missing_permission = False
                                    if missing_permission:
                                        permission = 'speech_to_text' if path == 'speech-to-text' else 'text_to_speech'
                                        raise HTTPException(503, f'ElevenLabs API key is missing {permission} permission. Enable it in your ElevenLabs API key settings. If you replace the key in .env, restart the backend.')
                                    raise HTTPException(503, 'ElevenLabs rejected the backend configuration. Check credentials and voice access.')
                                raise HTTPException(502, 'ElevenLabs could not complete the voice request. Check the selected model and voice.')
                            chunks, size = [], 0
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > limit:
                                    raise HTTPException(502, 'ElevenLabs response exceeded the local size limit.')
                                chunks.append(chunk)
                            return b''.join(chunks)
            except (TimeoutError, httpx.TimeoutException):
                raise HTTPException(504, 'Voice request timed out. Typed commands remain available.') from None
            except httpx.RequestError:
                raise HTTPException(502, 'Cannot reach ElevenLabs. Typed commands remain available.') from None

    async def transcribe(self, data):
        validate_recording(data)
        started = time.monotonic()
        try:
            raw = await self._call('speech-to-text', limit=256_000,
                                   files={'file': ('recording.wav', data, 'audio/wav')},
                                   data={'model_id': 'scribe_v2', 'language_code': 'en',
                                         'tag_audio_events': 'false', 'diarize': 'false',
                                         'timestamps_granularity': 'none'})
            try:
                text = json.loads(raw)['text']
                if not isinstance(text, str):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise HTTPException(502, 'ElevenLabs returned an invalid transcript.') from None
            text = text.strip()
            if not text:
                raise HTTPException(422, 'No speech was detected. Try a short spoken command.')
            if len(text) > 2000:
                raise HTTPException(422, 'Transcript exceeds the command length limit.')
            return {'text': text, 'elapsed_ms': round((time.monotonic() - started) * 1000)}
        finally:
            logger.info('[PERF] voice.transcription %.3f ms', (time.monotonic() - started) * 1000)

    async def speak(self, text):
        voice = configured_value('ELEVENLABS_VOICE_ID')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', voice):
            raise HTTPException(503, 'Set a valid ELEVENLABS_VOICE_ID in the backend .env.')
        text = text.strip()
        if not 1 <= len(text) <= MAX_TEXT:
            raise HTTPException(422, 'Speech text must contain 1 to 500 characters.')
        started = time.monotonic()
        try:
            audio = await self._call(f'text-to-speech/{voice}?output_format=mp3_22050_32',
                                     limit=MAX_SPEECH_BYTES,
                                     json={'text': text, 'model_id': os.getenv('ELEVENLABS_MODEL_ID', 'eleven_flash_v2_5'),
                                           'voice_settings': {'stability': 0.55, 'similarity_boost': 0.75,
                                                              'style': 0, 'use_speaker_boost': False}})
            if not audio:
                raise HTTPException(502, 'ElevenLabs returned empty audio.')
            return audio, round((time.monotonic() - started) * 1000)
        finally:
            logger.info('[PERF] voice.synthesis %.3f ms', (time.monotonic() - started) * 1000)
