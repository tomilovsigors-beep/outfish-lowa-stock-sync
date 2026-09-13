import os
import time
import requests


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

    shop = os.environ["SHOPIFY_STORE_DOMAIN"]
    client_id = os.environ["SHOPIFY_CLIENT_ID"]
    client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]

    url = f"https://{shop}/admin/oauth/access_token"

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

    token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))

    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + expires_in

    return token


class ShopifyClient:
    def __init__(self):
        self.shop = os.environ["SHOPIFY_STORE_DOMAIN"]
        self.api_version = os.environ.get(
            "SHOPIFY_API_VERSION",
            "2026-07",
        )

    def graphql(self, query, variables=None):
        token = get_access_token()

        url = (
            f"https://{self.shop}/admin/api/"
            f"{self.api_version}/graphql.json"
        )

        response = requests.post(
            url,
            headers={
                "X-Shopify-Access-Token": token,
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "variables": variables or {},
            },
            timeout=60,
        )

        response.raise_for_status()
        payload = response.json()

        if payload.get("errors"):
            raise RuntimeError(payload["errors"])

        return payload["data"]
