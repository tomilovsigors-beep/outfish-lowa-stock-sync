import os
import time

import requests


PRODUCT_QUERY = r'''
query ProductInventory($id: ID!) {
  product(id: $id) {
    id
    title
    variants(first: 100) {
      nodes {
        id
        title
        selectedOptions {
          name
          value
        }
        inventoryItem {
          id
          inventoryLevels(first: 20) {
            nodes {
              location {
                id
                name
              }
              quantities(
                names: ["on_hand", "available", "committed"]
              ) {
                name
                quantity
              }
            }
          }
        }
      }
    }
  }
}
'''


SET_MUTATION = r'''
mutation SetInventory(
  $input: InventorySetQuantitiesInput!,
  $idempotencyKey: String!
) {
  inventorySetQuantities(input: $input)
    @idempotent(key: $idempotencyKey) {
    inventoryAdjustmentGroup {
      createdAt
      reason
      referenceDocumentUri
      changes {
        name
        delta
        quantityAfterChange
      }
    }
    userErrors {
      code
      field
      message
    }
  }
}
'''


_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def get_access_token():
    now = time.time()

    if (
        _token_cache["access_token"]
        and now < _token_cache["expires_at"] - 300
    ):
        return _token_cache["access_token"]

    domain = os.getenv("SHOPIFY_STORE_DOMAIN")
    client_id = os.getenv("SHOPIFY_CLIENT_ID")
    client_secret = os.getenv("SHOPIFY_CLIENT_SECRET")

    if not domain:
        raise RuntimeError(
            "SHOPIFY_STORE_DOMAIN is not configured"
        )

    if not client_id:
        raise RuntimeError(
            "SHOPIFY_CLIENT_ID is not configured"
        )

    if not client_secret:
        raise RuntimeError(
            "SHOPIFY_CLIENT_SECRET is not configured"
        )

    url = (
        f"https://{domain}/admin/oauth/access_token"
    )

    response = requests.post(
        url,
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if "access_token" not in data:
        raise RuntimeError(
            f"Shopify did not return access_token: {data}"
        )

    token = data["access_token"]
    expires_in = int(
        data.get("expires_in", 86400)
    )

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = (
        now + expires_in
    )

    return token


class Shopify:
    def __init__(
        self,
        domain=None,
        version=None,
    ):
        self.domain = (
            domain
            or os.getenv(
                "SHOPIFY_STORE_DOMAIN",
                "153ac6-2.myshopify.com",
            )
        )

        self.version = (
            version
            or os.getenv(
                "SHOPIFY_API_VERSION",
                "2026-07",
            )
        )

        self.url = (
            f"https://{self.domain}"
            f"/admin/api/{self.version}"
            f"/graphql.json"
        )

    def gql(
        self,
        query,
        variables=None,
    ):
        token = get_access_token()

        response = requests.post(
            self.url,
            headers={
                "X-Shopify-Access-Token": (
                    token
                ),
                "Content-Type": (
                    "application/json"
                ),
            },
            json={
                "query": query,
                "variables": (
                    variables or {}
                ),
            },
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):
            raise RuntimeError(
                data["errors"]
            )

        return data["data"]

    def product_inventory(
        self,
        product_id,
    ):
        data = self.gql(
            PRODUCT_QUERY,
            {
                "id": product_id,
            },
        )

        product = data["product"]

        if product is None:
            raise RuntimeError(
                "Shopify product not found: "
                f"{product_id}"
            )

        return product

    def set_on_hand(
        self,
        quantities,
        reference_uri,
        idempotency_key,
    ):
        input_data = {
            "name": "on_hand",
            "reason": "correction",
            "referenceDocumentUri": (
                reference_uri
            ),
            "quantities": quantities,
        }

        data = self.gql(
            SET_MUTATION,
            {
                "input": input_data,
                "idempotencyKey": (
                    idempotency_key
                ),
            },
        )

        return data[
            "inventorySetQuantities"
        ]
