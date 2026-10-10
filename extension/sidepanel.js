const observeButton = document.querySelector("#observe-button");
const backendButton = document.querySelector("#backend-button");
const pageTitle = document.querySelector("#page-title");
const pageUrl = document.querySelector("#page-url");
const pageExcerpt = document.querySelector("#page-excerpt");
const elementsContainer = document.querySelector("#elements");
const statusText = document.querySelector("#status");

let currentObservation = null;
const confirmationRequired = /\b(submit|send|delete|remove|publish|purchase|pay|drop|enroll|unsubscribe|cancel|confirm)\b/i;

async function sendToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !/^https?:/.test(tab.url || "")) {
    throw new Error("Open a regular website tab to use Orion.");
  }

  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["content.js"],
  });

  return chrome.tabs.sendMessage(tab.id, message);
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
  statusText.textContent = "Inspecting active tab…";

  try {
    const response = await sendToActiveTab({ type: "observe" });
    if (!response?.ok) throw new Error(response?.error || "Could not inspect this page.");
    renderObservation(response.observation);
    statusText.textContent = "Page observed.";
  } catch (error) {
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

  statusText.textContent = `Clicking element ${index}…`;

  try {
    const response = await sendToActiveTab({ type: "click", index });
    if (!response?.ok) throw new Error(response?.error || "Could not click that element.");
    statusText.textContent = "Clicked. Refreshing the page observation…";
    window.setTimeout(observePage, 900);
  } catch (error) {
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

observeButton.addEventListener("click", observePage);
backendButton.addEventListener("click", checkBackend);