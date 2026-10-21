"""Offline end-to-end integration tests: supplier HTML -> proposed location changes.

This suite MUST never touch real Shopify or Alpinus; it uses HTML fixtures
and an in-memory Shopify inventory snapshot.
"""
import unittest
from datetime import datetime, timezone
from alpinus_sync.daily_capture import parse_detail, PRODUCTS
from alpinus_sync.safe_plan import plan

FJORD = "gid://shopify/Location/107805770066"
NOW = datetime(2026,10,18,20,tzinfo=timezone.utc)

def html(code, pairs):
    body = "".join(
        '<div class="attribute-button-ui last-lvl-ui table-row-ui">'
        '<span class="name-column-ui supply-value-lq">%s</span>'
        '<span data-stock-value="%s"></span></div>' % pair
        for pair in pairs
    )
    return "<html><body><h1>%s</h1>%s</body></html>" % (code,body)

def pipeline(cesu=1):
    extracted = parse_detail(html("NQ35000",[("S",17),("L",6)]),PRODUCTS[0])
    snapshot = {
        "supplier":[dict(sku=p["sku"],quantity=p["quantity"],
                         verified_at="2026-10-18T19:00:00Z")
                    for p in extracted],
        "shopify":[
            dict(inventory_item_id="gid://shopify/InventoryItem/"+str(k),
                 sku=p["sku"],vendor="Alpinus",
                 cesu_available=cesu,fjord_available=2)
            for k,p in enumerate(extracted,1)
        ],
        "approved_inventory_item_ids": [
            "gid://shopify/InventoryItem/1","gid://shopify/InventoryItem/2"
        ],
    }
    return plan(snapshot, now=NOW)

class PipelineTests(unittest.TestCase):
    def test_two_variants_proposed_at_fjord_only(self):
        result=pipeline()
        self.assertEqual(result["proposed_count"],2)
        self.assertTrue(all(d["location_id"]==FJORD for d in result["decisions"]))
        self.assertEqual({d["proposed_available"] for d in result["decisions"]},{17,6})
        self.assertTrue(all(d["cesu_available_unchanged"]==1 for d in result["decisions"]))

    def test_cesu_priority(self):
        self.assertTrue(all(d["customer_lead_time_days"]==2 for d in pipeline(1)["decisions"]))
        self.assertTrue(all(d["customer_lead_time_days"]==5 for d in pipeline(0)["decisions"]))

    def test_html_incomplete_refuses_plan(self):
        with self.assertRaises(ValueError):
            parse_detail(html("NQ35000",[("S",17)]),PRODUCTS[0])

    def test_unapproved_item_skipped(self):
        snapshot={
          "supplier":[{"sku":"NQ35000-S","quantity":17,"verified_at":"2026-10-18T19:00:00Z"}],
          "shopify":[{"sku":"NQ35000-S","inventory_item_id":"gid://shopify/InventoryItem/1",
                      "vendor":"Alpinus","cesu_available":1,"fjord_available":2}],
          "approved_inventory_item_ids":[]
        }
        d=plan(snapshot,now=NOW)["decisions"][0]
        self.assertEqual(d["action"],"SKIP")
        self.assertEqual(d["reason"],"not_approved_for_alpinus_inventory")

if __name__=="__main__":
    unittest.main()
