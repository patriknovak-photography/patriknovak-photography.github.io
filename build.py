#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sestaví web z fotografií ve složce photos/ do složky docs/.

    python build.py            sestaví web
    python build.py --serve    sestaví web a otevře náhled v prohlížeči
    python build.py --clean    smaže docs/ a sestaví vše znovu

Potřebuje Python 3.11+ a knihovnu Pillow (pip install pillow).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import io
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PHOTOS = ROOT / "photos"
SRC = ROOT / "src"
OUT = ROOT / "docs"
MANIFEST = OUT / ".build-manifest.json"

# Velikosti a kvalita obrázků. Změna čísla VERSION vynutí nové vygenerování všech obrázků.
VERSION = 3
THUMB_HEIGHT, THUMB_MAX_WIDTH, THUMB_Q = 560, 1500, 80
MEDIUM_BOX, MEDIUM_Q = 1400, 82
LARGE_BOX, LARGE_BOX_PANO, LARGE_Q = 2400, 3000, 84
RESERVED = {"en", "img", "assets", "o-mne", "kontakt", "about", "contact"}
BLANK = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="

UI = {
    "cs": dict(
        albums="Alba", about="O mně", contact="Kontakt", other="English", other_code="en",
        rights="Všechna práva vyhrazena.", next_album="Další album", all_albums="Všechna alba",
        photo="fotografie", write="Napsat zprávu", name="Jméno", email="E-mail", message="Zpráva",
        send="Odeslat zprávu", privacy="Zprávu doručí služba Web3Forms. Vaše údaje použiji jen k odpovědi.",
        skip="Přeskočit na obsah", nf_title="Stránka nenalezena", nf_text="Tahle stránka tu není.",
        nf_back="Zpět na úvod", subject="Zpráva z webu",
        js=dict(viewer="Prohlížení fotografie", prev="Předchozí fotografie", next="Další fotografie",
                close="Zavřít", sending="Odesílám…", sent="Zpráva odeslána. Děkuji.",
                failed="Zprávu se nepodařilo odeslat. Zkuste to prosím znovu.",
                formOff="Formulář zatím není zapnutý. V souboru site.toml chybí klíč web3forms_key."),
    ),
    "en": dict(
        albums="Albums", about="About", contact="Contact", other="Česky", other_code="cs",
        rights="All rights reserved.", next_album="Next album", all_albums="All albums",
        photo="photograph", write="Write a message", name="Name", email="Email", message="Message",
        send="Send message", privacy="The message is delivered by Web3Forms. I use your details only to reply.",
        skip="Skip to content", nf_title="Page not found", nf_text="This page does not exist.",
        nf_back="Back to the start", subject="Message from the website",
        js=dict(viewer="Photograph viewer", prev="Previous photograph", next="Next photograph",
                close="Close", sending="Sending…", sent="Message sent. Thank you.",
                failed="The message could not be sent. Please try again.",
                formOff="The form is not switched on yet. The web3forms_key is missing in site.toml."),
    ),
}


def fail(msg: str) -> "None":
    print("\nCHYBA: " + msg)
    sys.exit(1)


def load_toml(path: Path) -> dict:
    try:
        import tomllib as toml
    except ImportError:
        try:
            import tomli as toml  # type: ignore
        except ImportError:
            fail("Je potřeba Python 3.11 nebo novější (nebo doinstaluj: pip install tomli). "
                 f"Teď běží Python {sys.version.split()[0]}.")
    try:
        with open(path, "rb") as f:
            return toml.load(f)
    except Exception as e:  # chyba v zápisu souboru
        fail(f"Soubor {path.relative_to(ROOT)} má chybu v zápisu: {e}")
    return {}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "album"


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def count_label(n: int, lang: str) -> str:
    if lang == "en":
        return f"{n} photograph" + ("" if n == 1 else "s")
    return f"{n} " + ("fotografie" if 1 <= n <= 4 else "fotografií")


# ── obrázky ─────────────────────────────────────────────────────────────────

def prepare_image(src: Path):
    """Načte fotografii, srovná otočení a převede barvy do sRGB."""
    from PIL import Image, ImageOps, ImageCms
    im = Image.open(src)
    icc = im.info.get("icc_profile")
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    if icc:
        try:
            prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if "sRGB" not in ImageCms.getProfileDescription(prof):
                im = ImageCms.profileToProfile(im.convert("RGB"), prof, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:
            pass
    return im.convert("RGB")


def save_jpeg(im, dst: Path, quality: int, author: str) -> None:
    from PIL import Image
    exif = Image.Exif()
    plain = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode()
    exif[0x013B] = plain
    exif[0x8298] = f"(c) {plain}. All rights reserved."
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True, exif=exif.tobytes())


def fitted(im, box: int):
    from PIL import Image, ImageFilter
    if max(im.size) <= box:
        return im
    out = im.copy()
    out.thumbnail((box, box), Image.LANCZOS, reducing_gap=3.0)
    return out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=30, threshold=1))


def make_derivatives(src: Path, base: Path, author: str, cache: dict, key: str) -> dict:
    """Vytvoří náhled (-t), střední (-m) a velkou (-l) verzi. Hotové a nezměněné přeskočí."""
    from PIL import Image, ImageFilter, ImageStat
    st = src.stat()
    sig = [st.st_size, VERSION]  # velikost souboru stačí; čas změny se při kopírování a rozbalování mění
    names = {k: base.with_name(base.name + f"-{k}.jpg") for k in "tml"}
    old = cache.get(key)
    if old and old.get("sig") == sig and all(p.exists() for p in names.values()):
        return old
    im = prepare_image(src)
    w, h = im.size
    ar = w / h
    large = fitted(im, LARGE_BOX_PANO if max(ar, 1 / ar) >= 1.8 else LARGE_BOX)
    medium = fitted(large, MEDIUM_BOX)
    tw = min(THUMB_MAX_WIDTH, round(THUMB_HEIGHT * ar))
    th = round(tw / ar)
    thumb = large.resize((tw, th), Image.LANCZOS, reducing_gap=3.0) if th < large.size[1] else large
    thumb = thumb.filter(ImageFilter.UnsharpMask(radius=0.5, percent=40, threshold=1))
    save_jpeg(large, names["l"], LARGE_Q, author)
    save_jpeg(medium, names["m"], MEDIUM_Q, author)
    save_jpeg(thumb, names["t"], THUMB_Q, author)
    r, g, b = (round(v) for v in ImageStat.Stat(thumb.resize((16, 16))).mean[:3])
    info = dict(sig=sig, w=large.size[0], h=large.size[1], mw=medium.size[0], mh=medium.size[1],
                tw=thumb.size[0], th=thumb.size[1], color=f"#{r:02x}{g:02x}{b:02x}")
    cache[key] = info
    return info


# ── načtení obsahu ──────────────────────────────────────────────────────────

def load_albums(cfg: dict, cache: dict) -> list[dict]:
    if not PHOTOS.is_dir():
        fail("Chybí složka photos/.")
    albums, seen = [], set()
    for folder in sorted(p for p in PHOTOS.iterdir() if p.is_dir() and p.name[0] not in "_."):
        files = sorted(f for f in folder.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"))
        if not files:
            print(f"  přeskočeno (prázdné): {folder.name}")
            continue
        meta = load_toml(folder / "album.toml") if (folder / "album.toml").exists() else {}
        base_name = re.sub(r"^\d+[-_ ]*", "", folder.name)
        slug_cs = slugify(meta.get("slug_cs") or base_name)
        slug_en = slugify(meta.get("slug_en") or meta.get("title_en") or base_name)
        for s in (slug_cs, slug_en):
            if s in RESERVED:
                fail(f"Album {folder.name}: adresa '{s}' je vyhrazená, zvol jiný název složky nebo slug.")
        if slug_cs in seen:
            fail(f"Dvě alba mají stejnou adresu '{slug_cs}'. Přejmenuj jednu ze složek.")
        seen.add(slug_cs)
        title_cs = meta.get("title_cs") or base_name.replace("-", " ").capitalize()
        album = dict(
            folder=folder.name, slug=dict(cs=slug_cs, en=slug_en),
            title=dict(cs=title_cs, en=meta.get("title_en") or title_cs),
            intro=dict(cs=meta.get("intro_cs", ""), en=meta.get("intro_en", "")),
            theme="light" if meta.get("theme") == "light" else "dark", photos=[],
        )
        print(f"  {folder.name}: {len(files)} fotografií", flush=True)
        for f in files:
            stem = slugify(f.stem)
            try:
                info = make_derivatives(f, OUT / "img" / slug_cs / stem, cfg["name"], cache, f"{folder.name}/{f.name}")
            except Exception as e:
                print(f"    ! {f.name} nejde zpracovat ({e}) – vynecháno")
                continue
            album["photos"].append(dict(info, file=f.name, key=f"{folder.name}/{f.name}", url=f"img/{slug_cs}/{stem}"))
        if not album["photos"]:
            continue
        cover = meta.get("cover")
        album["cover"] = next((p for p in album["photos"] if p["file"] == cover), album["photos"][0])
        if cover and album["cover"]["file"] != cover:
            print(f"    ! titulní fotka '{cover}' v albu není, použita první")
        albums.append(album)
    if not albums:
        fail("Ve složce photos/ není žádné album s fotografiemi.")
    return albums


def find_photo(albums: list[dict], ref: str):
    ref = ref.strip().replace("\\", "/")
    for a in albums:
        for p in a["photos"]:
            if p["key"] == ref:
                return p
    return None


# ── HTML ────────────────────────────────────────────────────────────────────

class Site:
    def __init__(self, cfg: dict, albums: list[dict], version: str):
        self.cfg, self.albums, self.v = cfg, albums, version
        self.base = (cfg.get("base_url") or "").rstrip("/")
        self.year = dt.date.today().year
        self.pages: list[tuple[str, str]] = []  # (cesta, html)
        self.urls: list[tuple[str, str]] = []   # (cs, en) pro sitemap

    # adresy stránek, vždy relativně ke kořeni webu
    def path(self, lang: str, kind: str, album: dict | None = None) -> str:
        pre = "" if lang == "cs" else "en/"
        if kind == "home":
            return pre
        if kind == "album":
            return f"{pre}{album['slug'][lang]}/"
        return pre + {"about": {"cs": "o-mne/", "en": "about/"}, "contact": {"cs": "kontakt/", "en": "contact/"}}[kind][lang]

    def page(self, lang: str, kind: str, body: str, *, title: str, desc: str, theme: str,
             album: dict | None = None, og: dict | None = None, over: bool = False) -> None:
        ui, cfg = UI[lang], self.cfg
        here = self.path(lang, kind, album)
        up = "../" * here.count("/")
        other = self.path(ui["other_code"], kind, album)
        home = self.path(lang, "home")
        nav = [("home", ui["albums"], home + "#alba"), ("about", ui["about"], self.path(lang, "about")),
               ("contact", ui["contact"], self.path(lang, "contact"))]
        current = ' aria-current="page"'
        links = "".join(
            f'<a href="{up}{href}"{current if k == kind else ""}>{esc(label)}</a>'
            for k, label, href in nav)
        meta = ""
        if self.base:
            meta += f'<link rel="canonical" href="{self.base}/{here}">\n'
            for code in ("cs", "en"):
                meta += f'<link rel="alternate" hreflang="{code}" href="{self.base}/{self.path(code, kind, album)}">\n'
            meta += f'<meta property="og:type" content="website">\n<meta property="og:title" content="{esc(title)}">\n'
            meta += f'<meta property="og:description" content="{esc(desc)}">\n<meta property="og:url" content="{self.base}/{here}">\n'
            if og:
                meta += (f'<meta property="og:image" content="{self.base}/{og["url"]}-m.jpg">\n'
                         f'<meta property="og:image:width" content="{og["mw"]}">\n<meta property="og:image:height" content="{og["mh"]}">\n'
                         '<meta name="twitter:card" content="summary_large_image">\n')
        protect = ' class="protect"' if cfg.get("protect_images", True) else ""
        color = "#131514" if theme == "dark" else "#e7e9e8"
        doc = f"""<!doctype html>
<html lang="{lang}" data-theme="{theme}"{protect}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="{esc(cfg['name'])}">
<meta name="theme-color" content="{color}">
{meta}<link rel="icon" href="{up}favicon.svg" type="image/svg+xml">
<link rel="preload" href="{up}assets/fonts/lora.woff" as="font" type="font/woff" crossorigin>
<link rel="stylesheet" href="{up}assets/style.css?v={self.v}">
</head>
<body>
<a class="skip" href="#obsah">{esc(ui['skip'])}</a>
<header class="head{' over' if over else ''}">
<a class="name" href="{up}{home}">{esc(cfg['name'])}</a>
<nav>{links}<a class="lang" href="{up}{other}" lang="{ui['other_code']}" hreflang="{ui['other_code']}">{esc(ui['other'])}</a></nav>
</header>
<main id="obsah">
{body.replace('{UP}', up)}
</main>
<footer class="foot">
<span>© {self.year} {esc(cfg['name'])}. {esc(ui['rights'])}</span>
<a href="{up}{self.path(lang, 'contact')}">{esc(ui['contact'])}</a>
</footer>
<script type="application/json" id="i18n">{json.dumps(ui['js'], ensure_ascii=False)}</script>
<script src="{up}assets/site.js?v={self.v}" defer></script>
</body>
</html>
"""
        self.pages.append((here + "index.html", doc))
        if lang == "cs":
            self.urls.append((here, other))

    def srcset(self, p: dict, sizes: tuple[str, ...]) -> str:
        w = {"t": p["tw"], "m": p["mw"], "l": p["w"]}
        return ", ".join(f"{{UP}}{p['url']}-{s}.jpg {w[s]}w" for s in sizes)

    def home(self, lang: str) -> None:
        cfg, t = self.cfg, self.cfg[lang]
        slides = []
        for i, ref in enumerate(cfg.get("hero", [])):
            name, _, focus = ref.partition("|")
            p = find_photo(self.albums, name)
            if not p:
                if lang == "cs":
                    print(f"    ! úvodní fotka '{name.strip()}' nenalezena – vynecháno")
                continue
            pos = f' style="object-position:{esc(focus.strip())}"' if focus.strip() else ""
            sizes = "(orientation: portrait) 260vw, 100vw"
            if not slides:
                img = (f'<img src="{{UP}}{p["url"]}-m.jpg" srcset="{self.srcset(p, ("m", "l"))}" sizes="{sizes}" '
                       f'width="{p["w"]}" height="{p["h"]}" alt="" fetchpriority="high" draggable="false"{pos}>')
            else:
                img = (f'<img src="{BLANK}" data-src="{{UP}}{p["url"]}-m.jpg" data-srcset="{self.srcset(p, ("m", "l"))}" '
                       f'sizes="{sizes}" width="{p["w"]}" height="{p["h"]}" alt="" draggable="false"{pos}>')
            slides.append(f'<div class="slide{" on" if not slides else ""}" style="background:{p["color"]}">{img}</div>')
        if not slides:
            p = self.albums[0]["cover"]
            slides.append(f'<div class="slide on"><img src="{{UP}}{p["url"]}-l.jpg" width="{p["w"]}" height="{p["h"]}" alt="" draggable="false"></div>')
        wall = []
        for a in self.albums:
            c = a["cover"]
            ar = c["w"] / c["h"]
            shape = "landscape" if ar > 1.15 else "portrait" if ar < 0.87 else "square"
            wall.append(
                f'<a class="piece {shape}" href="{{UP}}{self.path(lang, "album", a)}">'
                f'<div class="frame" style="background:{c["color"]}"><img src="{{UP}}{c["url"]}-m.jpg" srcset="{self.srcset(c, ("t", "m", "l"))}" '
                f'sizes="(max-width: 760px) 100vw, 56vw" width="{c["w"]}" height="{c["h"]}" alt="" loading="lazy" decoding="async" draggable="false"></div>'
                f'<div class="label"><span class="t">{esc(a["title"][lang])}</span>'
                f'<span class="n">{count_label(len(a["photos"]), lang)}</span></div></a>')
        body = f"""<section class="hero">
{chr(10).join(slides)}
<div class="sign"><h1>{esc(cfg['name'])}</h1><p class="tag">{esc(t.get('tagline', ''))}</p></div>
</section>
<section class="wall" id="alba" aria-label="{esc(UI[lang]['albums'])}">
{chr(10).join(wall)}
</section>"""
        first = find_photo(self.albums, cfg.get("hero", [""])[0].partition("|")[0]) if cfg.get("hero") else None
        self.page(lang, "home", body, title=f"{cfg['name']} – {t.get('tagline', '')}", desc=t.get("description", ""),
                  theme="dark", og=first or self.albums[0]["cover"], over=True)

    def album(self, lang: str, a: dict, nxt: dict) -> None:
        ui, title = UI[lang], a["title"][lang]
        items = []
        for i, p in enumerate(a["photos"], 1):
            ar = p["w"] / p["h"]
            sizes = f"(max-width: 760px) {min(100, round(ar * 66))}vw, {round(ar * 520)}px"
            lazy = ' loading="lazy" decoding="async"' if i > 4 else ""
            items.append(
                f'<a href="{{UP}}{p["url"]}-l.jpg" data-m="{{UP}}{p["url"]}-m.jpg" data-mw="{p["mw"]}" data-w="{p["w"]}" data-h="{p["h"]}" '
                f'style="--ar:{ar:.4f};background:{p["color"]}"><img src="{{UP}}{p["url"]}-t.jpg" srcset="{self.srcset(p, ("t", "m"))}" '
                f'sizes="{sizes}" width="{p["tw"]}" height="{p["th"]}" alt="{esc(title)} – {ui["photo"]} {i}"{lazy} draggable="false"></a>')
        intro = a["intro"][lang]
        body = f"""<div class="title">
<h1>{esc(title)}</h1>
<p class="intro">{esc(intro)}<span>{count_label(len(a['photos']), lang)}</span></p>
</div>
<div class="grid">
{chr(10).join(items)}
</div>
<nav class="onward">
<a class="next" href="{{UP}}{self.path(lang, 'album', nxt)}"><small>{esc(ui['next_album'])}</small><span>{esc(nxt['title'][lang])}</span></a>
<a class="all" href="{{UP}}{self.path(lang, 'home')}#alba">{esc(ui['all_albums'])}</a>
</nav>"""
        desc = f"{title} – {intro}" if intro else f"{title} – {self.cfg['name']}"
        self.page(lang, "album", body, title=f"{title} – {self.cfg['name']}", desc=desc, theme=a["theme"], album=a, og=a["cover"])

    def about(self, lang: str) -> None:
        ui, t = UI[lang], self.cfg[lang]
        paras = [p.strip() for p in re.split(r"\n\s*\n", t.get("about", "").strip()) if p.strip()]
        lead = ' class="lead"'
        text = "".join(f'<p{lead if i == 0 else ""}>{esc(p)}</p>' for i, p in enumerate(paras))
        p = find_photo(self.albums, self.cfg.get("about_image", ""))
        fig = ""
        if p:
            fig = (f'<figure><img src="{{UP}}{p["url"]}-m.jpg" srcset="{self.srcset(p, ("t", "m"))}" sizes="(max-width: 760px) 80vw, 30rem" '
                   f'width="{p["mw"]}" height="{p["mh"]}" alt="" draggable="false"></figure>')
        body = f"""<div class="page{'' if fig else ' solo'}">
<div>
<h1>{esc(ui['about'])}</h1>
{text}
<p><a class="more" href="{{UP}}{self.path(lang, 'contact')}">{esc(ui['write'])}</a></p>
</div>
{fig}
</div>"""
        self.page(lang, "about", body, title=f"{ui['about']} – {self.cfg['name']}", desc=paras[0] if paras else "", theme="light", og=p)

    def contact(self, lang: str) -> None:
        ui, t = UI[lang], self.cfg[lang]
        key = (self.cfg.get("web3forms_key") or "").strip()
        body = f"""<div class="page solo">
<div>
<h1>{esc(ui['contact'])}</h1>
<p class="lead">{esc(t.get('contact_intro', ''))}</p>
<p class="note">{esc(t.get('prints', ''))}</p>
<form data-contact action="https://api.web3forms.com/submit" method="post">
<input type="hidden" name="access_key" value="{esc(key)}">
<input type="hidden" name="subject" value="{esc(ui['subject'])} – {esc(self.cfg['name'])}">
<input type="hidden" name="from_name" value="{esc(self.cfg['name'])} web">
<div class="hp" aria-hidden="true"><input type="checkbox" name="botcheck" tabindex="-1" autocomplete="off"></div>
<label>{esc(ui['name'])}<input type="text" name="name" autocomplete="name" required></label>
<label>{esc(ui['email'])}<input type="email" name="email" autocomplete="email" required></label>
<label>{esc(ui['message'])}<textarea name="message" required></textarea></label>
<button class="send" type="submit">{esc(ui['send'])}</button>
<p class="status" role="status"></p>
<p class="small">{esc(ui['privacy'])}</p>
</form>
</div>
</div>"""
        self.page(lang, "contact", body, title=f"{ui['contact']} – {self.cfg['name']}", desc=t.get("prints", ""), theme="light")

    def not_found(self) -> str:
        root = (self.base + "/") if self.base else "./"
        blocks = "".join(
            f'<p class="lead" lang="{l}">{esc(UI[l]["nf_text"])} <a class="more" href="{root}{self.path(l, "home")}">{esc(UI[l]["nf_back"])}</a></p>'
            for l in ("cs", "en"))
        return f"""<!doctype html>
<html lang="cs" data-theme="dark">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(UI['cs']['nf_title'])} – {esc(self.cfg['name'])}</title><meta name="robots" content="noindex">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{root}assets/style.css?v={self.v}"></head>
<body><header class="head"><a class="name" href="{root}">{esc(self.cfg['name'])}</a></header>
<main><div class="page solo"><div><h1>404</h1>{blocks}</div></div></main></body></html>
"""

    def build(self) -> None:
        for lang in ("cs", "en"):
            if lang not in self.cfg:
                fail(f"V site.toml chybí oddíl [{lang}].")
            self.home(lang)
            for i, a in enumerate(self.albums):
                self.album(lang, a, self.albums[(i + 1) % len(self.albums)])
            self.about(lang)
            self.contact(lang)


# ── sestavení ───────────────────────────────────────────────────────────────

def build(clean: bool = False) -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        fail("Chybí knihovna Pillow. Nainstaluj ji příkazem:  pip install pillow")
    cfg = load_toml(ROOT / "site.toml")
    if not cfg.get("name"):
        fail("V site.toml chybí name.")
    if clean and OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(exist_ok=True)
    old = {}
    if MANIFEST.exists():
        try:
            old = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            old = {}
    cache = old.get("images", {})

    print("Fotografie:")
    albums = load_albums(cfg, cache)

    css, js = (SRC / "style.css").read_bytes(), (SRC / "site.js").read_bytes()
    version = hashlib.md5(css + js).hexdigest()[:8]
    site = Site(cfg, albums, version)
    site.build()

    written: set[str] = set()

    def put(rel: str, data: bytes | str) -> None:
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if not dst.exists() or dst.read_bytes() != raw:
            dst.write_bytes(raw)
        written.add(rel)

    for rel, doc in site.pages:
        put(rel, doc)
    put("404.html", site.not_found())
    put("assets/style.css", css)
    put("assets/site.js", js)
    put("favicon.svg", (SRC / "favicon.svg").read_bytes())
    for f in sorted((SRC / "fonts").iterdir()):
        put(f"assets/fonts/{f.name}", f.read_bytes())
    put(".nojekyll", "")
    if site.base:
        rows = "".join(
            f'<url><loc>{site.base}/{cs}</loc>'
            f'<xhtml:link rel="alternate" hreflang="cs" href="{site.base}/{cs}"/>'
            f'<xhtml:link rel="alternate" hreflang="en" href="{site.base}/{en}"/></url>\n'
            f'<url><loc>{site.base}/{en}</loc>'
            f'<xhtml:link rel="alternate" hreflang="cs" href="{site.base}/{cs}"/>'
            f'<xhtml:link rel="alternate" hreflang="en" href="{site.base}/{en}"/></url>\n'
            for cs, en in site.urls)
        put("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                           f'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n{rows}</urlset>\n')
        put("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site.base}/sitemap.xml\n")
    else:
        put("robots.txt", "User-agent: *\nAllow: /\n")

    used = {p["key"] for a in albums for p in a["photos"]}
    for a in albums:
        for p in a["photos"]:
            for s in "tml":
                written.add(f"{p['url']}-{s}.jpg")
    # úklid: smaže jen to, co dřív vytvořil tento skript a už není potřeba
    for rel in set(old.get("files", [])) - written:
        f = OUT / rel
        if f.is_file():
            f.unlink()
            try:
                f.parent.rmdir()
            except OSError:
                pass
    MANIFEST.write_text(json.dumps(dict(files=sorted(written), images={k: v for k, v in cache.items() if k in used}),
                                   ensure_ascii=False), encoding="utf-8")

    total = sum(len(a["photos"]) for a in albums)
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"\nHotovo: {len(albums)} alb, {total} fotografií, {len(site.pages)} stránek, {size:.0f} MB ve složce docs/")
    if not (cfg.get("web3forms_key") or "").strip():
        print("Pozor: kontaktní formulář neodesílá, v site.toml chybí web3forms_key.")
    if not site.base:
        print("Tip: až budeš znát adresu webu, doplň ji do site.toml jako base_url.")


def serve(port: int) -> None:
    import functools
    import http.server
    import threading
    import webbrowser
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as e:
        fail(f"Port {port} je obsazený ({e}). Zkus: python build.py --serve --port {port + 1}")
    url = f"http://127.0.0.1:{port}/"
    print(f"\nNáhled běží na {url}\nUkončíš ho klávesami Ctrl+C nebo zavřením okna.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nNáhled ukončen.")
    finally:
        httpd.server_close()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Sestaví fotografický web do složky docs/.")
    ap.add_argument("--serve", action="store_true", help="po sestavení spustí náhled v prohlížeči")
    ap.add_argument("--port", type=int, default=8000, help="port náhledu (výchozí 8000)")
    ap.add_argument("--clean", action="store_true", help="smaže docs/ a sestaví vše znovu")
    args = ap.parse_args()
    try:
        build(clean=args.clean)
    except SystemExit:
        raise
    except Exception as e:
        fail(f"Sestavení selhalo: {type(e).__name__}: {e}")
    if args.serve:
        serve(args.port)


if __name__ == "__main__":
    main()
