#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chroma Spirits - generative NFT collection generator.

Outputs:
  output/images/<id>.png        1024x1024 art
  output/metadata/<id>.json     OpenSea-compatible metadata
  output/rarity_report.csv      rarity score + rank per token
  output/gallery.html           local browser to review the collection
  output/combos.json            uniqueness registry (so you can extend safely)
"""

import argparse
import csv
import json
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

FINAL = 1024          # final image size
SS = 2                # supersampling factor (draw big, downscale -> antialiasing)
W = FINAL * SS

COLLECTION_NAME = "Chroma Spirits"
SYMBOL = "CHROMA"
ARTIST = "Chroma Labs"

# ---------------------------------------------------------------------------
# palettes: name, bg_top, bg_bottom, body, shade, face, ink, weight
# ---------------------------------------------------------------------------
PALETTES = [
    ("Sunset",    (255, 168, 120), (255, 86, 132),  (255, 205, 165), (235, 165, 130), (255, 238, 224), (70, 32, 44), 14),
    ("Ocean",     (110, 205, 255), (32, 74, 180),   (115, 215, 235), (75, 175, 205),  (222, 250, 255), (10, 34, 64), 14),
    ("Mint",      (190, 255, 215), (32, 175, 125),  (150, 240, 190), (105, 205, 155), (235, 255, 245), (12, 52, 40), 13),
    ("Grape",     (205, 155, 255), (88, 38, 158),   (175, 140, 250), (135, 100, 215), (240, 232, 255), (36, 16, 64), 12),
    ("Bubblegum", (255, 195, 232), (228, 58, 148),  (255, 160, 205), (230, 120, 175), (255, 235, 245), (74, 14, 48), 12),
    ("Sand",      (255, 228, 175), (188, 128, 58),  (235, 200, 150), (200, 160, 110), (255, 245, 225), (66, 42, 18), 11),
    ("Storm",     (165, 180, 205), (48, 58, 88),    (150, 165, 195), (110, 125, 155), (230, 238, 250), (18, 22, 38), 11),
    ("Lime",      (238, 255, 128), (108, 178, 38),  (205, 240, 95),  (165, 205, 60),  (245, 255, 220), (36, 54, 10), 10),
    ("Neon",      (255, 86, 224),  (38, 0, 88),     (95, 250, 240),  (45, 200, 205),  (225, 255, 255), (14, 8, 40), 8),
    ("Ice",       (238, 251, 255), (118, 168, 220), (240, 250, 255), (185, 215, 240), (255, 255, 255), (30, 48, 72), 5),
    ("Gold",      (255, 232, 145), (178, 118, 18),  (255, 205, 70),  (225, 165, 30),  (255, 245, 210), (74, 46, 4), 3),
    ("Void",      (64, 32, 115),   (9, 4, 22),      (72, 56, 115),   (46, 35, 80),    (155, 140, 205), (6, 3, 14), 2),
]

# ---------------------------------------------------------------------------
# traits: (name, weight) - weights are relative inside each category
# ---------------------------------------------------------------------------
PATTERNS = [("Plain", 26), ("Stripes", 18), ("Dots", 16), ("Rays", 14), ("Grid", 14), ("Bokeh", 12)]
EYES = [("Round", 18), ("Cute", 16), ("Sleepy", 13), ("Dot", 12), ("Angry", 10),
        ("Wink", 8), ("Star", 7), ("Heart", 6), ("X", 5), ("Laser", 5)]
MOUTHS = [("Smile", 18), ("Open", 14), ("Cat", 13), ("Tongue", 12), ("Flat", 11),
          ("Frown", 9), ("Grin", 9), ("Smirk", 7), ("Fang", 7)]
HEADWEAR = [("None", 30), ("Beanie", 13), ("Cap", 12), ("Headphones", 10), ("Bow", 9),
            ("Horns", 7), ("Halo", 6), ("Antenna", 6), ("Crown", 3), ("Top Hat", 4)]
EYEWEAR = [("None", 38), ("Round Glasses", 15), ("Sunglasses", 14), ("Visor", 10),
           ("Monocle", 8), ("3D Glasses", 8), ("Diamond Shades", 4), ("Heart Glasses", 3)]
COLLARS = [("None", 30), ("Scarf", 15), ("Chain", 14), ("Bow Tie", 12), ("Tie", 12),
           ("Medal", 7), ("Tag", 6)]
EARS = [("None", 55), ("Cat", 16), ("Bunny", 12), ("Bear", 10), ("Robot", 7)]
AURAS = [("None", 74), ("Spark", 18), ("Cosmic", 6), ("Divine", 2)]

TRAIT_ORDER = ["Palette", "Background", "Eyes", "Mouth", "Headwear", "Eyewear", "Collar", "Ears", "Aura"]
TRAIT_MAP = {
    "Palette": [(p[0], p[7]) for p in PALETTES],
    "Background": PATTERNS,
    "Eyes": EYES,
    "Mouth": MOUTHS,
    "Headwear": HEADWEAR,
    "Eyewear": EYEWEAR,
    "Collar": COLLARS,
    "Ears": EARS,
    "Aura": AURAS,
}

ACCENTS = [(255, 71, 117), (52, 150, 255), (255, 209, 55), (80, 230, 160),
           (255, 120, 220), (245, 245, 250), (35, 35, 50), (255, 140, 60)]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class ScaledDraw:
    """ImageDraw wrapper that lets us design in 1024-space while drawing at 2048."""

    def __init__(self, im, k=SS):
        self._d = ImageDraw.Draw(im)
        self._k = k

    def _xy(self, xy):
        return [c * self._k for c in xy]

    def _kw(self, kw):
        if "width" in kw:
            kw["width"] = max(1, int(round(kw["width"] * self._k)))
        return kw

    def rectangle(self, xy, **kw):
        return self._d.rectangle(self._xy(xy), **self._kw(kw))

    def rounded_rectangle(self, xy, radius=10, **kw):
        return self._d.rounded_rectangle(self._xy(xy), radius=radius * self._k, **self._kw(kw))

    def ellipse(self, xy, **kw):
        return self._d.ellipse(self._xy(xy), **self._kw(kw))

    def circle(self, center, r, **kw):
        cx, cy = center
        return self.ellipse([cx - r, cy - r, cx + r, cy + r], **kw)

    def polygon(self, points, **kw):
        return self._d.polygon([(x * self._k, y * self._k) for x, y in points], **self._kw(kw))

    def arc(self, xy, start, end, **kw):
        return self._d.arc(self._xy(xy), start, end, **self._kw(kw))

    def pieslice(self, xy, start, end, **kw):
        return self._d.pieslice(self._xy(xy), start, end, **self._kw(kw))

    def line(self, xy, **kw):
        return self._d.line([(x * self._k, y * self._k) for x, y in xy], **self._kw(kw))


def pick(weighted):
    names = [n for n, _ in weighted]
    weights = [w for _, w in weighted]
    return random.choices(names, weights=weights, k=1)[0]


def prob_of(trait, value):
    total = sum(w for _, w in TRAIT_MAP[trait])
    w = dict(TRAIT_MAP[trait])[value]
    return w / total


def tier_of(p):
    if p <= 0.03:
        return "Legendary"
    if p <= 0.10:
        return "Rare"
    if p <= 0.25:
        return "Uncommon"
    return "Common"


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def star_points(cx, cy, r_out, r_in, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def heart_points(cx, cy, s):
    return ([(cx - s * 0.55, cy - s * 0.25)], [(cx, cy + s * 0.6)])


def draw_heart(d, cx, cy, s, **kw):
    d.circle((cx - s * 0.34, cy - s * 0.22), s * 0.42, **kw)
    d.circle((cx + s * 0.34, cy - s * 0.22), s * 0.42, **kw)
    d.polygon([(cx - s * 0.72, cy - s * 0.02), (cx + s * 0.72, cy - s * 0.02), (cx, cy + s * 0.78)], **kw)


# ---------------------------------------------------------------------------
# background
# ---------------------------------------------------------------------------

def make_background(pal, pattern, rng):
    c_top, c_bottom = pal[1], pal[2]
    img = Image.new("RGBA", (W, W))
    strip = Image.new("RGBA", (1, W))
    sp = strip.load()
    for y in range(W):
        sp[0, y] = lerp(c_top, c_bottom, y / (W - 1)) + (255,)
    img = strip.resize((W, W), Image.BILINEAR)

    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ScaledDraw(layer)
    ink = pal[6]

    if pattern == "Stripes":
        step = 96
        for i in range(-14, 30):
            x0 = i * step
            d.line([(x0, 0), (x0 + W // SS, W // SS)], fill=ink + (26,), width=26)
    elif pattern == "Dots":
        step = 88
        for y in range(40, FINAL, step):
            for x in range(40, FINAL, step):
                d.circle((x, y), 9, fill=(255, 255, 255, 60))
    elif pattern == "Rays":
        cx, cy = FINAL // 2, -140
        for i in range(14):
            a0 = i * (360 / 14)
            a1 = a0 + (360 / 14) / 2
            pts = [(cx, cy)]
            for a in (a0, a1):
                rad = math.radians(a)
                pts.append((cx + 2600 * math.cos(rad), cy + 2600 * math.sin(rad)))
            d.polygon(pts, fill=(255, 255, 255, 34))
    elif pattern == "Grid":
        for i in range(0, FINAL + 1, 76):
            d.line([(i, 0), (i, FINAL)], fill=ink + (30,), width=3)
            d.line([(0, i), (FINAL, i)], fill=ink + (30,), width=3)
    elif pattern == "Bokeh":
        for _ in range(22):
            x = rng.randint(0, FINAL)
            y = rng.randint(0, FINAL)
            r = rng.randint(18, 74)
            col = (255, 255, 255) if rng.random() < 0.6 else lerp(c_top, c_bottom, rng.random())
            d.circle((x, y), r, fill=col + (34,), outline=(255, 255, 255, 46), width=3)

    return Image.alpha_composite(img, layer)


# ---------------------------------------------------------------------------
# character
# ---------------------------------------------------------------------------

BODY_TOP, BODY_BOTTOM, BODY_L, BODY_R = 430, 960, 300, 724
BODY_RADIUS = 200
FACE_BOX = [392, 485, 632, 690]
EYE_L, EYE_R = (458, 556), (566, 556)
MOUTH_C = (512, 645)
HEAD_TOP = 430

FOOT_L, FOOT_R = (447, 946), (577, 946)


def silhouette_shapes(ears):
    shapes = [
        ("ellipse", [FOOT_L[0] - 72, FOOT_L[1] - 34, FOOT_L[0] + 72, FOOT_L[1] + 34]),
        ("ellipse", [FOOT_R[0] - 72, FOOT_R[1] - 34, FOOT_R[0] + 72, FOOT_R[1] + 34]),
        ("rrect", [BODY_L, BODY_TOP, BODY_R, BODY_BOTTOM, BODY_RADIUS]),
    ]
    if ears == "Cat":
        shapes.append(("poly", [(402, 468), (447, 336), (516, 452)]))
        shapes.append(("poly", [(622, 468), (577, 336), (508, 452)]))
    elif ears == "Bunny":
        shapes.append(("ellipse", [412, 246, 476, 478]))
        shapes.append(("ellipse", [548, 246, 612, 478]))
    elif ears == "Bear":
        shapes.append(("ellipse", [372, 358, 486, 472]))
        shapes.append(("ellipse", [538, 358, 652, 472]))
    elif ears == "Robot":
        shapes.append(("rrect", [282, 534, 350, 618, 14]))
        shapes.append(("rrect", [674, 534, 742, 618, 14]))
    return shapes


def paint_shapes(d, shapes, **kw):
    for kind, args in shapes:
        if kind == "ellipse":
            d.ellipse(args, **kw)
        elif kind == "rrect":
            d.rounded_rectangle(args[:-1], radius=args[-1], **kw)
        elif kind == "poly":
            d.polygon(args, **kw)


def build_silhouette(pal, ears, erode=13):
    """Union of all body shapes -> dark outline edge + flat body fill."""
    mask = Image.new("L", (W, W), 0)
    dm = ScaledDraw(mask)
    paint_shapes(dm, silhouette_shapes(ears), fill=255)

    out = Image.new("RGBA", (W, W), pal[6] + (255,))
    inner = mask.filter(ImageFilter.MinFilter(erode))
    fill_layer = Image.new("RGBA", (W, W), pal[3] + (255,))
    out.paste(fill_layer, (0, 0), inner)
    return out, inner


def body_shading(inner, pal):
    """Soft dark gradient on the lower body for depth."""
    y0, y1, alpha = int(560 * SS), int(980 * SS), 70
    ramp = Image.new("L", (1, W), 0)
    rp = ramp.load()
    for y in range(W):
        if y <= y0:
            v = 0
        elif y >= y1:
            v = alpha
        else:
            v = int(alpha * (y - y0) / (y1 - y0))
        rp[0, y] = v
    ramp = ramp.resize((W, W), Image.NEAREST)
    layer = Image.new("RGBA", (W, W), pal[4] + (255,))
    layer.putalpha(ImageChops.multiply(ramp, inner))
    return layer


def draw_ears_inner(img, ears, pal, accent):
    if ears in ("None", "Robot"):
        return
    d = ScaledDraw(img)
    if ears == "Cat":
        d.polygon([(424, 448), (450, 372), (494, 442)], fill=accent + (255,))
        d.polygon([(600, 448), (574, 372), (530, 442)], fill=accent + (255,))
    elif ears == "Bunny":
        d.ellipse([424, 274, 464, 452], fill=accent + (255,))
        d.ellipse([560, 274, 600, 452], fill=accent + (255,))
    elif ears == "Bear":
        d.circle((429, 415), 27, fill=accent + (255,))
        d.circle((595, 415), 27, fill=accent + (255,))


def draw_face(d, pal, accent):
    d.ellipse(FACE_BOX, fill=pal[5] + (255,))
    # blush
    d.ellipse([404, 612, 452, 646], fill=accent + (130,))
    d.ellipse([572, 612, 620, 646], fill=accent + (130,))


def draw_eyes(layer, d, style, pal, accent):
    ink = pal[6]
    white = (255, 255, 255)
    for (ex, ey) in (EYE_L, EYE_R):
        if style == "Round":
            d.circle((ex, ey), 34, fill=white, outline=ink, width=5)
            d.circle((ex, ey), 16, fill=ink)
            d.circle((ex - 8, ey - 9), 6, fill=white)
        elif style == "Cute":
            d.ellipse([ex - 40, ey - 44, ex + 40, ey + 44], fill=white, outline=ink, width=5)
            d.ellipse([ex - 21, ey - 26, ex + 21, ey + 28], fill=ink)
            d.circle((ex - 9, ey - 13), 8, fill=white)
            d.circle((ex + 11, ey + 12), 4, fill=white)
        elif style == "Dot":
            d.circle((ex, ey), 15, fill=ink)
        elif style == "Sleepy":
            d.ellipse([ex - 34, ey - 30, ex + 34, ey + 30], fill=white, outline=ink, width=5)
            d.circle((ex, ey + 6), 15, fill=ink)
            d.line([(ex - 34, ey - 8), (ex + 34, ey - 8)], fill=ink, width=9)
        elif style == "Angry":
            d.ellipse([ex - 34, ey - 30, ex + 34, ey + 30], fill=white, outline=ink, width=5)
            d.circle((ex, ey + 4), 15, fill=ink)
            sgn = -1 if ex < 512 else 1
            d.line([(ex - 34 * sgn, ey - 40), (ex + 26 * sgn, ey - 16)], fill=ink, width=11)
        elif style == "Wink":
            if ex == EYE_L:
                d.circle((ex, ey), 30, fill=white, outline=ink, width=5)
                d.circle((ex, ey), 14, fill=ink)
                d.circle((ex - 7, ey - 8), 5, fill=white)
            else:
                d.arc([ex - 32, ey - 30, ex + 32, ey + 34], 200, 340, fill=ink, width=10)
        elif style == "Star":
            d.polygon(star_points(ex, ey, 36, 15), fill=accent, outline=ink)
            d.circle((ex, ey), 7, fill=white)
        elif style == "Heart":
            draw_heart(d, ex, ey + 2, 64, fill=(255, 82, 120), outline=ink)
        elif style == "X":
            d.line([(ex - 26, ey - 26), (ex + 26, ey + 26)], fill=ink, width=11)
            d.line([(ex - 26, ey + 26), (ex + 26, ey - 26)], fill=ink, width=11)
        elif style == "Laser":
            d.circle((ex, ey), 22, fill=(255, 40, 40), outline=ink, width=5)
            d.circle((ex, ey), 9, fill=(255, 210, 210))


def draw_mouth(d, style, pal, accent):
    ink = pal[6]
    mx, my = MOUTH_C
    if style == "Smile":
        d.arc([mx - 52, my - 34, mx + 52, my + 30], 20, 160, fill=ink, width=10)
    elif style == "Frown":
        d.arc([mx - 46, my - 20, mx + 46, my + 44], 200, 340, fill=ink, width=10)
    elif style == "Flat":
        d.line([(mx - 44, my), (mx + 44, my)], fill=ink, width=10)
    elif style == "Open":
        d.ellipse([mx - 34, my - 22, mx + 34, my + 34], fill=ink)
        d.ellipse([mx - 20, my + 4, mx + 20, my + 32], fill=(255, 96, 110))
    elif style == "Cat":
        d.arc([mx - 52, my - 26, mx - 4, my + 24], 20, 160, fill=ink, width=9)
        d.arc([mx + 4, my - 26, mx + 52, my + 24], 20, 160, fill=ink, width=9)
    elif style == "Tongue":
        d.arc([mx - 50, my - 34, mx + 50, my + 10], 20, 160, fill=ink, width=10)
        d.ellipse([mx - 20, my - 4, mx + 20, my + 38], fill=(255, 96, 110), outline=ink, width=5)
    elif style == "Grin":
        d.pieslice([mx - 52, my - 26, mx + 52, my + 36], 0, 180, fill=ink)
        d.rectangle([mx - 52, my - 26, mx + 52, my - 10], fill=(255, 255, 255))
        d.line([(mx - 18, my - 26), (mx - 18, my - 10)], fill=ink, width=4)
        d.line([(mx + 18, my - 26), (mx + 18, my - 10)], fill=ink, width=4)
    elif style == "Smirk":
        d.arc([mx - 44, my - 24, mx + 52, my + 30], 10, 130, fill=ink, width=10)
    elif style == "Fang":
        d.pieslice([mx - 40, my - 20, mx + 40, my + 34], 0, 180, fill=ink)
        d.polygon([(mx - 24, my + 4), (mx - 8, my + 4), (mx - 16, my + 26)], fill=(255, 255, 255))
        d.polygon([(mx + 8, my + 4), (mx + 24, my + 4), (mx + 16, my + 26)], fill=(255, 255, 255))


def draw_headwear(d, style, pal, accent):
    ink = pal[6]
    if style == "None":
        return
    if style == "Beanie":
        d.rounded_rectangle([365, 330, 659, 470], radius=56, fill=accent, outline=ink, width=7)
        d.rounded_rectangle([353, 436, 671, 494], radius=26, fill=lerp(accent, (255, 255, 255), 0.35), outline=ink, width=7)
        d.circle((512, 316), 30, fill=(255, 255, 255), outline=ink, width=7)
    elif style == "Cap":
        d.pieslice([368, 296, 656, 520], 180, 360, fill=accent, outline=ink, width=7)
        d.rounded_rectangle([500, 448, 726, 496], radius=22, fill=lerp(accent, (0, 0, 0), 0.25), outline=ink, width=7)
        d.circle((512, 314), 16, fill=ink)
    elif style == "Crown":
        d.polygon([(386, 452), (386, 384), (436, 430), (474, 330), (512, 418),
                   (550, 330), (588, 430), (638, 384), (638, 452)], fill=(255, 209, 55), outline=ink)
        d.rectangle([386, 428, 638, 458], fill=(255, 209, 55), outline=ink, width=6)
        for gx in (452, 512, 572):
            d.circle((gx, 444), 12, fill=accent, outline=ink, width=4)
    elif style == "Halo":
        d.ellipse([434, 336, 590, 384], outline=(255, 224, 120), width=13)
        d.ellipse([444, 344, 580, 376], outline=(255, 250, 220), width=5)
    elif style == "Horns":
        d.polygon([(386, 458), (438, 318), (494, 448)], fill=(240, 240, 248), outline=ink)
        d.polygon([(638, 458), (586, 318), (530, 448)], fill=(240, 240, 248), outline=ink)
    elif style == "Antenna":
        d.line([(512, 448), (512, 336)], fill=ink, width=10)
        d.circle((512, 316), 27, fill=accent, outline=ink, width=7)
    elif style == "Top Hat":
        d.rectangle([425, 300, 599, 452], fill=ink)
        d.rectangle([425, 400, 599, 444], fill=accent)
        d.rounded_rectangle([361, 434, 663, 478], radius=20, fill=ink)
    elif style == "Headphones":
        d.arc([349, 318, 675, 546], 195, 345, fill=ink, width=18)
        d.rounded_rectangle([292, 508, 372, 612], radius=26, fill=accent, outline=ink, width=7)
        d.rounded_rectangle([652, 508, 732, 612], radius=26, fill=accent, outline=ink, width=7)
    elif style == "Bow":
        d.polygon([(512, 412), (432, 362), (432, 466)], fill=accent, outline=ink)
        d.polygon([(512, 412), (592, 362), (592, 466)], fill=accent, outline=ink)
        d.circle((512, 412), 21, fill=lerp(accent, (0, 0, 0), 0.2), outline=ink, width=6)


def draw_collar(d, style, pal, accent):
    ink = pal[6]
    if style == "None":
        return
    if style == "Scarf":
        d.rounded_rectangle([336, 748, 688, 824], radius=38, fill=accent, outline=ink, width=7)
        d.rounded_rectangle([598, 796, 668, 902], radius=22, fill=accent, outline=ink, width=7)
        d.line([(600, 836), (666, 836)], fill=ink, width=5)
    elif style == "Chain":
        for i in range(9):
            x = 372 + i * 40
            y = 776 + int(26 * math.sin(math.pi * i / 8))
            d.circle((x, y), 15, outline=(255, 214, 90), width=7)
    elif style == "Bow Tie":
        d.polygon([(512, 786), (440, 744), (440, 830)], fill=accent, outline=ink)
        d.polygon([(512, 786), (584, 744), (584, 830)], fill=accent, outline=ink)
        d.circle((512, 786), 18, fill=lerp(accent, (0, 0, 0), 0.25), outline=ink, width=6)
    elif style == "Tie":
        d.rounded_rectangle([486, 748, 538, 796], radius=8, fill=accent, outline=ink, width=6)
        d.polygon([(486, 796), (538, 796), (560, 884), (512, 926), (464, 884)], fill=accent, outline=ink)
    elif style == "Medal":
        d.polygon([(470, 748), (554, 748), (534, 812), (490, 812)], fill=(230, 60, 80), outline=ink)
        d.circle((512, 848), 40, fill=(255, 209, 55), outline=ink, width=7)
        d.polygon(star_points(512, 848, 22, 9), fill=(255, 245, 200), outline=ink)
    elif style == "Tag":
        d.rounded_rectangle([366, 758, 658, 800], radius=21, fill=lerp(accent, (0, 0, 0), 0.15), outline=ink, width=6)
        d.circle((512, 846), 36, fill=(255, 214, 90), outline=ink, width=7)
        d.polygon(star_points(512, 846, 18, 8), fill=ink)


def draw_eyewear(layer, d, style, pal, accent):
    ink = pal[6]
    if style == "None":
        return
    if style == "Round Glasses":
        for (ex, ey) in (EYE_L, EYE_R):
            d.circle((ex, ey), 45, outline=ink, width=9)
        d.line([(EYE_L[0] + 45, EYE_L[1]), (EYE_R[0] - 45, EYE_R[1])], fill=ink, width=9)
        d.line([(EYE_L[0] - 45, EYE_L[1] - 6), (396, EYE_L[1] - 22)], fill=ink, width=9)
        d.line([(EYE_R[0] + 45, EYE_R[1] - 6), (628, EYE_R[1] - 22)], fill=ink, width=9)
    elif style == "Sunglasses":
        d.rounded_rectangle([EYE_L[0] - 52, EYE_L[1] - 32, EYE_L[0] + 48, EYE_L[1] + 32], radius=17, fill=ink)
        d.rounded_rectangle([EYE_R[0] - 48, EYE_R[1] - 32, EYE_R[0] + 52, EYE_R[1] + 32], radius=17, fill=ink)
        d.rectangle([EYE_L[0] + 44, EYE_L[1] - 8, EYE_R[0] - 44, EYE_R[1] + 8], fill=ink)
        d.line([(EYE_L[0] - 50, EYE_L[1] - 24), (EYE_L[0] - 24, EYE_L[1] - 4)], fill=(255, 255, 255, 160), width=6)
    elif style == "Visor":
        d.rounded_rectangle([396, 520, 628, 594], radius=26, fill=accent + (185,), outline=ink, width=8)
        d.line([(418, 542), (596, 542)], fill=(255, 255, 255, 150), width=8)
    elif style == "Monocle":
        d.circle((EYE_R[0], EYE_R[1]), 47, outline=(255, 214, 90), width=9)
        d.arc([EYE_R[0] - 6, EYE_R[1] + 40, EYE_R[0] + 70, EYE_R[1] + 130], 90, 200, fill=(255, 214, 90), width=7)
    elif style == "3D Glasses":
        d.rounded_rectangle([EYE_L[0] - 54, EYE_L[1] - 34, EYE_L[0] + 46, EYE_L[1] + 34], radius=14,
                            fill=(230, 46, 46, 190), outline=ink, width=8)
        d.rounded_rectangle([EYE_R[0] - 46, EYE_R[1] - 34, EYE_R[0] + 54, EYE_R[1] + 34], radius=14,
                            fill=(46, 110, 230, 190), outline=ink, width=8)
        d.line([(EYE_L[0] + 46, EYE_L[1]), (EYE_R[0] - 46, EYE_R[1])], fill=ink, width=10)
    elif style == "Diamond Shades":
        for (ex, ey) in (EYE_L, EYE_R):
            x0 = ex - 54
            for i, col in enumerate([(90, 240, 255), (150, 120, 255), (255, 120, 220), (255, 220, 110)]):
                d.rectangle([x0 + i * 27, ey - 30, x0 + (i + 1) * 27, ey + 30], fill=col + (215,))
        d.rectangle([EYE_L[0] + 54, EYE_L[1] - 8, EYE_R[0] - 54, EYE_R[1] + 8], fill=ink)
    elif style == "Heart Glasses":
        draw_heart(d, EYE_L[0], EYE_L[1], 76, fill=(255, 70, 120, 225), outline=ink)
        draw_heart(d, EYE_R[0], EYE_R[1], 76, fill=(255, 70, 120, 225), outline=ink)
        d.line([(EYE_L[0] + 44, EYE_L[1] - 6), (EYE_R[0] - 44, EYE_R[1] - 6)], fill=ink, width=9)


def draw_aura(layer, d, glow_layer, style, pal, accent, rng):
    if style == "None":
        return
    if style == "Spark":
        for _ in range(14):
            x = rng.randint(90, FINAL - 90)
            y = rng.randint(90, FINAL - 90)
            if BODY_L - 40 < x < BODY_R + 40 and BODY_TOP - 60 < y < BODY_BOTTOM:
                continue
            r = rng.randint(8, 18)
            d.polygon(star_points(x, y, r, r // 3, n=4), fill=(255, 244, 190))
    elif style == "Cosmic":
        gd = ScaledDraw(glow_layer)
        for col, rad in [((170, 90, 255), 300), ((255, 90, 200), 240)]:
            gd.ellipse([512 - rad, 640 - rad + 40, 512 + rad, 640 + rad + 40], fill=col + (110,))
        for _ in range(18):
            x = rng.randint(60, FINAL - 60)
            y = rng.randint(60, FINAL - 60)
            r = rng.randint(6, 16)
            d.polygon(star_points(x, y, r, r // 3, n=4), fill=(255, 255, 255))
    elif style == "Divine":
        gd = ScaledDraw(glow_layer)
        gd.ellipse([512 - 330, 640 - 330 + 40, 512 + 330, 640 + 330 + 40], fill=(255, 216, 90, 120))
        gd.ellipse([512 - 240, 640 - 240 + 40, 512 + 240, 640 + 240 + 40], fill=(255, 245, 200, 110))
        cx, cy = 512, 300
        for i in range(12):
            a = math.radians(i * 30)
            gd.line([(cx, cy), (cx + 900 * math.cos(a), cy + 900 * math.sin(a))],
                    fill=(255, 232, 150, 70), width=7)
        for _ in range(22):
            x = rng.randint(50, FINAL - 50)
            y = rng.randint(50, FINAL - 50)
            r = rng.randint(8, 18)
            d.polygon(star_points(x, y, r, r // 3, n=4), fill=(255, 250, 220))


# ---------------------------------------------------------------------------
# render one token
# ---------------------------------------------------------------------------

def render(traits, rng):
    pal = next(p for p in PALETTES if p[0] == traits["Palette"])
    accent = rng.choice(ACCENTS)

    img = make_background(pal, traits["Background"], rng)

    # ground shadow
    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sd = ScaledDraw(shadow)
    sd.ellipse([340, 930, 684, 1012], fill=(0, 0, 0, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14 * SS))
    img = Image.alpha_composite(img, shadow)

    # aura glow behind the body
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    body, inner = build_silhouette(pal, traits["Ears"])
    aura_top = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    aura_bottom = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    draw_aura(ScaledDraw(aura_top), ScaledDraw(aura_top), glow, traits["Aura"], pal, accent, rng)
    if traits["Aura"] in ("Cosmic", "Divine"):
        glow = glow.filter(ImageFilter.GaussianBlur(55 * SS))
        img = Image.alpha_composite(img, glow)

    img = Image.alpha_composite(img, body)
    img = Image.alpha_composite(img, body_shading(inner, pal))

    d = ScaledDraw(img)
    draw_ears_inner(img, traits["Ears"], pal, accent)
    draw_face(d, pal, accent)
    draw_eyes(aura_top, d, traits["Eyes"], pal, accent)
    draw_mouth(d, traits["Mouth"], pal, accent)
    draw_collar(d, traits["Collar"], pal, accent)
    draw_headwear(d, traits["Headwear"], pal, accent)

    eyewear = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    draw_eyewear(eyewear, ScaledDraw(eyewear), traits["Eyewear"], pal, accent)
    img = Image.alpha_composite(img, eyewear)
    img = Image.alpha_composite(img, aura_top)

    return img.resize((FINAL, FINAL), Image.LANCZOS)


# ---------------------------------------------------------------------------
# metadata / rarity
# ---------------------------------------------------------------------------

def lore_for(traits, rarest_trait, rarest_value, rarest_p):
    palettes_short = {
        "Gold": "forged from sunlight", "Void": "born at the edge of the void",
        "Ice": "carved from glacial light", "Neon": "charged with neon static",
    }
    origin = palettes_short.get(traits["Palette"], "drawn from the chroma spectrum")
    return (f"A {traits['Palette']} Chroma Spirit, {origin}. "
            f"Its rarest trait is {rarest_value} ({rarest_trait}), found in only "
            f"{rarest_p * 100:.1f}% of the collection.")


def build_metadata(token_id, traits, score, rank, total, cid_placeholder):
    p_min = 1.0
    t_min, v_min = "", ""
    for t in TRAIT_ORDER:
        p = prob_of(t, traits[t])
        if p < p_min:
            p_min, t_min, v_min = p, t, traits[t]
    tier = tier_of(p_min)
    desc = (f"{COLLECTION_NAME} #{token_id} — a one-of-one generative spirit. "
            + lore_for(traits, t_min, v_min, p_min) +
            f" Rarity rank {rank}/{total} ({tier}).")
    attrs = []
    for t in TRAIT_ORDER:
        p = prob_of(t, traits[t])
        attrs.append({"trait_type": t, "value": traits[t],
                      "tier": tier_of(p), "probability": round(p, 5)})
    return {
        "name": f"{COLLECTION_NAME} #{token_id}",
        "description": desc,
        "image": f"{cid_placeholder}/{token_id}.png",
        "external_url": "https://example.com/chroma-spirits",  # TODO: your site/social
        "attributes": attrs,
        "compiler": "Chroma Labs generator v1",
        "rarity_score": round(score, 3),
        "rarity_rank": rank,
    }


# ---------------------------------------------------------------------------
# gallery
# ---------------------------------------------------------------------------

def write_gallery(out_dir, rows):
    cards = []
    for r in rows:
        tier_class = r["tier"].lower()
        cards.append(
            f'<div class="card {tier_class}"><img src="images/{r["id"]}.png" loading="lazy">'
            f'<div class="meta"><b>#{r["id"]}</b> <span class="badge {tier_class}">{r["tier"]}</span>'
            f'<div class="sub">rank {r["rank"]} · score {r["score"]}</div>'
            f'<div class="traits">{r["traits_html"]}</div></div></div>')
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>{COLLECTION_NAME}</title><style>
body{{background:#12121a;color:#eee;font-family:Segoe UI,Arial;margin:20px}}
h1{{font-size:26px}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px}}
.card{{background:#1c1c26;border-radius:14px;overflow:hidden;border:2px solid #2a2a38}}
.card img{{width:100%;display:block}}
.legendary{{border-color:#ffd137}} .rare{{border-color:#57d6ff}} .uncommon{{border-color:#a67cff}}
.meta{{padding:10px 12px;font-size:14px}}
.badge{{padding:2px 8px;border-radius:20px;font-size:11px;background:#333}}
.badge.legendary{{background:#ffd137;color:#201600}} .badge.rare{{background:#57d6ff;color:#00202a}}
.badge.uncommon{{background:#a67cff;color:#170a33}}
.sub{{color:#999;font-size:12px;margin-top:4px}}
.traits{{color:#aaa;font-size:11px;margin-top:6px;line-height:1.5}}
</style></head><body><h1>{COLLECTION_NAME} — {len(rows)} spirits</h1>
<div class="grid">{''.join(cards)}</div></body></html>"""
    with open(os.path.join(out_dir, "gallery.html"), "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--start", type=int, default=0, help="first token id")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"))
    ap.add_argument("--cid", default="ipfs://REPLACE_WITH_CID",
                    help="ipfs://... prefix used in metadata image field")
    args = ap.parse_args()

    img_dir = os.path.join(args.out, "images")
    meta_dir = os.path.join(args.out, "metadata")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    combos_path = os.path.join(args.out, "combos.json")
    used = set()
    if os.path.exists(combos_path):
        with open(combos_path, encoding="utf-8") as f:
            used.update(tuple(c) for c in json.load(f))

    rng = random.Random(args.seed)
    new_combos = []
    rows = []

    # rarity score for every token will be computed after we know all traits
    generated = []
    for i in range(args.count):
        token_id = args.start + i
        while True:
            traits = {t: pick(TRAIT_MAP[t]) for t in TRAIT_ORDER}
            key = tuple(traits[t] for t in TRAIT_ORDER)
            if key not in used and key not in [tuple(g[1][t] for t in TRAIT_ORDER) for g in generated]:
                break
        used.add(key)
        new_combos.append(list(key))
        generated.append((token_id, traits))
        img = render(traits, rng)
        img.save(os.path.join(img_dir, f"{token_id}.png"))
        print(f"  rendered {token_id}  " + ", ".join(f"{t}={traits[t]}" for t in TRAIT_ORDER))

    # scores + ranks
    scored = []
    for token_id, traits in generated:
        score = sum(1.0 / prob_of(t, traits[t]) for t in TRAIT_ORDER)
        scored.append((token_id, traits, score))
    scored.sort(key=lambda x: -x[2])
    total = len(scored)
    for rank, (token_id, traits, score) in enumerate(scored, start=1):
        p_min = min(prob_of(t, traits[t]) for t in TRAIT_ORDER)
        meta = build_metadata(token_id, traits, score, rank, total, args.cid)
        with open(os.path.join(meta_dir, f"{token_id}.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        rows.append({
            "id": token_id, "rank": rank, "score": round(score, 2),
            "tier": tier_of(p_min),
            "traits_html": "<br>".join(f"{t}: {traits[t]}" for t in TRAIT_ORDER),
            "traits": traits,
        })

    rows.sort(key=lambda r: r["id"])
    with open(os.path.join(args.out, "rarity_report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token_id", "rarity_rank", "rarity_score", "tier"] + TRAIT_ORDER)
        for r in rows:
            w.writerow([r["id"], r["rank"], r["score"], r["tier"]] + [r["traits"][t] for t in TRAIT_ORDER])

    with open(combos_path, "w", encoding="utf-8") as f:
        json.dump([list(c) for c in used], f)

    write_gallery(args.out, rows)
    print(f"\nDone: {total} spirits -> {args.out}")
    print("Open gallery.html to review the collection.")


if __name__ == "__main__":
    main()
