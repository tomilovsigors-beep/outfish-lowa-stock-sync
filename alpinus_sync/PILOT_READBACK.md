# Alpinus live pilot — verified Shopify identity mapping

Last manual supplier verification: 2026-10-18 (B2B browser). This is a
mapping and audit record, **not a current supplier quantity feed**.
No scheduled job may reuse the quantities below without a NEW authenticated
B2B read and an exact match of supplier SKU, variant size, and Shopify item.

## Selenga — supplier model NQ35000
B2B: https://alpinusgroup.com/kurtka-damska-2-warstwowa-alpinus-selenga/3-61-1074
Shopify product gid://shopify/Product/10750909251922
- S: SKU NQ35000-S; inventoryItem gid://shopify/InventoryItem/55376446226770; B2B supply 753979; pilot B2B qty 17.
- L: SKU NQ35000-L; inventoryItem gid://shopify/InventoryItem/55376446292306; B2B supply 753977; pilot B2B qty 6.
Other sizes were not confirmed by pilot and must not be updated from this source.

## Urmia — supplier model QN35045
B2B: https://alpinusgroup.com/plaszcz-przeciwdeszczowy-damski-alpinus-urmia-qn35/3-61-1124
Shopify product gid://shopify/Product/10750891655506
- XS: QN35045XS; gid://shopify/InventoryItem/55376409788754; pilot B2B qty 16
- S: QN35045S; gid://shopify/InventoryItem/55376409821522; pilot B2B qty 58
- M: QN35045M; gid://shopify/InventoryItem/55376409854290; pilot B2B qty 61
- L: QN35045L; gid://shopify/InventoryItem/55376409887058; pilot B2B qty 84
- XL: QN35045XL; gid://shopify/InventoryItem/55376409919826; pilot B2B qty 49
- 2XL: QN350452XL; gid://shopify/InventoryItem/55376409952594; pilot B2B qty 23
B2B response did NOT prove unique per-size supply IDs or EAN mapping for Urmia.
Never treat repeated numbers in page UI as supply IDs.

Shopify inventory destination for both:
gid://shopify/Location/107805770066 (Cēsu 18, Fjord Nansen).

ALWAYS preserve Cēsu Veikals:
gid://shopify/Location/84891861330.
Never change LOWA gid://shopify/Location/107817075026.

Pilot readback confirmed expected supplier values in Fjord Nansen and unchanged
Cēsu/LOWA. This file deliberately lives only on the feature branch; don't
merge or activate a scheduled job until the supplier auth, daily capture,
Shopify variant matching, storefront delivery messaging, and stale-data failure
path are tested end to end.
