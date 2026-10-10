# Orion

Orion listens locally for **"Hey Orion"** or **"Orion"** in the desktop bubble. It recognizes the command on-device, sends only the recognized text to the local FastAPI backend, and uses Gemini to navigate the active tab through the open Chrome side panel. Microphone audio is not uploaded.

## Run the local backend

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
```

Download the offline English speech model once:

```sh
mkdir -p models
curl -L https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/orion-vosk-model.zip
unzip -q /tmp/orion-vosk-model.zip -d models
rm /tmp/orion-vosk-model.zip
```

Set `GEMINI_API_KEY` in the root `.env`. The planner defaults to `gemini-3.8-flash`; set `GEMINI_MODEL` there to override it.

Start the backend and leave it running:

```sh
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Load the Chrome extension

1. Open `chrome://extensions` in Google Chrome.
2. Turn on **Developer mode**.
3. Select **Load unpacked** and choose this repository's `extension` folder.
4. Open a regular website tab where you are signed in, such as your Canvas course.
5. Click the Orion extension icon to open the side panel. Keep it open while using voice commands.
6. Select **Observe this tab** once and grant Orion website access when Chrome prompts.

## Run the voice bubble

In a second terminal, from the repository root with `.venv` active:

```sh
python orion_bubble.py
```

On macOS, grant microphone access to the terminal app running the bubble. Say **"Hey Orion, open Modules"** or **"Orion, open my week five notes"**. You can also say just **"Orion"**, pause, then say the command within 10 seconds. The bubble shows its listening/sending status. The extension observes the current tab, asks Gemini for one safe next click at a time, then re-observes.

If asked to click a control labeled like submit, send, or delete, Orion requires confirmation in the extension panel. Spoken replies and spoken confirmation are not implemented yet.

The extension requests optional HTTP/HTTPS website access when you first observe a page. Chrome internal pages, including `chrome://extensions`, cannot be inspected.

## Stop

Stop the backend with `Ctrl+C` in its terminal and close the bubble with `Esc`. Reload the extension from `chrome://extensions` after changing extension files.
