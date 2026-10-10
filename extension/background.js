console.log("[ORION] Browser Bridge loaded.");

chrome.runtime.onInstalled.addListener(() => {
  console.log("[ORION] Extension installed successfully.");
});

chrome.action.onClicked.addListener(async () => {
  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  const currentTab = tabs[0];

  console.log("[ORION] Active tab:", {
    title: currentTab?.title,
    url: currentTab?.url
  });
});