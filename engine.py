import json, os, re
from pathlib import Path
from supplier import norm_size

ROOT=Path(__file__).resolve().parent
LOWA=os.getenv("LOWA_LOCATION_ID","gid://shopify/Location/107817075026")
VEIKALS=os.getenv("VEIKALS_LOCATION_ID","gid://shopify/Location/84891861330")


def load_json(name):
    with open(ROOT/"config"/name, encoding="utf-8") as f: return json.load(f)

def is_skip(model,color,width,rules):
    for r in rules:
        if (r["model"] in ("*",model) and r["color"] in ("*",color) and r["width"] in ("*",width)):
            return r["reason"]
    return None

def variant_size(v):
    # Exact numeric extraction only; no fuzzy product/title matching.
    vals=[o["value"] for o in v.get("selectedOptions",[])]+[v.get("title","")]
    for val in vals:
        s=norm_size(val)
        if s: return s
    return None

def qmap(level):
    return {q["name"]: q["quantity"] for q in level.get("quantities",[])}

def make_dry_run(supplier_rows, shopify):
    product_map=load_json("product_map.json"); rules=load_json("skip_rules.json")
    results=[]
    for row in supplier_rows:
        model,color,width=row["model"],row["color"],row["width"]
        reason=is_skip(model,color,width,rules)
        key=f"{model}|{color}|{width}"
        if reason:
            results.append({**row,"action":"skip_by_rule","reason":reason}); continue
        pid=product_map.get(key)
        if not pid:
            # Zero-only unresolved rows are harmless but still visible in log.
            results.append({**row,"action":"unmapped_product","reason":key}); continue
        p=shopify.product_inventory(pid)
        variants={variant_size(v):v for v in p["variants"]["nodes"] if variant_size(v)}
        for size,target in row["stock"].items():
            v=variants.get(size)
            if not v:
                if target != 0:
                    results.append({"model":model,"color":color,"width":width,"size":size,"target":target,"action":"skip_missing_variant","productId":pid})
                continue
            levels=v["inventoryItem"]["inventoryLevels"]["nodes"]
            byloc={x["location"]["id"]:x for x in levels}
            lowa=byloc.get(LOWA); store=byloc.get(VEIKALS)
            store_on=qmap(store).get("on_hand",0) if store else 0
            if lowa is None:
                if target>0 and store_on<=0:
                    results.append({"model":model,"color":color,"width":width,"size":size,"target":target,"action":"skip_lowa_inactive","productId":pid,"variantId":v["id"],"inventoryItemId":v["inventoryItem"]["id"],"storeOnHand":store_on})
                continue
            qm=qmap(lowa); current=qm.get("on_hand",0); committed=qm.get("committed",0); available=qm.get("available",0)
            action="no_change"
            # Store priority: do not create/activate LOWA solely because store has stock. Existing LOWA levels may still be reconciled.
            if current != target: action="update"
            results.append({"model":model,"color":color,"width":width,"size":size,"target":target,"action":action,"productId":pid,"variantId":v["id"],"inventoryItemId":v["inventoryItem"]["id"],"lowaOnHand":current,"lowaAvailable":available,"committed":committed,"storeOnHand":store_on})
    return results

def build_sync_batch(dry_rows):
    locked=load_json("locked_inventory_map.json")
    batch=[]; rejected=[]
    for r in dry_rows:
        if r.get("action")!="update": continue
        lock_key=f'{r["productId"]}|{r["size"]}'
        locked_item=locked.get(lock_key)
        if not locked_item or locked_item.get("inventoryItemId")!=r.get("inventoryItemId"):
            rejected.append({**r,"action":"blocked_unlocked_mapping"}); continue
        batch.append({"inventoryItemId":r["inventoryItemId"],"locationId":LOWA,"quantity":int(r["target"]),"changeFromQuantity":int(r["lowaOnHand"])})
    return batch,rejected
