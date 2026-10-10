
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


# ORION Project Root
ROOT = Path(__file__).resolve().parent.parent

# Dedicated Chrome profile.
PROFILE = ROOT / ".orion_chrome_profile"

# Initial approved sites for testing.
# We will support user-approved additional websites later.
ALLOWED_DOMAINS = {
    "wikipedia.org",
    "github.com",
    "youtube.com",
}


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme != "https":
        return False

    hostname = (parsed.hostname or "").lower()

    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ALLOWED_DOMAINS
    )


class UniversalBrowser:

    def __init__(self, context):
        self.context = context
        self.tabs = []

    def open_tab(self, url: str):
        if not allowed_url(url):
            print(f"[BLOCKED] {url}")
            return None

        page = self.context.new_page()

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000
            )

            self.tabs.append(page)

            print(f"\n[ORION] Opened: {page.url}")
            print(f"[TITLE] {page.title()}")

            return page

        except Exception as exc:
            print(f"[ERROR] {exc}")
            page.close()
            return None

    def list_tabs(self):
        print("\n========== OPEN TABS ==========")

        for index, page in enumerate(self.tabs):
            if not page.is_closed():
                print(f"{index}: {page.title()}")
                print(f"   {page.url}")

    def switch_tab(self, index: int):
        if index < 0 or index >= len(self.tabs):
            print("[ERROR] Invalid tab index.")
            return None

        page = self.tabs[index]

        if page.is_closed():
            print("[ERROR] Tab is already closed.")
            return None

        page.bring_to_front()

        print(f"\n[ORION] Switched to tab {index}")
        print(f"[TITLE] {page.title()}")

        return page

    def close_tab(self, index: int):
        if index < 0 or index >= len(self.tabs):
            print("[ERROR] Invalid tab index.")
            return

        page = self.tabs[index]

        if not page.is_closed():
            page.close()
            print(f"[ORION] Closed tab {index}")


def main():

    with sync_playwright() as playwright:

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            channel="chrome",
            headless=False,
            viewport={
                "width": 1440,
                "height": 900
            },
            accept_downloads=False,
        )

        browser = UniversalBrowser(context)

        try:
            print("\nORION UNIVERSAL BROWSER TEST")
            print("=" * 45)

            browser.open_tab(
                "https://www.wikipedia.org/"
            )

            browser.open_tab(
                "https://github.com/"
            )

            browser.open_tab(
                "https://www.youtube.com/"
            )

            browser.list_tabs()

            # Switch back to GitHub.
            browser.switch_tab(1)

            print("\n[ORION] Multiple tabs initialized!")
            print("Chrome will remain open.")

            input(
                "\nPress Enter to close ORION..."
            )

        finally:
            context.close()


if __name__ == "__main__":
    main()
