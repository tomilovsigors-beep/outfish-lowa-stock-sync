"""Extract image URL candidates from supplier product markup; verification/download is separate.

Do not treat URL extraction as evidence that bytes were downloaded or licensed.
"""
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

IMAGE_ATTRS = ("data-zoom-image", "data-large", "data-full", "data-original",
               "data-lazy-src", "data-src", "data-image", "src")
IMAGE_SUFFIX = re.compile(r"\.(?:jpe?g|png|webp|avif)(?:$|[?#])", re.I)
EXCLUDE = re.compile(r"(?:logo|favicon|flag|icon|placeholder|loader|sprite|badge|payment|social|produktpolski|css/img/)", re.I)


def absolute_image(src, page_url):
    if not isinstance(src, str):
        return None
    raw = src.strip().strip("'\"")
    if not raw or raw.startswith(("data:", "blob:", "javascript:", "#")):
        return None
    url = urljoin(page_url, raw)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if EXCLUDE.search(parsed.path):
        return None
    # Keep plausible media paths and image extensions, without the old '/img/' gate.
    if not (IMAGE_SUFFIX.search(parsed.path) or re.search(
            r"/(?:img|image|images|media|photos|products|upload|uploads|cache)/",
            parsed.path, re.I)):
        return None
    return url


def extract_image_urls(html, page_url, max_images=40):
    soup = BeautifulSoup(html, "html.parser")
    urls, seen = [], set()

    def add(value):
        url = absolute_image(value, page_url)
        if url and url not in seen and len(urls) < max_images:
            seen.add(url)
            urls.append(url)

    def add_srcset(value):
        # Responsive image source sets use image URL followed by width or density.
        for item in (value or "").split(","):
            part = item.strip().split()
            if part:
                add(part[0])

    # Priority: full-resolution gallery lightbox links, product media, then image elements.
    selectors = (
        ".product-gallery a[href], .gallery a[href], [data-gallery] a[href], "
        "a[data-fancybox][href], a[data-lightbox][href], "
        "a.open-gallery-lq[href], a[href][data-zoom-image], "
        ".product-gallery img, .gallery img, "
        "img.open-gallery-lq, [itemprop=image], "
        "picture source, img[data-original], img[data-zoom-image], img"
    )
    for element in soup.select(selectors):
        if element.name == "a":
            add(element.get("href"))
        for attr in IMAGE_ATTRS:
            add(element.get(attr))
        add_srcset(element.get("srcset"))
        add_srcset(element.get("data-srcset"))

    # Product schema often exposes media even when the DOM uses background images.
    for el in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(el.string or el.get_text())
        except (TypeError, ValueError):
            continue
        def walk(node, product=False):
            if isinstance(node, list):
                for value in node:
                    walk(value, product)
            elif isinstance(node, dict):
                kind = str(node.get("@type", "")).lower()
                is_product = product or kind == "product" or (
                    isinstance(node.get("@type"), list) and "Product" in node["@type"]
                )
                if is_product:
                    images = node.get("image") or []
                    for img in images if isinstance(images, list) else [images]:
                        add(img.get("url") or img.get("contentUrl") if isinstance(img, dict) else img)
                for key in ("@graph", "mainEntity", "itemListElement"):
                    if key in node:
                        walk(node[key], is_product)
        walk(payload)

    return urls
