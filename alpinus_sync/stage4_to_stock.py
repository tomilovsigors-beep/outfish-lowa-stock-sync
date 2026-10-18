"""Stage4 JSONL -> verified per-variant supplier stock. No Shopify writes."""
import argparse
import json
from datetime import datetime, timezone


def convert(events, mapping, verified_at=None):
    if not verified_at:
        raise ValueError("verified_at_required: Stage4 logs have no timestamp")
    dt = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt > datetime.now(timezone.utc):
        raise ValueError("verified_at must be timezone-aware and not in future")
    lookup = {}
    mapped_skus = set()
    for m in mapping:
        key = (str(m.get("supplier_product_id", "")), str(m.get("supply_id", "")), str(m.get("size", "")))
        sku = str(m.get("shopify_variant_sku", "")).strip()
        if not all(key) or not sku or key in lookup or sku in mapped_skus:
            raise ValueError("ambiguous_variant_mapping")
        lookup[key] = sku
        mapped_skus.add(sku)
    rows = {}
    errors = []
    summaries = []
    seen = set()
    for event in events:
        kind = event.get("event")
        if kind == "stage4_exact_error":
            errors.append(event)
        elif kind == "stage4_exact_summary":
            summaries.append(event)
        elif kind == "stage4_exact_product":
            pid = str(event.get("supplier_product_id", ""))
            if not pid or pid in seen:
                errors.append("duplicate_supplier_product")
                continue
            seen.add(pid)
            variants = event.get("variants") or []
            for variant in variants:
                key = (pid, str(variant.get("supply_id", "")), str(variant.get("size", "")))
                sku = lookup.get(key)
                qty = variant.get("qty")
                if sku and type(qty) is int and qty >= 0:
                    if sku in rows:
                        errors.append("duplicate_variant_sku")
                    else:
                        rows[sku] = {"supplier_product_id": pid, "sku": sku, "quantity": qty,
                                     "verified_at": verified_at}
    if len(summaries) != 1 or errors or summaries[0].get("processed") != len(seen):
        raise ValueError("incomplete_or_failed_stage4_batch")
    if summaries[0].get("classification_counts", {}).get("ERROR", 0):
        raise ValueError("stage4_batch_contains_errors")
    return {"supplier": list(rows.values()), "mapped_variants": len(rows),
            "unmapped_variants_are_excluded": True, "verified_at": verified_at}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage4_events_jsonl")
    p.add_argument("approved_variant_mapping_json")
    p.add_argument("--verified-at", required=True, help="Real supplier capture time (ISO 8601 UTC); not the conversion time")
    args = p.parse_args()
    with open(args.stage4_events_jsonl, encoding="utf-8") as f:
        events = [json.loads(s) for s in f if s.strip()]
    with open(args.approved_variant_mapping_json, encoding="utf-8") as f:
        mapping = json.load(f)
    print(json.dumps(convert(events, mapping, args.verified_at), ensure_ascii=False, indent=2))
