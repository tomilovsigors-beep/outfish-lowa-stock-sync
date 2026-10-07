"""Stage4 diagnostic: follow each explicit variant data-url and inspect variant-specific EANs."""
import asyncio, json, re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app import BASE_URL, open_logged_in_page
ITEMS=json.loads(Path("alpinus_bulk/stage4_variants_batch_001_selection.json").read_text(encoding="utf-8"))[:3]
EAN=re.compile(r"\b\d{13}\b")
def emit(event,**v): print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)
async def main():
 pw=browser=context=None
 try:
  pw,browser,context,_=await open_logged_in_page();req=context.request
  for p in ITEMS:
   r=await req.get(p["url"],timeout=30000);html=await r.text();s=BeautifulSoup(html,"html.parser")
   rows=s.select(".attribute-button-ui.last-lvl-ui.table-row-ui")
   out=[]
   for row in rows:
    size=(row.select_one(".name-column-ui.supply-value-lq") or row.select_one(".name-column-ui"))
    size=size.get_text(" ",strip=True) if size else ""
    q=row.select_one("[data-stock-value]")
    qty=int(q.get("data-stock-value")) if q and str(q.get("data-stock-value","")).isdigit() else None
    vurl=urljoin(BASE_URL+"/", (row.get("data-url") or "").lstrip("/"))
    vr=await req.get(vurl,timeout=30000);vhtml=await vr.text();vs=BeautifulSoup(vhtml,"html.parser")
    body=vs.get_text(" ",strip=True)
    eans=sorted(set(EAN.findall(body)))
    attrs={}
    for n in vs.select(".product-attributes-ui tr,.product-attributes-ui .table-row-ui,.product-attributes-ui li"):
      txt=re.sub(r"\s+"," ",n.get_text(" ",strip=True))
      if "EAN" in txt.upper() or "SYMBOL" in txt.upper():
        attrs[str(len(attrs))]=txt[:500]
    out.append({"size":size,"qty":qty,"supply_id":row.get("data-supply-id"),"variant_url":vurl,"eans":eans,"attr_snippets":attrs})
   emit("stage4_variant_url_diag",sku=p["sku"],catalog_index=p["catalog_index"],variant_count=len(out),variants=out)
 finally:
  if context:await context.close()
  if browser:await browser.close()
  if pw:await pw.stop()
if __name__=="__main__":asyncio.run(main())
