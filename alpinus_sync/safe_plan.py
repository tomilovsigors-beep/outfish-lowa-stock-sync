"""Read-only Alpinus inventory reconciliation planner. Never calls Shopify writes.

Input JSON: {"supplier":[{"supplier_product_id":"1","sku":"ABC-S","quantity":4,
"verified_at":"2026-10-18T18:00:00Z"}],
"shopify":[{"inventory_item_id":"gid://shopify/InventoryItem/123","sku":"ABC-S",
"vendor":"Alpinus","cesu_available":1,"fjord_available":2}],
"approved_inventory_item_ids":["gid://shopify/InventoryItem/123"]}

A plan is NOT authorization for mutation. A separate reviewed writer is required.
"""
import argparse
import json
from datetime import datetime, timezone

FJORD_LOCATION_ID = "gid://shopify/Location/107805770066"
CESU_LOCATION_ID = "gid://shopify/Location/84891861330"
MAX_AGE_HOURS = 26


def timestamp(value):
    if not value:
        raise ValueError("missing_verified_at")
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("naive_verified_at")
    return dt.astimezone(timezone.utc)


def normalize_sku(value):
    return str(value or "").strip().upper()


def plan(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    approved = set(payload.get("approved_inventory_item_ids", []))
    shop_by_sku = {}
    supplier_by_sku = {}
    for p in payload.get("shopify", []):
        shop_by_sku.setdefault(normalize_sku(p.get("sku")), []).append(p)
    for p in payload.get("supplier", []):
        supplier_by_sku.setdefault(normalize_sku(p.get("sku")), []).append(p)
    decisions = []
    for sku, records in sorted(supplier_by_sku.items()):
        d = {"sku": sku, "action": "SKIP", "reason": None}
        if not sku or len(records) != 1:
            d["reason"] = "missing_or_duplicate_supplier_sku"
        elif len(shop_by_sku.get(sku, [])) != 1:
            d["reason"] = "missing_or_ambiguous_shopify_variant"
        else:
            s, p = records[0], shop_by_sku[sku][0]
            iid = p.get("inventory_item_id")
            qty = s.get("quantity")
            try:
                age = (now - timestamp(s.get("verified_at"))).total_seconds() / 3600
            except (TypeError, ValueError):
                age = float("inf")
            if p.get("vendor", "").strip().casefold() != "alpinus":
                d["reason"] = "different_vendor"
            elif not iid or iid not in approved:
                d["reason"] = "not_approved_for_alpinus_inventory"
            elif type(qty) is not int or qty < 0:
                d["reason"] = "invalid_supplier_quantity"
            elif age < 0 or age > MAX_AGE_HOURS:
                d["reason"] = "stale_or_future_supplier_quantity"
            elif type(p.get("fjord_available")) is not int or type(p.get("cesu_available")) is not int:
                d["reason"] = "missing_location_inventory"
            elif p["cesu_available"] < 0 or p["fjord_available"] < 0:
                d["reason"] = "invalid_shopify_inventory"
            else:
                d.update(action="PROPOSE_FJORD_ONLY", reason=None,
                         inventory_item_id=iid, location_id=FJORD_LOCATION_ID,
                         old_available=p["fjord_available"], proposed_available=qty,
                         cesu_available_unchanged=p["cesu_available"],
                         customer_lead_time_days=2 if p["cesu_available"] > 0 else (5 if qty > 0 else None),
                         stock_source_priority="CESU" if p["cesu_available"] > 0 else "ALPINUS",
                         protected_fields=["title", "description", "images", "seo", "price", "sku"])
        decisions.append(d)
    return {"mode": "READ_ONLY_NO_SHOPIFY_WRITES", "target_location_id": FJORD_LOCATION_ID,
            "cesu_location_id": CESU_LOCATION_ID, "decisions": decisions,
            "proposed_count": sum(x["action"] == "PROPOSE_FJORD_ONLY" for x in decisions),
            "skipped_count": sum(x["action"] == "SKIP" for x in decisions)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alpinus read-only inventory safety planner")
    parser.add_argument("input_json", help="Supplier snapshot + Shopify snapshot + explicitly approved inventory IDs")
    args = parser.parse_args()
    with open(args.input_json, encoding="utf-8") as fh:
        payload = json.load(fh)
    print(json.dumps(plan(payload), ensure_ascii=False, indent=2))
