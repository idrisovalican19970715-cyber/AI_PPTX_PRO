"""Проверка: каждый слайд — свой JPEG (как в download_images после фикса)."""
import hashlib
import io
import re
import time
from pathlib import Path

import requests
from pptx import Presentation
from pptx.util import Emu

HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
    "Cache-Control": "no-cache",
}


def _valid_img(d: bytes) -> bool:
    return d[:3] == b"\xff\xd8\xff" or d[:4] == b"\x89PNG"


def _flickr_lock(tags: str, idx: int, title: str = "") -> int:
    h = hashlib.md5(f"{tags}|{idx}|{title}".encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:12], 16) % (2**31 - 2) + 1


def try_picsum(seed: str):
    safe = re.sub(r"[^a-zA-Z0-9]", "", str(seed)) or "x"
    r = requests.get(
        f"https://picsum.photos/seed/{safe}/1024/768",
        headers=HDR,
        timeout=15,
        allow_redirects=True,
    )
    if r.status_code == 200 and _valid_img(r.content):
        return r.content
    return None


def try_flickr(kw: str, idx: int, title: str):
    words = []
    for p in kw.replace(",", " ").split():
        w = re.sub(r"[^a-zA-Z0-9]", "", p).lower()
        if w and len(w) > 1:
            words.append(w)
    tags = ",".join(dict.fromkeys(words))[:80]
    if not tags:
        return None
    lock = _flickr_lock(tags, idx, title)
    r = requests.get(
        f"https://loremflickr.com/1024/768/{tags}",
        params={"lock": str(lock)},
        headers=HDR,
        timeout=15,
        allow_redirects=True,
    )
    if r.status_code == 200 and _valid_img(r.content):
        return r.content
    return None


def fetch_like_app(i: int, kw: str, title: str, sn: int):
    seed = hashlib.md5(f"{kw}|{sn}|{i}|{title}".encode("utf-8", errors="ignore")).hexdigest()
    b = try_picsum(seed)
    if b:
        return b, "picsum"
    b = try_flickr(kw, i, title) if kw else None
    if b:
        return b, "flickr"
    return None, "fail"


def _pptx_image_md5s(path: Path):
    prs = Presentation(str(path))
    out = []
    for i, sl in enumerate(prs.slides):
        for sh in sl.shapes:
            if sh.shape_type == 13:
                out.append((i + 1, hashlib.md5(sh.image.blob).hexdigest()[:16], len(sh.image.blob)))
    return out


def main():
    slides = [
        (1, "ocean,sunset,waves", "Intro"),
        (2, "business,team,meeting", "Chapter One"),
        (3, "city,night,lights", "Data"),
        (4, "forest,mountain,hike", "Summary"),
        (5, "coffee,laptop,desk", "Outro"),
    ]
    blobs = []
    digests = []
    for i, (sn, kw, title) in enumerate(slides):
        raw, src = fetch_like_app(i, kw, title, sn)
        assert raw, f"no image slide {i} ({src})"
        blobs.append(raw)
        digests.append(hashlib.md5(raw).hexdigest())
        print(f"  slide {i+1} ({src}): {len(raw)} bytes md5={digests[-1][:16]}")
        time.sleep(0.07)
    u = len(set(digests))
    print(f"\nTOTAL {len(digests)} images, {u} unique — {'OK' if u == len(digests) else 'FAIL'}")

    # Встраиваем в .pptx и снова проверяем (как у пользователя)
    out = Path(__file__).resolve().parent / "_test_unique_images.pptx"
    prs = Presentation()
    prs.slide_width = Emu(int(16 * 914400))
    prs.slide_height = Emu(int(9 * 914400))
    blank = prs.slide_layouts[6]
    for raw in blobs:
        slide = prs.slides.add_slide(blank)
        buf = io.BytesIO(raw)
        slide.shapes.add_picture(buf, Emu(0), Emu(0), Emu(int(10 * 914400)), Emu(int(7 * 914400)))
    prs.save(str(out))
    rows = _pptx_image_md5s(out)
    print(f"\nPPTX {out.name}: {len(rows)} shapes")
    for r in rows:
        print(f"  slide {r[0]}: {r[2]:>8} bytes  md5={r[1]}")
    u2 = len(set(r[1] for r in rows))
    ok2 = u2 == len(rows) == len(slides)
    print(f"  embedded: {u2} unique — {'OK' if ok2 else 'FAIL'}")
    return 0 if u == len(digests) and ok2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
