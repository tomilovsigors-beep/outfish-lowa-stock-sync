# Fjord Nansen supplier sync bootstrap

Isolated bootstrap for the Fjord Nansen B2B → Supplier Master → Shopify pipeline.

## Architecture

Fjord Nansen B2B → normalized supplier records → Google Sheet Supplier Master → Shopify.

The first stage is intentionally read-only. No Shopify write is permitted until the B2B field mapping, generated SKU rules, warehouse mapping, translations, content prompts and image workflow are reviewed.

## Required Render environment variables

- `FJORD_B2B_BASE_URL=https://b2b.fjordnansen.com`
- `FJORD_B2B_LOGIN` — secret, set in Render only
- `FJORD_B2B_PASSWORD` — secret, set in Render only
- `FJORD_SUPPLIER_SHEET_ID=1RRsV9mHZMV3gfQGIJq1OGQgc0qyI4zqJ-yv9Fg9Ygl8`
- `GOOGLE_SERVICE_ACCOUNT_JSON` — secret, needed when automatic Sheet writes are enabled
- `SHOPIFY_STORE_DOMAIN` — myshopify domain for server-side automation
- `SHOPIFY_ADMIN_ACCESS_TOKEN` — secret, needed when Shopify writes are enabled
- `DRY_RUN=true`
- `SHOPIFY_WRITE_ENABLED=false`

## Safety

- Never fabricate EAN/GTIN.
- Missing supplier SKU must get a deterministic `FN-AUTO-...` SKU based on a stable supplier identity.
- Existing Outfish stock has priority over supplier stock.
- Initial product creation/update stays disabled until an audited B2B mapping is committed.
- Supplier credentials are read only from environment variables.
- The script exits safely while credentials are not configured.

## Current phase

Bootstrap/configuration only. After B2B credentials are added to Render, run the supplier audit before enabling any writes.
