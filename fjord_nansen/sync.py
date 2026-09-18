import os
import sys
from urllib.parse import urljoin

import requests

DEFAULT_BASE_URL = "https://b2b.fjordnansen.com"
SIGNIN_PATH = "/signin.php"

REQUIRED_FOR_B2B = ("FJORD_B2B_LOGIN", "FJORD_B2B_PASSWORD")
WRITE_KEYS = ("SHOPIFY_STORE_DOMAIN", "SHOPIFY_ADMIN_ACCESS_TOKEN")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def is_placeholder(value: str) -> bool:
    return value in {"", "__SET_ME__", "SET_ME", "CHANGEME"}


def flag(name: str, default: bool = False) -> bool:
    raw = env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def status() -> dict:
    missing_b2b = [k for k in REQUIRED_FOR_B2B if is_placeholder(env(k))]
    missing_shopify = [k for k in WRITE_KEYS if is_placeholder(env(k))]
    return {
        "base_url": env("FJORD_B2B_BASE_URL", DEFAULT_BASE_URL),
        "supplier_sheet_id_set": not is_placeholder(env("FJORD_SUPPLIER_SHEET_ID")),
        "b2b_credentials_ready": not missing_b2b,
        "missing_b2b": missing_b2b,
        "shopify_credentials_ready": not missing_shopify,
        "missing_shopify": missing_shopify,
        "dry_run": flag("DRY_RUN", True),
        "shopify_write_enabled": flag("SHOPIFY_WRITE_ENABLED", False),
    }


def check_public_signin(base_url: str) -> None:
    url = urljoin(base_url.rstrip("/") + "/", SIGNIN_PATH.lstrip("/"))
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Outfish-Fjord-Supplier-Sync/0.1"},
    )
    response.raise_for_status()
    body = response.text.lower()
    if "password" not in body or "login" not in body:
        raise RuntimeError("Fjord sign-in page was reachable but expected login fields were not found")
    print(f"Fjord public sign-in reachable: HTTP {response.status_code}")


def main() -> int:
    cfg = status()
    print("Fjord Nansen supplier sync bootstrap")
    print(f"Supplier sheet configured: {cfg['supplier_sheet_id_set']}")
    print(f"DRY_RUN={cfg['dry_run']}")
    print(f"SHOPIFY_WRITE_ENABLED={cfg['shopify_write_enabled']}")

    check_public_signin(cfg["base_url"])

    if not cfg["b2b_credentials_ready"]:
        print("B2B credentials are not configured yet; safe no-op.")
        print("Missing: " + ", ".join(cfg["missing_b2b"]))
        return 0

    if cfg["shopify_write_enabled"] and cfg["dry_run"]:
        raise RuntimeError("Invalid safety state: SHOPIFY_WRITE_ENABLED=true while DRY_RUN=true")

    if cfg["shopify_write_enabled"] and not cfg["shopify_credentials_ready"]:
        raise RuntimeError(
            "Shopify writes requested but credentials are missing: "
            + ", ".join(cfg["missing_shopify"])
        )

    # Deliberately no login POST or Shopify mutation yet.
    # The authenticated B2B flow will be implemented only after the first
    # credentialed supplier audit identifies the real form/actions, catalogue
    # structure, SKU/EAN fields, warehouse stock fields, RRP and image sources.
    print("Credentials detected. Bootstrap is ready for authenticated B2B audit.")
    print("No supplier login POST or Shopify write was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
