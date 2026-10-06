import asyncio, json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from app import BASE_URL, open_logged_in_page

MAX_PRODUCTS=min(50,int(os.getenv("ALPINUS_MAX_PRODUCTS","50")))
START_INDEX=int(os.getenv("ALPINUS_START_INDEX","0"))
if MAX_PRODUCTS < 1 or START_INDEX < 0:
    raise ValueError("ALPINUS_MAX_PRODUCTS must be 1..50 and ALPINUS_START_INDEX >= 0")
MAX_PAGES=int(os.getenv("ALPINUS_MAX_PAGES","300"))
CONCURRENCY=int(os.getenv("ALPINUS_CONCURRENCY","6"))
OUTPUT=os.getenv("ALPINUS_OUTPUT_JSONL",f"/tmp/alpinus_catalog_batch_{START_INDEX:04d}.jsonl")

PRODUCT_ID_RE=re.compile(r"/3-\d+-(\d+)$")
CATALOG_PAGE_RE=re.compile(r"^/produkty/produkty/(?:[^/?#]+/)*2-\d+$", re.I)
TEXT_SIZE_RE=re.compile(r"\b(2XL|3XL|4XL|XL|XS|S|M|L)\b",re.I)
RANGE_SIZE_RE=re.compile(r"\b(3[0-9]|4[0-9]|50)\s*[-/]\s*(3[0-9]|4[0-9]|50)\b")
NUM_SIZE_RE=re.compile(r"\b(3[4-9]|4[0-9]|50)\b")

CATEGORY_ROOTS={
    "MEN": BASE_URL+"/produkty/produkty/mezczyzni/2-6",
    "WOMEN": BASE_URL+"/produkty/produkty/kobiety/2-5",
    "EQUIPMENT": BASE_URL+"/produkty/produkty/wyposazenie/2-8",
    "KIDS": BASE_URL+"/produkty/produkty/dzieci/2-7",
}
CATEGORY_GROUP_IDS={"MEN":"6","WOMEN":"5","EQUIPMENT":"8","KIDS":"7"}

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
    def parse_pln_from_node(node):
        if not node:
            return None
        txt=node.get_text(" ",strip=True)
        m=re.search(r"(\d[\d\s]*[\.,]\d{2})\s*PLN",txt,re.I)
        if not m:
            return None
        return m.group(1).replace(" ","").replace(",", ".")

    rrp_pln=None
    for node in soup.select(".brutto-previous-lq"):
        txt=node.get_text(" ",strip=True).lower()
        if "sugerowana" in txt or node.select_one(".suger-mob") or "suger-mob" in (node.get("class") or []):
            rrp_pln=parse_pln_from_node(node)
            if rrp_pln:
                break
    if not rrp_pln:
        for node in soup.select(".suger-mob"):
            rrp_pln=parse_pln_from_node(node)
            if rrp_pln:
                break

    net_cost_pln=None
    for sel in [".netto-ui.netto-lq",".netto-price-ui",".netto-ui"]:
        for node in soup.select(sel):
            txt=node.get_text(" ",strip=True).lower()
            if "netto" in txt:
                net_cost_pln=parse_pln_from_node(node)
                if net_cost_pln:
                    break
        if net_cost_pln:
            break

    gross_b2b_pln=None
    for sel in [".brutto-ui.brutto-lq",".brutto-price-ui",".brutto-ui"]:
        for node in soup.select(sel):
            txt=node.get_text(" ",strip=True).lower()
            if "brutto" in txt and "sugerowana" not in txt:
                gross_b2b_pln=parse_pln_from_node(node)
                if gross_b2b_pln:
                    break
        if gross_b2b_pln:
            break
    # Verified supplier content blocks (authenticated product page).
    description_node=soup.select_one(".product-description-ui.product-description-lq")
    description_text=""
    description_html=""
    if description_node:
        description_text=re.sub(r"\\s+"," ",description_node.get_text(" ",strip=True)).strip()
        description_html=str(description_node)

    attributes=[]
    attributes_node=soup.select_one(".product-attributes-ui.product-attributes-js")
    if attributes_node:
        # Parse label/value pairs conservatively from table-like rows.
        for row in attributes_node.select("tr, .table-row-ui, .attribute-row-ui, li"):
            cells=[re.sub(r"\\s+"," ",x.get_text(" ",strip=True)).strip() for x in row.select("th,td,.name-ui,.value-ui,.attribute-name-ui,.attribute-value-ui")]
            cells=[x for x in cells if x]
            if len(cells)>=2:
                label=cells[0]
                value=" ".join(cells[1:])
                pair={"label":label,"value":value}
                if pair not in attributes:
                    attributes.append(pair)
        # Fallback: preserve clean text if markup is not table-like.
        if not attributes:
            txt=re.sub(r"\\s+"," ",attributes_node.get_text(" | ",strip=True)).strip()
            if txt:
                attributes=[{"label":"raw","value":txt}]

    images=[]
    gallery_imgs=soup.select("img.open-gallery-lq")
    for img in gallery_imgs:
        src=normalize_image(img.get("src") or img.get("data-src") or img.get("data-original"))
        if src and src not in images:
            images.append(src)
    # Fallback for pages whose gallery class is missing in raw HTML.
    if not images:
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

    variant_rows=[]
    row_selector=".attribute-button-ui.table-row-ui, .attribute-button-ui .table-row-ui"
    for row in soup.select(row_selector):
        row_text=row.get_text(" ",strip=True)
        qty=None
        for el in row.select("[data-stock-value], [data-max], input[max]"):
            raw=el.get("data-stock-value") or el.get("data-max") or el.get("max")
            if raw and str(raw).isdigit():
                qty=int(raw)
                break
        size=detect_size(row_text,qty if qty is not None else -1)
        row_eans=sorted(set(re.findall(r"\b\d{13}\b",row_text)))
        if size or qty is not None or row_eans:
            variant_rows.append({
                "size":size,
                "qty":qty,
                "eans":row_eans,
                "ean_mapping_safe": bool(size and qty is not None and len(row_eans)==1)
            })

    return {
        "supplier_product_id":supplier_product_id(url),
        "source_url":url,
        "title":title,
        "symbol":symbol,
        "eans":eans,
        "numeric_stock_rows":size_rows,
        "variant_rows":variant_rows,
        "variant_ean_mapping_safe": bool(variant_rows) and all(r["ean_mapping_safe"] for r in variant_rows if r.get("size")),
        "generic_stock":max(generic) if generic else None,
        "rrp_pln":rrp_pln,
        "b2b_gross_pln":gross_b2b_pln,
        "net_cost_pln":net_cost_pln,
        "description_text":description_text,
        "description_html":description_html,
        "attributes":attributes,
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

        # Deterministic branch discovery using only each top-level branch listing.
        # Alpinus product links in raw HTTP may encode a deeper category id (/3-51-ID etc.),
        # so membership is determined by presence on the branch's own paginated listing.
        for category,root in CATEGORY_ROOTS.items():
            category_products=set()
            raw_links=0
            pages_seen=0

            for page_num in range(1,31):
                if total_pages>=MAX_PAGES:
                    break
                page_url=root if page_num==1 else f"{root}?pageId={page_num}"
                total_pages+=1
                pages_seen+=1
                try:
                    html=await fetch_html(request_ctx,page_url,timeout=15000)
                    links=extract_links(page_url,html)
                except Exception as exc:
                    emit("discovery_page_error",{"category":category,"page":page_num,"url":page_url,"error":f"{type(exc).__name__}: {exc}"})
                    break

                page_ids=set()
                page_urls={}
                for href in links:
                    if not same_host(href):
                        continue
                    pid=supplier_product_id(href.split("?")[0].rstrip("/"))
                    if not pid:
                        continue
                    page_ids.add(pid)
                    page_urls.setdefault(pid,href.split("?")[0])

                new_ids=page_ids-category_products
                raw_links+=len(page_ids)

                # A page that contributes no new products means we passed the end
                # (or the server repeated the previous/first page).
                if page_num>1 and not new_ids:
                    pages_seen-=1
                    break

                for pid in new_ids:
                    category_products.add(pid)
                    product_by_id.setdefault(pid,page_urls[pid])
                    product_categories.setdefault(pid,set()).add(category)

                emit("category_discovery_progress",{
                    "category":category,
                    "page":page_num,
                    "page_products":len(page_ids),
                    "new_products":len(new_ids),
                    "category_unique_products":len(category_products),
                    "union_unique_products":len(product_by_id)
                })

                # Listings use 20 products/page; a short non-empty page is final.
                if page_ids and len(page_ids)<20:
                    break
                if not page_ids:
                    break

            category_stats[category]={
                "pages":pages_seen,
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

        all_product_urls=sorted(product_by_id.values(), key=lambda u: int(supplier_product_id(u)))
        product_urls=all_product_urls[START_INDEX:START_INDEX+MAX_PRODUCTS]
        emit("discovery_complete",{
            "pages":total_pages,
            "unique_products":len(all_product_urls),
            "batch_start_index":START_INDEX,
            "batch_size":len(product_urls),
            "batch_end_index_exclusive":START_INDEX+len(product_urls),
            "category_counts":category_counts,
            "membership_sum":membership_sum,
            "duplicates_across_categories":membership_sum-len(all_product_urls)
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
                        "variant_rows":row["variant_rows"],"variant_ean_mapping_safe":row["variant_ean_mapping_safe"],
                        "generic_stock":row["generic_stock"],"rrp_pln":row["rrp_pln"],
                        "b2b_gross_pln":row["b2b_gross_pln"],"net_cost_pln":row["net_cost_pln"],
                        "description_text":row["description_text"],"attributes":row["attributes"],
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
            "with_rrp":sum(1 for r in rows if r["rrp_pln"]),
            "with_net_cost":sum(1 for r in rows if r["net_cost_pln"]),
            "with_description":sum(1 for r in rows if r["description_text"]),
            "with_attributes":sum(1 for r in rows if r["attributes"]),
            "with_safe_variant_ean_mapping":sum(1 for r in rows if r["variant_ean_mapping_safe"])
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
