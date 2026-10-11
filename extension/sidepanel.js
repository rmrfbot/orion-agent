const observeButton = document.querySelector("#observe-button");
const backendButton = document.querySelector("#backend-button");
const pageTitle = document.querySelector("#page-title");
const pageUrl = document.querySelector("#page-url");
const actionStatus = document.querySelector("#action-status");
const pageExcerpt = document.querySelector("#page-excerpt");
const elementsContainer = document.querySelector("#elements");
const statusText = document.querySelector("#status");
const voiceButton = document.querySelector("#voice-button");
const voiceOrb = document.querySelector("#voice-orb");
const voiceRays = document.querySelector("#voice-rays");
const voiceIndicator = document.querySelector("#voice-indicator");
const voiceStatus = document.querySelector("#voice-status");
const microphoneHelpButton = document.querySelector("#microphone-help-button");

let currentObservation = null;
let pendingVoiceCommand = null;
let processingVoiceCommand = false;
let queuedVoiceCommands = [];
let voiceListening = false;
let voiceStarting = false;
let audioStream = null;
let audioContext = null;
let audioSource = null;
let audioProcessor = null;
let silentGain = null;
let audioSampleRate = 0;
let speechActive = false;
let speechChunks = [];
let silenceTail = [];
let speechDurationMs = 0;
let silenceDurationMs = 0;
let awaitingCommandUntil = 0;
const confirmationRequired = /\b(submit|send|delete|remove|publish|purchase|pay|drop|enroll|unsubscribe|cancel|confirm)\b/i;
const websitePermissions = { origins: ["http://*/*", "https://*/*"] };
const wakeWords = new Set(["orion", "ryan", "oreon", "orian", "rion"]);
const wakePrefixes = new Set(["hey", "they"]);

for (let index = 0; index < 40; index += 1) {
  const ray = document.createElement("span");
  ray.className = "voice-ray";
  ray.style.setProperty("--angle", `${index * 9}deg`);
  ray.style.setProperty("--delay", `${(index % 10) * -0.07}s`);
  voiceRays.append(ray);
}

function setVoiceState(state, message) {
  voiceOrb.dataset.state = state;
  voiceIndicator.textContent = state.toUpperCase();
  voiceStatus.textContent = message;
}

async function microphoneErrorMessage(error) {
  if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
    let permissionState = "unknown";
    try {
      permissionState = (await navigator.permissions.query({ name: "microphone" })).state;
    } catch {}
    return `Microphone blocked (${error.name}; Chrome permission: ${permissionState}). In chrome://settings/content/microphone, allow microphone access, remove Orion from the blocked list, and select your microphone.`;
  }
  if (error.name === "NotFoundError") {
    return "No microphone was found. Connect or enable a microphone, then try again.";
  }
  if (error.name === "NotReadableError") {
    return "The microphone is busy or unavailable. Close other apps using it, then try again.";
  }
  return error.message;
}

async function startVoiceListening() {
  if (voiceStarting || voiceListening) return;
  voiceStarting = true;
  voiceButton.disabled = true;
  voiceStatus.textContent = "Requesting microphone access...";

  try {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") {
      throw new Error("This Chrome version does not support microphone capture here.");
    }

    audioStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    audioContext = new AudioContext();
    await audioContext.resume();
    audioSampleRate = audioContext.sampleRate;
    audioSource = audioContext.createMediaStreamSource(audioStream);
    audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
    silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    audioProcessor.onaudioprocess = captureAudioFrame;
    audioSource.connect(audioProcessor);
    audioProcessor.connect(silentGain);
    silentGain.connect(audioContext.destination);

    voiceListening = true;
    voiceButton.textContent = "Stop listening";
    voiceButton.setAttribute("aria-pressed", "true");
    setVoiceState("listening", "Listening locally. Say 'Hey Orion' or 'Orion'.");
  } catch (error) {
    stopVoiceListening(false);
    setVoiceState("error", await microphoneErrorMessage(error));
  } finally {
    voiceStarting = false;
    voiceButton.disabled = false;
  }
}

function stopVoiceListening(showStatus = true) {
  voiceListening = false;
  speechActive = false;
  speechChunks = [];
  silenceTail = [];

  if (audioProcessor) {
    audioProcessor.onaudioprocess = null;
    audioProcessor.disconnect();
    audioProcessor = null;
  }
  if (audioSource) {
    audioSource.disconnect();
    audioSource = null;
  }
  if (silentGain) {
    silentGain.disconnect();
    silentGain = null;
  }
  if (audioStream) {
    audioStream.getTracks().forEach((track) => track.stop());
    audioStream = null;
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close().catch(() => {});
    audioContext = null;
  }

  voiceButton.textContent = "Start listening";
  voiceButton.setAttribute("aria-pressed", "false");
  if (showStatus) setVoiceState("off", "Microphone off.");
}

function captureAudioFrame(event) {
  if (!voiceListening) return;

  const input = event.inputBuffer.getChannelData(0);
  const samples = new Float32Array(input);
  let energy = 0;
  for (let index = 0; index < samples.length; index += 1) {
    energy += samples[index] * samples[index];
  }

  const rms = Math.sqrt(energy / samples.length);
  const frameDurationMs = samples.length / audioSampleRate * 1000;

  if (rms >= 0.009) {
    if (!speechActive) {
      speechActive = true;
      speechChunks = silenceTail;
      silenceTail = [];
      speechDurationMs = 0;
      silenceDurationMs = 0;
      setVoiceState("hearing", "Hearing speech...");
    }
    speechChunks.push(samples);
    speechDurationMs += frameDurationMs;
    silenceDurationMs = 0;
    if (speechDurationMs >= 9000) finishSpeechSegment();
  } else if (speechActive) {
    speechChunks.push(samples);
    speechDurationMs += frameDurationMs;
    silenceDurationMs += frameDurationMs;
    if (silenceDurationMs >= 600 || speechDurationMs >= 9000) finishSpeechSegment();
  } else {
    silenceTail.push(samples);
    if (silenceTail.length > 2) silenceTail.shift();
  }
}

function encodePcm16(chunks, inputRate) {
  const inputLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const input = new Float32Array(inputLength);
  let offset = 0;
  for (const chunk of chunks) {
    input.set(chunk, offset);
    offset += chunk.length;
  }

  const ratio = inputRate / 16000;
  const output = new Int16Array(Math.floor(input.length / ratio));
  for (let index = 0; index < output.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.max(start + 1, Math.floor((index + 1) * ratio)));
    let average = 0;
    for (let sample = start; sample < end; sample += 1) average += input[sample];
    average /= end - start;
    const clipped = Math.max(-1, Math.min(1, average));
    output[index] = clipped < 0 ? clipped * 32768 : clipped * 32767;
  }
  return output.buffer;
}

async function finishSpeechSegment() {
  if (!speechActive) return;
  const chunks = speechChunks;
  const sampleRate = audioSampleRate;
  speechActive = false;
  speechChunks = [];
  silenceTail = [];
  speechDurationMs = 0;
  silenceDurationMs = 0;

  if (chunks.reduce((total, chunk) => total + chunk.length, 0) < sampleRate * 0.25) {
    setVoiceState("listening", "Listening locally. Say 'Hey Orion' or 'Orion'.");
    return;
  }

  setVoiceState("transcribing", "Transcribing locally...");
  try {
    const response = await fetch("http://127.0.0.1:8000/voice/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Audio-Sample-Rate": "16000",
      },
      body: encodePcm16(chunks, sampleRate),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Backend returned HTTP ${response.status}.`);

    if (result.text) {
      setVoiceState("listening", `Heard: ${result.text}`);
      handleVoiceTranscript(result.text);
    } else {
      setVoiceState("listening", "Didn't catch that. Say 'Hey Orion' or 'Orion'.");
    }
  } catch (error) {
    setVoiceState("error", `Local transcription failed: ${error.message}`);
  }
}

function wakePhraseLength(words) {
  if (words.length > 1 && wakePrefixes.has(words[0]) && wakeWords.has(words[1])) return 2;
  if (words.length && wakeWords.has(words[0])) return 1;
  return 0;
}

function handleVoiceTranscript(transcript) {
  const words = transcript.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return;

  const wakeLength = wakePhraseLength(words);
  if (wakeLength) {
    const command = words.slice(wakeLength).join(" ").trim();
    if (command) {
      awaitingCommandUntil = 0;
      queueVoiceCommand(command);
    } else {
      awaitingCommandUntil = Date.now() + 10000;
      setVoiceState("waiting", "Wake word heard. Say your command within 10 seconds.");
    }
    return;
  }

  if (Date.now() <= awaitingCommandUntil) {
    awaitingCommandUntil = 0;
    queueVoiceCommand(words.join(" "));
    return;
  }

  setVoiceState("listening", `Heard '${words.slice(0, 5).join(" ")}'. Start with Orion.`);
}

function queueVoiceCommand(command) {
  queuedVoiceCommands.push(command);
  setVoiceState("sending", `Command queued: ${command}`);
  if (!pendingVoiceCommand && !processingVoiceCommand) {
    pendingVoiceCommand = queuedVoiceCommands.shift();
    processPendingVoiceCommand();
  }
}

function setActionStatus(message, isError = false) {
  actionStatus.textContent = message;
  actionStatus.classList.toggle("error", isError);
}

async function sendToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error("No active browser tab is available.");
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"],
  });

  return chrome.tabs.sendMessage(tab.id, message);
}

async function hasWebsiteAccess() {
  return chrome.permissions.contains(websitePermissions);
}

async function requestWebsiteAccess() {
  if (await hasWebsiteAccess()) return true;
  return chrome.permissions.request(websitePermissions);
}

function renderObservation(observation) {
  currentObservation = observation;
  pageTitle.textContent = observation.title || "Untitled page";
  pageUrl.textContent = observation.url;
  pageExcerpt.textContent = observation.textExcerpt || "No visible page text found.";
  elementsContainer.replaceChildren();

  if (observation.elements.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No visible links or buttons found.";
    elementsContainer.append(empty);
    return;
  }

  for (const item of observation.elements) {
    const row = document.createElement("div");
    row.className = "element-row";

    const label = document.createElement("span");
    label.className = "element-label";
    label.textContent = `${item.index}. ${item.text}`;
    label.title = item.href || item.tag;

    const clickButton = document.createElement("button");
    clickButton.className = "click-button";
    clickButton.type = "button";
    clickButton.textContent = "Click";
    clickButton.setAttribute("aria-label", `Click ${item.text}`);
    clickButton.addEventListener("click", () => clickElement(item.index));

    row.append(label, clickButton);
    elementsContainer.append(row);
  }
}

async function observePage() {
  observeButton.disabled = true;
  setActionStatus("Inspecting the active tab…");

  try {
    const siteAccessGranted = await requestWebsiteAccess();
    if (!siteAccessGranted) {
      throw new Error("Grant Orion site access in Chrome to inspect this page.");
    }

    const response = await sendToActiveTab({ type: "observe" });
    if (!response?.ok) throw new Error(response?.error || "Could not inspect this page.");
    renderObservation(response.observation);
    setActionStatus(`Observed ${response.observation.elements.length} visible controls.`);
    statusText.textContent = "Page observed.";
    processPendingVoiceCommand();
  } catch (error) {
    console.error("Orion could not observe the active tab:", error);
    setActionStatus(`Could not inspect the active tab: ${error.message}`, true);
    statusText.textContent = error.message;
  } finally {
    observeButton.disabled = false;
  }
}

async function clickElement(index) {
  const item = currentObservation?.elements.find((element) => element.index === index);
  if (item && confirmationRequired.test(item.text)) {
    const accepted = window.confirm(`This action may change or submit data: "${item.text}". Continue?`);
    if (!accepted) return;
  }

  setActionStatus(`Clicking element ${index}…`);

  try {
    const response = await sendToActiveTab({ type: "click", index });
    if (!response?.ok) throw new Error(response?.error || "Could not click that element.");
    setActionStatus("Clicked. Refreshing the page observation…");
    window.setTimeout(observePage, 900);
  } catch (error) {
    console.error("Orion could not click the page element:", error);
    setActionStatus(`Could not click that element: ${error.message}`, true);
    statusText.textContent = `${error.message} Re-observing…`;
    window.setTimeout(observePage, 900);
  }
}

async function checkBackend() {
  backendButton.disabled = true;
  statusText.textContent = "Contacting local backend…";

  try {
    const response = await fetch("http://127.0.0.1:8000/extension-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: currentObservation?.title || "",
        url: currentObservation?.url || "",
        element_count: currentObservation?.elements.length || 0,
      }),
    });

    if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
    const result = await response.json();
    statusText.textContent = `${result.message} (${result.element_count} elements) `;
  } catch (error) {
    statusText.textContent = `Backend unavailable: ${error.message}`;
  } finally {
    backendButton.disabled = false;
  }
}

async function pollVoiceCommands() {
  if (pendingVoiceCommand || processingVoiceCommand) return;

  try {
    const response = await fetch("http://127.0.0.1:8000/voice/commands/next");
    if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}.`);
    const result = await response.json();
    if (result.command) {
      pendingVoiceCommand = result.command;
      setActionStatus(`Voice command received: ${result.command}`);
      await processPendingVoiceCommand();
    }
  } catch (error) {
    statusText.textContent = `Voice connection unavailable: ${error.message}`;
  }
}

async function processPendingVoiceCommand() {
  if (!pendingVoiceCommand || processingVoiceCommand) return;
  if (!(await hasWebsiteAccess())) {
    setActionStatus("Click Observe once and grant website access to enable voice navigation.", true);
    setVoiceState("waiting", "Grant website access with Observe, then say your command again.");
    return;
  }

  const request = pendingVoiceCommand;
  const normalizedRequest = request.toLowerCase();
  if (/skip\s+(the\s+)?ad|skip\s+ads|skip\s+ad/.test(normalizedRequest)) {
    try {
      const response = await sendToActiveTab({ type: "skipAd" });
      if (response?.ok) {
        setActionStatus("Skipped the YouTube ad.");
        setVoiceState("listening", "Skipped the YouTube ad.");
        pendingVoiceCommand = null;
        processingVoiceCommand = false;
        return;
      }
      setActionStatus(response?.error || "No YouTube skip button was visible yet.", true);
      setVoiceState("listening", response?.error || "No YouTube skip button was visible yet.");
      pendingVoiceCommand = null;
      processingVoiceCommand = false;
      return;
    } catch (error) {
      setActionStatus(`Could not skip the ad: ${error.message}`, true);
      setVoiceState("error", `Could not skip the ad: ${error.message}`);
      pendingVoiceCommand = null;
      processingVoiceCommand = false;
      return;
    }
  }

  processingVoiceCommand = true;
  pendingVoiceCommand = null;
  statusText.textContent = `Working on: ${request}`;
  setVoiceState("working", `Working on: ${request}`);
  const history = [];

  try {
    for (let step = 0; step < 10; step += 1) {
      const pageResponse = await sendToActiveTab({ type: "observe" });
      if (!pageResponse?.ok) {
        throw new Error(pageResponse?.error || "Could not observe the active page.");
      }

      const observation = pageResponse.observation;
      renderObservation(observation);
      if (history.length && !history[history.length - 1].resultUrl) {
        history[history.length - 1].resultUrl = observation.url;
      }

      const planResponse = await fetch("http://127.0.0.1:8000/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request, history, observation }),
      });
      const plan = await planResponse.json();
      if (!planResponse.ok) {
        throw new Error(plan.detail || `Planner returned HTTP ${planResponse.status}.`);
      }

      setActionStatus(plan.narration || "Orion is deciding what to do next.");
      setVoiceState("working", plan.narration || "Orion is working in the current tab.");

      if (plan.action === "done") {
        setActionStatus(plan.reply || "Done.");
        setVoiceState("listening", plan.reply || "Done.");
        return;
      }
      if (plan.action === "fail") {
        setActionStatus(plan.reply || "I could not complete that request.", true);
        setVoiceState("listening", plan.reply || "I could not complete that request.");
        return;
      }
      if (plan.action !== "click") {
        throw new Error("Planner returned an unsupported action.");
      }

      const item = observation.elements.find((element) => element.index === plan.index);
      if (!item) throw new Error("Planner selected an element that is no longer visible.");
      if (confirmationRequired.test(item.text)) {
        const accepted = window.confirm(`This action may change or submit data: "${item.text}". Continue?`);
        if (!accepted) {
          setActionStatus("Stopped before the confirmed action.");
          setVoiceState("listening", "Stopped before the confirmed action.");
          return;
        }
      }

      const clickResult = await sendToActiveTab({ type: "click", index: plan.index });
      if (!clickResult?.ok) {
        throw new Error(clickResult?.error || "The browser did not confirm the click.");
      }
      history.push({
        action: "click",
        index: plan.index,
        narration: plan.narration || "",
        resultUrl: "",
      });
      await new Promise((resolve) => window.setTimeout(resolve, 900));
    }

    setActionStatus("Stopped after 10 browser actions. Ask Orion to continue if needed.", true);
    setVoiceState("listening", "Stopped after 10 browser actions.");
  } catch (error) {
    console.error("Orion voice navigation failed:", error);
    setActionStatus(`Voice navigation failed: ${error.message}`, true);
    setVoiceState("error", `Navigation failed: ${error.message}`);
  } finally {
    processingVoiceCommand = false;
    if (queuedVoiceCommands.length && !pendingVoiceCommand) {
      pendingVoiceCommand = queuedVoiceCommands.shift();
      processPendingVoiceCommand();
    }
  }
}

observeButton.addEventListener("click", observePage);
backendButton.addEventListener("click", checkBackend);
microphoneHelpButton.addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("microphone-permission.html") });
});
voiceButton.addEventListener("click", () => {
  if (voiceListening) stopVoiceListening();
  else startVoiceListening();
});
window.addEventListener("beforeunload", () => stopVoiceListening(false));
window.setInterval(pollVoiceCommands, 1200);