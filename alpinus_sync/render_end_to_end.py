"""Run one B2B-to-Shopify read-only reconciliation in Render.

No mutation endpoint is present. Existing products and inventories are untouched.
This job exits nonzero if B2B auth or Shopify identity checks fail.
"""
import asyncio
import json
import os
import sys
import urllib.request
from alpinus_sync.render_preflight import verify
from alpinus_sync.daily_capture import PRODUCTS

PRODUCT_GIDS = {
  "NQ35000": "gid://shopify/Product/10750909251922",
  "QN35045": "gid://shopify/Product/10750891655506",
}
QUERY = """query($id:ID!){product(id:$id){id vendor variants(first:50){nodes{sku inventoryItem{id inventoryLevels(first:10){nodes{location{id} quantities(names:["available"]){quantity}}}}}}}}"""

def shopify(query, variables):
    domain = os.environ["SHOPIFY_SHOP_DOMAIN"]
    token = os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"]
    if not domain.endswith(".myshopify.com") or "/" in domain:
        raise RuntimeError("invalid_shop_domain")
    req=urllib.request.Request("https://"+domain+"/admin/api/2025-10/graphql.json",
      data=json.dumps({"query":query,"variables":variables}).encode(),
      headers={"Content-Type":"application/json","X-Shopify-Access-Token":token})
    with urllib.request.urlopen(req,timeout=25) as response:
        payload=json.load(response)
    if payload.get("errors"):
        raise RuntimeError("shopify_query_failed")
    return payload["data"]

async def main():
    supplier=await verify()
    expected={sku for product in PRODUCTS for sku in product["sizes"].values()}
    shop_rows={}
    for code,pid in PRODUCT_GIDS.items():
        node=shopify(QUERY,{"id":pid})["product"]
        if not node or str(node["vendor"]).casefold()!="alpinus":
            raise RuntimeError("shopify_identity_failed")
        for v in node["variants"]["nodes"]:
            sku=v["sku"]
            if sku in expected:
                if sku in shop_rows:
                    raise RuntimeError("duplicate_shopify_sku")
                levels={x["location"]["id"]:x["quantities"][0]["quantity"]
                        for x in v["inventoryItem"]["inventoryLevels"]["nodes"]}
                if "gid://shopify/Location/107805770066" not in levels or "gid://shopify/Location/84891861330" not in levels:
                    raise RuntimeError("missing_required_location")
                shop_rows[sku]={"inventory_item_id":v["inventoryItem"]["id"],
                                "fjord":levels["gid://shopify/Location/107805770066"],
                                "cesu":levels["gid://shopify/Location/84891861330"]}
    if set(shop_rows)!=expected:
        raise RuntimeError("incomplete_shopify_variants")
    return {"result":"B2B_AND_SHOPIFY_VERIFIED_NO_WRITES",
            "b2b_variants":supplier["checked_variants"],
            "shopify_variants":len(shop_rows),
            "cesu_protected":True,"shopify_writes":0}

if __name__=="__main__":
    try:
        print(json.dumps(asyncio.run(main())))
    except Exception as e:
        print(json.dumps({"result":"FAILED_CLOSED","error_type":type(e).__name__}),file=sys.stderr)
        sys.exit(1)
