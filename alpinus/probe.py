import asyncio
import json
import os
import subprocess
import sys

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

URL = os.getenv("ALPINUS_BASE_URL", "https://alpinusgroup.com").rstrip("/") + "/logowanie/7"

def emit(label, value):
    print(label + "=" + json.dumps(value, ensure_ascii=False), flush=True)

async def main():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])

        context = await browser.new_context(viewport={"width":1440,"height":1000}, locale="pl-PL")
        page = await context.new_page()
        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

            fields = await page.locator("input:visible").evaluate_all("""
                els => els.map(el => ({
                    type: el.type || "",
                    name: el.name || "",
                    id: el.id || "",
                    placeholder: el.placeholder || "",
                    autocomplete: el.autocomplete || ""
                }))
            """)
            buttons = await page.locator("button:visible, input[type='submit']:visible").evaluate_all("""
                els => els.map(el => ({
                    tag: el.tagName || "",
                    type: el.type || "",
                    name: el.name || "",
                    id: el.id || "",
                    text: (el.innerText || el.value || "").trim()
                }))
            """)
            forms = await page.locator("form").evaluate_all("""
                els => els.map(el => ({
                    method: el.method || "",
                    action: el.action || "",
                    id: el.id || "",
                    className: el.className || ""
                }))
            """)
            emit("BROWSER_PROBE", {
                "url": page.url,
                "title": await page.title(),
                "fields": fields,
                "buttons": buttons,
                "forms": forms
            })
            return 0
        finally:
            await context.close()
            await browser.close()

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
