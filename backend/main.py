import json
from collections import deque
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from vosk import KaldiRecognizer, Model

from backend.agent import plan_action

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

VOSK_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "vosk-model-small-en-us-0.15"
MAX_VOICE_AUDIO_BYTES = 512_000

app = FastAPI(title="Orion Local API")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)

voice_commands = deque(maxlen=20)
voice_commands_lock = Lock()
vosk_model = None
vosk_model_lock = Lock()


class ExtensionCheck(BaseModel):
	title: str = Field(default="", max_length=500)
	url: str = Field(default="", max_length=2048)
	element_count: int = Field(ge=0, le=60)


class VoiceCommandRequest(BaseModel):
	command: str = Field(min_length=1, max_length=1000)


class PlanRequest(BaseModel):
	request: str = Field(min_length=1, max_length=1000)
	history: list[dict] = Field(default_factory=list)
	observation: dict


@app.get("/health")
def health():
	return {"ok": True, "service": "orion"}


@app.post("/extension-check")
def extension_check(payload: ExtensionCheck):
	return {
		"ok": True,
		"message": "Extension reached the Orion backend.",
		"page_title": payload.title,
		"element_count": payload.element_count,
	}


@app.post("/voice/transcribe")
async def transcribe_voice(request: Request):
	global vosk_model

	pcm_audio = await request.body()
	if not pcm_audio or len(pcm_audio) % 2:
		raise HTTPException(status_code=422, detail="Expected non-empty 16-bit PCM audio.")
	if len(pcm_audio) > MAX_VOICE_AUDIO_BYTES:
		raise HTTPException(status_code=413, detail="Voice segment is too large.")

	try:
		sample_rate = int(request.headers.get("x-audio-sample-rate", "16000"))
	except ValueError as error:
		raise HTTPException(status_code=400, detail="Invalid audio sample rate.") from error
	if sample_rate != 16000:
		raise HTTPException(status_code=400, detail="Audio must be resampled to 16000 Hz.")

	if vosk_model is None:
		with vosk_model_lock:
			if vosk_model is None:
				if not VOSK_MODEL_PATH.is_dir():
					raise HTTPException(status_code=503, detail="Local Vosk model is missing.")
				vosk_model = Model(str(VOSK_MODEL_PATH))

	recognizer = KaldiRecognizer(vosk_model, sample_rate)
	recognizer.AcceptWaveform(pcm_audio)
	transcript = json.loads(recognizer.FinalResult()).get("text", "")
	return {"text": transcript}


@app.post("/voice/command")
def receive_voice_command(payload: VoiceCommandRequest):
	command = payload.command.strip()
	if not command:
		raise HTTPException(status_code=422, detail="Command cannot be blank.")

	with voice_commands_lock:
		voice_commands.append(command)

	return {"ok": True, "queued": True}


@app.get("/voice/commands/next")
def next_voice_command():
	with voice_commands_lock:
		command = voice_commands.popleft() if voice_commands else None

	return {"command": command}


@app.post("/plan")
def create_plan(payload: PlanRequest):
	try:
		plan = plan_action(
			request=payload.request,
			history=payload.history,
			observation=payload.observation,
		)
	except Exception as error:
		raise HTTPException(status_code=502, detail=f"Gemini planning failed: {error}") from error

	action = plan.get("action")
	if action not in {"click", "done", "fail"}:
		raise HTTPException(status_code=502, detail="Gemini returned an unsupported action.")

	if action == "click":
		index = plan.get("index")
		elements = payload.observation.get("elements", [])
		if not isinstance(index, int) or isinstance(index, bool) or not any(
			item.get("index") == index for item in elements if isinstance(item, dict)
		):
			raise HTTPException(status_code=502, detail="Gemini selected an element outside the latest observation.")

	return plan
