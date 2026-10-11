(() => {
  if (globalThis.__orionContentScriptInstalled) return;
  globalThis.__orionContentScriptInstalled = true;

  const selector = "a, button, [role='button'], [role='link'], input[type='submit']";
  let lastElements = [];

  function visible(element) {
    const style = getComputedStyle(element);
    return (
      element.getClientRects().length > 0 &&
      style.visibility !== "hidden" &&
      style.display !== "none" &&
      element.getAttribute("aria-disabled") !== "true" &&
      !element.disabled
    );
  }

  function labelFor(element) {
    return (
      element.innerText ||
      element.getAttribute("aria-label") ||
      element.getAttribute("title") ||
      element.getAttribute("placeholder") ||
      element.value ||
      ""
    ).trim().replace(/\s+/g, " ").slice(0, 80);
  }

  function isYouTubePage() {
    return /youtube\.com|youtu\.be/.test(location.href);
  }

  function findYoutubeSkipButton() {
    if (!isYouTubePage()) {
      return null;
    }

    const selectors = [
      "button.ytp-ad-skip-button-modern",
      "button.ytp-ad-skip-button",
      "button.ytp-ad-overlay-close-button",
      "button[aria-label*='Skip ads' i]",
      "button[aria-label*='Skip ad' i]",
      "button[aria-label*='Skip' i]",
      "button[title*='Skip' i]",
      "[class*='skip'][class*='button']",
    ];

    for (const selector of selectors) {
      const button = Array.from(document.querySelectorAll(selector)).find((element) => {
        if (!visible(element)) return false;
        const rect = element.getBoundingClientRect();
        if (rect.width < 12 || rect.height < 8) return false;

        const text = (element.innerText || element.getAttribute("aria-label") || element.getAttribute("title") || "").trim();
        const matchesSkip = /skip/i.test(text) || /skip/i.test(element.getAttribute("aria-label") || "") || /skip/i.test(element.getAttribute("title") || "");
        const inAdContext = !!element.closest(".ytp-ad-module, .ytp-ad-player-overlay, .ytp-ad-preview-container") || /ytp-ad/.test(element.className || "");
        return matchesSkip && (inAdContext || /ad/i.test(location.href));
      });

      if (button) return button;
    }

    return null;
  }

  function clickSafely(element) {
    if (!element) return false;

    try {
      element.scrollIntoView({ block: "center", inline: "center" });
    } catch {}

    try {
      element.click();
    } catch {}

    try {
      element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    } catch {}

    return true;
  }

  function skipYoutubeAdIfPresent() {
    if (!isYouTubePage()) return false;

    const button = findYoutubeSkipButton();
    if (!button) return false;

    const now = Date.now();
    const lastAttempt = skipYoutubeAdIfPresent.lastAttempt || 0;
    if (now - lastAttempt < 1500) return false;
    skipYoutubeAdIfPresent.lastAttempt = now;

    return clickSafely(button);
  }
  skipYoutubeAdIfPresent.lastAttempt = 0;

  function startYoutubeAdMonitor() {
    if (window.__orionYoutubeAdMonitorStarted) return;
    window.__orionYoutubeAdMonitorStarted = true;

    const runCheck = () => {
      if (!document.hidden) {
        try {
          skipYoutubeAdIfPresent();
        } catch {}
      }
    };

    runCheck();

    const observer = new MutationObserver(runCheck);
    observer.observe(document.body || document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "aria-label", "title", "style"],
    });

    window.__orionYoutubeAdObserver = observer;
    window.setInterval(runCheck, 800);
  }

  startYoutubeAdMonitor();

  function observe() {
    lastElements = Array.from(document.querySelectorAll(selector))
      .filter(visible)
      .slice(0, 60)
      .map((element, index) => ({
        element,
        index,
        tag: element.tagName.toLowerCase(),
        text: labelFor(element) || "(unlabeled)",
        href: element instanceof HTMLAnchorElement ? element.href : null,
      }));

    return {
      url: location.href,
      title: document.title,
      elements: lastElements.map(({ index, tag, text, href }) => ({
        index,
        tag,
        text,
        href,
      })),
      textExcerpt: (document.body?.innerText || "").slice(0, 1500),
    };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    try {
      if (message?.type === "observe") {
        sendResponse({ ok: true, observation: observe() });
        return false;
      }

      if (message?.type === "readText") {
        sendResponse({ text: (document.body?.innerText || "").slice(0, 15000) });
        return false;
      }

      if (message?.type === "click") {
        const item = lastElements[message.index];
        if (!item || item.index !== message.index) {
          sendResponse({ ok: false, error: "That index is stale. Observe the page again." });
          return false;
        }

        item.element.click();
        sendResponse({ ok: true });
        return false;
      }

      if (message?.type === "skipAd") {
        const button = findYoutubeSkipButton();
        if (!button) {
          sendResponse({ ok: false, error: "No YouTube skip button is visible right now." });
          return false;
        }

        button.click();
        button.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
        sendResponse({ ok: true, skipped: true });
        return false;
      }
    } catch (error) {
      sendResponse({ ok: false, error: String(error) });
      return false;
    }

    return false;
  });
})();