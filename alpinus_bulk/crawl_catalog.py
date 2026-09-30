import asyncio, json, os, re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from app import BASE_URL, open_logged_in_page

MAX_PRODUCTS=int(os.getenv("ALPINUS_MAX_PRODUCTS","600"))
MAX_PAGES=int(os.getenv("ALPINUS_MAX_PAGES","120"))
OUTPUT=os.getenv("ALPINUS_OUTPUT_JSONL","/tmp/alpinus_catalog.jsonl")

def emit(event,payload):
    print(json.dumps({"event":event,"ts":datetime.now(timezone.utc).isoformat(),**payload},ensure_ascii=False,separators=(",",":")),flush=True)

def same_host(url):
    return urlparse(url).netloc==urlparse(BASE_URL).netloc

async def extract_product(page,url):
    await page.goto(url,wait_until="domcontentloaded",timeout=60000)
    try:
        await page.wait_for_load_state("networkidle",timeout=10000)
    except Exception:
        pass
    data=await page.evaluate("""() => {
      const clean=v=>(v||'').replace(/\s+/g,' ').trim();
      const title=clean(document.querySelector('h1')?.innerText||document.title);
      const body=clean(document.body?.innerText||'');
      const imgs=[...new Set([...document.querySelectorAll('img[src]')].map(i=>i.currentSrc||i.src).filter(Boolean))];
      const rows=[...document.querySelectorAll('[data-stock-value], [data-max], input[max]')].map(el=>({
        tag:el.tagName,
        text:clean(el.innerText||el.parentElement?.innerText||'').slice(0,500),
        stock:el.getAttribute('data-stock-value'),
        dataMax:el.getAttribute('data-max'),
        max:el.getAttribute('max'),
        value:el.getAttribute('value'),
        name:el.getAttribute('name'),
        id:el.id||''
      }));
      const attrs=[...document.querySelectorAll('*')].map(el=>{
        const o={}; for (const a of el.attributes||[]) if (/ean|gtin|stock|price|netto|size|variant|supply|symbol|code/i.test(a.name)) o[a.name]=a.value;
        return Object.keys(o).length?{tag:el.tagName,attrs:o,text:clean(el.innerText||'').slice(0,300)}:null;
      }).filter(Boolean).slice(0,250);
      const links=[...document.querySelectorAll('a[href]')].map(a=>({text:clean(a.innerText),href:a.href})).filter(x=>x.text&&x.href);
      return {title,body:body.slice(0,25000),imgs:imgs.slice(0,80),rows,attrs,links:links.slice(0,120)};
    }""")
    low=data["body"].lower()
    symbol=""
    for pat in [r"symbol\s*[:\-]?\s*([a-z0-9\-]+)",r"kod producenta\s*[:\-]?\s*([a-z0-9\-]+)"]:
        m=re.search(pat,low,re.I)
        if m:
            symbol=m.group(1).upper(); break
    eans=sorted(set(re.findall(r"\b\d{13}\b",data["body"])))
    prices=re.findall(r"(\d+[\.,]\d{2})\s*PLN",data["body"],re.I)
    sizes=[]
    for el in data["rows"]:
        txt=el.get("text") or ""
        m=re.search(r"\b(2XL|3XL|4XL|XL|XS|S|M|L|\d{2}(?:-\d{2})?)\b",txt,re.I)
        qty=el.get("stock") or el.get("dataMax") or el.get("max")
        if m and qty and str(qty).isdigit():
            sizes.append({"size":m.group(1).upper(),"qty":int(qty)})
    return {
      "source_url":url,"title":data["title"],"symbol":symbol,"eans":eans,
      "numeric_stock_rows":sizes,"prices_pln_detected":prices[:20],
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
            await page.goto(url,wait_until="domcontentloaded",timeout=60000)
            try: await page.wait_for_load_state("networkidle",timeout=8000)
            except Exception: pass
            links=await page.locator("a[href]").evaluate_all("""els=>els.map(a=>a.href).filter(Boolean)""")
            for href in links:
                href=href.split("#")[0]
                if not same_host(href): continue
                path=urlparse(href).path.lower()
                if re.search(r"/3-\d+-\d+$",path):
                    if href not in product_urls: product_urls.append(href)
                elif any(k in path for k in ["/but","/odzie","/biel","/spod","/kurt","/plecak","/akces","/skarp","/produkt"]):
                    if href not in seen_pages and href not in queue and len(queue)<300: queue.append(href)
            emit("discovery_progress",{"pages":len(seen_pages),"products":len(product_urls),"queue":len(queue)})
        rows=[]
        for i,url in enumerate(product_urls[:MAX_PRODUCTS],1):
            try:
                row=await extract_product(page,url); rows.append(row)
                emit("product",{"i":i,"total":len(product_urls[:MAX_PRODUCTS]),"url":url,"title":row["title"],"stock_rows":len(row["numeric_stock_rows"])})
            except Exception as exc:
                emit("product_error",{"i":i,"url":url,"error":f"{type(exc).__name__}: {exc}"})
        with open(OUTPUT,"w",encoding="utf-8") as fh:
            for row in rows: fh.write(json.dumps(row,ensure_ascii=False)+"\n")
        emit("crawl_summary",{"ok":True,"products_discovered":len(product_urls),"rows":len(rows),"output":OUTPUT})
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if p: await p.stop()

if __name__=="__main__":
    asyncio.run(main())
