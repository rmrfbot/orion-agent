# Orion

Orion's first Chrome extension spike reads the active tab only after you open the side panel. It can list and click visible page controls, then send page metadata to the local FastAPI backend. This spike does not yet include speech recognition or Gemini planning.

## Run the local backend

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

Leave the backend running at `http://127.0.0.1:8000`.

## Load the Chrome extension

1. Open `chrome://extensions` in Google Chrome.
2. Turn on **Developer mode**.
3. Select **Load unpacked** and choose this repository's `extension` folder.
4. Open a regular website tab where you are signed in, such as your Canvas course.
5. Click the Orion extension icon to open the side panel.
6. Select **Observe this tab** and grant Orion website access when Chrome prompts. It can then list visible links and buttons. Select **Click** beside an item to activate it.
7. Select **Test connection**. A successful response confirms the side panel reached FastAPI.

The extension uses `activeTab` and injects its content script only after you use the panel. It does not have persistent access to every website. Chrome internal pages, including `chrome://extensions`, cannot be inspected.

## Stop

Stop the backend with `Ctrl+C` in its terminal. Reload the extension from `chrome://extensions` after changing extension files.
