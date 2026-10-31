"""locate_wm.py —— 不预设尺寸，自动定位右下角水印包围盒。

对右下角搜索区做平面拟合估底色，残差明显偏亮的连通像素即水印，取包围盒。
"""
import sys
from crop_png import read_png, unfilter
from analyze_wm import fit_plane, lum
import zlib, struct


def load(path):
    ihdr, idat = read_png(path)
    w, h, bd, ct = struct.unpack('>IIBB', ihdr[:10])
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    return w, h, bpp, unfilter(zlib.decompress(idat), w, h, bpp)


def locate(path, region_w=None, region_h=None, th=12.0):
    w, h, bpp, px = load(path)
    rw = region_w or max(560, w // 3)
    rh = region_h or max(220, h // 8)
    x0, y0 = max(0, w - rw), max(0, h - rh)
    pts = [(x, y, lum(px, bpp, w, x, y)) for y in range(y0, h) for x in range(x0, w)]
    a, b, c = fit_plane(pts)
    for _ in range(4):
        inner = [(x, y, L) for (x, y, L) in pts if L - (a * x + b * y + c) < th * 0.6]
        a, b, c = fit_plane(inner)
    hits = [(x, y) for (x, y, L) in pts if L - (a * x + b * y + c) > th]
    if not hits:
        return None
    xs = [p[0] for p in hits]
    ys = [p[1] for p in hits]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    print('%s  (%dx%d)' % (path.split('/')[-1], w, h))
    print('  命中 %d 像素   bbox x[%d-%d] y[%d-%d]  尺寸 %dx%d' % (len(hits), bx0, bx1, by0, by1, bw, bh))
    print('  距右边 %d px  距底边 %d px' % (w - 1 - bx1, h - 1 - by1))
    print('  尺寸/宽度 %.4f  %%  尺寸/高度 %.4f %%' % (bw / w * 100, bh / h * 100))
    return dict(w=w, h=h, x0=bx0, x1=bx1, y0=by0, y1=by1, bw=bw, bh=bh,
                right=w - 1 - bx1, bottom=h - 1 - by1)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        locate(p)
        print()
