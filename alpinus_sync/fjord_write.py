"""Guarded Shopify stock update at exactly one warehouse."""
from alpinus_sync.render_end_to_end import shopify

FJORD = "gid://shopify/Location/107805770066"

def apply_fjord_change(inventory_item_id, old_quantity, new_quantity):
    if not inventory_item_id.startswith("gid://shopify/InventoryItem/"):
        raise ValueError("unapproved_inventory_item")
    if type(new_quantity) is not int or new_quantity < 0:
        raise ValueError("invalid_quantity")
    if type(old_quantity) is not int or old_quantity < 0:
        raise ValueError("invalid_old_quantity")
    mutation = """mutation($input:InventorySetQuantitiesInput!){
      inventorySetQuantities(input:$input){userErrors{field message code}}
    }"""
    variables = {"input":{
       "name":"available","reason":"correction",
       "ignoreCompareQuantity":False,
       "quantities":[{"inventoryItemId":inventory_item_id,
        "locationId":FJORD,"quantity":new_quantity,
        "compareQuantity":old_quantity}]}}
    result=shopify(mutation, variables)
    errors=result["inventorySetQuantities"]["userErrors"]
    if errors:
        raise RuntimeError("shopify_quantity_rejected")
