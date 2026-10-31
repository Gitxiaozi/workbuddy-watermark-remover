"""rebuild_mask.py —— 重建水印 alpha 蒙版

平台若更换水印样式（字号、位置、新增图标），旧蒙版会失效。此时用两张
"纯色/极简背景"的测试图重新生成 assets/wm_alpha_ref.png。

用法：
  python rebuild_mask.py 灰底图1.png 灰底图2.png

两张图建议用同一提示词生成，例如：
  "Flat neutral gray studio gradient background only, completely empty,
   minimal, no subject, no text."
"""
import os
import struct
import sys
import zlib

from analyze_wm import analyse
from crop_png import read_png, unfilter, write_png

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, os.pardir, 'assets', 'wm_alpha_ref.png'))
MW, MH = 144, 84          # 右下角取样窗尺寸（固定像素，已实测与图片尺寸无关）


def alpha_of(path):
    ihdr, idat = read_png(path)
    w, h = struct.unpack('>II', ihdr[:8])
    if w < MW or h < MH:
        raise SystemExit('图片太小：%s (%dx%d)' % (path, w, h))
    a, _, _, _, _ = analyse(path, w - MW, h - MH, w, h, os.path.splitext(path)[0] + '_mask')
    return a


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    alphas = [alpha_of(p) for p in sys.argv[1:]]
    n = len(alphas[0])
    avg = [sum(a[i] for a in alphas) / len(alphas) for i in range(n)]
    buf = bytes(min(255, round(v * 255)) for v in avg)
    write_png(OUT, MW, MH, 1, 0, buf)
    print('蒙版已重建 ->', OUT)
    print('alpha 峰值 %.3f   非零占比 %.1f%%' % (max(avg), sum(1 for v in avg if v > 0.01) * 100.0 / n))


if __name__ == '__main__':
    main()
