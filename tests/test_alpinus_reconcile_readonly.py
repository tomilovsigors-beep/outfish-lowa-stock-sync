import unittest
from decimal import Decimal
from alpinus.reconcile_readonly import decide, index_shopify

class Tests(unittest.TestCase):
    def setUp(self):
        self.active = {"id":"active-1","status":"ACTIVE","variants":[{"sku":"ABC","barcode":"5901234567890"}]}
        self.draft = {"id":"draft-1","status":"DRAFT","variants":[{"sku":"DEF","barcode":"5901234567891"}]}
        self.sku, self.ean = index_shopify([self.active,self.draft])
    def row(self, sku="ABC", price="100"):
        return {"supplier_product_id":"1","symbol":sku,"eans":[],"rrp_pln":price}
    def test_active_never_written(self):
        self.assertEqual(decide(self.row(),self.sku,self.ean,Decimal(".25"))["decision"],"KEEP_ACTIVE")
    def test_draft_needs_completion(self):
        self.assertEqual(decide(self.row("DEF"),self.sku,self.ean,Decimal(".25"))["decision"],"COMPLETE_DRAFT")
    def test_under_20(self):
        self.assertEqual(decide(self.row("NEW","70"),self.sku,self.ean,Decimal(".25"))["decision"],"SKIP_UNDER_20")
    def test_equal_20_allowed(self):
        self.assertEqual(decide(self.row("NEW","80"),self.sku,self.ean,Decimal(".25"))["decision"],"HOLD_UNMATCHED")
    def test_missing_price_held(self):
        self.assertEqual(decide(self.row("NEW",None),self.sku,self.ean,Decimal(".25"))["decision"],"HOLD_PRICE")
    def test_ambiguous_match(self):
        sku,ean=index_shopify([self.active,{"id":"other","status":"DRAFT","variants":[{"sku":"ABC"}]}])
        self.assertEqual(decide(self.row(),sku,ean,Decimal(".25"))["decision"],"HOLD_AMBIGUOUS")

if __name__=="__main__":
    unittest.main()
