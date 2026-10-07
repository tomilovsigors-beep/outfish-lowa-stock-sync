import os
import uuid

import requests
from flask import Flask, jsonify, request

from supplier import parse_xlsx_bytes
from shopify import Shopify
from engine import (
    make_dry_run,
    build_sync_batch,
)


app = Flask(__name__)


def shop():
    return Shopify()


def supplier_rows():
    url = os.getenv(
        "SUPPLIER_XLSX_URL"
    )

    if not url:
        raise RuntimeError(
            "SUPPLIER_XLSX_URL "
            "is not configured"
        )

    response = requests.get(
        url,
        timeout=60,
    )

    response.raise_for_status()

    return parse_xlsx_bytes(
        response.content
    )


@app.get("/")
def index():
    return {
        "ok": True,
        "service": (
            "outfish-lowa-stock-sync"
        ),
        "health": "/health",
        "dryRun": "/dry-run",
        "scopes": "/scopes",
        "liveSyncEnabled": (
            os.getenv(
                "ALLOW_LIVE_SYNC",
                "false",
            ).lower()
            == "true"
        ),
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": (
            "outfish-lowa-stock-sync"
        ),
        "liveSyncEnabled": (
            os.getenv(
                "ALLOW_LIVE_SYNC",
                "false",
            ).lower()
            == "true"
        ),
    }


@app.get("/scopes")
def scopes():
    query = """
    query {
      currentAppInstallation {
        accessScopes {
          handle
        }
      }
    }
    """

    data = shop().gql(query)

    scopes = [
        item["handle"]
        for item
        in data[
            "currentAppInstallation"
        ]["accessScopes"]
    ]

    return jsonify(
        {
            "scopes": scopes,
            "hasWriteInventory": (
                "write_inventory"
                in scopes
            ),
        }
    )


@app.get("/dry-run")
def dry_run():
    rows = make_dry_run(
        supplier_rows(),
        shop(),
    )

    counts = {}

    for row in rows:
        action = row["action"]

        counts[action] = (
            counts.get(
                action,
                0,
            )
            + 1
        )

    return jsonify(
        {
            "counts": counts,
            "rows": rows,
        }
    )


@app.post("/sync")
def sync():
    if (
        os.getenv(
            "ALLOW_LIVE_SYNC",
            "false",
        ).lower()
        != "true"
    ):
        return {
            "error": (
                "live sync disabled"
            )
        }, 403

    secret = os.getenv(
        "SYNC_SECRET"
    )

    if (
        not secret
        or request.headers.get(
            "X-Sync-Secret"
        )
        != secret
    ):
        return {
            "error": "forbidden"
        }, 403

    rows = make_dry_run(
        supplier_rows(),
        shop(),
    )

    batch, rejected = (
        build_sync_batch(rows)
    )

    if rejected:
        return jsonify(
            {
                "error": (
                    "unlocked mappings "
                    "present"
                ),
                "blocked": rejected,
                "proposed": batch,
            }
        ), 409

    if not batch:
        return {
            "ok": True,
            "message": (
                "nothing to change"
            ),
            "changed": 0,
        }

    client = shop()
    all_results = []

    for i in range(
        0,
        len(batch),
        50,
    ):
        part = batch[
            i:i + 50
        ]

        operation_id = str(
            uuid.uuid4()
        )

        reference_uri = (
            "gid://"
            "outfish-lowa-stock-sync/"
            f"SyncJob/{operation_id}"
        )

        result = client.set_on_hand(
            part,
            reference_uri,
            operation_id,
        )

        if result.get(
            "userErrors"
        ):
            return jsonify(
                {
                    "error": (
                        "shopify "
                        "rejected batch"
                    ),
                    "details": (
                        result[
                            "userErrors"
                        ]
                    ),
                    "reference": (
                        reference_uri
                    ),
                    "idempotencyKey": (
                        operation_id
                    ),
                }
            ), 409

        all_results.append(
            result
        )

    return jsonify(
        {
            "ok": True,
            "changed": len(batch),
            "results": all_results,
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "10000",
            )
        ),
    )
