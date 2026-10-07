"""Alpinus stage 4 batch 001: exact variant/size/EAN/stock resolver.
Authenticated supplier read-only. Never writes Shopify.
Only emits a size->EAN mapping when evidence is explicit in the supplier page.
"""
import asyncio, json, os, re
from pathlib import Path
from bs4 import BeautifulSoup
from app import open_logged_in_page

SELECTED=json.loads(Path("alpinus_bulk/stage4_variants_batch_001_selection.json").read_text(encoding="utf-8"))
EAN_RE=re.compile(r"\b\d{13}\b")
TEXT_SIZE_RE=re.compile(r"(?<![A-Z0-9])(3XL|2XL|4XL|XL|XS|S|M|L)(?![A-Z0-9])",re.I)
RANGE_RE=re.compile(r"\b(3[0-9]|4[0-9]|50)\s*[-/]\s*(3[0-9]|4[0-9]|50)\b")
NUM_RE=re.compile(r"(?<!\d)(3[4-9]|4[0-9]|50)(?!\d)")
WEARABLE_RE=re.compile(r"\b(kurtka|koszulka|spodnie|buty|sandały|sandaly|bluza|płaszcz|plaszcz|bielizna|rękawiczki|rekawiczki|polar|szorty)\b",re.I)

def emit(event,**v):
    print(json.dumps({"event":event,**v},ensure_ascii=False,separators=(",",":")),flush=True)

def clean(s):
    return re.sub(r"\s+"," ",s or "").strip()

def sizes_in(text):
    text=clean(text)
    out=[]
    for m in TEXT_SIZE_RE.finditer(text):
        v=m.group(1).upper()
        if v not in out: out.append(v)
    for m in RANGE_RE.finditer(text):
        v=f"{m.group(1)}-{m.group(2)}"
        if v not in out: out.append(v)
    for m in NUM_RE.finditer(text):
        v=m.group(1)
        if v not in out: out.append(v)
    return out

def qty_from_node(node):
    if not node: return None
    for el in [node]+list(node.select("[data-stock-value],[data-max],input[max],input[name*=quantity],input[name*=ilosc],input[name*=qty]")):
        for a in ("data-stock-value","data-max","max","data-qty","data-stock","data-quantity"):
            raw=el.get(a) if hasattr(el,"get") else None
            if raw is not None and str(raw).strip().isdigit():
                return int(str(raw).strip())
    text=clean(node.get_text(" ",strip=True))
    for pat in (r"(?:stan|stock|ilość|ilosc|quantity|qty)\s*[:=]?\s*(\d+)",):
        m=re.search(pat,text,re.I)
        if m:return int(m.group(1))
    return None

def explicit_ean_size_evidence(soup):
    evidence=[]
    seen=set()
    # Direct structured rows/options/labels first.
    candidates=soup.select("tr,.table-row-ui,.attribute-button-ui,option,label,li,[data-ean],[data-barcode],[data-gtin],[data-size],[data-rozmiar]")
    for node in candidates:
        txt=clean(node.get_text(" ",strip=True))
        attrs=" ".join(f"{k}={v}" for k,v in node.attrs.items())
        blob=clean(txt+" "+attrs)
        eans=sorted(set(EAN_RE.findall(blob)))
        ss=sizes_in(blob)
        if len(eans)==1 and len(ss)==1:
            key=(ss[0],eans[0])
            if key not in seen:
                seen.add(key)
                evidence.append({"size":ss[0],"ean":eans[0],"qty":qty_from_node(node),"evidence":"structured_node","snippet":blob[:500]})
    # Nearest ancestor around each EAN text node.
    for text_node in soup.find_all(string=EAN_RE):
        eans=EAN_RE.findall(str(text_node))
        if not eans: continue
        node=text_node.parent
        for _ in range(6):
            if not node:break
            blob=clean(node.get_text(" ",strip=True)+" "+" ".join(f"{k}={v}" for k,v in node.attrs.items()))
            ss=sizes_in(blob)
            ee=sorted(set(EAN_RE.findall(blob)))
            if len(ss)==1 and len(ee)==1:
                key=(ss[0],ee[0])
                if key not in seen:
                    seen.add(key)
                    evidence.append({"size":ss[0],"ean":ee[0],"qty":qty_from_node(node),"evidence":"nearest_ancestor","snippet":blob[:500]})
                break
            node=node.parent
    # Script/JSON fragments only if a single EAN and a single size coexist locally.
    for script in soup.find_all("script"):
        raw=script.string or script.get_text() or ""
        if not raw:continue
        for m in EAN_RE.finditer(raw):
            lo=max(0,m.start()-350);hi=min(len(raw),m.end()+350)
            blob=clean(raw[lo:hi])
            ee=sorted(set(EAN_RE.findall(blob)));ss=sizes_in(blob)
            if len(ee)==1 and len(ss)==1:
                key=(ss[0],ee[0])
                if key not in seen:
                    seen.add(key)
                    evidence.append({"size":ss[0],"ean":ee[0],"qty":None,"evidence":"script_local","snippet":blob[:500]})
    return evidence

def stock_sizes(soup):
    rows=[];seen=set()
    for el in soup.select("[data-stock-value],[data-max],input[max],input[name*=quantity],input[name*=ilosc],input[name*=qty]"):
        raw=el.get("data-stock-value") or el.get("data-max") or el.get("max")
        if not(raw and str(raw).isdigit()):continue
        qty=int(raw)
        node=el
        blob=""
        for _ in range(4):
            if not node:break
            blob=clean(node.get_text(" ",strip=True)+" "+" ".join(f"{k}={v}" for k,v in node.attrs.items()))
            ss=sizes_in(blob)
            if len(ss)==1:break
            node=node.parent
        ss=sizes_in(blob)
        if len(ss)==1:
            key=(ss[0],qty)
            if key not in seen:
                seen.add(key);rows.append({"size":ss[0],"qty":qty})
    return rows

async def main():
    if len(SELECTED)!=50 or len({x["supplier_product_id"] for x in SELECTED})!=50:
        raise RuntimeError("Expected exactly 50 unique products")
    pw=browser=context=None
    try:
        pw,browser,context,_=await open_logged_in_page()
        req=context.request
        for p in SELECTED:
            try:
                res=await req.get(p["url"],timeout=30000)
                html=await res.text()
                if res.status!=200 or "Dostęp tylko dla zalogowanych kontrahentów" in html:
                    raise RuntimeError(f"http_or_auth_{res.status}")
                soup=BeautifulSoup(html,"html.parser")
                body=clean(soup.get_text(" ",strip=True))
                eans=sorted(set(EAN_RE.findall(body)))
                stocks=stock_sizes(soup)
                evidence=explicit_ean_size_evidence(soup)
                # Keep only one-to-one mappings; conflicting evidence makes both ambiguous.
                by_size={}
                by_ean={}
                for ev in evidence:
                    by_size.setdefault(ev["size"],set()).add(ev["ean"])
                    by_ean.setdefault(ev["ean"],set()).add(ev["size"])
                resolved=[]
                for ev in evidence:
                    if len(by_size.get(ev["size"],set()))==1 and len(by_ean.get(ev["ean"],set()))==1:
                        key=(ev["size"],ev["ean"])
                        if key not in {(x["size"],x["ean"]) for x in resolved}:
                            qty=next((x["qty"] for x in stocks if x["size"]==ev["size"]),ev.get("qty"))
                            resolved.append({"size":ev["size"],"ean":ev["ean"],"qty":qty,"evidence":ev["evidence"]})
                source_sizes=sorted({x["size"] for x in stocks},key=lambda x:(len(x),x))
                mapped_sizes={x["size"] for x in resolved};mapped_eans={x["ean"] for x in resolved}
                if len(source_sizes)==0 and len(eans)==1:
                    classification="SINGLE_PRODUCT_ONE_EAN"
                elif len(source_sizes)==1 and len(eans)==1:
                    classification="ONE_SIZE_ONE_EAN"
                    if not resolved:resolved=[{"size":source_sizes[0],"ean":eans[0],"qty":stocks[0]["qty"],"evidence":"single_size_single_ean"}]
                elif source_sizes and len(resolved)==len(source_sizes) and mapped_eans==set(eans):
                    classification="EXACT_VARIANT_MAP"
                elif source_sizes:
                    classification="PARTIAL_OR_AMBIGUOUS_VARIANT_MAP"
                else:
                    classification="IDENTITY_REVIEW"
                wearable=bool(WEARABLE_RE.search(p.get("title","")))
                min_size_rule_ok=(not wearable) or len(source_sizes)>=2
                emit("stage4_product_done",catalog_index=p["catalog_index"],supplier_product_id=p["supplier_product_id"],sku=p["sku"],title=p.get("title"),
                     source_sizes=stocks,source_eans=eans,resolved_variants=resolved,classification=classification,
                     unresolved_sizes=[x for x in source_sizes if x not in mapped_sizes],unresolved_eans=[x for x in eans if x not in mapped_eans],
                     wearable=wearable,min_two_sizes_ok=min_size_rule_ok,evidence_count=len(evidence))
            except Exception as ex:
                emit("stage4_product_error",catalog_index=p["catalog_index"],supplier_product_id=p["supplier_product_id"],sku=p["sku"],error=f"{type(ex).__name__}: {ex}")
        emit("stage4_batch_summary",processed=50,status="READ_ONLY_VARIANT_RESOLUTION")
    finally:
        if context:await context.close()
        if browser:await browser.close()
        if pw:await pw.stop()

if __name__=="__main__":
    asyncio.run(main())
