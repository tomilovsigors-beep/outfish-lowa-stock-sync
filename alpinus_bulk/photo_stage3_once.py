"""Scoped photo-only supplier crawl for stage 3, first 50 eligible products.

Fetches original photo bytes via authorized Render supplier session. Never touches Shopify.
Original files under /tmp are TEMPORARY, not durable: no completion claim until
separate verified private permanent storage is established.
"""
import asyncio, hashlib, json, os, re
from pathlib import Path
from urllib.parse import urlparse

from app import open_logged_in_page
from photo_gallery import extract_image_urls

SELECTED = json.loads("[{\"catalog_index\":1,\"supplier_product_id\":\"1204\",\"sku\":\"SU11922\",\"url\":\"https://alpinusgroup.com/kurtka-meska-softshell-alpinus-arbent-su11922/3-6-1204\"},{\"catalog_index\":2,\"supplier_product_id\":\"1193\",\"sku\":\"MK35089\",\"url\":\"https://alpinusgroup.com/kurtka-meska-narciarska-softshell-alpinus-ariz-mk3/3-6-1193\"},{\"catalog_index\":3,\"supplier_product_id\":\"1205\",\"sku\":\"BR35119\",\"url\":\"https://alpinusgroup.com/kurtka-meska-narciarska-alpinus-tochal-br35119/3-6-1205\"},{\"catalog_index\":5,\"supplier_product_id\":\"1179\",\"sku\":\"MK35468\",\"url\":\"https://alpinusgroup.com/koszulka-meska-grafen-alpinus-dirfi-mk35468/3-6-1179\"},{\"catalog_index\":6,\"supplier_product_id\":\"1216\",\"sku\":\"GC35626\",\"url\":\"https://alpinusgroup.com/czapka-merino-alpinus-dunree-gc35626/3-6-1216\"},{\"catalog_index\":7,\"supplier_product_id\":\"1196\",\"sku\":\"IM35531\",\"url\":\"https://alpinusgroup.com/kurtka-meska-puchowa-alpinus-kiruna-im35531/3-6-1196\"},{\"catalog_index\":8,\"supplier_product_id\":\"1194\",\"sku\":\"MK35095\",\"url\":\"https://alpinusgroup.com/spodnie-narciarskie-softshell-meskie-alpinus-kamar/3-6-1194\"},{\"catalog_index\":9,\"supplier_product_id\":\"1206\",\"sku\":\"BR35125\",\"url\":\"https://alpinusgroup.com/kurtka-meska-narciarska-alpinus-tochal-br35125/3-6-1206\"},{\"catalog_index\":10,\"supplier_product_id\":\"1201\",\"sku\":\"ES35510\",\"url\":\"https://alpinusgroup.com/kurtka-meska-merino-alpinus-wanaka-es35510/3-6-1201\"},{\"catalog_index\":11,\"supplier_product_id\":\"1220\",\"sku\":\"BR35107\",\"url\":\"https://alpinusgroup.com/kurtka-meska-narciarska-alpinus-cedras-br35107/3-6-1220\"},{\"catalog_index\":12,\"supplier_product_id\":\"1197\",\"sku\":\"IM35524\",\"url\":\"https://alpinusgroup.com/kurtka-meska-puchowa-alpinus-kiruna-im35524/3-6-1197\"},{\"catalog_index\":15,\"supplier_product_id\":\"1214\",\"sku\":\"GC35624\",\"url\":\"https://alpinusgroup.com/czapka-merino-alpinus-lugmore-gc35624/3-6-1214\"},{\"catalog_index\":17,\"supplier_product_id\":\"1195\",\"sku\":\"IM35517\",\"url\":\"https://alpinusgroup.com/kurtka-meska-puchowa-alpinus-kiruna-im35517/3-6-1195\"},{\"catalog_index\":19,\"supplier_product_id\":\"1200\",\"sku\":\"ES35503\",\"url\":\"https://alpinusgroup.com/kurtka-meska-merino-alpinus-wanaka-es35503/3-6-1200\"},{\"catalog_index\":21,\"supplier_product_id\":\"1173\",\"sku\":\"MG35374\",\"url\":\"https://alpinusgroup.com/buty-trekkingowe-alpinus-gemona-low-mg35374/3-6-1173\"},{\"catalog_index\":22,\"supplier_product_id\":\"1127\",\"sku\":\"EV35170\",\"url\":\"https://alpinusgroup.com/rekawiczki-woodporne-alpinus-bracklinn-czarne-ev35/3-6-1127\"},{\"catalog_index\":23,\"supplier_product_id\":\"1129\",\"sku\":\"SI35149\",\"url\":\"https://alpinusgroup.com/meska-bielizna-termoaktywna-alpinus-gausdal-si3514/3-6-1129\"},{\"catalog_index\":24,\"supplier_product_id\":\"1115\",\"sku\":\"MK35058\",\"url\":\"https://alpinusgroup.com/kurtka-meska-softshell-alpinus-roignais-mk35058/3-6-1115\"},{\"catalog_index\":26,\"supplier_product_id\":\"1133\",\"sku\":\"NX35143\",\"url\":\"https://alpinusgroup.com/raczki-alpinus-krywan-nx35143/3-6-1133\"},{\"catalog_index\":27,\"supplier_product_id\":\"1159\",\"sku\":\"JI35334\",\"url\":\"https://alpinusgroup.com/koszulka-meska-merino-alpinus-otago/3-6-1159\"},{\"catalog_index\":28,\"supplier_product_id\":\"1172\",\"sku\":\"MG35366\",\"url\":\"https://alpinusgroup.com/buty-trekkingowe-alpinus-gemona-mid-mg35366/3-6-1172\"},{\"catalog_index\":29,\"supplier_product_id\":\"1132\",\"sku\":\"SF35174\",\"url\":\"https://alpinusgroup.com/kurtka-meska-alpinus-hozat-sf35174/3-6-1132\"},{\"catalog_index\":31,\"supplier_product_id\":\"1137\",\"sku\":\"RT35261\",\"url\":\"https://alpinusgroup.com/rekawiczki-zimowe-alpinus-scafell-pro-rt35261/3-6-1137\"},{\"catalog_index\":32,\"supplier_product_id\":\"1136\",\"sku\":\"QN35190\",\"url\":\"https://alpinusgroup.com/plaszcz-meski-alpinus-ararat/3-6-1136\"},{\"catalog_index\":33,\"supplier_product_id\":\"1178\",\"sku\":\"MK35442\",\"url\":\"https://alpinusgroup.com/spodnie-trekkingowe-meskie-alpinus-dekan-mk35442/3-6-1178\"},{\"catalog_index\":34,\"supplier_product_id\":\"1075\",\"sku\":\"AO35158\",\"url\":\"https://alpinusgroup.com/bielizna-termoaktywna-unisex-set-alpinus-merino-ao/3-6-1075\"},{\"catalog_index\":35,\"supplier_product_id\":\"1125\",\"sku\":\"AO35162\",\"url\":\"https://alpinusgroup.com/bielizna-termoaktywna-meska-alpinus-hemis-set-ao35/3-6-1125\"},{\"catalog_index\":36,\"supplier_product_id\":\"1145\",\"sku\":\"GO35293\",\"url\":\"https://alpinusgroup.com/sandaly-alpinus-ladeira-go35280/3-6-1145\"},{\"catalog_index\":37,\"supplier_product_id\":\"1131\",\"sku\":\"SF35180\",\"url\":\"https://alpinusgroup.com/kurtka-meska-alpinus-hozat-sf35180/3-6-1131\"},{\"catalog_index\":38,\"supplier_product_id\":\"1126\",\"sku\":\"AO35166\",\"url\":\"https://alpinusgroup.com/bielizna-termoaktywna-meska-alpinus-hemis-set-ao35/3-6-1126\"},{\"catalog_index\":40,\"supplier_product_id\":\"1147\",\"sku\":\"GO35299\",\"url\":\"https://alpinusgroup.com/sandaly-alpinus-ladeira-go35280/3-6-1147\"},{\"catalog_index\":41,\"supplier_product_id\":\"1054\",\"sku\":\"FF11982\",\"url\":\"https://alpinusgroup.com/kurtka-meska-softshell-alpinus-pourri/3-6-1054\"},{\"catalog_index\":42,\"supplier_product_id\":\"1069\",\"sku\":\"NQ35006\",\"url\":\"https://alpinusgroup.com/kurtka-meska-2-5-warstwowa-alpinus-girdima/3-6-1069\"},{\"catalog_index\":43,\"supplier_product_id\":\"1071\",\"sku\":\"NQ11994\",\"url\":\"https://alpinusgroup.com/kurtka-meska-2-warstwowa-alpinus-arys-nq11994/3-6-1071\"},{\"catalog_index\":44,\"supplier_product_id\":\"1033\",\"sku\":\"FP11892\",\"url\":\"https://alpinusgroup.com/koszulka-meska-alpinus-kitreli-fp11892/3-6-1033\"},{\"catalog_index\":45,\"supplier_product_id\":\"1032\",\"sku\":\"FP11886\",\"url\":\"https://alpinusgroup.com/koszulka-meska-alpinus-tokat-fp11886/3-6-1032\"},{\"catalog_index\":46,\"supplier_product_id\":\"1070\",\"sku\":\"NQ11988\",\"url\":\"https://alpinusgroup.com/kurtka-meska-2-warstwowa-alpinus-arys-nq11988/3-6-1070\"},{\"catalog_index\":47,\"supplier_product_id\":\"1057\",\"sku\":\"JA11940\",\"url\":\"https://alpinusgroup.com/spodnie-trekkingowe-meskie-alpinus-vitorog/3-6-1057\"},{\"catalog_index\":48,\"supplier_product_id\":\"1058\",\"sku\":\"JA11946\",\"url\":\"https://alpinusgroup.com/spodnie-trekkingowe-meskie-alpinus-vitorog/3-6-1058\"},{\"catalog_index\":49,\"supplier_product_id\":\"1031\",\"sku\":\"FP11880\",\"url\":\"https://alpinusgroup.com/koszulka-meska-alpinus-tokat-fp11880/3-6-1031\"},{\"catalog_index\":50,\"supplier_product_id\":\"1030\",\"sku\":\"FP11874\",\"url\":\"https://alpinusgroup.com/koszulka-meska-alpinus-tokat-fp11874/3-6-1030\"},{\"catalog_index\":51,\"supplier_product_id\":\"1028\",\"sku\":\"FP11862\",\"url\":\"https://alpinusgroup.com/koszulka-meska-polo-alpinus-sherali-fp11862/3-6-1028\"},{\"catalog_index\":52,\"supplier_product_id\":\"1027\",\"sku\":\"FP11856\",\"url\":\"https://alpinusgroup.com/koszulka-meska-polo-alpinus-sherali-fp11856/3-6-1027\"},{\"catalog_index\":53,\"supplier_product_id\":\"1029\",\"sku\":\"FP11868\",\"url\":\"https://alpinusgroup.com/koszulka-meska-polo-alpinus-sherali-fp11868/3-6-1029\"},{\"catalog_index\":54,\"supplier_product_id\":\"1034\",\"sku\":\"FP11898\",\"url\":\"https://alpinusgroup.com/koszulka-meska-alpinus-kitreli-fp11898/3-6-1034\"},{\"catalog_index\":55,\"supplier_product_id\":\"1073\",\"sku\":\"NQ35018\",\"url\":\"https://alpinusgroup.com/kurtka-meska-2-5-warstwowa-alpinus-girdiman-nq3501/3-6-1073\"},{\"catalog_index\":56,\"supplier_product_id\":\"1056\",\"sku\":\"JA11934\",\"url\":\"https://alpinusgroup.com/spodnie-trekkingowe-meskie-alpinus-vitorog/3-6-1056\"},{\"catalog_index\":57,\"supplier_product_id\":\"1072\",\"sku\":\"NQ35012\",\"url\":\"https://alpinusgroup.com/kurtka-meska-2-5-warstwowa-alpinus-girdiman-nq3501/3-6-1072\"},{\"catalog_index\":58,\"supplier_product_id\":\"1016\",\"sku\":\"NQ11680\",\"url\":\"https://alpinusgroup.com/kurtka-meska-hardshell-alpinus-gedu-nq11680/3-6-1016\"},{\"catalog_index\":59,\"supplier_product_id\":\"1055\",\"sku\":\"GH11425\",\"url\":\"https://alpinusgroup.com/sandaly-alpinus-sosneado/3-6-1055\"}]")
DEST = Path("/tmp/alpinus_stage3_photo_batch_001")
MAX_CONCURRENT = 4
IMAGE_LIMIT = 40


def emit(event, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=False, separators=(",", ":")), flush=True)


def signature_ok(data):
    return (data.startswith(bytes.fromhex("ffd8ff")) or
            data.startswith(bytes.fromhex("89504e470d0a1a0a")) or
            (data.startswith(b"RIFF") and data[8:12] == b"WEBP") or
            (len(data) > 12 and data[4:12] in (b"ftypavif", b"ftypavis")))


def extension(data):
    if data.startswith(bytes.fromhex("ffd8")): return ".jpg"
    if data.startswith(bytes.fromhex("89504e47")): return ".png"
    if data.startswith(b"RIFF"): return ".webp"
    return ".avif"


async def main():
    expected_count = 2 if os.getenv("ALPINUS_STAGE3_PHOTO_BATCH") == "007" else 50
    if len(SELECTED) != expected_count or len({x["supplier_product_id"] for x in SELECTED}) != expected_count:
        raise RuntimeError(f"Expected exactly {expected_count} unique suppliers")
    browser = pw = context = None
    try:
        pw, browser, context, _ = await open_logged_in_page()
        request = context.request
        DEST.mkdir(parents=True, exist_ok=True)
        limiter = asyncio.Semaphore(MAX_CONCURRENT)
        completed = []
        async def check_product(index, product):
            async with limiter:
                pid = product["supplier_product_id"]
                sku = product["sku"]
                url = product["url"]
                if not urlparse(url).path.endswith("-" + pid):
                    emit("photo_product_error", supplier_product_id=pid, sku=sku,
                         reason="supplier_id_url_mismatch")
                    return {"id": pid, "photos": 0, "error": "supplier_id_url_mismatch"}
                try:
                    response = await request.get(url, timeout=30000)
                    if response.status != 200:
                        raise RuntimeError("supplier_product_http_" + str(response.status))
                    html = await response.text()
                    if "Dostęp tylko dla zalogowanych kontrahentów" in html:
                        raise RuntimeError("supplier_auth_required")
                    candidates = extract_image_urls(html, url, IMAGE_LIMIT)
                    saved = []
                    for photo_index, image_url in enumerate(candidates, 1):
                        try:
                            asset = await request.get(image_url, timeout=25000)
                            if asset.status != 200:
                                raise RuntimeError("photo_http_" + str(asset.status))
                            data = await asset.body()
                            if len(data) < 1500 or not signature_ok(data):
                                raise RuntimeError("photo_invalid_magic_or_too_small")
                            folder = DEST / pid
                            folder.mkdir(parents=True, exist_ok=True)
                            dest = folder / (f"{photo_index:02d}" + extension(data))
                            dest.write_bytes(data)
                            meta = {"url": image_url, "bytes": len(data),
                                    "sha256": hashlib.sha256(data).hexdigest()}
                            saved.append(meta)
                            emit("photo_asset_verified", source_index=product["catalog_index"],
                                 supplier_product_id=pid, sku=sku, photo_index=photo_index, **meta)
                        except Exception as exc:
                            emit("photo_asset_error", supplier_product_id=pid, sku=sku,
                                 photo_index=photo_index, error=f"{type(exc).__name__}: {exc}")
                    emit("photo_product_done", source_index=product["catalog_index"],
                         supplier_product_id=pid, sku=sku,
                         image_candidates=len(candidates), downloaded_images=len(saved),
                         storage="RENDER_TMP_NON_DURABLE")
                    return {"id": pid, "photos": len(saved), "candidates": len(candidates)}
                except Exception as exc:
                    emit("photo_product_error", supplier_product_id=pid, sku=sku,
                         error=f"{type(exc).__name__}: {exc}")
                    return {"id": pid, "photos": 0, "error": str(exc)}
        results = await asyncio.gather(*(check_product(i, x) for i, x in enumerate(SELECTED)))
        emit("photo_batch_summary", processed=len(results),
             products_with_downloads=sum(x["photos"] > 0 for x in results),
             verified_file_count=sum(x["photos"] for x in results),
             failures=sum(bool(x.get("error")) for x in results),
             durable_storage=False, status="PHOTO_SOURCE_FETCH_ONLY")
    finally:
        if context: await context.close()
        if browser: await browser.close()
        if pw: await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
