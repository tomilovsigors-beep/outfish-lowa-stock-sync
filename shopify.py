import requests

PRODUCT_QUERY = r'''
query ProductInventory($id: ID!) {
  product(id: $id) {
    id title
    variants(first: 100) {
      nodes {
        id title
        selectedOptions { name value }
        inventoryItem {
          id
          inventoryLevels(first: 20) {
            nodes {
              location { id name }
              quantities(names: ["on_hand", "available", "committed"]) { name quantity }
            }
          }
        }
      }
    }
  }
}
'''

SET_MUTATION = r'''
mutation SetInventory($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup { createdAt reason referenceDocumentUri changes { name delta } }
    userErrors { code field message }
  }
}
'''

class Shopify:
    def __init__(self, domain, token, version="2026-07"):
        self.url=f"https://{domain}/admin/api/{version}/graphql.json"
        self.headers={"X-Shopify-Access-Token": token, "Content-Type":"application/json"}
    def gql(self, query, variables):
        r=requests.post(self.url, headers=self.headers, json={"query":query,"variables":variables}, timeout=60)
        r.raise_for_status(); data=r.json()
        if data.get("errors"): raise RuntimeError(data["errors"])
        return data["data"]
    def product_inventory(self, product_id):
        return self.gql(PRODUCT_QUERY,{"id":product_id})["product"]
    def set_on_hand(self, quantities, reference_uri):
        inp={"name":"on_hand","reason":"correction","referenceDocumentUri":reference_uri,"quantities":quantities}
        return self.gql(SET_MUTATION,{"input":inp})["inventorySetQuantities"]
