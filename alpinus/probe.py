import json
import os
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = os.getenv("ALPINUS_BASE_URL", "https://alpinusgroup.com").rstrip("/") + "/"
LOGIN = os.getenv("ALPINUS_B2B_LOGIN", "").strip()
PASSWORD = os.getenv("ALPINUS_B2B_PASSWORD", "").strip()


def emit(label, value):
    print(f"{label}={json.dumps(value, ensure_ascii=False)}", flush=True)


def find_login_form(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        if form.find("input", {"type": "password"}):
            return soup, form, urljoin(page_url, form.get("action") or page_url)
    return soup, None, None


def build_payload(form):
    payload = {}
    for tag in form.find_all("input"):
        name = tag.get("name")
        if not name:
            continue
        typ = (tag.get("type") or "text").lower()
        if typ in {"submit", "button", "image", "file"}:
            continue
        if typ in {"checkbox", "radio"} and not tag.has_attr("checked"):
            continue
        payload[name] = tag.get("value", "")

    user_fields = ["email", "login", "username", "user", "mail"]
    pass_fields = ["password", "pass", "passwd", "haslo"]

    lower_names = {k.lower(): k for k in payload}
    for candidate in user_fields:
        if candidate in lower_names:
            payload[lower_names[candidate]] = LOGIN
            break
    else:
        for tag in form.find_all("input"):
            typ = (tag.get("type") or "text").lower()
            if typ in {"email", "text"} and tag.get("name"):
                payload[tag["name"]] = LOGIN
                break

    for candidate in pass_fields:
        if candidate in lower_names:
            payload[lower_names[candidate]] = PASSWORD
            break
    else:
        p = form.find("input", {"type": "password"})
        if p and p.get("name"):
            payload[p["name"]] = PASSWORD

    return payload


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Outfish-Alpinus-Sync/0.1 (+inventory integration)"
    })

    first = session.get(BASE_URL, timeout=30, allow_redirects=True)
    first.raise_for_status()
    soup, form, action = find_login_form(first.text, first.url)

    emit("PUBLIC_PROBE", {
        "status": first.status_code,
        "final_url": first.url,
        "title": soup.title.get_text(" ", strip=True)[:200] if soup.title else "",
        "login_form_found": bool(form),
        "credentials_configured": bool(LOGIN and PASSWORD),
    })

    if form is None:
        print("No password form found; stopping safely.", flush=True)
        return 0

    fields = []
    for tag in form.find_all("input"):
        if tag.get("name"):
            fields.append({
                "name": tag.get("name"),
                "type": (tag.get("type") or "text").lower(),
            })
    emit("LOGIN_FORM", {
        "method": (form.get("method") or "GET").upper(),
        "action": action,
        "fields": fields,
    })

    if not (LOGIN and PASSWORD):
        print("Alpinus credentials not configured; safe no-op.", flush=True)
        return 0

    payload = build_payload(form)
    method = (form.get("method") or "GET").upper()
    headers = {"Referer": first.url}

    if method == "POST":
        response = session.post(action, data=payload, headers=headers, timeout=30, allow_redirects=True)
    else:
        response = session.get(action, params=payload, headers=headers, timeout=30, allow_redirects=True)
    response.raise_for_status()

    after, password_form, _ = find_login_form(response.text, response.url)
    text = " ".join(after.stripped_strings).lower()
    markers = [m for m in ["wyloguj", "logout", "konto", "profil", "zamówienia", "zamowienia"] if m in text]
    authenticated = password_form is None and bool(markers)

    links = []
    for a in after.find_all("a", href=True):
        href = urljoin(response.url, a["href"])
        label = " ".join(a.stripped_strings).strip()
        if href.startswith(BASE_URL) and label:
            links.append({"label": label[:120], "url": href})
        if len(links) >= 40:
            break

    emit("AUTH_PROBE", {
        "authenticated": authenticated,
        "status": response.status_code,
        "final_url": response.url,
        "title": after.title.get_text(" ", strip=True)[:200] if after.title else "",
        "marker_hits": markers,
        "sample_internal_links": links[:20],
    })

    if not authenticated:
        print("Authentication was not confirmed; no catalog crawling and no Shopify writes.", flush=True)
        return 2

    print("Authentication confirmed. Catalog discovery can be enabled next.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
