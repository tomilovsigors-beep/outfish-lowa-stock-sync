"""Alpinus stage 4 batch 006: exact variant structure collector.
Authenticated supplier read-only. Captures exact size, current stock, supply ID and product EAN pool.
Never guesses multi-variant size->EAN mapping. Never writes Shopify.
"""
import asyncio, json, re
from pathlib import Path
from bs4 import BeautifulSoup
from app import open_logged_in_page

SELECTED=json.loads(Path("alpinus_bulk/stage4_variants_batch_006_selection.json").read_text(encoding="utf-8"))
EAN_RE=re.compile(r"\b\d{13}\b")
WEARABLE_RE=re.compile(r"\b(kurtka|koszulka|spodnie|buty|sandały|sandaly|bluza|płaszcz|plaszcz|bielizna|rękawiczki|rekawiczki|polar|szorty)\b",re.I)

def emit(event,**v):
    print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)

def ean_sequence(soup):
    # Preserve supplier display order from the 'Kod EAN' attribute, never sort.
    attr=soup.select_one(".product-attributes-ui.product-attributes-js")
    if attr:
        for row in attr.select("tr,.table-row-ui,.attribute-row-ui,li"):
            txt=re.sub(r"\s+"," ",row.get_text(" ",strip=True))
            if "EAN" in txt.upper():
                vals=[]
                for e in EAN_RE.findall(txt):
                    if e not in vals: vals.append(e)
                if vals:return vals
    vals=[]
    for e in EAN_RE.findall(soup.get_text(" ",strip=True)):
        if e not in vals:vals.append(e)
    return vals

def variant_rows(soup):
    out=[]
    seen=set()
    for row in soup.select(".attribute-button-ui.last-lvl-ui.table-row-ui"):
        size_el=row.select_one(".name-column-ui.supply-value-lq") or row.select_one(".name-column-ui")
        size=re.sub(r"\s+"," ",size_el.get_text(" ",strip=True)).strip() if size_el else ""
        stock_el=row.select_one("[data-stock-value]")
        raw=stock_el.get("data-stock-value") if stock_el else None
        qty=int(raw) if raw is not None and str(raw).isdigit() else None
        supply_id=str(row.get("data-supply-id") or (stock_el.get("data-supply-id") if stock_el else "") or "")
        key=(size,supply_id)
        if size and key not in seen:
            seen.add(key)
            out.append({"size":size,"qty":qty,"supply_id":supply_id,"variant_url":row.get("data-url"),"data_code":row.get("data-code")})
    return out

async def main():
    if len(SELECTED)!=50 or len({x["supplier_product_id"] for x in SELECTED})!=50:
        raise RuntimeError("Expected exactly 50 unique products")
    pw=browser=context=None
    try:
        pw,browser,context,_=await open_logged_in_page();req=context.request
        counts={}
        for p in SELECTED:
            try:
                r=await req.get(p["url"],timeout=30000);html=await r.text()
                if r.status!=200 or "Dostęp tylko dla zalogowanych kontrahentów" in html:
                    raise RuntimeError(f"http_or_auth_{r.status}")
                soup=BeautifulSoup(html,"html.parser")
                rows=variant_rows(soup)
                eans=ean_sequence(soup)
                wearable=bool(WEARABLE_RE.search(p.get("title","")))
                unique_sizes=len({x["size"] for x in rows})
                duplicate_sizes=unique_sizes!=len(rows)
                if len(rows)==0 and len(eans)==1:
                    classification="SINGLE_PRODUCT_ONE_EAN"
                    safe_map=[]
                elif len(rows)==1 and len(eans)==1:
                    classification="SINGLE_VARIANT_EXACT_EAN"
                    safe_map=[{"size":rows[0]["size"],"qty":rows[0]["qty"],"supply_id":rows[0]["supply_id"],"ean":eans[0]}]
                elif len(rows)>=2 and len(eans)==len(rows) and not duplicate_sizes:
                    classification="MULTI_VARIANT_EAN_COUNT_MATCH_MAPPING_UNCONFIRMED"
                    safe_map=[]
                elif len(rows)>=2:
                    classification="MULTI_VARIANT_EAN_COUNT_MISMATCH_OR_DUPLICATE"
                    safe_map=[]
                elif len(rows)==0 and len(eans)>1:
                    classification="EAN_POOL_WITHOUT_VARIANT_ROWS"
                    safe_map=[]
                else:
                    classification="IDENTITY_REVIEW"
                    safe_map=[]
                min_two_sizes_ok=(not wearable) or unique_sizes>=2
                counts[classification]=counts.get(classification,0)+1
                emit("stage4_exact_product",catalog_index=p["catalog_index"],supplier_product_id=p["supplier_product_id"],sku=p["sku"],title=p.get("title"),source_url=p["url"],
                     variants=rows,ean_sequence=eans,classification=classification,safe_size_ean_map=safe_map,
                     wearable=wearable,min_two_sizes_ok=min_two_sizes_ok,unique_size_count=unique_sizes,duplicate_sizes=duplicate_sizes)
            except Exception as ex:
                counts["ERROR"]=counts.get("ERROR",0)+1
                emit("stage4_exact_error",catalog_index=p["catalog_index"],supplier_product_id=p["supplier_product_id"],sku=p["sku"],error=f"{type(ex).__name__}: {ex}")
        emit("stage4_exact_summary",processed=50,classification_counts=counts,status="VARIANT_STRUCTURE_CAPTURED_NO_GUESSED_EAN_MAPPING")
    finally:
        if context:await context.close()
        if browser:await browser.close()
        if pw:await pw.stop()

if __name__=="__main__":
    asyncio.run(main())
