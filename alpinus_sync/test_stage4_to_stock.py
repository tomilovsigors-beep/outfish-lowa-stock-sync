"""Offline regression tests for stage4 event conversion."""
import unittest
from stage4_to_stock import convert

P = {"event":"stage4_exact_product","supplier_product_id":"123",
     "sku":"PARENT-SKU","variants":[{"size":"M","supply_id":"500","qty":3}]}
S = {"event":"stage4_exact_summary","processed":1,"classification_counts":{}}
M = [{"supplier_product_id":"123","size":"M","supply_id":"500","shopify_variant_sku":"VARIANT-M"}]


class TestConversion(unittest.TestCase):
    def test_exact_approved_mapping_only(self):
        output = convert([P,S],M,"2026-10-18T18:00:00Z")
        self.assertEqual(output["supplier"][0]["sku"],"VARIANT-M")
        self.assertEqual(output["supplier"][0]["quantity"],3)

    def test_no_parent_sku_guessing(self):
        self.assertEqual(convert([P,S],[],"2026-10-18T18:00:00Z")["supplier"],[])

    def test_partial_batch_denied(self):
        with self.assertRaises(ValueError):
            convert([P,{"event":"stage4_exact_summary","processed":50,"classification_counts":{}}],M)

    def test_error_denied(self):
        with self.assertRaises(ValueError):
            convert([P,S,{"event":"stage4_exact_error","error":"auth"}],M)

    def test_duplicate_mapping_denied(self):
        with self.assertRaises(ValueError):
            convert([P,S],M+M)


if __name__ == "__main__":
    unittest.main()
