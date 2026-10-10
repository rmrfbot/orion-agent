
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

try:
    print("\nAvailable Gemini models:\n")

    for model in client.models.list():
        actions = model.supported_actions or []

        if "generateContent" in actions:
            print(model.name)

finally:
    client.close()
