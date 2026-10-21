"""One-shot safe diagnostics for Alpinus in Render. NO Shopify calls or writes."""
import asyncio, json, os, re
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
URL="https://alpinusgroup.com/kurtka-damska-2-warstwowa-alpinus-selenga/3-61-1074"
LOGIN="https://alpinusgroup.com/logowanie/7"
def safe_url(url):
    p=urlsplit(url)
    return p.scheme+"://"+p.netloc+p.path
def emit(stage,**data):
    print(json.dumps({"stage":stage,**data},ensure_ascii=False),flush=True)
async def inspect(page,label):
    html=await page.content()
    return {"method":label,"url":safe_url(page.url),"title":(await page.title())[:100],
            "html_length":len(html),"has_code":"NQ35000" in html.upper(),
            "stock_nodes":await page.locator("[data-stock-value]").count(),
            "variant_rows":await page.locator(".attribute-button-ui.last-lvl-ui.table-row-ui").count()}
async def run():
    login=os.getenv("ALPINUS_B2B_LOGIN","")
    password=os.getenv("ALPINUS_B2B_PASSWORD","")
    emit("credentials_present",login=bool(login),password=bool(password),
         login_trim_difference=login!=login.strip(),password_trim_difference=password!=password.strip())
    if not login or not password: return
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        context=await browser.new_context(locale="pl-PL",viewport={"width":1440,"height":1000})
        page=await context.new_page()
        observed=[]
        def response(r):
            if len(observed)<65 and "alpinusgroup.com" in r.url:
                observed.append({"method":r.request.method,"url":safe_url(r.url),"status":r.status})
        page.on("response",response)
        try:
            await page.goto(LOGIN,wait_until="domcontentloaded",timeout=60000)
            await page.wait_for_timeout(1500)
            emit("login_form",url=safe_url(page.url),email_count=await page.locator('input[name="email"]').count(),
                 password_count=await page.locator('input[name="password"]').count(),
                 button_count=await page.locator('button.sign-in-lq.enter-key-trigger-lq').count())
            email=page.locator('input[name="email"]').first
            pwd=page.locator('input[name="password"]').first
            if await email.count() and await pwd.count():
                await email.fill(login)
                await pwd.fill(password)
                button=page.locator('button.sign-in-lq.enter-key-trigger-lq').first
                if await button.count(): await button.click(timeout=15000)
                else: await pwd.press("Enter")
                await page.wait_for_timeout(5000)
            emit("post_login",url=safe_url(page.url),title=(await page.title())[:100],
                 cookie_names=sorted(set(x["name"] for x in await context.cookies())),
                 storage_keys=await page.evaluate("() => Object.keys(localStorage).slice(0,25)"),
                 responses=observed)
            raw=await context.request.get(URL,timeout=30000)
            body=await raw.text()
            emit("raw_http",status=raw.status,url=safe_url(raw.url),html_length=len(body),
                 has_code="NQ35000" in body.upper(),stock_attr_occurrences=len(re.findall("data-stock-value",body)),
                 login_form_marker='sign-in-form-js' in body)
            await page.goto(URL,wait_until="domcontentloaded",timeout=60000)
            try: await page.locator("[data-stock-value]").first.wait_for(timeout=18000)
            except Exception: pass
            emit("browser_dom",**(await inspect(page,"page.goto")),
                 login_form_count=await page.locator('input[name="password"]').count())
        finally:
            await browser.close()
if __name__=="__main__":
    try: asyncio.run(run())
    except Exception as exc:
        emit("failure",error_type=type(exc).__name__,safe_detail=str(exc).split("\n")[0][:170])
        raise SystemExit(1)
