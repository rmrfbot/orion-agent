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
    } catch (error) {
      sendResponse({ ok: false, error: String(error) });
      return false;
    }

    return false;
  });
})();