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

CATEGORY_ROOTS={
    "MEN": BASE_URL+"/produkty/produkty/mezczyzni/2-6",
    "WOMEN": BASE_URL+"/produkty/produkty/kobiety/2-5",
    "EQUIPMENT": BASE_URL+"/produkty/produkty/wyposazenie/2-8",
    "KIDS": BASE_URL+"/produkty/produkty/dzieci/2-7",
}

def emit(event,payload):
    print(json.dumps({"event":event,"ts":datetime.now(timezone.utc).isoformat(),**payload},ensure_ascii=False,separators=(",",":")),flush=True)

def same_host(url):
    return urlparse(url).netloc==urlparse(BASE_URL).netloc

def supplier_product_id(url):
    m=PRODUCT_ID_RE.search(urlparse(url).path.lower())
    return m.group(1) if m else ""

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
    for n in nums:
        if n != qty:
            return str(n)
    return None

def extract_links(base_url, html):
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        raw=(a.get("href") or "").strip()
        if not raw or raw.startswith(("#","javascript:","mailto:","tel:")):
            continue
        # Alpinus emits many root-relative-looking hrefs without a leading slash.
        # Resolve those from the site root, never from the current category path.
        if raw.startswith(("http://","https://","//")):
            href=urljoin(BASE_URL+"/",raw)
        else:
            href=urljoin(BASE_URL+"/",raw.lstrip("/"))
        if href and href not in out:
            out.append(href)
    return out

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

async def fetch_html(request_ctx,url,timeout=15000):
    last=None
    for attempt in range(1,4):
        try:
            resp=await request_ctx.get(url,timeout=timeout,fail_on_status_code=False)
            text=await resp.text()
            if resp.status==200 and len(text)>300:
                return text
            last=RuntimeError(f"HTTP {resp.status}, len={len(text)}")
        except Exception as exc:
            last=exc
        await asyncio.sleep(0.5*attempt)
    raise last or RuntimeError("Unknown HTTP fetch error")

async def fetch_product(request_ctx,url):
    html=await fetch_html(request_ctx,url,timeout=20000)
    return parse_product_html(url,html)

async def main():
    p=browser=context=None
    try:
        p,browser,context,page=await open_logged_in_page()
        request_ctx=context.request

        product_by_id={}
        product_categories={}
        category_stats={}
        total_pages=0

        for category,root in CATEGORY_ROOTS.items():
            seen_pages=set()
            queue=[root]
            raw_links=0
            category_products=set()

            while queue and total_pages<MAX_PAGES and len(product_by_id)<MAX_PRODUCTS:
                url=queue.pop(0)
                if url in seen_pages:
                    continue
                seen_pages.add(url)
                total_pages+=1
                try:
                    html=await fetch_html(request_ctx,url,timeout=15000)
                    links=extract_links(url,html)
                except Exception as exc:
                    emit("discovery_page_error",{"category":category,"url":url,"error":f"{type(exc).__name__}: {exc}"})
                    continue

                for href in links:
                    href=href.split("#")[0]
                    if not same_host(href):
                        continue
                    path=urlparse(href).path.lower()
                    pid=supplier_product_id(href)
                    if pid:
                        raw_links+=1
                        category_products.add(pid)
                        product_by_id.setdefault(pid,href)
                        product_categories.setdefault(pid,set()).add(category)
                    elif CATALOG_PAGE_RE.match(path.rstrip("/")):
                        clean=href.split("?")[0].rstrip("/")
                        if clean and clean not in seen_pages and clean not in queue and len(queue)<2500:
                            queue.append(clean)

                emit("category_discovery_progress",{
                    "category":category,
                    "category_pages":len(seen_pages),
                    "total_pages":total_pages,
                    "raw_product_links":raw_links,
                    "category_unique_products":len(category_products),
                    "union_unique_products":len(product_by_id),
                    "queue":len(queue)
                })

            category_stats[category]={
                "pages":len(seen_pages),
                "raw_product_links":raw_links,
                "unique_products":len(category_products)
            }
            emit("category_discovery_complete",{"category":category,**category_stats[category]})

        memberships={k:sorted(v) for k,v in product_categories.items()}
        category_counts={c:sum(1 for cats in memberships.values() if c in cats) for c in CATEGORY_ROOTS}
        overlap_counts={
            "multi_category_products":sum(1 for cats in memberships.values() if len(cats)>1),
            "single_category_products":sum(1 for cats in memberships.values() if len(cats)==1),
        }
        membership_sum=sum(category_counts.values())
        unique_union=len(product_by_id)

        emit("category_summary",{
            "category_counts":category_counts,
            "membership_sum":membership_sum,
            "unique_union":unique_union,
            "duplicate_memberships":membership_sum-unique_union,
            "overlap_counts":overlap_counts,
            "category_stats":category_stats
        })

        product_urls=list(product_by_id.values())[:MAX_PRODUCTS]
        emit("discovery_complete",{
            "pages":total_pages,
            "unique_products":len(product_urls),
            "category_counts":category_counts,
            "membership_sum":membership_sum,
            "duplicates_across_categories":membership_sum-len(product_urls)
        })

        q=asyncio.Queue()
        for i,u in enumerate(product_urls,1):
            q.put_nowait((i,u))
        rows=[]; lock=asyncio.Lock()

        async def worker(worker_id):
            while True:
                try: i,url=q.get_nowait()
                except asyncio.QueueEmpty: break
                try:
                    row=await fetch_product(request_ctx,url)
                    pid=row["supplier_product_id"]
                    row["categories"]=memberships.get(pid,[])
                    async with lock: rows.append(row)
                    emit("product_data",{
                        "i":i,"total":len(product_urls),"worker":worker_id,
                        "supplier_product_id":pid,
                        "categories":row["categories"],
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
        emit("crawl_summary",{
            "ok":True,
            "products_discovered":len(product_urls),
            "rows":len(rows),
            "category_counts":category_counts,
            "membership_sum":membership_sum,
            "audit":audit,
            "output":OUTPUT
        })
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if p: await p.stop()

if __name__=="__main__":
    asyncio.run(main())
