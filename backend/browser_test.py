import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as playwright:

        # Launch Google Chrome instead of Chromium
        browser = await playwright.chromium.launch(
            channel="chrome",
            headless=False
        )

        page = await browser.new_page()

        await page.goto("https://www.wikipedia.org/")

        print("Page title:", await page.title())
        print("Current URL:", page.url)

        await page.screenshot(
            path="browser_test.png",
            full_page=True
        )

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
