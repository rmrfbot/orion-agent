
import os
from pathlib import Path
from dotenv import load_dotenv

root = Path(__file__).resolve().parent.parent
env_path = root / ".env"

load_dotenv(env_path, override=True)

key = os.getenv("GEMINI_API_KEY", "").strip()

print("Environment file exists:", env_path.exists())
print("API key loaded:", bool(key))
print("API key length:", len(key))
print("Gemini model:", os.getenv("GEMINI_MODEL"))
