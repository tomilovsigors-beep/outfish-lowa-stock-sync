"""Read-only Alpinus import eligibility and Shopify reconciliation.

This module NEVER writes to Shopify. Inputs are snapshots (JSON/JSONL).
Exactly one terminal decision is recorded for every supplier product.
"""
from __future__ import annotations
import argparse
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

MIN_EUR = Decimal("20.00")

def eur(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None

def normalize(value):
    return "".join(c for c in str(value or "").upper() if c.isalnum())

def index_shopify(products):
    by_sku, by_barcode = {}, {}
    for p in products:
        for v in p.get("variants", []):
            for key, index in ((v.get("sku"), by_sku), (v.get("barcode"), by_barcode)):
                if key:
                    index.setdefault(normalize(key), []).append(p)
    return by_sku, by_barcode

def decide(row, by_sku, by_barcode, fx_pln_to_eur):
    pid = row.get("supplier_product_id")
    rrp = eur(row.get("rrp_pln"))
    if fx_pln_to_eur is None or fx_pln_to_eur <= 0 or rrp is None:
        return {"id": pid, "decision": "HOLD_PRICE", "reason": "missing verified RRP or FX"}
    price = (rrp * fx_pln_to_eur).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if price < MIN_EUR:
        return {"id": pid, "decision": "SKIP_UNDER_20", "price_eur": str(price)}
    matches = {}
    for key in [row.get("symbol"), *(row.get("eans") or [])]:
        k = normalize(key)
        if k:
            for p in by_sku.get(k, []) + by_barcode.get(k, []):
                matches[p["id"]] = p
    if len(matches) > 1:
        return {"id": pid, "decision": "HOLD_AMBIGUOUS", "price_eur": str(price)}
    if matches:
        product = next(iter(matches.values()))
        status = str(product.get("status", "")).upper()
        return {"id": pid, "decision": "KEEP_ACTIVE" if status == "ACTIVE" else "COMPLETE_DRAFT" if status == "DRAFT" else "HOLD_STATUS",
                "shopify_product_id": product["id"], "price_eur": str(price)}
    # No SKU/EAN match does NOT prove absence: human/secondary title matching is required.
    return {"id": pid, "decision": "HOLD_UNMATCHED", "price_eur": str(price), "reason": "verify no existing Shopify product"}

def load(path):
    data = Path(path).read_text(encoding="utf-8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in data.splitlines() if line.strip()]
    obj = json.loads(data)
    return obj if isinstance(obj, list) else obj["products"]

def run(source, shopify, fx, out, batch_size):
    products = load(source)
    existing = load(shopify)
    by_sku, by_barcode = index_shopify(existing)
    seen = set()
    decisions = []
    for i in range(0, len(products), batch_size):
        for p in products[i:i+batch_size]:
            pid = p.get("supplier_product_id")
            if not pid or pid in seen:
                raise ValueError("Missing or duplicate supplier_product_id: " + str(pid))
            seen.add(pid)
            decisions.append(decide(p, by_sku, by_barcode, fx))
        # Atomic checkpoint: retries overwrite the same deterministic read-only result.
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps({"processed": len(decisions), "source_total": len(products),
                                   "decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    return decisions

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True, help="Supplier JSONL snapshot")
    p.add_argument("--shopify", required=True, help="Shopify product JSON snapshot with variants")
    p.add_argument("--fx-pln-to-eur", required=True, type=Decimal, help="Verified rate, not an estimate")
    p.add_argument("--out", required=True)
    p.add_argument("--batch-size", type=int, default=20)
    a = p.parse_args()
    if not 1 <= a.batch_size <= 50:
        p.error("batch size must be 1..50")
    results = run(a.source, a.shopify, a.fx_pln_to_eur, a.out, a.batch_size)
    print(json.dumps({"processed": len(results), "decisions": {d: sum(x["decision"] == d for x in results) for d in sorted(set(x["decision"] for x in results))}}))
