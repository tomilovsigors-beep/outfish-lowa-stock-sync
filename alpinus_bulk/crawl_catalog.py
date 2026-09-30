import asyncio, json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from app import BASE_URL, open_logged_in_page

MAX_PRODUCTS=int(os.getenv("ALPINUS_MAX_PRODUCTS","600"))
MAX_PAGES=int(os.getenv("ALPINUS_MAX_PAGES","300"))
CONCURRENCY=int(os.getenv("ALPINUS_CONCURRENCY","6"))
OUTPUT=os.getenv("ALPINUS_OUTPUT_JSONL","/tmp/alpinus_catalog.jsonl")

PRODUCT_ID_RE=re.compile(r"/3-\d+-(\d+)$")
TEXT_SIZE_RE=re.compile(r"\b(2XL|3XL|4XL|XL|XS|S|M|L)\b",re.I)
RANGE_SIZE_RE=re.compile(r"\b(3[0-9]|4[0-9]|50)\s*[-/]\s*(3[0-9]|4[0-9]|50)\b")
NUM_SIZE_RE=re.compile(r"\b(3[4-9]|4[0-9]|50)\b")

def emit(event,payload):
    print(json.dumps({"event":event,"ts":datetime.now(timezone.utc).isoformat(),**payload},ensure_ascii=False,separators=(",",":")),flush=True)

def same_host(url):
    return urlparse(url).netloc==urlparse(BASE_URL).netloc

def supplier_product_id(url):
    m=PRODUCT_ID_RE.search(urlparse(url).path.lower())
    return m.group(1) if m else ""

async def safe_goto(page,url,timeout=20000):
    for attempt in range(1,3):
        try:
            await page.goto(url,wait_until="commit",timeout=timeout)
            try: await page.wait_for_selector("body",timeout=6000)
            except Exception: pass
            return True
        except Exception:
            if attempt<2: await asyncio.sleep(1)
            else: raise
    return False

def normalize_image(src):
    if not src:
        return None
    low=src.lower()
    if "css/img/" in low or low.endswith(".gif") or "produktpolski" in low:
        return None
    if src.startswith("//"):
        src="https:"+src
    elif src.startswith("/"):
        src=urljoin(BASE_URL+"/",src)
    elif not src.startswith("http"):
        src=urljoin(BASE_URL+"/",src)
    return src if "/img/" in src else None

def detect_size(text, qty):
    text=re.sub(r"\s+"," ",text or "").strip()
    m=TEXT_SIZE_RE.search(text)
    if m:
        return m.group(1).upper()
    m=RANGE_SIZE_RE.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    nums=[int(x) for x in NUM_SIZE_RE.findall(text)]
    # Never treat the stock number itself as a size. If a nearby distinct
    # footwear/apparel-sized number exists, use that; otherwise stock is generic.
    for n in nums:
        if n != qty:
            return str(n)
    return None

def parse_product_html(url, html):
    soup=BeautifulSoup(html,"html.parser")
    title=(soup.find("h1").get_text(" ",strip=True) if soup.find("h1") else (soup.title.get_text(" ",strip=True) if soup.title else ""))
    body=soup.get_text(" ",strip=True)
    low=body.lower()
    symbol=""
    for pat in [r"symbol\s*[:\-]?\s*([a-z0-9\-]+)",r"kod producenta\s*[:\-]?\s*([a-z0-9\-]+)"]:
        m=re.search(pat,low,re.I)
        if m:
            symbol=m.group(1).upper()
            break
    eans=sorted(set(re.findall(r"\b\d{13}\b",body)))
    prices=re.findall(r"(\d+[\.,]\d{2})\s*PLN",body,re.I)
    images=[]
    for img in soup.find_all("img"):
        src=normalize_image(img.get("src") or img.get("data-src") or img.get("data-original"))
        if src and src not in images:
            images.append(src)

    size_rows=[]; generic=[]
    candidates=soup.select("[data-stock-value], [data-max], input[max], input[name*=quantity], input[name*=ilosc], input[name*=qty]")
    for el in candidates:
        qty=el.get("data-stock-value") or el.get("data-max") or el.get("max")
        if not (qty and str(qty).isdigit()):
            continue
        qty=int(qty)
        txt=" ".join(filter(None,[
            el.get_text(" ",strip=True),
            el.parent.get_text(" ",strip=True) if el.parent else "",
            el.get("name") or "",
            el.get("id") or ""
        ]))
        size=detect_size(txt,qty)
        if size:
            row={"size":size,"qty":qty}
            if row not in size_rows:
                size_rows.append(row)
        else:
            generic.append(qty)
    return {
        "supplier_product_id":supplier_product_id(url),
        "source_url":url,
        "title":title,
        "symbol":symbol,
        "eans":eans,
        "numeric_stock_rows":size_rows,
        "generic_stock":max(generic) if generic else None,
        "prices_pln_detected":prices[:20],
        "images":images[:40],
        "body_excerpt":body[:8000]
    }

async def fetch_product(request_ctx,url):
    last=None
    for attempt in range(1,4):
        try:
            resp=await request_ctx.get(url,timeout=20000,fail_on_status_code=False)
            status=resp.status
            text=await resp.text()
            if status==200 and len(text)>500:
                return parse_product_html(url,text)
            last=RuntimeError(f"HTTP {status}, len={len(text)}")
        except Exception as exc:
            last=exc
        await asyncio.sleep(attempt)
    raise last or RuntimeError("Unknown fetch error")

async def main():
    p=browser=context=None
    try:
        p,browser,context,page=await open_logged_in_page()
        seen_pages=set(); product_by_id={}; raw_product_urls=0
        queue=[
            BASE_URL+"/produkty/produkty/mezczyzni/2-6",
            BASE_URL+"/produkty/produkty/kobiety/2-5",
            BASE_URL+"/produkty/produkty/wyposazenie/2-8",
            BASE_URL+"/produkty/produkty/dzieci/2-7",
        ]
        while queue and len(seen_pages)<MAX_PAGES and len(product_by_id)<MAX_PRODUCTS:
            url=queue.pop(0)
            if url in seen_pages:
                continue
            seen_pages.add(url)
            try:
                await safe_goto(page,url)
                try: await page.wait_for_timeout(400)
                except Exception: pass
                links=await page.locator("a[href]").evaluate_all("els=>els.map(a=>a.href).filter(Boolean)")
            except Exception as exc:
                emit("discovery_page_error",{"url":url,"error":f"{type(exc).__name__}: {exc}"})
                continue
            for href in links:
                href=href.split("#")[0]
                if not same_host(href):
                    continue
                path=urlparse(href).path.lower()
                pid=supplier_product_id(href)
                if pid:
                    raw_product_urls+=1
                    product_by_id.setdefault(pid,href)
                elif "/produkty/" in path:
                    # Traverse the supplier's catalog graph exhaustively from the
                    # four top-level roots. This catches pagination and nested
                    # categories without relying on Polish keyword heuristics.
                    clean=href.split("?")[0].rstrip("/")
                    if clean and clean not in seen_pages and clean not in queue and len(queue)<2500:
                        queue.append(clean)
            emit("discovery_progress",{"pages":len(seen_pages),"raw_product_urls":raw_product_urls,"unique_products":len(product_by_id),"queue":len(queue)})

        product_urls=list(product_by_id.values())[:MAX_PRODUCTS]
        emit("discovery_complete",{"pages":len(seen_pages),"raw_product_urls":raw_product_urls,"unique_products":len(product_urls),"duplicates_removed":max(0,raw_product_urls-len(product_urls))})

        q=asyncio.Queue()
        for i,u in enumerate(product_urls,1):
            q.put_nowait((i,u))
        rows=[]; lock=asyncio.Lock(); request_ctx=context.request

        async def worker(worker_id):
            while True:
                try: i,url=q.get_nowait()
                except asyncio.QueueEmpty: break
                try:
                    row=await fetch_product(request_ctx,url)
                    async with lock: rows.append(row)
                    emit("product_data",{
                        "i":i,"total":len(product_urls),"worker":worker_id,
                        "supplier_product_id":row["supplier_product_id"],
                        "source_url":row["source_url"],"title":row["title"],"symbol":row["symbol"],
                        "eans":row["eans"],"numeric_stock_rows":row["numeric_stock_rows"],
                        "generic_stock":row["generic_stock"],"prices_pln_detected":row["prices_pln_detected"],
                        "images":row["images"][:12]
                    })
                except Exception as exc:
                    emit("product_error",{"i":i,"worker":worker_id,"url":url,"error":f"{type(exc).__name__}: {exc}"})
                finally: q.task_done()

        await asyncio.gather(*[worker(i) for i in range(1,CONCURRENCY+1)])

        with open(OUTPUT,"w",encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row,ensure_ascii=False)+"\n")
        audit={
            "with_numeric_stock":sum(1 for r in rows if r["numeric_stock_rows"]),
            "with_generic_stock":sum(1 for r in rows if r["generic_stock"] is not None),
            "with_any_stock":sum(1 for r in rows if r["numeric_stock_rows"] or r["generic_stock"] is not None),
            "with_ean":sum(1 for r in rows if r["eans"]),
            "with_images":sum(1 for r in rows if r["images"]),
            "with_prices":sum(1 for r in rows if r["prices_pln_detected"])
        }
        emit("crawl_summary",{"ok":True,"products_discovered":len(product_urls),"rows":len(rows),"audit":audit,"output":OUTPUT})
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if p: await p.stop()

if __name__=="__main__":
    asyncio.run(main())
