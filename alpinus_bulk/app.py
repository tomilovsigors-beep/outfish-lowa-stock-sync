import os
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL=os.getenv("ALPINUS_BASE_URL","https://alpinusgroup.com").rstrip("/")
LOGIN_PATH=os.getenv("ALPINUS_LOGIN_PATH","/logowanie/7")
LOGIN=os.getenv("ALPINUS_B2B_LOGIN","")
PASSWORD=os.getenv("ALPINUS_B2B_PASSWORD","")

async def open_logged_in_page():
    if not LOGIN or not PASSWORD:
        raise RuntimeError("ALPINUS credentials are not configured")
    p = await async_playwright().start()
    browser = None
    try:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(viewport={"width":1440,"height":1000}, locale="pl-PL")
        page = await context.new_page()
        await page.goto(urljoin(BASE_URL, LOGIN_PATH), wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        email = page.locator('input[name="email"]').first
        password = page.locator('input[name="password"]').first
        if await email.count() and await password.count():
            await email.fill(LOGIN)
            await password.fill(PASSWORD)
            button = page.locator("button.sign-in-lq.enter-key-trigger-lq").first
            if await button.count():
                await button.click(timeout=12000)
            else:
                await password.press("Enter")
            await page.wait_for_timeout(2000)
        if not await authenticated(page):
            # Comarch e-Sklep documents its native POST Customer/Login action
            # requiring the site's own CSRF. Do not assume another endpoint.
            await page.goto(urljoin(BASE_URL, LOGIN_PATH), wait_until="domcontentloaded")
            csrf = await page.evaluate("""() => {
                const field = document.querySelector('input[name="__csrf"]');
                return field?.value || window.__CSRF || null;
            }""")
            if not csrf:
                raise RuntimeError("ALPINUS_CSRF_MISSING")
            response = await context.request.post(
                page.url,
                form={"__action":"Customer/Login", "__csrf":str(csrf),
                      "email":LOGIN,"password":PASSWORD,"remember":"true"},
                timeout=30000)
            if not response.ok:
                raise RuntimeError("ALPINUS_NATIVE_LOGIN_HTTP_ERROR")
            await page.goto(urljoin(BASE_URL, LOGIN_PATH), wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
        if not await authenticated(page):
            raise RuntimeError("ALPINUS_NATIVE_LOGIN_REJECTED")
        return p,browser,context,page
    except Exception:
        if browser: await browser.close()
        await p.stop()
        raise

async def authenticated(page):
    body = await page.content()
    return "Wyloguj" in body or "Jesteś zalogowany" in body
