const observeButton = document.querySelector("#observe-button");
const backendButton = document.querySelector("#backend-button");
const pageTitle = document.querySelector("#page-title");
const pageUrl = document.querySelector("#page-url");
const actionStatus = document.querySelector("#action-status");
const pageExcerpt = document.querySelector("#page-excerpt");
const elementsContainer = document.querySelector("#elements");
const statusText = document.querySelector("#status");

let currentObservation = null;
let pendingVoiceCommand = null;
let processingVoiceCommand = false;
const confirmationRequired = /\b(submit|send|delete|remove|publish|purchase|pay|drop|enroll|unsubscribe|cancel|confirm)\b/i;
const websitePermissions = { origins: ["http://*/*", "https://*/*"] };

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
    return;
  }

  processingVoiceCommand = true;
  const request = pendingVoiceCommand;
  pendingVoiceCommand = null;
  statusText.textContent = `Working on: ${request}`;
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

      if (plan.action === "done") {
        setActionStatus(plan.reply || "Done.");
        return;
      }
      if (plan.action === "fail") {
        setActionStatus(plan.reply || "I could not complete that request.", true);
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
  } catch (error) {
    console.error("Orion voice navigation failed:", error);
    setActionStatus(`Voice navigation failed: ${error.message}`, true);
  } finally {
    processingVoiceCommand = false;
  }
}

observeButton.addEventListener("click", observePage);
backendButton.addEventListener("click", checkBackend);
window.setInterval(pollVoiceCommands, 1200);