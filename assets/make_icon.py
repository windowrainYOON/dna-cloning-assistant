#!/usr/bin/env python3
"""Draw the app icon and pack it into assets/AppIcon.icns.

    python3 assets/make_icon.py        # needs Pillow; only for regenerating

The generated AppIcon.icns and the .iconset PNGs are committed, so a build
machine does not need Pillow — build/build_macos.sh just uses the .icns.

The artwork is a macOS-style rounded square holding a plasmid: a dark ring
with coloured feature arcs, directional arrowheads and a small double helix
through the middle, echoing the map the app draws.
"""

from __future__ import annotations

import math
import os
import struct
import sys

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # pragma: no cover - regeneration helper only
    sys.exit("Pillow is required to regenerate the icon: pip install pillow")

HERE = os.path.dirname(os.path.abspath(__file__))
SS = 4                      # supersampling factor
BASE = 1024

BG_TOP = (23, 32, 58)
BG_BOTTOM = (12, 16, 30)
RING = (46, 58, 90)
HELIX = (120, 142, 190)
ARCS = [                    # (start, end) in degrees, colour
    ((-72, 18), (91, 157, 255)),      # blue  — promoter / tag region
    ((34, 104), (59, 201, 160)),      # green — insert
    ((120, 168), (240, 180, 41)),     # amber — resistance marker
    ((184, 236), (214, 110, 196)),    # pink  — origin
]


def rounded_mask(size: int, radius_ratio: float = 0.2237) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return mask


def vertical_gradient(size: int, top: tuple[int, int, int],
                      bottom: tuple[int, int, int]) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        grad.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return grad.resize((size, size), Image.BILINEAR)


def arrow_head(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float,
               angle_deg: float, width: float, color: tuple[int, int, int]) -> None:
    """A triangle sitting on the ring, pointing clockwise."""
    a = math.radians(angle_deg)
    tip = (cx + radius * math.cos(a), cy + radius * math.sin(a))
    back = math.radians(angle_deg - 7)
    inner = radius - width * 0.95
    outer = radius + width * 0.95
    draw.polygon([tip,
                  (cx + inner * math.cos(back), cy + inner * math.sin(back)),
                  (cx + outer * math.cos(back), cy + outer * math.sin(back))],
                 fill=color)


def draw_icon(size: int = BASE * SS) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base = vertical_gradient(size, BG_TOP, BG_BOTTOM).convert("RGBA")
    img.paste(base, (0, 0), rounded_mask(size))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [size * 0.08, -size * 0.35, size * 0.92, size * 0.55], fill=(80, 120, 220, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.07)))

    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = size * 0.305
    w = size * 0.052

    d.ellipse([cx - r - w / 2, cy - r - w / 2, cx + r + w / 2, cy + r + w / 2],
              outline=RING, width=int(w))

    for (a0, a1), color in ARCS:
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=color, width=int(w))
        arrow_head(d, cx, cy, r, a1 + 3, w, color)

    # double helix across the middle of the plasmid
    amp = size * 0.072
    span = size * 0.30
    steps = 240
    strand_w = int(size * 0.019)
    pts_a, pts_b = [], []
    for i in range(steps + 1):
        t = i / steps
        x = cx - span + 2 * span * t
        phase = t * 3.1 * math.pi
        pts_a.append((x, cy + amp * math.sin(phase)))
        pts_b.append((x, cy - amp * math.sin(phase)))
    for i in range(0, steps, 12):
        xa, ya = pts_a[i]
        xb, yb = pts_b[i]
        if abs(ya - yb) > amp * 0.35:
            d.line([(xa, ya), (xb, yb)], fill=(90, 110, 155), width=int(size * 0.012))
    d.line(pts_a, fill=HELIX, width=strand_w, joint="curve")
    d.line(pts_b, fill=(94, 214, 182), width=strand_w, joint="curve")

    # top highlight, the usual macOS sheen
    sheen = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sheen).ellipse(
        [-size * 0.2, -size * 0.75, size * 1.2, size * 0.42], fill=(255, 255, 255, 26))
    img.alpha_composite(Image.composite(sheen, Image.new("RGBA", (size, size), (0, 0, 0, 0)),
                                        rounded_mask(size)))
    return img


ICNS_TYPES = [
    (b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64),
    (b"ic07", 128), (b"ic13", 256), (b"ic08", 256), (b"ic14", 512),
    (b"ic09", 512), (b"ic10", 1024),
]
ICONSET = [  # (filename, pixel size) — the Apple .iconset layout
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def main() -> None:
    master = draw_icon()
    out_dir = os.path.join(HERE, "AppIcon.iconset")
    os.makedirs(out_dir, exist_ok=True)
    rendered: dict[int, bytes] = {}
    for name, px in ICONSET:
        img = master.resize((px, px), Image.LANCZOS)
        path = os.path.join(out_dir, name)
        img.save(path, "PNG")
        if px not in rendered:
            with open(path, "rb") as fh:
                rendered[px] = fh.read()
    master.resize((1024, 1024), Image.LANCZOS).save(os.path.join(HERE, "icon-1024.png"), "PNG")

    chunks = b"".join(
        t + struct.pack(">I", len(rendered[px]) + 8) + rendered[px] for t, px in ICNS_TYPES)
    icns = b"icns" + struct.pack(">I", len(chunks) + 8) + chunks
    with open(os.path.join(HERE, "AppIcon.icns"), "wb") as fh:
        fh.write(icns)
    print(f"wrote {out_dir}, icon-1024.png and AppIcon.icns ({len(icns):,} bytes)")


if __name__ == "__main__":
    main()
