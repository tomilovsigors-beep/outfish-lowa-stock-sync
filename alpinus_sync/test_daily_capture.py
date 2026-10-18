"""Offline checks for authenticated B2B stock extraction."""
import unittest
from alpinus_sync.daily_capture import parse_detail, PRODUCTS


def page(code, sizes):
    rows = "".join(
        '<div class="attribute-button-ui last-lvl-ui table-row-ui" data-supply-id="%s">'
        '<span class="name-column-ui supply-value-lq">%s</span>'
        '<span data-stock-value="%s"></span></div>' % (i, size, qty)
        for i, (size, qty) in enumerate(sizes, 100)
    )
    return "<html><body><h1>Alpinus %s</h1>%s</body></html>" % (code, rows)


class SupplierReadOnlyTests(unittest.TestCase):
    def test_selenga_exact_sizes(self):
        rows = parse_detail(page("NQ35000", [("S", 17), ("L", 6)]), PRODUCTS[0])
        self.assertEqual({r["sku"]: r["quantity"] for r in rows},
                         {"NQ35000-S": 17, "NQ35000-L": 6})

    def test_urmia_six_sizes(self):
        sizes = [("XS",16),("S",58),("M",61),("L",84),("XL",49),("2XL",23)]
        rows = parse_detail(page("QN35045",sizes),PRODUCTS[1])
        self.assertEqual(len(rows),6)
        self.assertEqual(sum(r["quantity"] for r in rows),291)

    def test_missing_size_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_detail(page("NQ35000",[("S",17)]),PRODUCTS[0])

    def test_duplicated_size_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_detail(page("NQ35000",[("S",17),("S",3),("L",6)]),PRODUCTS[0])

    def test_non_numeric_quantity_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_detail(page("NQ35000",[("S","duzo"),("L",6)]),PRODUCTS[0])

    def test_supplier_wrong_product_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_detail(page("OTHER",[("S",17),("L",6)]),PRODUCTS[0])

    def test_logged_out_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_detail("Dostęp tylko dla zalogowanych kontrahentów NQ35000",PRODUCTS[0])


if __name__ == "__main__":
    unittest.main()
