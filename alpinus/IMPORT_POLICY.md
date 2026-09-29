# Alpinus import policy for Outfish

This file is the hard safety contract for the Alpinus supplier integration.

## Existing Shopify products

If an Alpinus product/variant already exists in Shopify, DO NOT modify its product card.

Blocked for existing products:
- title
- handle
- description/body HTML
- SEO title
- SEO description
- vendor
- product type
- tags
- collections
- images/media
- translations
- price
- compare-at price
- cost
- publication status
- options / variant structure

Existing product cards are immutable under this integration.

Inventory policy for existing products will be handled separately only after explicit SKU/EAN ownership matching is validated.

## New products

Create only supplier products that are genuinely in stock.

For apparel / footwear / sized clothing:
- require at least 2 distinct in-stock sizes before product creation;
- never create unavailable sizes as sellable stock;
- never infer stock from a generic "available" badge if exact variant stock is not confirmed.

Target Shopify inventory location for new Alpinus stock:
- virtual warehouse: Fjord Nansen
- location id: gid://shopify/Location/107805770066
- customer-facing delivery promise is managed by the existing Outfish configuration and must remain 5 working days;
- never expose "Fjord Nansen" as supplier/warehouse text to customers.

## Pricing

Supplier prices are in PLN.

For every new product/variant capture both:
1. supplier purchase cost (not customer-visible);
2. supplier RRP.

Conversion:
- use current PLN -> EUR FX rate at import run time;
- convert RRP to EUR;
- round final customer RRP to a whole EUR amount (no cents);
- preserve the original PLN values and FX rate in audit/source data;
- do not overwrite prices of existing Shopify products.

Cost must be stored in Shopify's cost field / inventory item cost where supported, not in customer-visible product copy.

## Media

For new products:
- import all verified supplier/manufacturer product images available for the exact SKU/model/variant;
- include gallery images available on the supplier product page;
- avoid unrelated colour/variant imagery unless explicitly tied to that exact product.

## Collections / navigation

All new products must be mapped into existing Outfish collections/categories.
Do not create random duplicate category names.
Base collection names remain English.

## Content languages

Base product card language: English.

Then create:
- Latvian: native-quality copy, informed by Latvian search demand from Google Search Console and available Google Ads keyword/search data;
- Russian: native-quality copy using the same verified product facts.

Do not translate literally. Each language is written independently from the same verified facts.

## Product-content source rules

Use only verified exact-product information:
- exact manufacturer page for the exact SKU/model/variant;
- supplier product data;
- exact technical specifications;
- official feature descriptions / tests / dimensions / materials / ratings.

Never invent facts.
Never borrow specifications from a neighbouring size, colour or similar model unless confirmed for the exact product.

Preserve all meaningful manufacturer facts and explain practical benefits only when supported by the source.

## Shopify content rules

For NEW products only:
- keyword-first English title;
- detailed premium technical HTML description;
- all meaningful specifications preserved;
- SEO title and meta description;
- all verified photos;
- exact SKU/EAN/variant values;
- existing Outfish collection mapping;
- EN + LV + RU localized content.

For EXISTING products:
- no card rewrite of any kind.

## Audit gates before Shopify write

The write stage must stop when any of these is true:
- supplier authentication not confirmed;
- product stock cannot be verified;
- SKU/EAN identity is ambiguous;
- a product appears to already exist but matching is not certain;
- apparel/footwear has fewer than 2 in-stock sizes;
- RRP or purchase cost is missing when pricing requires it;
- FX rate is unavailable;
- image set cannot be reliably tied to the exact product;
- category mapping is unresolved.

When uncertain: skip, log, and review. Never guess.
