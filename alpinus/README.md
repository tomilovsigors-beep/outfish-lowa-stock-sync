# Outfish Alpinus B2B integration

Purpose: connect the authenticated Alpinus Group B2B catalog to Outfish Shopify inventory.

## Safety stage

Current code is **probe-only**:

- opens `https://alpinusgroup.com`;
- discovers the login form dynamically;
- authenticates only when credentials exist in environment variables;
- confirms login using post-login markers;
- does **not** crawl the catalog yet;
- does **not** write anything to Shopify.

This is intentional. The first authenticated run is used to learn the Comarch B2B catalog/stock structure before import and daily stock sync are enabled.

## Secrets

Keep these only in Render environment variables:

- `ALPINUS_B2B_LOGIN`
- `ALPINUS_B2B_PASSWORD`

Non-secret defaults:

- `ALPINUS_BASE_URL=https://alpinusgroup.com`
- Shopify target: `153ac6-2.myshopify.com`

Never commit supplier credentials to GitHub.

## Planned flow

Alpinus B2B → normalized products/variants/EAN/SKU/stock → review gate → Shopify product import → daily inventory reconciliation.

Existing Outfish rules remain the default safety policy:

- existing product content and prices are not overwritten by stock refresh;
- stock is matched by stable supplier identifiers (prefer EAN/SKU);
- unknown/unmapped variants stop the write stage rather than guessing;
- supplier outages result in a safe no-op, never a mass zeroing.
