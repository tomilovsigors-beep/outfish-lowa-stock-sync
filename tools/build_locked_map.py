"""Build a candidate immutable mapping from a reviewed dry-run JSON.
Usage: python tools/build_locked_map.py dry-run.json > config/locked_inventory_map.candidate.json
Review diff manually, then rename to locked_inventory_map.json.
"""
import json,sys
j=json.load(open(sys.argv[1],encoding="utf-8")); out={}
for r in j.get("rows",[]):
    if r.get("productId") and r.get("inventoryItemId") and r.get("size"):
        out[f'{r["productId"]}|{r["size"]}']={"inventoryItemId":r["inventoryItemId"],"variantId":r.get("variantId"),"model":r.get("model"),"color":r.get("color"),"width":r.get("width"),"size":r.get("size")}
print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
