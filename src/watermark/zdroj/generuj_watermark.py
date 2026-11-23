#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generátor watermarku „Monogram“ (návrh 3): PN v rozích hledáčku + PATRIK NOVÁK.

Vytvoří do složky vystup/:
    watermark-monogram-{bila,cerna}.svg            plná verze (se jménem)
    watermark-monogram-{bila,cerna}-<šířka>.png    PNG s průhledností
    watermark-znacka-{bila,cerna}.svg / .png       jen hledáček s PN (pro malé velikosti)

Potřebuje:  pip install pillow fonttools
Písma:      fonty/Lora-Variable.ttf a fonty/Inter-Medium.otf (licence OFL, přiloženy)

    python generuj_watermark.py
    python generuj_watermark.py --out D:\\Web\\patrik-novak-foto\\src\\watermark --widths 250 500 1000 2000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── vzhled (jednotky viewBoxu, šířka 300) ───────────────────────────────────
W = 300.0
FRAME_X0, FRAME_X1 = 50.0, 250.0      # svislé hrany hledáčku
FRAME_Y0, FRAME_Y1 = 12.0, 212.0      # vodorovné hrany hledáčku
ARM = 30.0                            # délka ramene rohu
STROKE = 3.0                          # tloušťka rohů (původně 2.6, zesíleno kvůli malým velikostem)
PN_SIZE = 112.0                       # velikost písma PN (Lora Regular)
PN_TRACK = -0.01
NAME_SIZE = 17.5                      # velikost jména (Inter Medium)
NAME_TRACK = 0.34
NAME_BASE = 252.0                     # účaří jména
H_FULL, H_MARK = 264.0, 224.0         # výška plné verze / značky

COLORS = {"bila": "#ffffff", "cerna": "#111111"}


def fail(msg: str) -> None:
    print("CHYBA: " + msg)
    sys.exit(1)


class Face:
    """Obrysy textu z písma jako seznam kontur (polygonů) s kerningem."""

    def __init__(self, path: Path):
        from fontTools.ttLib import TTFont
        if not path.exists():
            fail(f"Chybí písmo {path}")
        self.f = TTFont(str(path))
        if "fvar" in self.f:
            from fontTools.varLib import instancer
            self.f = instancer.instantiateVariableFont(self.f, {"wght": 400})
        self.gs, self.cmap = self.f.getGlyphSet(), self.f.getBestCmap()
        self.upm = self.f["head"].unitsPerEm
        self.cap = getattr(self.f["OS/2"], "sCapHeight", 0) or 700
        self.pairs, self.classes = self._kern()

    def _kern(self):
        pairs, classes = {}, []
        if "GPOS" not in self.f:
            return pairs, classes
        g = self.f["GPOS"].table
        idx = set()
        for fr in g.FeatureList.FeatureRecord:
            if fr.FeatureTag == "kern":
                idx.update(fr.Feature.LookupListIndex)
        for i in sorted(idx):
            for st in g.LookupList.Lookup[i].SubTable:
                if st.LookupType == 9:
                    st = st.ExtSubTable
                if st.LookupType != 2:
                    continue
                cov = st.Coverage.glyphs
                if st.Format == 1:
                    for g1, ps in zip(cov, st.PairSet):
                        for r in ps.PairValueRecord:
                            v = getattr(r.Value1, "XAdvance", 0) if r.Value1 else 0
                            if v:
                                pairs.setdefault((g1, r.SecondGlyph), v)
                else:
                    classes.append((set(cov), st.ClassDef1.classDefs, st.ClassDef2.classDefs, st.Class1Record))
        return pairs, classes

    def kern(self, a: str, b: str) -> float:
        if (a, b) in self.pairs:
            return self.pairs[(a, b)]
        for cov, c1, c2, recs in self.classes:
            if a in cov:
                r = recs[c1.get(a, 0)].Class2Record[c2.get(b, 0)]
                return (getattr(r.Value1, "XAdvance", 0) if r.Value1 else 0) or 0
        return 0

    def contours(self, text: str, size: float, cx: float, baseline: float, tracking: float = 0.0):
        """Kontury textu vystředěného podle skutečného ohraničení (ne podle posuvů)."""
        from fontTools.pens.recordingPen import RecordingPen
        s = size / self.upm
        x, prev, raw = 0.0, None, []
        for ch in text:
            g = self.cmap.get(ord(ch))
            if g is None:
                fail(f"Písmo neobsahuje znak {ch!r}")
            if prev:
                x += self.kern(prev, g) * s
            pen = RecordingPen()
            self.gs[g].draw(pen)
            for c in flatten(pen.value):
                raw.append([(x + px * s, -py * s) for px, py in c])
            x += self.gs[g].width * s + tracking * size
            prev = g
        xs = [p[0] for c in raw for p in c]
        dx = cx - (min(xs) + max(xs)) / 2
        return [[(px + dx, baseline + py) for px, py in c] for c in raw]


def flatten(ops, steps: int = 12):
    """RecordingPen → seznam uzavřených polygonů (křivky rozdělené na úsečky)."""
    out, cur, start, last = [], [], None, None

    def quad(p0, p1, p2):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
                for t in (i / steps for i in range(1, steps + 1))]

    def cubic(p0, p1, p2, p3):
        return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
                      for a, b, c, d in zip(p0, p1, p2, p3))
                for t in (i / steps for i in range(1, steps + 1))]

    for op, args in ops:
        if op == "moveTo":
            cur, start, last = [args[0]], args[0], args[0]
        elif op == "lineTo":
            cur.append(args[0]); last = args[0]
        elif op == "qCurveTo":
            pts = list(args)
            if pts[-1] is None:  # kontura jen z off-curve bodů
                pts = pts[:-1]
                pts.append(((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2))
                cur, last = [pts[-1]], pts[-1]
            for i in range(len(pts) - 1):
                c = pts[i]
                e = pts[i + 1] if i == len(pts) - 2 else ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
                cur += quad(last, c, e); last = e
        elif op == "curveTo":
            p1, p2, p3 = args
            cur += cubic(last, p1, p2, p3); last = p3
        elif op in ("closePath", "endPath"):
            if len(cur) > 2:
                out.append(cur)
            cur = []
    return out


def corners() -> list[list[tuple[float, float]]]:
    """Čtyři rohy hledáčku jako vyplněné tvary L (čtvercové zakončení, ostrý roh)."""
    h = STROKE / 2
    shapes = []
    for x, y, dx, dy in ((FRAME_X0, FRAME_Y0, 1, 1), (FRAME_X1, FRAME_Y0, -1, 1),
                         (FRAME_X0, FRAME_Y1, 1, -1), (FRAME_X1, FRAME_Y1, -1, -1)):
        ox, oy = x - dx * h, y - dy * h          # vnější roh
        ix, iy = x + dx * h, y + dy * h          # vnitřní roh
        ex, ey = x + dx * (ARM + h), y + dy * (ARM + h)
        shapes.append([(ox, oy), (ex, oy), (ex, iy), (ix, iy), (ix, ey), (ox, ey)])
    return shapes


def build(fonts: Path):
    lora = Face(fonts / "Lora-Variable.ttf")
    inter = Face(fonts / "Inter-Medium.otf")
    cy = (FRAME_Y0 + FRAME_Y1) / 2
    pn = lora.contours("PN", PN_SIZE, W / 2, cy + lora.cap / lora.upm * PN_SIZE / 2, PN_TRACK)
    name = inter.contours("PATRIK NOVÁK", NAME_SIZE, W / 2, NAME_BASE, NAME_TRACK)
    # každá skupina = jedna cesta s pravidlem even-odd (díry v písmenech)
    mark = [[c] for c in corners()] + [pn]
    return {"monogram": (H_FULL, mark + [name]), "znacka": (H_MARK, mark)}


def f2(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def to_svg(h: float, groups, color: str) -> str:
    paths = "".join(
        '<path fill-rule="evenodd" d="' + "".join(
            "M" + "L".join(f"{f2(x)} {f2(y)}" for x, y in c) + "Z" for c in g) + '"/>'
        for g in groups)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f2(W)} {f2(h)}" width="{f2(W)}" height="{f2(h)}">'
            f'<title>Patrik Novák</title><g fill="{color}">{paths}</g></svg>\n')


def to_mask(h: float, groups, width: int, ss: int = 4):
    """Rastrování s vyhlazením: každá skupina even-odd (XOR kontur), skupiny se sčítají."""
    from PIL import Image, ImageChops, ImageDraw
    k = width / W * ss
    size = (width * ss, round(h * width / W) * ss)
    total = Image.new("L", size, 0)
    for g in groups:
        acc = Image.new("1", size, 0)
        for c in g:
            m = Image.new("1", size, 0)
            ImageDraw.Draw(m).polygon([(x * k, y * k) for x, y in c], fill=1)
            acc = ImageChops.logical_xor(acc, m)
        total = ImageChops.lighter(total, acc.convert("L"))
    return total.resize((size[0] // ss, size[1] // ss), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Vygeneruje finální soubory watermarku Monogram.")
    ap.add_argument("--out", default=str(HERE / "vystup"), help="cílová složka")
    ap.add_argument("--fonts", default=str(HERE / "fonty"), help="složka s Lora-Variable.ttf a Inter-Medium.otf")
    ap.add_argument("--widths", type=int, nargs="+", default=[250, 500, 1000, 2000], help="šířky PNG v px")
    a = ap.parse_args()
    try:
        from PIL import Image
    except ImportError:
        fail("Chybí Pillow:  pip install pillow")
    try:
        import fontTools  # noqa: F401
    except ImportError:
        fail("Chybí fontTools:  pip install fonttools")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for variant, (h, groups) in build(Path(a.fonts)).items():
        masks = {w: to_mask(h, groups, w) for w in a.widths}
        for cname, color in COLORS.items():
            base = f"watermark-{variant}-{cname}"
            (out / f"{base}.svg").write_text(to_svg(h, groups, color), encoding="utf-8")
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            for w, m in masks.items():
                im = Image.new("RGBA", m.size, rgb + (0,))
                im.putalpha(m)
                im.save(out / f"{base}-{w}.png", optimize=True)
        print(f"  {variant}: SVG + PNG {', '.join(map(str, a.widths))} px (bílá, černá)")
    print(f"Hotovo: {out}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
