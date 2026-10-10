import json
import os

from google import genai
from google.genai import types


SYSTEM_PROMPT = """You are Orion, a careful browser navigation assistant.
Use only the current page observation and the supplied action history.
Choose exactly one action and return valid JSON with keys: action, index, narration, reply.
Allowed actions are click, done, and fail. For click, index must be one of the
observed element indices. Click only one element at a time; the page will be
observed again after every click. Never invent an element or claim a click worked.
Do not click controls that submit, send, delete, purchase, or otherwise commit
important changes. If the request is complete, use done. If you cannot identify
a safe next step, use fail and briefly explain why in reply.
Keep narration and reply concise and suitable for voice playback."""


def plan_action(request, history, observation):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured in the backend .env file.")

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=json.dumps({
                "request": request,
                "history": history,
                "observation": observation,
            }),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
    finally:
        client.close()

    if not response.text:
        raise RuntimeError("Gemini returned an empty plan.")

    plan = json.loads(response.text)
    if not isinstance(plan, dict):
        raise ValueError("Gemini returned a plan that was not a JSON object.")
    return plan