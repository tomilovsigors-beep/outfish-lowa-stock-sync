"""Stage4 diagnostic: inspect real authenticated variant markup for first 3 products only."""
import asyncio, json, re
from pathlib import Path
from app import open_logged_in_page
from bs4 import BeautifulSoup

ITEMS=json.loads(Path("alpinus_bulk/stage4_variants_batch_001_selection.json").read_text(encoding="utf-8"))[:3]
def emit(event,**v): print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)
async def main():
 pw=browser=context=None
 try:
  pw,browser,context,_=await open_logged_in_page()
  req=context.request
  for p in ITEMS:
   r=await req.get(p["url"],timeout=30000);html=await r.text();soup=BeautifulSoup(html,"html.parser")
   nodes=[]
   sels=[".attribute-button-ui",".table-row-ui","[data-stock-value]","[data-max]","input[max]","option","select","[data-ean]","[data-barcode]","[data-gtin]"]
   seen=set()
   for sel in sels:
    for n in soup.select(sel):
     key=str(n)[:8000]
     if key in seen:continue
     seen.add(key)
     txt=re.sub(r"\s+"," ",n.get_text(" ",strip=True))
     attrs={k:v for k,v in n.attrs.items()}
     if re.search(r"\b\d{13}\b",key) or "stock" in key.lower() or "max=" in key.lower() or txt:
      nodes.append({"selector":sel,"tag":n.name,"attrs":attrs,"text":txt[:600],"html":key[:1800]})
   # EAN local snippets from raw HTML.
   snippets=[]
   for m in re.finditer(r"\b\d{13}\b",html):
    snippets.append(re.sub(r"\s+"," ",html[max(0,m.start()-350):min(len(html),m.end()+350)])[:900])
    if len(snippets)>=12:break
   emit("stage4_diag_product",catalog_index=p["catalog_index"],sku=p["sku"],nodes=nodes[:80],ean_snippets=snippets)
 finally:
  if context:await context.close()
  if browser:await browser.close()
  if pw:await pw.stop()
if __name__=="__main__":asyncio.run(main())
