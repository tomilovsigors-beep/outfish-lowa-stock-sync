import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = "https://outfish-lowa-stock-sync.onrender.com"

DRY_RUN_URL = f"{BASE_URL}/dry-run"
SYNC_URL = f"{BASE_URL}/sync"

ALLOWED_ACTIONS = {
    "no_change",
    "update",
    "skip_by_rule",
    "skip_lowa_inactive",
    "skip_missing_variant",
}


def fail(message, details=None):
    print()
    print("WEEKLY SYNC FAILED")
    print(message)

    if details is not None:
        print(
            json.dumps(
                details,
                ensure_ascii=False,
                indent=2,
            )
        )

    sys.exit(1)


def get_json(url):
    try:
        with urllib.request.urlopen(
            url,
            timeout=600,
        ) as response:
            body = response.read().decode("utf-8")

            if response.status != 200:
                fail(
                    f"GET {url} returned HTTP {response.status}",
                    body,
                )

            return json.loads(body)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        fail(
            f"GET {url} returned HTTP {exc.code}",
            body,
        )

    except Exception as exc:
        fail(
            f"GET {url} failed: {exc}"
        )


def post_sync(secret):
    request = urllib.request.Request(
        SYNC_URL,
        data=b"",
        method="POST",
        headers={
            "X-Sync-Secret": secret,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=900,
        ) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body)

            print()
            print(f"SYNC HTTP {response.status}")
            print(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            if response.status != 200:
                fail(
                    "Sync returned non-200",
                    data,
                )

            return data

    except urllib.error.HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            details = json.loads(body)
        except Exception:
            details = body

        fail(
            f"POST /sync returned HTTP {exc.code}",
            details,
        )

    except Exception as exc:
        fail(
            f"POST /sync failed: {exc}"
        )


def main():
    secret = os.getenv("SYNC_SECRET")

    if not secret:
        fail(
            "SYNC_SECRET is not configured"
        )

    print("Running weekly LOWA preflight...")

    dry_run = get_json(DRY_RUN_URL)

    counts = dry_run.get("counts", {})
    rows = dry_run.get("rows", [])

    print()
    print("Dry-run counts:")
    print(
        json.dumps(
            counts,
            ensure_ascii=False,
            indent=2,
        )
    )

    unexpected_rows = []

    for row in rows:
        action = row.get("action")

        if action not in ALLOWED_ACTIONS:
            unexpected_rows.append(row)

    if unexpected_rows:
        fail(
            "Unexpected/new mappings detected in dry-run",
            unexpected_rows,
        )

    unmapped_count = counts.get(
        "unmapped_product",
        0,
    )

    if unmapped_count:
        fail(
            "New unmapped product/model detected",
            {
                "unmapped_product": unmapped_count
            },
        )

    blocked_count = counts.get(
        "blocked_unlocked_mapping",
        0,
    )

    if blocked_count:
        fail(
            "Unlocked inventory mappings detected",
            {
                "blocked_unlocked_mapping": blocked_count
            },
        )

    update_count = counts.get(
        "update",
        0,
    )

    print()
    print(
        f"Preflight OK. Updates proposed: {update_count}"
    )

    result = post_sync(secret)

    changed = result.get(
        "changed",
        0,
    )

    if changed != update_count:
        fail(
            "Sync result does not match dry-run update count",
            {
                "dry_run_updates": update_count,
                "sync_changed": changed,
            },
        )

    print()
    print(
        f"WEEKLY SYNC SUCCESS: {changed} changes applied"
    )


if __name__ == "__main__":
    main()
