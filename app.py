import os, uuid, requests
from flask import Flask, jsonify, request
from supplier import parse_xlsx_bytes
from shopify import Shopify
from engine import make_dry_run, build_sync_batch

app=Flask(__name__)

def shop():
    token=os.getenv("SHOPIFY_ACCESS_TOKEN")
    if not token: raise RuntimeError("SHOPIFY_ACCESS_TOKEN is not configured")
    return Shopify(os.getenv("SHOPIFY_STORE_DOMAIN","153ac6-2.myshopify.com"), token, os.getenv("SHOPIFY_API_VERSION","2026-07"))

def supplier_rows():
    url=os.getenv("SUPPLIER_XLSX_URL")
    if not url: raise RuntimeError("SUPPLIER_XLSX_URL is not configured")
    r=requests.get(url,timeout=60); r.raise_for_status()
    return parse_xlsx_bytes(r.content)

@app.get("/health")
def health():
    return {"ok":True,"service":"outfish-lowa-stock-sync","liveSyncEnabled":os.getenv("ALLOW_LIVE_SYNC","false").lower()=="true"}

@app.get("/dry-run")
def dry_run():
    rows=make_dry_run(supplier_rows(),shop())
    counts={}
    for r in rows: counts[r["action"]]=counts.get(r["action"],0)+1
    return jsonify({"counts":counts,"rows":rows})

@app.post("/sync")
def sync():
    # Three independent locks: env flag + secret header + immutable mapping file.
    if os.getenv("ALLOW_LIVE_SYNC","false").lower()!="true": return {"error":"live sync disabled"},403
    secret=os.getenv("SYNC_SECRET")
    if not secret or request.headers.get("X-Sync-Secret")!=secret: return {"error":"forbidden"},403
    rows=make_dry_run(supplier_rows(),shop())
    batch,rejected=build_sync_batch(rows)
    if rejected: return jsonify({"error":"unlocked mappings present","blocked":rejected,"proposed":batch}),409
    if not batch: return {"ok":True,"message":"nothing to change","changed":0}
    # Keep batches modest and CAS-safe. Shopify rejects stale changeFromQuantity values.
    s=shop(); all_results=[]
    for i in range(0,len(batch),50):
        part=batch[i:i+50]
        ref=f"gid://outfish-lowa-stock-sync/SyncJob/{uuid.uuid4()}"
        res=s.set_on_hand(part,ref)
        if res.get("userErrors"): return jsonify({"error":"shopify rejected batch","details":res["userErrors"],"reference":ref}),409
        all_results.append(res)
    return jsonify({"ok":True,"changed":len(batch),"results":all_results})
