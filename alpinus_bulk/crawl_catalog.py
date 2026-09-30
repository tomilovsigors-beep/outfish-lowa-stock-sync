import asyncio, json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from app import BASE_URL, open_logged_in_page

MAX_PRODUCTS=int(os.getenv("ALPINUS_MAX_PRODUCTS","600"))
MAX_PAGES=int(os.getenv("ALPINUS_MAX_PAGES","45"))
CONCURRENCY=int(os.getenv("ALPINUS_CONCURRENCY","2"))
OUTPUT=os.getenv("ALPINUS_OUTPUT_JSONL","/tmp/alpinus_catalog.jsonl")

def emit(event,payload):
    print(json.dumps({"event":event,"ts":datetime.now(timezone.utc).isoformat(),**payload},ensure_ascii=False,separators=(",",":")),flush=True)

def same_host(url):
    return urlparse(url).netloc==urlparse(BASE_URL).netloc

async def safe_goto(page,url,timeout=20000):
    for attempt in range(1,4):
        try:
            await page.goto(url,wait_until="commit",timeout=timeout)
            try:
                await page.wait_for_selector("body",timeout=8000)
            except Exception:
                pass
            return True
        except Exception as exc:
            msg=str(exc)
            if "ERR_ABORTED" in msg or "Navigation interrupted" in msg:
                await asyncio.sleep(.5*attempt)
                if page.url and same_host(page.url):
                    return True
            elif attempt<3:
                await asyncio.sleep(1.0*attempt)
            else:
                raise
    return False

async def extract_product(page,url):
    await safe_goto(page,url)
    try: await page.wait_for_timeout(1200)
    except Exception: pass
    data=await page.evaluate(r"""() => {
      const clean=v=>(v||'').replace(/\s+/g,' ').trim();
      const title=clean(document.querySelector('h1')?.innerText||document.title);
      const body=clean(document.body?.innerText||'');
      const imgs=[...new Set([...document.querySelectorAll('img[src]')].map(i=>i.currentSrc||i.src).filter(Boolean))];
      const rows=[...document.querySelectorAll('[data-stock-value], [data-max], input[max], input[name*=quantity], input[name*=ilosc], input[name*=qty]')].map(el=>({
        text:clean(el.innerText||el.parentElement?.innerText||'').slice(0,500),
        stock:el.getAttribute('data-stock-value'),
        dataMax:el.getAttribute('data-max'),
        max:el.getAttribute('max')
      }));
      return {title,body:body.slice(0,25000),imgs:imgs.slice(0,80),rows};
    }""")
    low=data["body"].lower()
    symbol=""
    for pat in [r"symbol\s*[:\-]?\s*([a-z0-9\-]+)",r"kod producenta\s*[:\-]?\s*([a-z0-9\-]+)"]:
        m=re.search(pat,low,re.I)
        if m: symbol=m.group(1).upper(); break
    eans=sorted(set(re.findall(r"\b\d{13}\b",data["body"])))
    prices=re.findall(r"(\d+[\.,]\d{2})\s*PLN",data["body"],re.I)
    sizes=[]; generic=[]
    for el in data["rows"]:
        txt=el.get("text") or ""
        qty=el.get("stock") or el.get("dataMax") or el.get("max")
        if not (qty and str(qty).isdigit()): continue
        qty=int(qty)
        m=re.search(r"\b(2XL|3XL|4XL|XL|XS|S|M|L|\d{2}(?:-\d{2})?)\b",txt,re.I)
        if m: sizes.append({"size":m.group(1).upper(),"qty":qty})
        else: generic.append(qty)
    return {
      "source_url":url,"title":data["title"],"symbol":symbol,"eans":eans,
      "numeric_stock_rows":sizes,"generic_stock":max(generic) if generic else None,
      "prices_pln_detected":prices[:20],
      "images":[x for x in data["imgs"] if "/img/" in x][:40],
      "body_excerpt":data["body"][:8000]
    }

async def main():
    p=browser=context=None
    try:
        p,browser,context,page=await open_logged_in_page()
        seen_pages=set(); product_urls=[]; queue=[BASE_URL+"/"]
        while queue and len(seen_pages)<MAX_PAGES and len(product_urls)<MAX_PRODUCTS:
            url=queue.pop(0)
            if url in seen_pages: continue
            seen_pages.add(url)
            try:
                await safe_goto(page,url)
                try: await page.wait_for_timeout(500)
                except Exception: pass
                links=await page.locator("a[href]").evaluate_all("""els=>els.map(a=>a.href).filter(Boolean)""")
            except Exception as exc:
                emit("discovery_page_error",{"url":url,"error":f"{type(exc).__name__}: {exc}"})
                continue
            for href in links:
                href=href.split("#")[0]
                if not same_host(href): continue
                path=urlparse(href).path.lower()
                if re.search(r"/3-\d+-\d+$",path):
                    if href not in product_urls: product_urls.append(href)
                elif any(k in path for k in ["/but","/odzie","/biel","/spod","/kurt","/plecak","/akces","/skarp","/produkt","/term","/obuw"]):
                    if href not in seen_pages and href not in queue and len(queue)<500: queue.append(href)
            emit("discovery_progress",{"pages":len(seen_pages),"products":len(product_urls),"queue":len(queue)})
        product_urls=product_urls[:MAX_PRODUCTS]
        emit("discovery_complete",{"pages":len(seen_pages),"products":len(product_urls)})
        q=asyncio.Queue()
        for i,u in enumerate(product_urls,1): q.put_nowait((i,u))
        rows=[]; lock=asyncio.Lock()
        async def worker(worker_id):
            wp=await context.new_page()
            while True:
                try: i,url=q.get_nowait()
                except asyncio.QueueEmpty: break
                try:
                    row=await extract_product(wp,url)
                    async with lock: rows.append(row)
                    emit("product_data",{"i":i,"total":len(product_urls),"worker":worker_id,**{k:row[k] for k in ["source_url","title","symbol","eans","numeric_stock_rows","generic_stock","prices_pln_detected"]},"images":row["images"][:12]})
                except Exception as exc:
                    emit("product_error",{"i":i,"worker":worker_id,"url":url,"error":f"{type(exc).__name__}: {exc}"})
                finally: q.task_done()
            await wp.close()
        await asyncio.gather(*[worker(i) for i in range(1,CONCURRENCY+1)])
        with open(OUTPUT,"w",encoding="utf-8") as fh:
            for row in rows: fh.write(json.dumps(row,ensure_ascii=False)+"\n")
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
