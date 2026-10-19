"""One-shot safe Alpinus stock synchronizer. Default is dry-run.

Use ALPINUS_ENABLE_WRITES=YES only after supplier and Shopify credentials
have been checked in the same Render environment.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from alpinus_bulk.app import open_logged_in_page
from alpinus_sync.daily_capture import PRODUCTS, parse_detail
from alpinus_sync.render_end_to_end import PRODUCT_GIDS, QUERY, shopify
from alpinus_sync.fjord_write import apply_fjord_change

FJORD="gid://shopify/Location/107805770066"
CESU="gid://shopify/Location/84891861330"
APPROVED={
"NQ35000-S":"gid://shopify/InventoryItem/55376446226770",
"NQ35000-L":"gid://shopify/InventoryItem/55376446292306",
"QN35045XS":"gid://shopify/InventoryItem/55376409788754",
"QN35045S":"gid://shopify/InventoryItem/55376409821522",
"QN35045M":"gid://shopify/InventoryItem/55376409854290",
"QN35045L":"gid://shopify/InventoryItem/55376409887058",
"QN35045XL":"gid://shopify/InventoryItem/55376409919826",
"QN350452XL":"gid://shopify/InventoryItem/55376409952594"}

def levels(item):
    return {x["location"]["id"]:x["quantities"][0]["quantity"]
            for x in item["inventoryLevels"]["nodes"]}

async def capture():
    pw=browser=context=None
    try:
        pw,browser,context,_=await open_logged_in_page()
        all_rows=[]
        for product in PRODUCTS:
            response=await context.request.get(product["url"],timeout=30000)
            if response.status!=200: raise RuntimeError("supplier_http_failure")
            all_rows.extend(parse_detail(await response.text(), product))
        if len(all_rows)!=8: raise RuntimeError("supplier_incomplete_batch")
        return all_rows
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()

def snapshot():
    result={}
    for code,pid in PRODUCT_GIDS.items():
        p=shopify(QUERY,{"id":pid})["product"]
        if not p or p["vendor"].strip().lower()!="alpinus":
            raise RuntimeError("wrong_vendor")
        for v in p["variants"]["nodes"]:
            sku=v["sku"]
            if sku not in APPROVED: continue
            iid=v["inventoryItem"]["id"]
            if iid!=APPROVED[sku] or sku in result:
                raise RuntimeError("identity_mismatch")
            q=levels(v["inventoryItem"])
            if FJORD not in q or CESU not in q: raise RuntimeError("required_location_missing")
            result[sku]={"iid":iid,"fjord":q[FJORD],"cesu":q[CESU]}
    if set(result)!=set(APPROVED):raise RuntimeError("shopify_incomplete")
    return result

async def run():
    rows=await capture()
    source={r["sku"]:r["quantity"] for r in rows}
    if len(source)!=8 or set(source)!=set(APPROVED):raise RuntimeError("supplier_wrong_variants")
    before=snapshot()
    live=os.getenv("ALPINUS_ENABLE_WRITES")=="YES"
    if live:
        for sku,quantity in source.items():
            item=before[sku]
            if quantity!=item["fjord"]:
                apply_fjord_change(item["iid"],item["fjord"],quantity)
        after=snapshot()
        if any(after[s]["fjord"]!=source[s] or after[s]["cesu"]!=before[s]["cesu"] for s in source):
            raise RuntimeError("verification_failure")
    return {"result":"LIVE_VERIFIED" if live else "DRY_RUN_VERIFIED",
            "count":len(source),"writes_enabled":live,
            "verified_at":datetime.now(timezone.utc).isoformat()}

if __name__=="__main__":
    try: print(json.dumps(asyncio.run(run())))
    except Exception as exc:
        print(json.dumps({"result":"FAILED_CLOSED","error_type":type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
