"""Final remediation for 25 deferred Alpinus photo cases.
Authenticated Render only. No Shopify writes.
Searches broader HTML sources plus probable larger variants of supplier thumbnails.
"""
import asyncio, hashlib, json, os, re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from app import open_logged_in_page
from photo_gallery import extract_image_urls

SELECTED=json.loads(Path("alpinus_bulk/photo_stage3_remediation_25_selection.json").read_text(encoding="utf-8"))
DEST=Path("/tmp/alpinus_stage3_remediation_25")
MAX_CONCURRENT=4

IMG_RE=re.compile(r'''(?:"|')([^"'<>\s]+?\.(?:jpe?g|png|webp|avif)(?:\?[^"'<>\s]*)?)(?:"|')''',re.I)

def emit(event, **v):
    print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)

def valid_magic(data):
    return (data.startswith(bytes.fromhex("ffd8ff")) or data.startswith(bytes.fromhex("89504e470d0a1a0a")) or
            (data.startswith(b"RIFF") and data[8:12]==b"WEBP") or
            (len(data)>12 and data[4:12] in (b"ftypavif",b"ftypavis")))

def ext(data):
    if data.startswith(bytes.fromhex("ffd8")): return ".jpg"
    if data.startswith(bytes.fromhex("89504e47")): return ".png"
    if data.startswith(b"RIFF"): return ".webp"
    return ".avif"

def candidates(html,page_url):
    out=[]; seen=set()
    def add(u,kind):
        if not u: return
        u=urljoin(page_url,u.strip())
        p=urlparse(u)
        if p.scheme not in ("http","https") or not p.netloc: return
        if not re.search(r"\.(?:jpe?g|png|webp|avif)(?:$|[?#])",p.path,re.I): return
        if any(x in p.path.lower() for x in ("logo","favicon","icon","sprite","payment","flag")): return
        key=u
        if key not in seen:
            seen.add(key);out.append((u,kind))
    for u in extract_image_urls(html,page_url,80): add(u,"gallery")
    soup=BeautifulSoup(html,"html.parser")
    for sel,attr,kind in [
        ('meta[property="og:image"]',"content","og"),
        ('meta[name="twitter:image"]',"content","twitter"),
        ('link[rel="image_src"]',"href","image_src"),
        ('[style*="background-image"]',"style","background"),
    ]:
        for el in soup.select(sel):
            val=el.get(attr)
            if attr=="style" and val:
                m=re.search(r'url\((["\']?)(.*?)\1\)',val,re.I)
                val=m.group(2) if m else None
            add(val,kind)
    for m in IMG_RE.finditer(html):
        add(m.group(1),"raw_html")
    base=list(out)
    for u,kind in base:
        variants=[]
        if "/img/small/" in u:
            variants += [
                u.replace("/img/small/","/img/"),
                u.replace("/img/small/","/img/large/"),
                u.replace("/img/small/","/img/big/"),
                u.replace("/img/small/","/img/original/"),
            ]
        for v in variants: add(v,"derived_large")
    return out

async def main():
    if len(SELECTED)!=25 or len({x["supplier_product_id"] for x in SELECTED})!=25:
        raise RuntimeError("Expected exactly 25 unique remediation products")
    pw=browser=context=None
    try:
        pw,browser,context,_=await open_logged_in_page()
        request=context.request
        DEST.mkdir(parents=True,exist_ok=True)
        sem=asyncio.Semaphore(MAX_CONCURRENT)
        async def one(p):
            async with sem:
                pid=str(p["supplier_product_id"]);sku=p["sku"];url=p["url"]
                try:
                    res=await request.get(url,timeout=30000)
                    html=await res.text()
                    if res.status!=200 or "Dostęp tylko dla zalogowanych kontrahentów" in html:
                        raise RuntimeError(f"product_http_or_auth_{res.status}")
                    cand=candidates(html,url)
                    saved=[]; tried=[]
                    for image_url,kind in cand:
                        try:
                            ir=await request.get(image_url,timeout=25000)
                            data=await ir.body() if ir.status==200 else b""
                            tried.append({"url":image_url,"kind":kind,"status":ir.status,"bytes":len(data)})
                            if ir.status!=200 or len(data)<1500 or not valid_magic(data):
                                continue
                            folder=DEST/pid;folder.mkdir(parents=True,exist_ok=True)
                            path=folder/(f"{len(saved)+1:02d}"+ext(data));path.write_bytes(data)
                            rec={"url":image_url,"kind":kind,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
                            saved.append(rec)
                            emit("remediation_asset_verified",supplier_product_id=pid,sku=sku,catalog_index=p["catalog_index"],**rec)
                            if kind=="derived_large" and len(data)>=12000:
                                break
                        except Exception as ex:
                            tried.append({"url":image_url,"kind":kind,"error":f"{type(ex).__name__}:{ex}"})
                    best=max(saved,key=lambda x:x["bytes"],default=None)
                    emit("remediation_product_done",supplier_product_id=pid,sku=sku,catalog_index=p["catalog_index"],
                         candidates=len(cand),verified_assets=len(saved),best=best,
                         max_verified_bytes=max([x["bytes"] for x in saved],default=0),
                         tried_count=len(tried))
                    return {"id":pid,"saved":len(saved),"best":best}
                except Exception as ex:
                    emit("remediation_product_error",supplier_product_id=pid,sku=sku,catalog_index=p["catalog_index"],error=f"{type(ex).__name__}: {ex}")
                    return {"id":pid,"saved":0,"error":str(ex)}
        results=await asyncio.gather(*(one(p) for p in SELECTED))
        emit("remediation_summary",processed=len(results),products_recovered=sum(r["saved"]>0 for r in results),
             products_still_missing=sum(r["saved"]==0 for r in results),
             verified_assets=sum(r["saved"] for r in results))
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()

if __name__=="__main__":
    asyncio.run(main())
