# Orion

The Orion bubble now lives in Chrome's side panel. It listens locally for **"Hey Orion"** or **"Orion"**, sends short speech segments only to the local FastAPI backend for Vosk transcription, then uses Gemini to navigate the active tab. Microphone audio is not sent to a cloud speech service.

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
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Load the Chrome extension

1. Open `chrome://extensions` in Google Chrome.
2. Turn on **Developer mode**.
3. Select **Load unpacked** and choose this repository's `extension` folder.
4. Open a regular website tab where you are signed in, such as your Canvas course.
5. Click the Orion extension icon to open the side panel. Keep it open while using voice commands.
6. Select **Observe this tab** once and grant Orion website access when Chrome prompts.

## Use voice navigation

1. Open a regular website tab where you are signed in, such as your Canvas course.
2. Click the Orion extension icon and select **Observe this tab** once. Grant website access when Chrome prompts.
3. Click **Start listening** in the orb and grant Chrome microphone access.
4. Say **"Hey Orion, open Modules"** or **"Orion, open my week five notes"**. You can also say **"Orion"**, pause, then give the command within 10 seconds.

The orb shows listening, transcription, and command status. Keep the side panel open while using voice commands. Stop the mic with **Stop listening**. The desktop `orion_bubble.py` file is an older prototype and is not needed for this workflow.

If the panel reports microphone permission denied, select **Open microphone setup**. In the new Orion tab, select **Request microphone access** and allow Chrome's prompt. Close that tab and select **Start listening** in the side panel again. If Chrome still denies the request, check macOS **System Settings > Privacy & Security > Microphone** and Chrome's **Sites can ask to use your microphone** setting.

If asked to click a control labeled like submit, send, or delete, Orion requires confirmation in the extension panel. Spoken replies and spoken confirmation are not implemented yet.

The extension requests optional HTTP/HTTPS website access when you first observe a page. Chrome internal pages, including `chrome://extensions`, cannot be inspected.

## Stop

Stop the backend with `Ctrl+C` in its terminal. Reload the extension from `chrome://extensions` after changing extension files.
