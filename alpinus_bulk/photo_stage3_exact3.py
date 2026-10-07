"""Strict official Alpinus recovery for 3 exact remaining SKUs.
Only accepts image URLs containing exact SKU or model token. No Shopify writes.
"""
import asyncio, hashlib, json, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app import open_logged_in_page

ITEMS=[
 {"catalog_index":1,"supplier_product_id":"1204","sku":"SU11922","page":"https://www.alpinus.eu/kurtka-meska-softshell-alpinus-arbent,3,3594,131404","tokens":["su11922","arbent"]},
 {"catalog_index":60,"supplier_product_id":"1035","sku":"FP11898","page":"https://www.alpinus.eu/koszulka-meska-alpinus-kitreli,3,2965,131396","tokens":["fp11898","fp11904","kitreli"]},
 {"catalog_index":61,"supplier_product_id":"1008","sku":"BR11959","page":"https://www.alpinus.eu/en/men-s-softshell-jacket-alpinus-stenshuvud,3,3621,131352","tokens":["br11959","stenshuvud"]},
]

def emit(event,**v):
 print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)

def valid(data):
 return len(data)>=1500 and (data.startswith(bytes.fromhex("ffd8ff")) or data.startswith(bytes.fromhex("89504e470d0a1a0a")) or (data.startswith(b"RIFF") and data[8:12]==b"WEBP"))

def collect(html,page,tokens):
 soup=BeautifulSoup(html,"html.parser")
 urls=[];seen=set()
 def add(raw,kind):
  if not raw:return
  u=urljoin(page,raw.strip())
  low=u.lower()
  if not any(t in low for t in tokens):return
  if u in seen:return
  seen.add(u);urls.append((u,kind))
 for el in soup.select("img,source,a[href],meta[property='og:image'],meta[name='twitter:image'],link[rel='image_src']"):
  for attr in ("src","data-src","data-original","data-large","data-full","data-zoom-image","href","content"):
   add(el.get(attr),"dom")
  for attr in ("srcset","data-srcset"):
   for part in (el.get(attr) or "").split(","):
    if part.strip():add(part.strip().split()[0],"srcset")
 # raw quoted image-like URLs, still token-gated
 pat=re.compile(r'''(?:"|')([^"'<>\s]+)(?:"|')''')
 for m in pat.finditer(html):
  raw=m.group(1)
  if any(t in raw.lower() for t in tokens) and ("/img/" in raw.lower() or re.search(r"\.(?:jpe?g|png|webp|avif)(?:$|[?#])",raw,re.I)):
   add(raw,"raw")
 return urls

async def main():
 pw=browser=context=None
 try:
  pw,browser,context,_=await open_logged_in_page()
  request=context.request
  results=[]
  for p in ITEMS:
   res=await request.get(p["page"],timeout=30000)
   html=await res.text()
   emit("exact3_page",sku=p["sku"],supplier_product_id=p["supplier_product_id"],status=res.status,page=p["page"])
   cand=collect(html,p["page"],p["tokens"])
   verified=[];hashes=set()
   for u,k in cand:
    try:
     ir=await request.get(u,timeout=25000)
     data=await ir.body() if ir.status==200 else b""
     if ir.status==200 and valid(data):
      h=hashlib.sha256(data).hexdigest()
      if h not in hashes:
       hashes.add(h)
       rec={"url":u,"kind":k,"bytes":len(data),"sha256":h}
       verified.append(rec)
       emit("exact3_asset_verified",supplier_product_id=p["supplier_product_id"],sku=p["sku"],catalog_index=p["catalog_index"],**rec)
    except Exception:
     pass
   best=max(verified,key=lambda x:x["bytes"],default=None)
   emit("exact3_product_done",supplier_product_id=p["supplier_product_id"],sku=p["sku"],catalog_index=p["catalog_index"],candidates=len(cand),verified_assets=len(verified),best=best,max_bytes=max([x["bytes"] for x in verified],default=0))
   results.append(verified)
  emit("exact3_summary",processed=3,recovered=sum(bool(x) for x in results),still_missing=sum(not x for x in results),verified_assets=sum(len(x) for x in results))
 finally:
  if context:await context.close()
  if browser:await browser.close()
  if pw:await pw.stop()

if __name__=="__main__":
 asyncio.run(main())
