#!/usr/bin/env python3
"""NaverMap 앱 아이콘(1024px PNG) 생성. 사용법: python3 make_icon.py <출력경로.png>"""
import sys
from PIL import Image, ImageDraw

SS = 4096   # 슈퍼샘플
OUT = 1024  # 최종 크기


def vgradient(size, top, bottom):
    img = Image.new("RGB", (1, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return img.resize((size, size))


def draw():
    base = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    grad = vgradient(SS, (0x18, 0xD1, 0x73), (0x02, 0xA8, 0x50)).convert("RGBA")  # 네이버 그린
    mask = Image.new("L", (SS, SS), 0)
    m = int(SS * 0.085)
    r = int((SS - 2 * m) * 0.2235)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, SS - m, SS - m], radius=r, fill=255)
    base.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(base)
    cx, head_y, R, tip_y = SS // 2, int(SS * 0.40), int(SS * 0.20), int(SS * 0.74)
    white = (255, 255, 255, 255)
    d.ellipse([cx - R, head_y - R, cx + R, head_y + R], fill=white)
    d.polygon([(cx - int(R * 0.86), head_y + int(R * 0.5)),
               (cx + int(R * 0.86), head_y + int(R * 0.5)),
               (cx, tip_y)], fill=white)
    return base


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "navermap_1024.png"
    draw().resize((OUT, OUT), Image.LANCZOS).save(out)
    print(out)
