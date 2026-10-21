# OUTFiSH × Alpinus B2B × Shopify — engineering handoff for Claude
**Prepared 2026-10-21.** Source of truth: actual GitHub code, Render service metadata and prior observed Shopify/B2B operations. **NOT FINISHED.** Do not claim automated sync is operational until actual authenticated supplier read, Shopify dry-run, live CAS write and readback succeed.

## 1. Goal and hard safety requirements
Storefront: https://outfish.lv (Shopify). Supplier: https://alpinusgroup.com (Polish Comarch e-Sklep based Alpinus B2B website). Goal: once/day obtain exact numeric stock *per variant/size* from authenticated supplier, match pre-approved Shopify SKU + inventoryItem ID, and update only Alpinus virtual warehouse inventory; verify the new Shopify quantity by API readback. Never touch existing product title, description, images, prices, SEO, handle or other supplier inventories. Do not create/publish products absent verified EAN, variant, pricing, stock, photos.

Locations:
- Priority physical store **Cēsu iela 18, Veikals**, Shopify Location `gid://shopify/Location/84891861330`: NEVER MUTATE; delivery expected 1–2 days.
- Alpinus virtual location currently named **Cēsu 18, (Fjord Nansen)**, `gid://shopify/Location/107805770066`: ONLY permitted stock-write target; delivery expected 5 days.
- Other LOWA virtual location **Cēcu 18, (Lowa)**, `gid://shopify/Location/107817075026`: NEVER MUTATE.
- A single size may be simultaneously available at Cēsu and supplier; physical store takes fulfillment/delivery priority. **Storefront variant-specific delivery promises have NOT been implemented/verified.** Code's lead-time field in read-only planner is not storefront configuration.
- Fail closed if authentication uncertain, sizes/quantities nonnumeric, mappings duplicate/ambiguous, or source stale. One daily cron, no five-minute cron. Keep writes disabled unless all prerequisites verified.

## 2. Project links
GitHub: https://github.com/tomilovsigors-beep/outfish-lowa-stock-sync
Active development branch: `feature/alpinus-location-safe-planner-20261018`
Branch code: https://github.com/tomilovsigors-beep/outfish-lowa-stock-sync/tree/feature/alpinus-location-safe-planner-20261018
Draft PR #1: https://github.com/tomilovsigors-beep/outfish-lowa-stock-sync/pull/1
Offline tests GitHub Action examples: https://github.com/tomilovsigors-beep/outfish-lowa-stock-sync/actions/runs/39217119617 (successful, 24+ fixture scenarios in past workflow; does NOT prove live B2B login or Shopify write).
Render workspace `tea-da6tqdgn74is73ek62jg`, Frankfurt.
Active daily cron https://dashboard.render.com/cron/crn-dau3bk6k1f9s73a6ibig
Suspended 5-minute cron https://dashboard.render.com/cron/crn-dau3nlek1f9s73a7qpu0
Alpinus Selenga B2B https://alpinusgroup.com/kurtka-damska-2-warstwowa-alpinus-selenga/3-61-1074
Alpinus Urmia B2B https://alpinusgroup.com/plaszcz-przeciwdeszczowy-damski-alpinus-urmia-qn35/3-61-1124
Outfish Selenga https://outfish.lv/products/sieviesu-membranas-jaka-10000-mitrumizturiba-2-slani-alpinus
Outfish Urmia https://outfish.lv/products/sieviesu-lietu-metelis-8000-mm-alpinus

## 3. Verified Render configuration as of 2026-10-21
DAILY: `outfish-alpinus-probe`, service ID `crn-dau3bk6k1f9s73a6ibig`.
- suspended: **not_suspended**
- branch: `feature/alpinus-location-safe-planner-20261018`, autoDeploy yes
- schedule: `15 3 * * *`, **03:15 UTC daily** (Riga time varies with DST)
- build command: `pip install -r alpinus/requirements.txt && python -m playwright install chromium`
- start command: `python -m playwright install chromium && python -m alpinus_sync.daily_sync`
- 0.5c-512mb starter, Frankfurt EU Central.
- `ALPINUS_ENABLE_WRITES=OFF` was set via Render API with merge (no other env vars replaced), so code is dry-run only. Reconfirm before any enablement.
- Latest known deployed git commit `80770b69bec5f0cd79cd9a1958ce8042985f4584`, Render deployment `dep-dbc9i1psrm7s738360t0`, status LIVE since 2026-10-21 10:51 UTC. **No confirmed successful dry-run for this commit**. Previous bot tried triggering via browser automation but its result was not received, and subsequent Render log query had no new run.
- This cron still executes each day but historically fails; a failing scheduled job is not a working integration.

5-MINUTE: `outfish-alpinus-readonly-test`, ID `crn-dau3nlek1f9s73a7qpu0`.
- schedule `*/5 * * * *`, branch main, old `python alpinus/probe.py`; **suspended:user**, confirmed via Render API after browser UI Suspend. Do not resume.

## 4. Existing GitHub files and architecture (all paths relative repo)
`alpinus_sync/daily_sync.py`: LIVE ENTRYPOINT. Calls `capture()`, reads two supplier product pages through Playwright `BrowserContext.request.get`, parses approved size quantities, then Shopify snapshot via Admin GraphQL. If `ALPINUS_ENABLE_WRITES == "YES"`, loops 8 allowed sizes and CAS-writes changes via `fjord_write.apply_fjord_change`, rereads Shopify and checks Fjord and Cēsu values. Otherwise returns `DRY_RUN_VERIFIED` only after supplier+Shopify read validations. Logs sanitized `FAILED_CLOSED` with exception type and short detail.
`alpinus_bulk/app.py`: Playwright Chromium launcher and Alpinus B2B login. Reads credentials from Render `ALPINUS_B2B_LOGIN` and `ALPINUS_B2B_PASSWORD`. Latest commit `80770b69` attempts normal JS login, checks HTML for literal `Wyloguj` or `Jesteś zalogowany`, then attempts a **UNVERIFIED** Comarch-style POST (form `__action=Customer/Login`, `__csrf`, credentials). There is no evidence this fallback is supported by this exact Alpinus host, correct for this version or safe to rely on. **Do NOT assume success or that endpoint is documented for Alpinus.** Needs actual network inspection of native browser form flow or official supplier API documentation. Do not fake log-in success by removing positive verification.
`alpinus_sync/daily_capture.py`: read-only `PRODUCTS` mapping and parser. Requires product code text + all 2 Selenga sizes and all 6 Urmia sizes; parse CSS `.attribute-button-ui.last-lvl-ui.table-row-ui`, `.name-column-ui.supply-value-lq`, `[data-stock-value]`. Fixture tested, not proved on Render authenticated HTML.
`alpinus_sync/fjord_write.py`: one-location Shopify GraphQL `inventorySetQuantities` with `ignoreCompareQuantity:false`, `compareQuantity`, target Fjord ID only. NOT LIVE VERIFIED. Its own validation only checks InventoryItem GID prefix, but caller's `APPROVED` map is strict. Reason `correction`.
`alpinus_sync/render_end_to_end.py`: earlier read-only B2B+Shopify verifier, contains Admin GraphQL read query/client, shares credentials `SHOPIFY_SHOP_DOMAIN` and `SHOPIFY_ADMIN_ACCESS_TOKEN`. Not the current cron entrypoint.
`alpinus_sync/safe_plan.py`: standalone READ-ONLY safety plan: exact SKUs, vendor Alpinus, approved IIDs, freshness 26h, locations, delivery hints. **Not used by current daily_sync.py.** Current live pipeline lacks this age check.
`alpinus_sync/stage4_to_stock.py`: Stage4 conversion requiring explicit per-size mapping; read-only.
`alpinus_sync/render_preflight.py`: B2B read-only preflight; not active.
`alpinus_sync/test_daily_capture.py`, `test_pipeline.py`, `test_safe_plan.py`, `test_stage4_to_stock.py`: fixtures/unit tests.
`.github/workflows/alpinus-offline-tests.yml`: unittest discovery; historically success. Needs actual integration tests/mocks for new login, CAS and failures.
`alpinus/requirements.txt`: playwright==1.55.0, beautifulsoup4==4.12.3.
`alpinus/probe.py`: old legacy cron program on main, previously did no stock sync.
`alpinus_bulk/stage4_variants_batch7.py`: bulk variant/EAN/supply_id read-only extraction.

## 5. Hardcoded approved variants and observed manual Shopify results
Both product stocks were **manually** changed via connected Shopify set_inventory earlier; never describe them as automatic. Supplier numeric amounts came from earlier authenticated TinyFish readings and are now STALE; do not reuse as a new supplier snapshot.

| Product | Supplier model | Size | Exact Shopify SKU | InventoryItem ID suffix | Historical Fjord qty set | Historical Cēsu qty read |
|---|---|---|---|---|---:|---:|
| Selenga product `gid://shopify/Product/10750909251922` | NQ35000 | S | NQ35000-S | 55376446226770 | 17 | 1 |
| Selenga | NQ35000 | L | NQ35000-L | 55376446292306 | 6 | 1 |
| Urmia product `gid://shopify/Product/10750891655506` | QN35045 | XS | QN35045XS | 55376409788754 | 16 | 1 |
| Urmia | QN35045 | S | QN35045S | 55376409821522 | 58 | 2 |
| Urmia | QN35045 | M | QN35045M | 55376409854290 | 61 | 0 |
| Urmia | QN35045 | L | QN35045L | 55376409887058 | 84 | 1 |
| Urmia | QN35045 | XL | QN35045XL | 55376409919826 | 49 | 1 |
| Urmia | QN35045 | 2XL | QN350452XL | 55376409952594 | 23 | 1 |

Supplier Selenga B2B historically S data-stock-value=17 with supply_id 753979 and L=6 with supply_id 753977. Urmia B2B historically XS=16, S=58, M=61, L=84, XL=49, 2XL=23; reliable per-size supply_id not extracted. Do NOT presume EAN mappings from ordering.
Other Selenga sizes XS/M/XL are NOT approved for this daily sync: M was previously present in Shopify with Fjord2/Cēsu1 but supplier truth not confirmed. Do not update.
Arco 3 ALU tent SKU RO11109 supplier shows qualitative `dużo` not integer; Shopify draft product `gid://shopify/Product/11191397548370`, historical Fjord42 unverified; do not publish or sync.

## 6. What we did chronologically and precise errors
1. Established locations and SKU mapping; successfully manually wrote and reread Fjord stock on 8 variants while protecting physical Cēsu and LOWA.
2. Created read-only planner and synthetic parser tests; GitHub Actions successful. Multiple ineffective iterative checks delayed real Render integration.
3. Developed `daily_capture.py`, `daily_sync.py`, `fjord_write.py`, `render_end_to_end.py`. GitHub feature branch and draft PR only; changed Render daily service to feature branch and new start command.
4. Authorized Render dashboard browser profile using TinyFish and **suspended** redundant 5-minute cron. The Render MCP lacks update/suspend cron methods, so used authenticated browser UI.
5. First live Render execution `FAILED_CLOSED` with Playwright Error: Chromium executable not found at `/opt/render/.cache/ms-playwright/chromium_headless_shell-1187/chrome-linux/headless_shell`. Fixed by installing chromium at runtime in cron startCommand. Browser now launches. Note redundant browser install in build and start; optimize after correctness.
6. Next failures from supplier HTML: `supplier_product_code_mismatch`, `supplier_auth_lost` and `ALPINUS authentication failed`. These indicate that render is not reliably seeing an authenticated supplier product page. Login-page parser triggers if `Zaloguj się` in early rendered content; could false-positive. Positive authentication check `Wyloguj` might be locale/HTML structure sensitive.
7. Inspected login page through TinyFish: actual `https://alpinusgroup.com/logowanie/7`; `input[name="email"].login-inputs-ui`; `input[name="password"].login-inputs-ui`; button `button.sign-in-lq.enter-key-trigger-lq.button-ui`; JS-controlled div `.form-js.sign-in-form-js.centered-ui`. Form submission managed by JS, no native HTML action. Browser TinyFish authenticated profile for supplier `prof_c5beb643e8d74adb` had earlier successful product stock capture, **NOT shared with Render**; a later login-page inspection showed login page, so do not assume continuing authorization.
8. Latest code commit `80770b69` attempts Comarch CSRF POST fallback but it has **NOT been proven on this host**, and no success confirmed. Trigger after last deployment not verified. Keep fail-closed rather than misleading success.
9. Shopify environment: `ALPINUS_ENABLE_WRITES=OFF` set explicitly. **Zero confirmed automated Shopify writes**.

## 7. Credentials, permissions and access: NO PASSWORDS IN REPO OR THIS REPORT
Render dashboard user access was authenticated via connected TinyFish profile `prof_a07e679cafef4b16` (default). Render API connector workspace `tea-da6tqdgn74is73ek62jg` works and can get_service/list_logs/trigger_deploy/update_environment_variables (update MERGES by default). Render UI browser via TinyFish profile can edit build/start commands, Trigger Run, suspend cron.
Supplier TinyFish browser profile `prof_c5beb643e8d74adb` (Outfish Alpinus B2B). Session is separate from Render and may expire.
Connected Shopify connector provides inventory read/write and product lookup. Shopify Admin GraphQL requires credentials in **Render env**:
- `ALPINUS_B2B_LOGIN` (secret) + `ALPINUS_B2B_PASSWORD` (secret)
- `SHOPIFY_SHOP_DOMAIN` (a .myshopify.com domain, not `outfish.lv`)
- `SHOPIFY_ADMIN_ACCESS_TOKEN` (Admin API access token; must authorize read inventory, read products and write inventory)
- `ALPINUS_ENABLE_WRITES=OFF` until confirmed safe end to end.
Previously the existence of Alpinus credentials was reported by probes; validity is unverified. Shopify vars in Render are **not confirmed present**. Neither Render nor TinyFish stored browser session substitutes for stable supplier app credentials. If credentials missing or invalid, use user's secure Render UI to enter/refill; NEVER ask user to paste passwords into Claude chat or commit them to GitHub.
Potential supplier solution: request an official Alpinus B2B API/export or IP allowlisted machine-account, if site rejects automated login; verify any purported endpoint with actual authenticated browser network traffic or written vendor docs before using it.

## 8. Important implementation defects Claude should fix BEFORE writes
- **Authentication**: Comarch CSRF fallback is an educated guess, not proven supported Alpinus flow. Do not send passwords to unverified endpoint; validate exact login POST URL and request format against vendor site. The current login routine uses string `Wyloguj` as proof, which may miss success or falsely detect text in templates. Better verify authenticated-only inventory DOM on a known product page, product code and numeric stock.
- **Playwright request vs page**: after browser UI login, `context.request.get(url)` may receive different HTML/redirect from `page.goto(url)`. Test both with cookies in same BrowserContext; consider page navigation + DOM-based capture and exact final URL.
- **Supplier parser**: product-code-in-body check might fail for legitimate B2B page showing variants via JS or metadata. Do not simply remove identity check; use canonical URL, SKU in DOM or verified attributes/structured identity.
- **Shopify GraphQL**: `render_end_to_end.py` read query `inventoryLevels(first:10)` and `quantities(names:["available"])` are UNVERIFIED with actual configured Render access. API version `2025-10`; check compatibility. `inventorySetQuantities` mutation untested; verify input contract, safe CAS userErrors, rate limits and compareQty.
- **Atomicity**: current 8 sequential CAS writes may partially apply if later variant fails. Add explicit partial-failure reporting and bounded retry only after refetch, idempotency, audit trail, not indiscriminate retry. Preserve Cēsu and LOWA.
- **Freshness**: `safe_plan.py` enforces max 26 hours but `daily_sync.py` **does not call it**. Capture timestamp just before fetching, validate source freshness from actual run, disallow replay of old data.
- **Mapping completeness**: `capture()` checks count=8 and set of SKUs but strict numerical stock; ensure cross-product URL/SKU association and duplicate fail-close. `snapshot()` reads only 10 inventory levels, which currently suffices for known locations but should not silently truncate.
- **No live storefront delivery logic**: 1–2 days Cēsu vs 5 days Fjord is a requirement, not verified checkout behavior. Fulfillment priority also not proven in Shopify configuration.
- **Operating safety**: until successful dry-run, leave `ALPINUS_ENABLE_WRITES=OFF`, and consider pausing daily cron if repeated failures create unnecessary cost/noise (do not suspend without user decision).
- **Tests**: fixtures passed but new auth/mutation code not covered. Need integration and mocks and post-run confirmation.

## 9. Exact recommended execution plan (avoid infinite audits)
A. On Render after commit 80770b69 LIVE, trigger one **DRY RUN** and read log; last proven result was auth failure. Avoid duplicate simultaneous runs.
B. Inspect exact browser login using authenticated human session/network traffic or official supplier integration docs; correct `alpinus_bulk/app.py` so Render obtains fresh authenticated session unattended, and supplier product pages show 8 numeric sizes. Do not import transient TinyFish cookies into Render as a daily plan.
C. Check Render env for presence (not values) of all four keys; secure user input only if missing/expired. Verify actual Shopify API GraphQL read in Render.
D. Capture exact eight supplier quantities and timestamp, verify source product identity and expected SKUs; compare to live Shopify snapshot. Return `DRY_RUN_VERIFIED count:8` with NO Shopify changes. Check local Cēsu and LOWA readbacks.
E. Once API mutation contract tested, perform controlled live update with `ALPINUS_ENABLE_WRITES=YES` on the **single existing daily job**; monitor success `LIVE_VERIFIED count:8`, immediate readback of all eight Fjord values and unchanged Cēsu / LOWA. If any errors, fail closed, disable writes.
F. Confirm one daily scheduled run and no 5-min cron. Validate variant-aware shipping/fulfillment local priority (1–2d) vs supplier fallback (5d). Expand beyond 8 only when exact per-size mapping and supplier numeric stock proven.
G. Write `OPERATIONS_RUNBOOK.md` with failure alarms, credential rotation, rollback, test/evidence links.

## 10. Acceptance criteria
- A real Render run using its own credentials logs authenticated B2B capture of eight exact numeric SKU quantities, with identity and freshness checks.
- Shopify Admin API in same Render run successfully reads products/variants and all relevant locations.
- After explicit approved enablement, Fjord-only CAS mutation performs and eight Fjord values read back exactly equal supplier values.
- Cēsu and LOWA stock unchanged, unrelated products/prices/images untouched.
- Another scheduled daily run succeeds, 5-min cron remains suspended.
- Physical store priority and 1–2-day shipping vs supplier 5-day delivery are verified for actual storefront variants.
Only then mark DONE.

## 11. Honesty about evidence
Manual Shopify stock verification occurred in prior interactions, not re-read while producing this document. Old quantities should not be treated as live/current. Last Render metadata was freshly read while preparing this report on 2026-10-21. GitHub code above freshly fetched. User is frustrated by repeated synthetic tests and incremental updates; solve concrete blocker in a single concentrated sequence, reporting only genuinely completed steps and blockers.

**Confidentiality:** No passwords, API tokens or session cookies in this handoff. Grant Claude access through the user's own tools/authorization; do not infer it has the same connector sessions.
