#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Génère l'icône de l'application Clairvue (assets/clairvue.ico + .png).

Best-effort : en cas d'erreur, on ne plante pas le build (pas d'icône, c'est tout).
Lancé par build_exe.bat et par la CI avant PyInstaller.
"""
import os
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def _make(size: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Fond : carré arrondi, léger dégradé vertical bleu.
    radius = int(size * 0.22)
    top = (58, 130, 247)
    bot = (37, 99, 235)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / max(1, size - 1)
        c = (
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t),
            255,
        )
        gd.line([(0, y), (size, y)], fill=c)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(bg, (0, 0), mask)

    # Loupe (symbole « voir clair »).
    cx, cy = size * 0.43, size * 0.42
    rad = size * 0.24
    lw = max(2, int(size * 0.07))
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 255, 255), width=lw)
    # Reflet.
    d.ellipse(
        [cx - rad * 0.55, cy - rad * 0.55, cx - rad * 0.05, cy - rad * 0.05],
        fill=(255, 255, 255, 150),
    )
    # Manche.
    hx, hy = cx + rad * 0.72, cy + rad * 0.72
    d.line([hx, hy, size * 0.82, size * 0.82], fill=(255, 255, 255, 255), width=int(lw * 1.3))

    # Étincelle (IA).
    sx, sy, s = size * 0.72, size * 0.26, size * 0.06
    d.line([sx - s, sy, sx + s, sy], fill=(255, 255, 255, 230), width=max(2, int(size * 0.025)))
    d.line([sx, sy - s, sx, sy + s], fill=(255, 255, 255, 230), width=max(2, int(size * 0.025)))
    return img


def main():
    try:
        sizes = [16, 32, 48, 64, 128, 256]
        imgs = [_make(s) for s in sizes]
        ico_path = os.path.join(OUT_DIR, "clairvue.ico")
        png_path = os.path.join(OUT_DIR, "clairvue.png")
        imgs[-1].save(ico_path, format="ICO", sizes=[(s, s) for s in sizes])
        imgs[-1].save(png_path, format="PNG")
        print("Icône générée :", ico_path)
    except Exception as exc:  # pragma: no cover
        print("Icône non générée (ignoré) :", exc, file=sys.stderr)


if __name__ == "__main__":
    main()
