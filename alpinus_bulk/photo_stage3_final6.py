"""Exceptional final recovery for six remaining Alpinus products.
Prefers official Alpinus B2B/retail sources; no Shopify writes.
"""
import asyncio, hashlib, json, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from app import open_logged_in_page
from photo_gallery import extract_image_urls

ITEMS = [
 {"catalog_index":1,"supplier_product_id":"1204","sku":"SU11922","b2b":"https://alpinusgroup.com/kurtka-meska-softshell-alpinus-arbent-su11922/3-6-1204","official_public":["https://www.alpinus.eu/kurtka-meska-softshell-alpinus-arbent,3,3594,131404"]},
 {"catalog_index":60,"supplier_product_id":"1035","sku":"FP11898","b2b":"https://alpinusgroup.com/koszulka-meska-alpinus-kitreli-fp11904/3-6-1035","official_public":["https://www.alpinus.eu/koszulka-meska-alpinus-kitreli,3,2965,131396"]},
 {"catalog_index":61,"supplier_product_id":"1008","sku":"BR11959","b2b":"https://alpinusgroup.com/kurtka-meska-softshell-alpinus-stenshuvud-br43371/3-6-1008","official_public":["https://www.alpinus.eu/en/men-s-softshell-jacket-alpinus-stenshuvud,3,3621,131352"]},
 {"catalog_index":62,"supplier_product_id":"990","sku":"YT11537","b2b":"https://alpinusgroup.com/kurtka-meska-puchowa-alpinus-monviso-yt11537/3-6-990","official_public":[]},
 {"catalog_index":308,"supplier_product_id":"1189","sku":"PO35500","b2b":"https://alpinusgroup.com/plecak-alpinus-retba-30-po35500/3-8-1189","official_public":[]},
 {"catalog_index":396,"supplier_product_id":"669","sku":"AC18953","b2b":"https://alpinusgroup.com/spiwor-alpinus-warm-1200-180x75cm-granatowy-ac1895/3-8-669","official_public":[]},
]

IMG_RE=re.compile(r'''(?:"|')([^"'<>\s]+?(?:/img/[^"'<>\s]+|\.(?:jpe?g|png|webp|avif)(?:\?[^"'<>\s]*)?))(?:"|')''',re.I)

def emit(event, **v):
    print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)

def ok(data):
    return len(data)>=1500 and (data.startswith(bytes.fromhex("ffd8ff")) or data.startswith(bytes.fromhex("89504e470d0a1a0a")) or (data.startswith(b"RIFF") and data[8:12]==b"WEBP"))

def collect(html,page):
    out=[];seen=set()
    def add(u,kind):
        if not u:return
        u=urljoin(page,u.strip())
        if u in seen:return
        if not urlparse(u).scheme:return
        seen.add(u);out.append((u,kind))
        m=re.search(r"/img/(?:small/)?(\d+)(?:/[^?#]*)?",u,re.I)
        if m:
            p=urljoin(u,f"/img/{m.group(1)}/product.jpg")
            if p not in seen:seen.add(p);out.append((p,"parent_product_jpg"))
    for u in extract_image_urls(html,page,120):add(u,"extractor")
    soup=BeautifulSoup(html,"html.parser")
    for sel,attr,kind in [('meta[property="og:image"]',"content","og"),('meta[name="twitter:image"]',"content","twitter"),('link[rel="image_src"]',"href","image_src")]:
        for el in soup.select(sel):add(el.get(attr),kind)
    for el in soup.select("img,source,a[href]"):
        for attr in ("src","data-src","data-original","data-large","data-full","data-zoom-image","href"):
            add(el.get(attr),"dom")
        for attr in ("srcset","data-srcset"):
            for part in (el.get(attr) or "").split(","):
                if part.strip():add(part.strip().split()[0],"srcset")
    for m in IMG_RE.finditer(html):add(m.group(1),"raw")
    return out

async def main():
    pw=browser=context=None
    try:
        pw,browser,context,_=await open_logged_in_page()
        request=context.request
        results=[]
        for p in ITEMS:
            urls=[("b2b",p["b2b"])]+[("official_public",u) for u in p["official_public"]]
            cand=[];seen=set()
            for source,page in urls:
                try:
                    res=await request.get(page,timeout=30000)
                    html=await res.text()
                    emit("final6_page",supplier_product_id=p["supplier_product_id"],sku=p["sku"],source=source,status=res.status,page=page)
                    for u,k in collect(html,page):
                        if u not in seen:seen.add(u);cand.append((u,f"{source}:{k}"))
                except Exception as ex:
                    emit("final6_page_error",supplier_product_id=p["supplier_product_id"],sku=p["sku"],source=source,error=str(ex))
            verified=[]
            for u,k in cand:
                try:
                    res=await request.get(u,timeout=25000)
                    data=await res.body() if res.status==200 else b""
                    if res.status==200 and ok(data):
                        rec={"url":u,"kind":k,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
                        if rec["sha256"] not in {x["sha256"] for x in verified}:
                            verified.append(rec)
                            emit("final6_asset_verified",supplier_product_id=p["supplier_product_id"],sku=p["sku"],catalog_index=p["catalog_index"],**rec)
                except Exception:
                    pass
            best=max(verified,key=lambda x:x["bytes"],default=None)
            emit("final6_product_done",supplier_product_id=p["supplier_product_id"],sku=p["sku"],catalog_index=p["catalog_index"],verified_assets=len(verified),candidate_count=len(cand),best=best,max_bytes=max([x["bytes"] for x in verified],default=0))
            results.append((p,verified))
        emit("final6_summary",processed=6,recovered=sum(bool(v) for _,v in results),still_missing=sum(not v for _,v in results),verified_assets=sum(len(v) for _,v in results))
    finally:
        if context:await context.close()
        if browser:await browser.close()
        if pw:await pw.stop()

if __name__=="__main__":
    asyncio.run(main())
