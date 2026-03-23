import os
import sys
import io
import json
import re
import time
import traceback
import urllib.parse
import hashlib
import logging
from pathlib import Path

import requests
import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

load_dotenv()

# Windows: консоль по умолчанию cp1252 — кириллица в print/logging даёт UnicodeEncodeError
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

logging.basicConfig(level=logging.INFO, format="%(message)s")
_IMG_LOG = logging.getLogger("ai_pptx.images")

TEMPLATE_PATH = Path(__file__).parent / "template.pptx"

# Wikimedia требует идентифицируемый User-Agent (не обычный браузер без контакта)
HDR = {
    "User-Agent": "AI_PPTX_PRO/1.0 (presentation generator; +https://github.com) Python-requests",
    "Accept": "application/json,text/plain,*/*",
}

SLIDE_W_IN, SLIDE_H_IN = 16.0, 9.0

VOLUME_MAP = {
    "Краткая выжимка": "1 короткое предложение на пункт (макс 12 слов).",
    "Средне": "1-2 предложения на пункт.",
    "Детальный лонгрид": "2-3 развёрнутых предложения с деталями.",
}

THEMES = {
    "Тёмный (Gamma-style)": {
        "bg": (0x0F, 0x17, 0x2A),
        "card": (0x1E, 0x29, 0x3B),
        "title_color": (0xFF, 0xFF, 0xFF),
        "text_color": (0xE2, 0xE6, 0xE9),
        "muted": (0x94, 0xA3, 0xB8),
        "accent": (0x97, 0xB8, 0xFF),
        "num_bg": (0x33, 0x42, 0x55),
        "num_fg": (0x97, 0xB8, 0xFF),
    },
    "Тёплый тёмный": {
        "bg": (0x1A, 0x0F, 0x0F),
        "card": (0x2D, 0x1B, 0x1B),
        "title_color": (0xFF, 0xE5, 0xE5),
        "text_color": (0xFA, 0xEB, 0xEB),
        "muted": (0xBF, 0x9B, 0x9B),
        "accent": (0xFF, 0x8A, 0x8A),
        "num_bg": (0x3D, 0x25, 0x25),
        "num_fg": (0xFF, 0x8A, 0x8A),
    },
    "Светлый": {
        "bg": (0xF8, 0xFA, 0xFC),
        "card": (0xFF, 0xFF, 0xFF),
        "title_color": (0x0F, 0x17, 0x2A),
        "text_color": (0x33, 0x42, 0x55),
        "muted": (0x64, 0x74, 0x8B),
        "accent": (0x33, 0x82, 0xF6),
        "num_bg": (0xE2, 0xE8, 0xF0),
        "num_fg": (0x33, 0x82, 0xF6),
    },
}

for _k, _v in [("draft_data", None), ("generation_step", 1),
               ("user_images", []), ("user_images_hash", ""), ("pptx_bytes", None)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

st.set_page_config(page_title="AI Презентатор Pro", page_icon="✨",
                   layout="wide", initial_sidebar_state="expanded")


def _sync_streamlit_secrets_to_env() -> None:
    """Streamlit Cloud: Secrets → os.environ (после set_page_config, без лишних вызовов st до него)."""
    try:
        sec = st.secrets
        for k in ("GEMINI_API_KEY", "PEXELS_API_KEY", "UNSPLASH_ACCESS_KEY"):
            if k in sec and str(sec[k]).strip():
                os.environ[k] = str(sec[k]).strip()
    except Exception:
        pass


_sync_streamlit_secrets_to_env()

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
html,body,.stApp{font-family:'Inter',sans-serif}
.block-container{max-width:1100px;padding-top:2rem}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f172a,#1e293b)}
section[data-testid="stSidebar"] *{color:#e0e0e0!important}
.slide-preview{border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.2);margin:8px 0 16px}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Настройки")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Только для текста/JSON слайдов. Сообщение «лимит API» при генерации темы — это квота Gemini, не Pexels/Wikimedia.",
    )
    num_slides = st.slider("Слайдов", 3, 15, 8)
    text_volume = st.selectbox("Плотность текста", list(VOLUME_MAP.keys()), index=1)
    design_theme = st.selectbox("Тема", list(THEMES.keys()), index=0)
    PHOTO_PIPELINES = {
        "Поиск по теме: Pexels → Unsplash → Wikimedia": "search",
        "AI Pollinations + сток (дольше)": "ai_first",
        "Только LoremFlickr + запасные (быстро)": "flickr_fast",
    }
    photo_mode_label = st.selectbox(
        "Фото на слайдах",
        list(PHOTO_PIPELINES.keys()),
        index=0,
        help="Поиск: реальные фото по ключевым словам (в .env — PEXELS_API_KEY и/или UNSPLASH_ACCESS_KEY; без ключей работает Wikimedia Commons).",
    )
    photo_pipeline = PHOTO_PIPELINES[photo_mode_label]
    uploaded_images = st.file_uploader("📎 Свои фото", accept_multiple_files=True, type=["png", "jpg", "jpeg"])
    if uploaded_images:
        h = hashlib.md5(b"".join(f.name.encode() + str(f.size).encode() for f in uploaded_images)).hexdigest()
        if h != st.session_state.user_images_hash:
            st.session_state.user_images = [f.read() for f in uploaded_images]
            st.session_state.user_images_hash = h
    else:
        st.session_state.user_images = []
        st.session_state.user_images_hash = ""
    st.divider()
    st.caption(".env или Streamlit Secrets: GEMINI*, PEXELS*, UNSPLASH* · см. файл ЗАПУСК_В_ИНТЕРНЕТ.md")

effective_key = api_key or os.getenv("GEMINI_API_KEY", "")

# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def _valid_img(d: bytes) -> bool:
    return d[:3] == b"\xff\xd8\xff" or d[:4] == b"\x89PNG"

def _norm(t: str) -> str:
    return t.replace("\\n", "\n")


def _img_audit(slide_idx: int, source: str, event: str, detail: str = "") -> None:
    """Аудит в консоль/лог: изоляция состояния по слайду."""
    tail = f" | {detail}" if detail else ""
    line = f"[PPTX slide {slide_idx + 1}] [{source}] {event}{tail}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(enc, errors="replace").decode(enc), flush=True)
    try:
        _IMG_LOG.info(line)
    except UnicodeEncodeError:
        _IMG_LOG.info(line.encode("ascii", errors="replace").decode("ascii"))


def _bytes_md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _loremflickr_json_indicates_real_match(tags: str) -> bool:
    """
    RCA: LoremFlickr отдаёт один и тот же «запасной» JPEG (часто кот/Tomboli) с HTTP 200,
    если по тегам нет фото. JSON API при этом указывает defaultImage и rawFileUrl=null.
    """
    try:
        r = requests.get(
            f"https://loremflickr.com/json/1024/768/{tags}",
            headers={**HDR, "Cache-Control": "no-cache"},
            timeout=14,
        )
        if r.status_code != 200:
            return False
        j = r.json()
        file_url = j.get("file") or ""
        if "defaultImage" in file_url:
            return False
        raw = j.get("rawFileUrl")
        if raw is None or raw == "":
            return False
        return True
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        _IMG_LOG.debug("flickr json check error: %s", e)
        return False


def _failure_placeholder_stream(accent: tuple, slide_number: int, w: int = 1024, h: int = 576) -> io.BytesIO:
    """Текстовый плейсхолдер вместо скрытого «кота» или градиента при полном провале цепочки."""
    bg = (
        max(20, min(255, accent[0] // 5)),
        max(20, min(255, accent[1] // 5)),
        max(30, min(255, accent[2] // 5)),
    )
    img = Image.new("RGB", (w, h), color=bg)
    draw = ImageDraw.Draw(img)
    try:
        from PIL import ImageFont

        font = ImageFont.truetype("arial.ttf", max(22, w // 40))
    except OSError:
        font = ImageFont.load_default()
    lines = ("Image rendering failed", f"(slide {slide_number})")
    y = h // 2 - 36
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), ln, fill=(220, 220, 230), font=font)
        y += (bbox[3] - bbox[1]) + 8
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def _clean_json(text: str) -> list[dict]:
    c = re.sub(r"```(?:json)?\s*|\s*```", "", text.strip())
    m = re.search(r"\[.*]", c, re.DOTALL)
    if not m:
        st.error("Gemini вернул невалидный JSON.")
        st.code(text[:600])
        st.stop()
    try:
        d = json.loads(m.group())
    except json.JSONDecodeError as e:
        st.error(f"JSON ошибка: {e}")
        st.stop()
    if not isinstance(d, list) or not d:
        st.error("Пустой массив.")
        st.stop()
    return d

# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI — Gamma-style prompt with layout types
# ═══════════════════════════════════════════════════════════════════════════════
def generate_structure(user_input: str, is_raw: bool) -> list[dict]:
    if not effective_key:
        st.error("Введите Gemini API Key")
        st.stop()
    genai.configure(api_key=effective_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    vol = VOLUME_MAP[text_volume]
    src = (f'Материал:\n"""\n{user_input}\n"""' if is_raw
           else f'Тема: "{user_input}"')

    prompt = f"""Ты — ведущий дизайнер презентаций уровня Gamma AI.

ЯЗЫК: Определи язык запроса. title/content — СТРОГО на этом языке. image_keywords — ВСЕГДА английский.

{src}

Создай {num_slides} слайдов. Детализация: {vol}

ТИПЫ СЛАЙДОВ (чередуй для разнообразия):
- "title" — титульный слайд (только для первого)
- "split" — изображение сбоку + нумерованный список из 3 пунктов
- "banner" — широкое фото-баннер сверху + 3 колонки с иконками внизу
- "text" — текстовый слайд без фото, с длинным содержанием

СТРУКТУРА JSON (строго, без markdown):
[
  {{
    "slide_number": 1,
    "layout": "title",
    "title": "Главный заголовок",
    "subtitle": "Подзаголовок или краткое описание",
    "points": [],
    "image_keywords": "skyline,conference,audience,stage"
  }},
  {{
    "slide_number": 2,
    "layout": "split",
    "title": "Заголовок слайда",
    "subtitle": "",
    "points": [
      {{"heading": "Подзаголовок 1", "text": "Описание пункта"}},
      {{"heading": "Подзаголовок 2", "text": "Описание пункта"}},
      {{"heading": "Подзаголовок 3", "text": "Описание пункта"}}
    ],
    "image_keywords": "whiteboard,meeting,team,office"
  }},
  {{
    "slide_number": 3,
    "layout": "banner",
    "title": "Заголовок",
    "subtitle": "",
    "points": [
      {{"heading": "Колонка 1", "text": "Описание"}},
      {{"heading": "Колонка 2", "text": "Описание"}},
      {{"heading": "Колонка 3", "text": "Описание"}}
    ],
    "image_keywords": "factory,robot,assembly,line"
  }},
  {{
    "slide_number": 4,
    "layout": "text",
    "title": "Заголовок",
    "subtitle": "Полный текстовый контент с деталями. Несколько абзацев.",
    "points": [],
    "image_keywords": ""
  }}
]

ПРАВИЛА:
- Слайд 1 ВСЕГДА layout="title"
- Чередуй split и banner для контентных слайдов
- Последний слайд может быть "text" (заключение)
- image_keywords (ОЧЕНЬ ВАЖНО для фото): 4-6 английских тегов через запятую — только КОНКРЕТНЫЕ визуальные вещи,
  которые реально сфотографировать: объекты, места, профессии, природа, техника (например: hospital,doctor,stethoscope
  или solar,panel,rooftop,sunlight). ЗАПРЕЩЕНО: абстракции вроде success,innovation,future,growth,quality — их нельзя снять на фото.
  Каждый слайд — НОВЫЙ набор тегов, строго по содержанию ЭТОГО слайда и общей темы.
- points: ровно 3 пункта для split/banner. У каждого heading + text.
- Для layout="text" и "title" points=[] пустой"""

    for attempt in range(3):
        try:
            resp = model.generate_content(prompt)
            return _clean_json(resp.text)
        except Exception as e:
            err = str(e)
            # Только Google Gemini (generate_content): квота RPM/TPM или бесплатный лимит.
            # К фото Pexels / Unsplash / Wikimedia / Pollinations это сообщение НЕ относится.
            if (
                "429" in err
                or "RESOURCE_EXHAUSTED" in err
                or "quota" in err.lower()
                or "rate" in err.lower() and "limit" in err.lower()
            ):
                time.sleep(5 * (attempt + 1))
                st.warning(
                    f"**Лимит Google Gemini** (генерация текста/структуры слайдов, не картинки). "
                    f"Повтор через паузу… **{attempt + 1}/3**.\n\n"
                    f"Если постоянно: проверь квоту в [Google AI Studio](https://aistudio.google.com/), "
                    f"другой API-ключ или тариф."
                )
                logging.info("[Gemini quota] attempt %s/3: %s", attempt + 1, err[:500])
                continue
            st.error(f"Ошибка: {e}")
            st.stop()
    st.error("3 попытки Gemini не удались — смени ключ или подожди.")
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE DOWNLOAD — поиск (Pexels / Unsplash / Wikimedia) + Pollinations + LoremFlickr
# ═══════════════════════════════════════════════════════════════════════════════
def _build_image_search_query(d: dict, slide_idx: int) -> str:
    """Запрос на англ. для stock API: теги слайда + латинские слова из заголовка."""
    kw = (d.get("image_keywords") or "").strip()
    parts = []
    for p in kw.replace(",", " ").split():
        w = re.sub(r"[^\w\s-]", "", p, flags=re.UNICODE).strip()
        if len(w) > 1:
            parts.append(w)
    title = d.get("title") or ""
    for w in re.findall(r"[a-zA-Z]{3,}", title):
        parts.append(w)
    q = " ".join(dict.fromkeys(parts))[:220].strip()
    if len(q) < 2:
        q = f"presentation topic slide {slide_idx + 1}"
    return q


def _download_image_url(url: str, slide_idx: int, source: str) -> bytes | None:
    if not url:
        return None
    try:
        _img_audit(slide_idx, source, "DOWNLOAD_URL", url[:140])
        r = requests.get(url, headers={**HDR, "Cache-Control": "no-cache"}, timeout=50, allow_redirects=True)
        if r.status_code == 200 and _valid_img(r.content) and len(r.content) > 800:
            _img_audit(slide_idx, source, "BYTES", f"{len(r.content)}B md5={_bytes_md5(r.content)[:16]}")
            return r.content
        _img_audit(slide_idx, source, "BAD_RESPONSE", f"status={r.status_code} len={len(r.content)}")
    except requests.RequestException as e:
        _img_audit(slide_idx, source, "URL_ERROR", repr(e))
    return None


def _try_pexels(query: str, slide_idx: int) -> bytes | None:
    key = (os.getenv("PEXELS_API_KEY") or "").strip()
    if not key:
        _img_audit(slide_idx, "Pexels", "SKIP", "нет PEXELS_API_KEY в .env — pexels.com/api")
        return None
    try:
        page = 1 + (slide_idx % 5)
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query[:200], "per_page": 15, "page": page},
            headers={"Authorization": key},
            timeout=25,
        )
        _img_audit(slide_idx, "Pexels", "API", f"status={r.status_code} q={query[:60]!r}")
        if r.status_code != 200:
            return None
        photos = (r.json() or {}).get("photos") or []
        if not photos:
            return None
        pick = photos[slide_idx % len(photos)]
        src = pick.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        return _download_image_url(url, slide_idx, "Pexels")
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        _img_audit(slide_idx, "Pexels", "ERROR", repr(e))
    return None


def _try_unsplash(query: str, slide_idx: int) -> bytes | None:
    key = (os.getenv("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        _img_audit(slide_idx, "Unsplash", "SKIP", "нет UNSPLASH_ACCESS_KEY — unsplash.com/developers")
        return None
    try:
        page = 1 + (slide_idx % 4)
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query[:200], "per_page": 12, "page": page},
            headers={"Authorization": f"Client-ID {key}"},
            timeout=25,
        )
        _img_audit(slide_idx, "Unsplash", "API", f"status={r.status_code} q={query[:60]!r}")
        if r.status_code != 200:
            return None
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        pick = results[slide_idx % len(results)]
        url = (pick.get("urls") or {}).get("regular") or (pick.get("urls") or {}).get("full")
        return _download_image_url(url, slide_idx, "Unsplash")
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        _img_audit(slide_idx, "Unsplash", "ERROR", repr(e))
    return None


def _try_wikimedia(query: str, slide_idx: int) -> bytes | None:
    """Wikimedia Commons — без API-ключа, только тематический поиск файлов."""
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": query[:200],
                "gsrnamespace": 6,
                "gsrlimit": 24,
                "prop": "imageinfo",
                "iiprop": "url|mime|thumburl",
                "iiurlwidth": 1280,
            },
            headers={**HDR, "Cache-Control": "no-cache"},
            timeout=22,
        )
        _img_audit(slide_idx, "Wikimedia", "API", f"status={r.status_code} q={query[:50]!r}")
        if r.status_code != 200:
            return None
        pages = ((r.json() or {}).get("query") or {}).get("pages") or {}
        candidates = []
        for _pid, p in pages.items():
            ii = (p.get("imageinfo") or [{}])[0]
            mime = (ii.get("mime") or "").lower()
            if not mime.startswith("image/") or "svg" in mime:
                continue
            url = ii.get("thumburl") or ii.get("url")
            if url:
                candidates.append((p.get("index", 9999), url))
        candidates.sort(key=lambda x: x[0])
        urls = [u for _, u in candidates]
        if not urls:
            return None
        url = urls[slide_idx % len(urls)]
        return _download_image_url(url, slide_idx, "Wikimedia")
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        _img_audit(slide_idx, "Wikimedia", "ERROR", repr(e))
    return None


def _pollination_seed(kw: str, idx: int, title: str) -> int:
    h = hashlib.md5(f"{kw}|{idx}|{title}|pollen".encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:8], 16) % 999_999_937 + 1


def _build_pollination_prompt(d: dict, idx: int) -> str:
    """Англ. промпт для AI-изображения строго по смыслу слайда."""
    kw = (d.get("image_keywords") or "").strip()
    title = (d.get("title") or "").strip()
    subtitle = (d.get("subtitle") or "").strip()
    parts = [
        "professional editorial photograph for a corporate presentation slide",
        "natural lighting, sharp focus, high resolution",
        "single clear subject, realistic, no text, no letters, no watermark, no logo",
    ]
    if kw:
        parts.append("subject and setting: " + kw.replace(",", ", "))
    if title:
        parts.append('slide title theme (visualize literally): ' + title[:100])
    if subtitle and len(subtitle) < 200:
        parts.append("context: " + subtitle[:160])
    for pt in (d.get("points") or [])[:2]:
        h = (pt.get("heading") or "").strip()
        if h:
            parts.append("detail: " + h[:70])
    return ", ".join(parts)[:320]


def _try_pollinations(prompt: str, seed: int, slide_idx: int):
    enc = urllib.parse.quote(prompt[:300], safe="")
    for attempt in range(3):
        s = (seed + attempt * 97_573) % 999_999_937 + 1
        try:
            _img_audit(slide_idx, "Pollinations", "REQUEST", f"attempt={attempt+1} seed={s} prompt[:80]={prompt[:80]!r}")
            r = requests.get(
                f"https://image.pollinations.ai/prompt/{enc}",
                params={
                    "width": "1024",
                    "height": "576",
                    "seed": str(s),
                    "nologo": "true",
                },
                headers={**HDR, "Cache-Control": "no-cache"},
                timeout=90,
            )
            if r.status_code == 200 and _valid_img(r.content) and len(r.content) > 5000:
                _img_audit(
                    slide_idx,
                    "Pollinations",
                    "DOWNLOAD",
                    f"{len(r.content)}B md5={_bytes_md5(r.content)[:16]}",
                )
                return r.content
            _img_audit(slide_idx, "Pollinations", "FAIL", f"status={r.status_code} len={len(r.content)}")
            if r.status_code == 429:
                time.sleep(8)
            elif r.status_code >= 500:
                time.sleep(3)
        except requests.RequestException as e:
            _img_audit(slide_idx, "Pollinations", "ERROR", repr(e))
            time.sleep(4)
    return None

def _flickr_lock(tags: str, idx: int, title: str = "") -> int:
    """LoremFlickr: lock= выбирает конкретное фото; CDN часто игнорирует ?random= (дубликаты)."""
    h = hashlib.md5(f"{tags}|{idx}|{title}".encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:12], 16) % (2**31 - 2) + 1


def _try_flickr(keywords, idx=0, title=""):
    words = []
    for p in keywords.replace(",", " ").split():
        w = re.sub(r"[^a-zA-Z0-9]", "", p).lower()
        if w and len(w) > 1:
            words.append(w)
    tags = ",".join(dict.fromkeys(words))[:80]
    if not tags:
        _img_audit(idx, "LoremFlickr", "SKIP", "empty tags (e.g. non-Latin keywords stripped)")
        return None
    if not _loremflickr_json_indicates_real_match(tags):
        _img_audit(
            idx,
            "LoremFlickr",
            "SKIP",
            "no real Flickr match — would be defaultImage placeholder (known 'ghost cat' source)",
        )
        return None
    lock = _flickr_lock(tags, idx, title)
    url = f"https://loremflickr.com/1024/768/{tags}"
    try:
        r = requests.get(
            url,
            params={"lock": str(lock)},
            headers={**HDR, "Cache-Control": "no-cache"},
            timeout=12,
            allow_redirects=True,
        )
        _img_audit(idx, "LoremFlickr", "HTTP", f"{r.status_code} url={url} lock={lock}")
        if r.status_code == 200 and _valid_img(r.content):
            _img_audit(idx, "LoremFlickr", "DOWNLOAD", f"{len(r.content)}B md5={_bytes_md5(r.content)[:16]}")
            return r.content
    except requests.RequestException as e:
        _img_audit(idx, "LoremFlickr", "ERROR", repr(e))
    return None

def _try_picsum(seed, slide_idx: int):
    safe = re.sub(r"[^a-zA-Z0-9]", "", str(seed)) or "x"
    url = f"https://picsum.photos/seed/{safe}/1024/768"
    try:
        _img_audit(slide_idx, "Picsum", "REQUEST", url)
        r = requests.get(
            url,
            headers={**HDR, "Cache-Control": "no-cache"},
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code == 200 and _valid_img(r.content):
            _img_audit(slide_idx, "Picsum", "DOWNLOAD", f"{len(r.content)}B md5={_bytes_md5(r.content)[:16]}")
            return r.content
    except requests.RequestException as e:
        _img_audit(slide_idx, "Picsum", "ERROR", repr(e))
    return None


def _accept_raster_for_slide(raw: bytes, source: str, slide_idx: int, prev_md5: list) -> bool:
    """
    Изоляция состояния: каждый принятый кадр уникален относительно предыдущего API-кадра
    (ловит застрявший один и тот же ответ/CDN).
    """
    h = _bytes_md5(raw)
    if not source.startswith("user") and prev_md5[0] is not None and h == prev_md5[0]:
        _img_audit(slide_idx, source, "REJECT", f"consecutive duplicate md5={h[:16]} (stale/cached payload)")
        return False
    prev_md5[0] = h
    _img_audit(slide_idx, source, "INJECT_OK", f"buffer md5={h[:16]} len={len(raw)}")
    return True


def download_images(slides, user_imgs, accent, writer=None, photo_pipeline: str = "search"):
    """
    photo_pipeline:
      search — Pexels → Unsplash → Wikimedia → LoremFlickr → Picsum → плейсхолдер
      ai_first — Pollinations → затем как выше
      flickr_fast — LoremFlickr → Pollinations → Picsum → …
    """
    results = []
    pool = list(user_imgs)
    prev_md5 = [None]

    for i, d in enumerate(slides):
        if d.get("layout") == "text":
            results.append(None)
            _img_audit(i, "pipeline", "SKIP", "text layout — no image slot")
            continue

        if pool:
            raw = pool.pop(0)
            if raw and _valid_img(raw):
                _accept_raster_for_slide(raw, "user_upload", i, prev_md5)
                buf = io.BytesIO(raw)
                buf.seek(0)
                results.append(buf)
                _img_audit(i, "user_upload", "BYTESIO", "seek=0 ready for add_picture")
                continue

        kw = (d.get("image_keywords") or "").strip()
        title = (d.get("title") or "").strip()
        sn = d.get("slide_number", i + 1)
        pollen_prompt = _build_pollination_prompt(d, i)
        pseed = _pollination_seed(kw, i, title)

        def try_place(blob: bytes, src: str) -> bool:
            if not blob or not _valid_img(blob):
                return False
            if not _accept_raster_for_slide(blob, src, i, prev_md5):
                return False
            b = io.BytesIO(blob)
            b.seek(0)
            results.append(b)
            return True

        try:
            if photo_pipeline == "search":
                q = _build_image_search_query(d, i)
                if writer:
                    writer(f"Слайд {i+1}/{len(slides)}: поиск фото «{q[:45]}…»")
                stock_done = False
                for label, fetcher in (
                    ("Pexels", _try_pexels),
                    ("Unsplash", _try_unsplash),
                    ("Wikimedia", _try_wikimedia),
                ):
                    blob = fetcher(q, i)
                    if try_place(blob or b"", label):
                        stock_done = True
                        time.sleep(0.18)
                        break
                if stock_done:
                    continue

            if photo_pipeline == "ai_first":
                if writer:
                    writer(f"Слайд {i+1}/{len(slides)}: AI-фото по теме…")
                img = _try_pollinations(pollen_prompt, pseed, i)
                if try_place(img, "Pollinations"):
                    time.sleep(0.4)
                    continue

            if writer:
                writer(f"Слайд {i+1}/{len(slides)}: сток LoremFlickr…")
            img = _try_flickr(kw, i, title) if kw else None
            if try_place(img or b"", "LoremFlickr"):
                time.sleep(0.1)
                continue

            if photo_pipeline == "flickr_fast":
                if writer:
                    writer(f"Слайд {i+1}/{len(slides)}: запасной AI…")
                img = _try_pollinations(pollen_prompt, pseed, i)
                if try_place(img or b"", "Pollinations"):
                    time.sleep(0.4)
                    continue

            seed_fb = hashlib.md5(f"{kw}|{sn}|{i}|{title}".encode("utf-8", errors="ignore")).hexdigest()
            img = _try_picsum(seed_fb, i)
            if try_place(img or b"", "Picsum"):
                time.sleep(0.08)
                continue
            seed2 = kw.replace(",", "-").replace(" ", "") + f"-slide{sn}-idx{i}"
            img = _try_picsum(seed2, i)
            if try_place(img or b"", "Picsum"):
                time.sleep(0.08)
                continue
            title_kw = re.sub(r"[^a-zA-Z\s]", "", title).replace(" ", ",")
            img = _try_flickr(title_kw, i + 500, title) if title_kw else None
            if try_place(img or b"", "LoremFlickr_title"):
                time.sleep(0.1)
                continue

            if writer:
                writer(f"Слайд {i+1}/{len(slides)}: плейсхолдер (без «кота»)…")
            _img_audit(i, "pipeline", "FALLBACK", "text placeholder — never LoremFlickr defaultImage")
            ph = _failure_placeholder_stream(accent, i + 1)
            raw_ph = ph.getvalue()
            prev_md5[0] = _bytes_md5(raw_ph)
            _img_audit(i, "placeholder", "INJECT_OK", f"md5={prev_md5[0][:16]} (no duplicate guard)")
            ph.seek(0)
            results.append(ph)
        except Exception as e:
            _img_audit(i, "pipeline", "EXCEPTION", repr(e))
            if writer:
                writer(f"Слайд {i+1}/{len(slides)}: ошибка — плейсхолдер")
            ph = _failure_placeholder_stream(accent, i + 1)
            raw_ph = ph.getvalue()
            prev_md5[0] = _bytes_md5(raw_ph)
            _img_audit(i, "placeholder_error", "INJECT_OK", f"md5={prev_md5[0][:16]}")
            ph.seek(0)
            results.append(ph)

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# PPTX BUILDER — Gamma AI architecture
# ═══════════════════════════════════════════════════════════════════════════════
def _emu(inches):
    return Emu(int(inches * 914400))

def _rgb(t):
    return RGBColor(*t)

def _clear(prs):
    lst = prs.slides._sldIdLst
    for s in list(lst):
        rid = s.get(qn("r:id"))
        if rid:
            prs.part.drop_rel(rid)
        lst.remove(s)

def _move_back(slide, shape):
    tree = slide.shapes._spTree
    el = shape._element
    tree.remove(el)
    tree.insert(2, el)

def _textbox(slide, left, top, w, h, text, size, color, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(_emu(left), _emu(top), _emu(w), _emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.color.rgb = _rgb(color)
    p.font.bold = bold
    p.alignment = align
    return box

def _multiline(slide, left, top, w, h, text, size, color):
    box = slide.shapes.add_textbox(_emu(left), _emu(top), _emu(w), _emu(h))
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(_norm(text).split("\n")):
        line = line.strip()
        if not line:
            continue
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(size)
        p.font.color.rgb = _rgb(color)
        p.space_after = Pt(4)
    return box

def _numbered_circle(slide, x, y, num, theme):
    sz = 0.45
    sh = slide.shapes.add_shape(9, _emu(x), _emu(y), _emu(sz), _emu(sz))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _rgb(theme["num_bg"])
    sh.line.fill.background()
    sh.text_frame.paragraphs[0].text = str(num)
    sh.text_frame.paragraphs[0].font.size = Pt(14)
    sh.text_frame.paragraphs[0].font.bold = True
    sh.text_frame.paragraphs[0].font.color.rgb = _rgb(theme["num_fg"])
    sh.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

def _accent_line(slide, x, y, h, color):
    sh = slide.shapes.add_shape(1, _emu(x), _emu(y), _emu(0.04), _emu(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _rgb(color)
    sh.line.fill.background()

def _set_alpha(shape, pct):
    sf = shape._element.spPr.find(qn("a:solidFill"))
    if sf is not None and len(sf) > 0:
        a = sf[0].makeelement(qn("a:alpha"), {})
        a.set("val", str(int((100 - pct) * 1000)))
        sf[0].append(a)

def build_pptx(slides_data, theme_key, user_imgs, progress_cb=None, photo_pipeline: str = "search"):
    T = THEMES[theme_key]
    SW, SH = SLIDE_W_IN, SLIDE_H_IN

    prs = Presentation()
    prs.slide_width = _emu(SW)
    prs.slide_height = _emu(SH)
    blank = prs.slide_layouts[6]

    def _status(msg):
        if progress_cb:
            progress_cb(0, len(slides_data) + 1, msg)

    images = download_images(slides_data, user_imgs, T["accent"], _status, photo_pipeline)

    for i, d in enumerate(slides_data):
        if progress_cb:
            progress_cb(i + 1, len(slides_data) + 1, f"Слайд {i+1}/{len(slides_data)}…")

        slide = prs.slides.add_slide(blank)
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = _rgb(T["bg"])

        layout = d.get("layout", "split")
        title = d.get("title", "")
        subtitle = d.get("subtitle", "")
        points = d.get("points", [])
        img = images[i] if i < len(images) else None
        if img is not None:
            img.seek(0)
            _img_audit(i, "python-pptx", "add_picture", f"layout={layout} stream_pos={img.tell()}")

        # ════════════ TITLE SLIDE ════════════
        if layout == "title":
            if img:
                pic = slide.shapes.add_picture(img, Emu(0), Emu(0), _emu(SW), _emu(SH))
                _move_back(slide, pic)
            overlay = slide.shapes.add_shape(1, Emu(0), _emu(SH * 0.45), _emu(SW), _emu(SH * 0.55))
            overlay.fill.solid()
            overlay.fore_color = None
            overlay.fill.fore_color.rgb = _rgb(T["bg"])
            overlay.line.fill.background()
            _set_alpha(overlay, 25)

            _textbox(slide, 0.8, SH * 0.50, SW - 1.6, 1.8, title, 42, T["title_color"], bold=True)
            if subtitle:
                _textbox(slide, 0.8, SH * 0.50 + 2.0, SW - 1.6, 1.0, subtitle, 20, T["muted"])

        # ════════════ SPLIT SLIDE (image + numbered list) ════════════
        elif layout == "split":
            img_on_left = (i % 2 == 1)
            img_w = 6.0
            text_start = img_w + 0.8 if img_on_left else 0.8
            img_x = 0.0 if img_on_left else SW - img_w

            if img:
                pic = slide.shapes.add_picture(img, _emu(img_x), Emu(0), _emu(img_w), _emu(SH))
                _move_back(slide, pic)

            accent_x = (img_w + 0.15) if img_on_left else (SW - img_w - 0.19)
            _accent_line(slide, accent_x, 0.4, SH - 0.8, T["accent"])

            text_w = SW - img_w - 1.4
            _textbox(slide, text_start, 0.6, text_w, 1.4, title, 30, T["title_color"], bold=True)

            y = 2.2
            for pi, pt in enumerate(points[:3]):
                _numbered_circle(slide, text_start, y, pi + 1, T)
                _textbox(slide, text_start + 0.65, y - 0.05, text_w - 0.8, 0.4,
                         pt.get("heading", ""), 17, T["title_color"], bold=True)
                _textbox(slide, text_start + 0.65, y + 0.40, text_w - 0.8, 0.9,
                         pt.get("text", ""), 13, T["text_color"])
                y += 2.0

        # ════════════ BANNER SLIDE (wide photo + 3 columns) ════════════
        elif layout == "banner":
            if img:
                pic = slide.shapes.add_picture(img, Emu(0), Emu(0), _emu(SW), _emu(3.2))
                _move_back(slide, pic)

            _textbox(slide, 0.8, 3.6, SW - 1.6, 0.8, title, 28, T["title_color"], bold=True)

            col_w = (SW - 2.4) / 3
            for ci, pt in enumerate(points[:3]):
                cx = 0.8 + ci * (col_w + 0.4)
                cy = 4.8
                _numbered_circle(slide, cx, cy, ci + 1, T)
                _textbox(slide, cx + 0.6, cy - 0.05, col_w - 0.7, 0.4,
                         pt.get("heading", ""), 16, T["title_color"], bold=True)
                _textbox(slide, cx + 0.6, cy + 0.40, col_w - 0.7, 1.8,
                         pt.get("text", ""), 12, T["text_color"])

        # ════════════ TEXT SLIDE (no image) ════════════
        elif layout == "text":
            _textbox(slide, 1.5, 1.0, SW - 3.0, 1.5, title, 34, T["title_color"], bold=True,
                     align=PP_ALIGN.CENTER)
            _accent_line(slide, SW / 2 - 1.5, 2.6, 0.04, T["accent"])
            if subtitle:
                _multiline(slide, 2.0, 3.2, SW - 4.0, SH - 4.0, subtitle, 15, T["text_color"])

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()

# ═══════════════════════════════════════════════════════════════════════════════
# SLIDE PREVIEW HTML
# ═══════════════════════════════════════════════════════════════════════════════
def _preview(d, i, theme_key):
    T = THEMES[theme_key]
    bg = "#{:02x}{:02x}{:02x}".format(*T["bg"])
    card = "#{:02x}{:02x}{:02x}".format(*T["card"])
    tc = "#{:02x}{:02x}{:02x}".format(*T["title_color"])
    tx = "#{:02x}{:02x}{:02x}".format(*T["text_color"])
    ac = "#{:02x}{:02x}{:02x}".format(*T["accent"])
    nb = "#{:02x}{:02x}{:02x}".format(*T["num_bg"])
    nf = "#{:02x}{:02x}{:02x}".format(*T["num_fg"])
    raw_kw = d.get("image_keywords") or "presentation"
    kw = urllib.parse.quote(raw_kw)
    lf_lock = _flickr_lock(raw_kw, i, "preview")
    layout = d.get("layout", "split")
    title = d.get("title", "")
    subtitle = d.get("subtitle", "")
    points = d.get("points", [])

    pts_html = ""
    for pi, pt in enumerate(points[:3]):
        pts_html += f"""<div style="display:flex;gap:8px;align-items:flex-start;margin-bottom:10px">
          <div style="min-width:28px;height:28px;background:{nb};border-radius:50%;display:flex;
            align-items:center;justify-content:center;color:{nf};font-weight:700;font-size:13px">{pi+1}</div>
          <div><div style="color:{tc};font-weight:700;font-size:14px">{pt.get('heading','')}</div>
          <div style="color:{tx};font-size:12px;margin-top:2px">{pt.get('text','')[:120]}</div></div></div>"""

    if layout == "title":
        return f"""<div class="slide-preview" style="position:relative;height:200px;
          background:url('https://loremflickr.com/700/200/{kw}?lock={lf_lock}') center/cover;border-radius:12px">
          <div style="position:absolute;bottom:0;left:0;right:0;padding:20px;
            background:linear-gradient(transparent,{bg}ee);border-radius:0 0 12px 12px">
            <div style="color:{tc};font-size:20px;font-weight:800">{title}</div>
            <div style="color:{tx};font-size:13px;margin-top:4px;opacity:.8">{subtitle[:120]}</div>
          </div></div>"""

    if layout == "split":
        img_side = "left" if i % 2 == 1 else "right"
        img_html = f'<img src="https://loremflickr.com/300/220/{kw}?lock={lf_lock}" style="width:38%;object-fit:cover;border-radius:{"12px 0 0 12px" if img_side=="left" else "0 12px 12px 0"}">'
        content = f'<div style="flex:1;padding:16px"><div style="color:{tc};font-size:16px;font-weight:700;margin-bottom:10px">{title}</div>{pts_html}</div>'
        if img_side == "left":
            inner = img_html + f'<div style="border-left:3px solid {ac};margin:10px 0"></div>' + content
        else:
            inner = content + f'<div style="border-right:3px solid {ac};margin:10px 0"></div>' + img_html
        return f'<div class="slide-preview" style="display:flex;min-height:200px;background:{card};border-radius:12px">{inner}</div>'

    if layout == "banner":
        return f"""<div class="slide-preview" style="background:{card};border-radius:12px;overflow:hidden">
          <img src="https://loremflickr.com/700/140/{kw}?lock={lf_lock}" style="width:100%;height:120px;object-fit:cover">
          <div style="padding:12px 16px">
            <div style="color:{tc};font-size:16px;font-weight:700;margin-bottom:10px">{title}</div>
            <div style="display:flex;gap:12px">{pts_html}</div>
          </div></div>"""

    return f"""<div class="slide-preview" style="background:{card};border-radius:12px;padding:20px;text-align:center">
      <div style="color:{tc};font-size:18px;font-weight:700;margin-bottom:8px">{title}</div>
      <div style="width:60px;height:3px;background:{ac};margin:0 auto 12px"></div>
      <div style="color:{tx};font-size:13px;text-align:left">{subtitle[:300]}</div></div>"""

# ═══════════════════════════════════════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════════════════════════════════════
st.title("✨ AI Презентатор Pro")
st.markdown("Gamma-style презентации с AI — тематические фото, нумерованные блоки, разные макеты.")

if st.session_state.generation_step == 1:
    t1, t2 = st.tabs(["📌 По теме", "📝 По тексту"])
    with t1:
        topic = st.text_input("Тема", placeholder="Например: Süni intellektin gələcəyi", key="topic_f")
    with t2:
        raw = st.text_area("Материал", height=200, key="raw_f")
    if st.button("🚀 Сгенерировать", type="primary", use_container_width=True):
        inp = topic.strip() or raw.strip()
        is_r = bool(raw.strip() and not topic.strip())
        if not inp:
            st.warning("Введите тему или текст.")
        else:
            with st.status("🧠 Генерация…", expanded=True) as status:
                st.write("Gemini AI…")
                result = generate_structure(inp, is_r)
                st.write(f"✅ {len(result)} слайдов")
                status.update(label="Готово!", state="complete", expanded=False)
            st.session_state.draft_data = result
            st.session_state.generation_step = 2
            st.session_state.pptx_bytes = None
            st.rerun()

if st.session_state.generation_step == 2 and st.session_state.draft_data:
    st.subheader("📝 Редактор")
    draft = st.session_state.draft_data
    for i, sl in enumerate(draft):
        layout_label = {"title": "🎬 Титульный", "split": "📐 Сплит", "banner": "🖼 Баннер", "text": "📄 Текст"}.get(sl.get("layout"), "❓")
        with st.expander(f"Слайд {i+1} ({layout_label}): {sl.get('title','')}", expanded=(i < 2)):
            st.markdown(_preview(sl, i, design_theme), unsafe_allow_html=True)
            c1, c2 = st.columns([1, 2])
            with c1:
                st.text_input("Заголовок", value=sl.get("title", ""), key=f"t_{i}")
                st.text_input("Теги фото (англ.)", value=sl.get("image_keywords", ""), key=f"kw_{i}")
            with c2:
                if sl.get("layout") in ("title", "text"):
                    st.text_area("Подзаголовок/текст", value=sl.get("subtitle", ""), height=100, key=f"sub_{i}")
                else:
                    for pi, pt in enumerate(sl.get("points", [])[:3]):
                        st.text_input(f"Пункт {pi+1} заголовок", value=pt.get("heading", ""), key=f"ph_{i}_{pi}")
                        st.text_input(f"Пункт {pi+1} текст", value=pt.get("text", ""), key=f"pt_{i}_{pi}")

    cb, cf = st.columns(2)
    with cb:
        if st.button("← Назад", use_container_width=True):
            st.session_state.generation_step = 1
            st.session_state.draft_data = None
            st.rerun()
    with cf:
        if st.button("🎨 Собрать PPTX", type="primary", use_container_width=True):
            for idx, sl in enumerate(draft):
                sl["title"] = st.session_state.get(f"t_{idx}", sl["title"])
                sl["image_keywords"] = st.session_state.get(f"kw_{idx}", sl.get("image_keywords", ""))
                if sl.get("layout") in ("title", "text"):
                    sl["subtitle"] = st.session_state.get(f"sub_{idx}", sl.get("subtitle", ""))
                else:
                    for pi in range(min(3, len(sl.get("points", [])))):
                        sl["points"][pi]["heading"] = st.session_state.get(f"ph_{idx}_{pi}", sl["points"][pi].get("heading", ""))
                        sl["points"][pi]["text"] = st.session_state.get(f"pt_{idx}_{pi}", sl["points"][pi].get("text", ""))

            with st.status("🎨 Сборка…", expanded=True) as status:
                prog = st.progress(0)
                def on_p(s, t, m):
                    prog.progress(s / t, text=m)
                try:
                    data = build_pptx(
                        draft,
                        design_theme,
                        list(st.session_state.user_images),
                        on_p,
                        photo_pipeline=photo_pipeline,
                    )
                    st.session_state.pptx_bytes = data
                    st.session_state.generation_step = 3
                    status.update(label="Готово!", state="complete", expanded=False)
                except Exception as e:
                    status.update(label="Ошибка", state="error")
                    st.error(str(e))
                    st.code(traceback.format_exc())
                    st.stop()
            st.rerun()

if st.session_state.generation_step == 3 and st.session_state.pptx_bytes:
    st.balloons()
    st.success("Презентация готова!")
    st.download_button("📥 Скачать", st.session_state.pptx_bytes, "AI_Presentation.pptx",
                       "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                       use_container_width=True)
    if st.button("🔄 Новая", use_container_width=True):
        for k in ("draft_data", "pptx_bytes"):
            st.session_state[k] = None
        st.session_state.generation_step = 1
        st.rerun()
