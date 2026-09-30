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
    p=await async_playwright().start()
    browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
    context=await browser.new_context(viewport={"width":1440,"height":1000},locale="pl-PL")
    page=await context.new_page()
    await page.goto(urljoin(BASE_URL,LOGIN_PATH),wait_until="domcontentloaded",timeout=60000)
    try:
        await page.wait_for_load_state("networkidle",timeout=15000)
    except PlaywrightTimeoutError:
        pass
    email=page.locator('input[name="email"]:visible').first
    password=page.locator('input[name="password"]:visible').first
    if await email.count() and await password.count():
        await email.fill(LOGIN)
        await password.fill(PASSWORD)
        submit=page.get_by_role("button",name="Zaloguj się",exact=True)
        if await submit.count():
            await submit.click(timeout=15000)
        else:
            await password.press("Enter")
        try:
            await page.wait_for_load_state("networkidle",timeout=30000)
        except PlaywrightTimeoutError:
            pass
    if await page.locator('input[name="password"]:visible').count():
        raise RuntimeError("ALPINUS authentication failed")
    return p,browser,context,page
