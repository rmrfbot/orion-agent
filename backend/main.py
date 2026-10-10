from collections import deque
from pathlib import Path
from threading import Lock

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from backend.agent import plan_action

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Orion Local API")

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)

voice_commands = deque(maxlen=20)
voice_commands_lock = Lock()


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
