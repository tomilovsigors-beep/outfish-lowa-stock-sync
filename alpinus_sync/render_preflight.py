"""Read-only deployment preflight. Exit nonzero on missing or stale B2B data.

Usage: python -m alpinus_sync.render_preflight
Does not write Shopify. Prints no credentials or supplier HTML.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from alpinus_sync.daily_capture import PRODUCTS, parse_detail
from alpinus_bulk.app import open_logged_in_page

async def verify():
    pw = browser = context = None
    try:
        pw, browser, context, _ = await open_logged_in_page()
        validated = []
        for product in PRODUCTS:
            response = await context.request.get(product["url"], timeout=30000)
            if response.status != 200:
                raise RuntimeError("supplier_non_200")
            variants = parse_detail(await response.text(), product)
            validated.extend(variants)
        expected = sum(len(p["sizes"]) for p in PRODUCTS)
        if len(validated) != expected:
            raise RuntimeError("incomplete_supplier_snapshot")
        return {"status":"supplier_read_verified","checked_variants":expected,
                "captured_at":datetime.now(timezone.utc).isoformat(),"writes":0}
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()

if __name__ == "__main__":
    try:
        print(json.dumps(asyncio.run(verify())))
    except Exception as exc:
        print(json.dumps({"status":"FAILED_CLOSED","error_type":type(exc).__name__,
                          "writes":0}),file=sys.stderr)
        sys.exit(1)
