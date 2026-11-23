#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Watermark podle návrhu Watermark_06: podpis, tah štětcem a PHOTOGRAPHY.

Varianty se liší jen písmem nápisu PHOTOGRAPHY:
    copperplate   původní písmo z PDF (Copperplate, Apple)
    quattrocento  Quattrocento Sans Bold   (OFL – volné i pro komerční použití)
    spectral      Spectral SC Bold         (OFL)
    cinzel        Cinzel 700               (OFL)

Nápis z volného písma se vysází do stejného místa, stejné výšky verzálek a stejné celkové šířky
jako v originálu (mezery mezi písmeny se dorovnají).

Zdroj ve složce podpis06/ (vyřezáno z Watermark_06.pdf, 400 dpi):
    podpis-linka.png       podpis a tah štětcem (bílá = inkoust)
    text-copperplate.png   původní nápis
    text-pozice.json       poloha a rozměr nápisu
Písma ve složce fonty/ (licence OFL přiloženy).

Výstup do vystup/:
    watermark-06-<varianta>-{bila,cerna}.svg / -<šířka>.png

Potřebuje:  pip install pillow numpy opencv-python

    python generuj_watermark06.py
    python generuj_watermark06.py --jen cinzel --widths 300 2000
    python generuj_watermark06.py --pismo vlastni=C:\\Windows\\Fonts\\neco.ttf
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLORS = {"bila": "#ffffff", "cerna": "#111111"}
W = 300.0
FONTS = {  # název: (soubor, váha u proměnného písma)
    "quattrocento": ("QuattrocentoSans-Bold.ttf", None),
    "spectral": ("SpectralSC-Bold.ttf", None),
    "cinzel": ("Cinzel[wght].ttf", 700),
}


def fail(msg: str) -> None:
    print("CHYBA: " + msg)
    sys.exit(1)


def f2(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def set_text(shape, box: dict, font_path: Path, wght):
    """Vysází text písmem font_path do obdélníku box (výška verzálek = h, šířka = w). -> maska 0–1."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    if not font_path.is_file():
        fail(f"Chybí písmo {font_path}")
    size = 1000
    f = ImageFont.truetype(str(font_path), size)
    if wght:
        try:
            axes = f.get_variation_axes()
            def nm(a):
                n = a.get("name", b"")
                return n.decode("utf-8", "ignore") if isinstance(n, bytes) else str(n)
            f.set_variation_by_axes([wght if nm(x) == "Weight" else x["default"] for x in axes])
        except Exception as e:
            print(f"  ! váhu {wght} u {font_path.name} nejde nastavit ({e}), použije se výchozí")
    glyphs = []
    for ch in box["text"]:
        l, t, r, b = f.getbbox(ch)
        im = Image.new("L", (r - l + 40, b - t + 40), 0)
        ImageDraw.Draw(im).text((20 - l, 20 - t), ch, font=f, fill=255)
        glyphs.append((im, t, b))
    top = min(g[1] for g in glyphs)
    bot = max(g[2] for g in glyphs)
    k = box["h"] / (bot - top)                    # výška verzálek -> h
    scaled = []
    for im, t, b in glyphs:
        a = np.asarray(im) > 0
        xs = np.nonzero(a.any(0))[0]
        im = im.crop((xs.min(), 0, xs.max() + 1, im.size[1]))
        w = max(1, round(im.size[0] * k))
        h = max(1, round(im.size[1] * k))
        scaled.append((im.resize((w, h), Image.LANCZOS), round((t - top - 20) * k)))
    ink_w = sum(s[0].size[0] for s in scaled)
    gap = (box["w"] - ink_w) / (len(scaled) - 1)  # rovnoměrné mezery do celkové šířky
    out = Image.new("L", (shape[1], shape[0]), 0)
    x = box["x"]
    for im, dy in scaled:
        out.paste(im, (round(x), box["y"] + dy), im)
        x += im.size[0] + gap
    return np.asarray(out, np.float32) / 255


def trace(mask, k: float, eps: float = 1.0):
    import cv2
    import numpy as np
    m = cv2.GaussianBlur((mask * 255).astype(np.uint8), (0, 0), 1.2)
    cs, _ = cv2.findContours((m >= 128).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        if abs(cv2.contourArea(c)) < 4:
            continue
        c = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(c) >= 3:
            out.append([(x * k, y * k) for x, y in c])
    return out


def to_svg(h, cs, color: str) -> str:
    d = "".join("M" + "L".join(f"{f2(x)} {f2(y)}" for x, y in c) + "Z" for c in cs)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f2(W)} {f2(h)}" width="{f2(W)}" height="{f2(h)}">'
            f'<title>Patrik Novák</title><path fill="{color}" fill-rule="evenodd" d="{d}"/></svg>\n')


def main() -> None:
    ap = argparse.ArgumentParser(description="Watermark podle Watermark_06 s různými písmy nápisu.")
    ap.add_argument("--src", default=str(HERE / "podpis06"))
    ap.add_argument("--fonts", default=str(HERE / "fonty"))
    ap.add_argument("--out", default=str(HERE / "vystup"))
    ap.add_argument("--widths", type=int, nargs="+", default=[250, 500, 1000, 2000])
    ap.add_argument("--jen", nargs="*", help="jen vybrané varianty (copperplate, quattrocento, spectral, cinzel, …)")
    ap.add_argument("--pismo", nargs="*", default=[], help="další varianta: nazev=cesta_k_pismu.ttf")
    a = ap.parse_args()
    for mod, pkg in (("cv2", "opencv-python"), ("numpy", "numpy"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            fail(f"Chybí knihovna {pkg}:  pip install {pkg}")
    import numpy as np
    from PIL import Image
    src, fonts = Path(a.src), Path(a.fonts)
    for p in ("podpis-linka.png", "text-copperplate.png", "text-pozice.json"):
        if not (src / p).is_file():
            fail(f"Chybí zdrojový soubor {src / p}")
    base = np.asarray(Image.open(src / "podpis-linka.png").convert("L"), np.float32) / 255
    box = json.loads((src / "text-pozice.json").read_text(encoding="utf-8"))
    variants = {"copperplate": None, **{n: (fonts / f, w) for n, (f, w) in FONTS.items()}}
    for item in a.pismo:
        n, _, p = item.partition("=")
        if not n or not p:
            fail(f"--pismo čeká zápis nazev=cesta (teď {item!r})")
        variants[n] = (Path(p), None)
    if a.jen:
        unknown = set(a.jen) - set(variants)
        if unknown:
            fail(f"Neznámé varianty: {', '.join(sorted(unknown))}. Možnosti: {', '.join(variants)}")
        variants = {k: v for k, v in variants.items() if k in a.jen}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, spec in variants.items():
        if spec is None:
            text = np.asarray(Image.open(src / "text-copperplate.png").convert("L"), np.float32) / 255
        else:
            text = set_text(base.shape, box, *spec)
        alpha = np.maximum(base, text)
        ys, xs = np.nonzero(alpha > 0.04)
        alpha = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        hp, wp = alpha.shape
        k = W / wp
        cs = trace(alpha, k)
        am = Image.fromarray(np.clip(alpha * 255 + 0.5, 0, 255).astype(np.uint8))
        for cname, color in COLORS.items():
            b = f"watermark-06-{name}-{cname}"
            (out / f"{b}.svg").write_text(to_svg(hp * k, cs, color), encoding="utf-8")
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            for w in a.widths:
                m = am.resize((w, max(1, round(w * hp / wp))), Image.LANCZOS, reducing_gap=3.0)
                im = Image.new("RGBA", m.size, rgb + (0,))
                im.putalpha(m)
                im.save(out / f"{b}-{w}.png", optimize=True)
        print(f"  {name}: {f2(W)}×{f2(hp * k)}, PNG {', '.join(map(str, a.widths))} px")
    print(f"Hotovo: {out}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
