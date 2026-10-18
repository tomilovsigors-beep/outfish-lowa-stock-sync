"""Offline safety tests: python -m unittest discover -s alpinus_sync -p 'test_*.py'."""
import unittest
from datetime import datetime, timezone
from safe_plan import plan, FJORD_LOCATION_ID

NOW = datetime(2026, 10, 18, 20, tzinfo=timezone.utc)
IID = "gid://shopify/InventoryItem/123"


def fixture(cesu=0, vendor="Alpinus", qty=4):
    return {
        "supplier": [{"sku": "ABC-S", "quantity": qty, "verified_at": "2026-10-18T18:00:00Z"}],
        "shopify": [{"sku": "ABC-S", "vendor": vendor, "inventory_item_id": IID,
                     "fjord_available": 1, "cesu_available": cesu}],
        "approved_inventory_item_ids": [IID],
    }


class TestSafety(unittest.TestCase):
    def decision(self, data):
        return plan(data, now=NOW)["decisions"][0]

    def test_cesu_wins_and_unchanged(self):
        d = self.decision(fixture(cesu=3))
        self.assertEqual(d["action"], "PROPOSE_FJORD_ONLY")
        self.assertEqual(d["customer_lead_time_days"], 2)
        self.assertEqual(d["cesu_available_unchanged"], 3)
        self.assertEqual(d["location_id"], FJORD_LOCATION_ID)

    def test_alpinus_five_days(self):
        d = self.decision(fixture())
        self.assertEqual(d["customer_lead_time_days"], 5)
        self.assertEqual(d["stock_source_priority"], "ALPINUS")

    def test_other_vendor_never_touched(self):
        self.assertEqual(self.decision(fixture(vendor="Fjord Nansen"))["reason"], "different_vendor")

    def test_approval_required(self):
        x = fixture()
        x["approved_inventory_item_ids"] = []
        self.assertEqual(self.decision(x)["reason"], "not_approved_for_alpinus_inventory")

    def test_stale_snapshot_rejected(self):
        x = fixture()
        x["supplier"][0]["verified_at"] = "2026-10-15T18:00:00Z"
        self.assertEqual(self.decision(x)["reason"], "stale_or_future_supplier_quantity")

    def test_duplicate_shopify_sku_rejected(self):
        x = fixture()
        x["shopify"].append(x["shopify"][0].copy())
        self.assertEqual(self.decision(x)["reason"], "missing_or_ambiguous_shopify_variant")

    def test_missing_supplier_qty_rejected(self):
        self.assertEqual(self.decision(fixture(qty=None))["reason"], "invalid_supplier_quantity")


if __name__ == "__main__":
    unittest.main()
