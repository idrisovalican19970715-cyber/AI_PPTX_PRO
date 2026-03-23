#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI: найти и скачать иллюстрацию по теме (те же источники, что в main.py).

Примеры:
  python fetch_illustration.py "solar panel rooftop"
  python fetch_illustration.py "team meeting office" -o slides/img01.jpg

Нужны ключи в .env: PEXELS_API_KEY и/или UNSPLASH_ACCESS_KEY.
Без ключей используется только Wikimedia Commons.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

HDR = {
    "User-Agent": "AI_PPTX_PRO/1.0 (presentation generator; +https://github.com) Python-requests",
    "Cache-Control": "no-cache",
    "Accept": "application/json,text/plain,*/*",
}


def valid_img(d: bytes) -> bool:
    return len(d) > 100 and (d[:3] == b"\xff\xd8\xff" or d[:4] == b"\x89PNG")


def download_url(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=HDR, timeout=50, allow_redirects=True)
        if r.status_code == 200 and valid_img(r.content):
            return r.content
    except requests.RequestException:
        pass
    return None


def try_pexels(query: str, pick: int) -> bytes | None:
    key = (os.getenv("PEXELS_API_KEY") or "").strip()
    if not key:
        return None
    r = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query[:200], "per_page": 12, "page": 1},
        headers={"Authorization": key},
        timeout=25,
    )
    if r.status_code != 200:
        print("Pexels HTTP", r.status_code, file=sys.stderr)
        return None
    photos = (r.json() or {}).get("photos") or []
    if not photos:
        return None
    p = photos[pick % len(photos)]
    src = p.get("src") or {}
    url = src.get("large2x") or src.get("large") or src.get("original")
    return download_url(url) if url else None


def try_unsplash(query: str, pick: int) -> bytes | None:
    key = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        return None
    r = requests.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query[:200], "per_page": 12, "page": 1},
        headers={"Authorization": f"Client-ID {key}"},
        timeout=25,
    )
    if r.status_code != 200:
        print("Unsplash HTTP", r.status_code, file=sys.stderr)
        return None
    results = (r.json() or {}).get("results") or []
    if not results:
        return None
    u = (results[pick % len(results)].get("urls") or {}).get("regular")
    return download_url(u) if u else None


def try_wikimedia(query: str, pick: int) -> bytes | None:
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query[:200],
            "gsrnamespace": 6,
            "gsrlimit": 20,
            "prop": "imageinfo",
            "iiprop": "url|mime|thumburl",
            "iiurlwidth": 1280,
        },
        headers=HDR,
        timeout=22,
    )
    if r.status_code != 200:
        return None
    pages = ((r.json() or {}).get("query") or {}).get("pages") or {}
    cand = []
    for _pid, p in pages.items():
        ii = (p.get("imageinfo") or [{}])[0]
        mime = (ii.get("mime") or "").lower()
        if not mime.startswith("image/") or "svg" in mime:
            continue
        url = ii.get("thumburl") or ii.get("url")
        if url:
            cand.append((p.get("index", 9999), url))
    cand.sort(key=lambda x: x[0])
    urls = [u for _, u in cand]
    if not urls:
        return None
    return download_url(urls[pick % len(urls)])


def fetch_first(query: str, pick: int = 0) -> tuple[bytes, str] | None:
    for name, fn in (
        ("pexels", try_pexels),
        ("unsplash", try_unsplash),
        ("wikimedia", try_wikimedia),
    ):
        raw = fn(query, pick)
        if raw:
            return raw, name
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Скачать иллюстрацию по теме")
    ap.add_argument("query", help="Тема на английском, напр. hospital doctor stethoscope")
    ap.add_argument("-o", "--output", type=Path, default=None, help="Файл .jpg/.png")
    ap.add_argument(
        "-n",
        "--variant",
        type=int,
        default=0,
        help="Номер варианта из выдачи (0..11), чтобы картинки отличались",
    )
    args = ap.parse_args()
    out = args.output
    if out is None:
        h = hashlib.md5(args.query.encode()).hexdigest()[:10]
        out = Path(f"illustration_{h}.jpg")

    got = fetch_first(args.query.strip(), pick=max(0, args.variant))
    if not got:
        print("Не удалось ничего скачать. Проверь интернет и ключи Pexels/Unsplash.", file=sys.stderr)
        return 1
    raw, src = got
    out.write_bytes(raw)
    print(f"OK: {len(raw)} bytes from {src} -> {out.resolve()}")
    print(f"md5: {hashlib.md5(raw).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
