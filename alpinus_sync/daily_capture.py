"""Read-only daily Alpinus B2B snapshot of proven Shopify variant mapping.

Invoke: python -m alpinus_sync.daily_capture
Requires ALPINUS_B2B_LOGIN / ALPINUS_B2B_PASSWORD (existing Render secrets).
Outputs one JSON report to stdout; never writes Shopify.
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from alpinus_bulk.app import open_logged_in_page

PRODUCTS = [
    {"name":"Selenga", "url":"https://alpinusgroup.com/kurtka-damska-2-warstwowa-alpinus-selenga/3-61-1074",
     "code":"NQ35000", "sizes":{"S":"NQ35000-S","L":"NQ35000-L"}},
    {"name":"Urmia", "url":"https://alpinusgroup.com/plaszcz-przeciwdeszczowy-damski-alpinus-urmia-qn35/3-61-1124",
     "code":"QN35045", "sizes":{"XS":"QN35045XS","S":"QN35045S","M":"QN35045M","L":"QN35045L","XL":"QN35045XL","2XL":"QN350452XL"}}
]

def parse_detail(html, product):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Dostęp tylko dla zalogowanych kontrahentów" in text or "Zaloguj się" in text[:300]:
        raise ValueError("supplier_auth_lost")
    if product["code"].lower() not in text.lower():
        raise ValueError("supplier_product_code_mismatch")
    found = {}
    for row in soup.select(".attribute-button-ui.last-lvl-ui.table-row-ui"):
        size_el = row.select_one(".name-column-ui.supply-value-lq") or row.select_one(".name-column-ui")
        size = re.sub(r"\\s+", " ", size_el.get_text(" ",strip=True)).strip().upper() if size_el else ""
        stock_el = row.select_one("[data-stock-value]")
        raw = stock_el.get("data-stock-value") if stock_el else None
        if size not in product["sizes"]:
            continue
        if size in found or raw is None or not str(raw).isdigit():
            raise ValueError("ambiguous_or_missing_variant_stock_" + size)
        found[size] = int(raw)
    if set(found) != set(product["sizes"]):
        raise ValueError("not_all_approved_sizes_found")
    return [{"sku":product["sizes"][size],"size":size,"quantity":qty,
             "supplier_code":product["code"],"product":product["name"]}
            for size,qty in sorted(found.items())]

async def main():
    pw=browser=context=None
    timestamp=datetime.now(timezone.utc).isoformat()
    try:
        pw,browser,context,_=await open_logged_in_page()
        rows=[]
        for product in PRODUCTS:
            response=await context.request.get(product["url"], timeout=30000)
            if response.status != 200:
                raise ValueError("supplier_http_error")
            rows.extend(parse_detail(await response.text(), product))
        print(json.dumps({"status":"VALIDATED_READ_ONLY", "source":"alpinusgroup.com",
                          "verified_at":timestamp,"rows":rows},ensure_ascii=False))
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()

if __name__=="__main__":
    asyncio.run(main())
