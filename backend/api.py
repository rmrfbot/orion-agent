
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    Depends,
    Header,
    HTTPException,
    status,
    Request,
    Response,
)
from pydantic import BaseModel, Field

from backend.browser_worker import BrowserWorker
from backend.performance import measure
from backend.voice_service import VoiceService, configuration, MAX_AUDIO_BYTES


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env", override=True)

LOCAL_TOKEN = os.getenv("ORION_LOCAL_TOKEN", "")

if not LOCAL_TOKEN:
    raise RuntimeError(
        "ORION_LOCAL_TOKEN is missing from the root .env file."
    )


# ============================================================
# 2. BROWSER WORKER
# ============================================================

# Create one browser worker for the entire application.
# It will own the Playwright instance and Google Chrome.
worker = BrowserWorker()
voice_service = VoiceService()


# ============================================================
# 3. APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("\n" + "=" * 55)
    print("ORION DESKTOP — STARTING")
    print("=" * 55)

    print("[ORION] Starting Gemini + Playwright browser worker...")

    # Launch the dedicated Chrome worker.
    worker.start()

    print("[ORION] Browser worker initialized.")
    print("[ORION] API is ready.")

    try:
        yield

    finally:
        print("\n[ORION] Shutting down browser worker...")
        worker.stop()
        print("[ORION] Shutdown complete.")


# ============================================================
# 4. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="ORION Desktop API",
    description=(
        "Local API for ORION, an AI-powered browser assistant "
        "using Gemini and Playwright."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


# ============================================================
# 5. REQUEST MODELS
# ============================================================

class BrowserCommand(BaseModel):
    instruction: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language browser instruction",
        examples=["Open GitHub in a new tab"],
    )


# ============================================================
# 6. LOCAL API AUTHENTICATION
# ============================================================

def verify_token(
    x_orion_token: str | None = Header(default=None)
):
    if (
        not x_orion_token
        or not secrets.compare_digest(
            x_orion_token,
            LOCAL_TOKEN,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid ORION local API token.",
        )


# ============================================================
# 7. HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():
    return {
        "status": (
            "healthy" if worker.running else "offline"
        ),
        "service": "ORION Desktop",
        "browser_worker": worker.running,
        "browser_state": worker.browser_state,
        "voice": configuration(),
    }


# ============================================================
# 8. CREATE BROWSER TASK
# ============================================================

@app.post(
    "/api/tasks",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_token)],
)
def create_task(command: BrowserCommand):
    """
    Queue a natural-language browser command.

    The worker processes it asynchronously on its
    dedicated thread.
    """

    if not worker.running:
        raise HTTPException(
            status_code=503,
            detail="Browser worker is offline.",
        )

    try:
        with measure('api.submit'):
            task = worker.submit(command.instruction)

        print(
            f"\n[API] New task submitted: "
            f"{command.instruction}"
        )

        return task

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )


# ============================================================
# 9. GET TASK STATUS
# ============================================================

@app.get(
    "/api/tasks/{task_id}",
    dependencies=[Depends(verify_token)],
)
def get_task(task_id: str):
    """
    Retrieve the status and result of a browser task.
    """

    task = worker.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found.",
        )

    return task


# ============================================================
# 10. ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():
    return {
        "application": "ORION",
        "version": "0.2.0",
        "status": (
            "online" if worker.running else "offline"
        ),
        "message": "ORION Desktop API is running.",
        "documentation": "/docs",
    }


# Voice requests run on FastAPI's event loop, never the Playwright owner thread.
def verify_voice_local(request: Request):
    if not request.client or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Voice endpoints accept localhost connections only.')


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


@app.post('/api/voice/transcribe', dependencies=[Depends(verify_token), Depends(verify_voice_local)])
async def transcribe_voice(request: Request):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() not in ('audio/wav', 'audio/x-wav'):
        raise HTTPException(415, 'Voice transport requires audio/wav.')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, 'Recording exceeds the 1 MB limit.')
        data.extend(chunk)
    return await voice_service.transcribe(bytes(data))


@app.post('/api/voice/speak', dependencies=[Depends(verify_token), Depends(verify_voice_local)])
async def speak_voice(command: SpeechRequest):
    audio, elapsed = await voice_service.speak(command.text)
    return Response(audio, media_type='audio/mpeg', headers={
        'Cache-Control': 'no-store', 'X-ORION-Voice-Elapsed-Ms': str(elapsed)})
