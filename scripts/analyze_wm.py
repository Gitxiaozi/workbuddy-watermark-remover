"""水印分析工具：从纯色底图上反推水印的 alpha 蒙版。

原理：输出 = 原图*(1-a) + 涂色*a  =>  a = (输出 - 原图) / (涂色 - 原图)
纯色底图的"原图"用平面拟合从水印区域外围插值得到（纯 Python 最小二乘）。
"""
import sys, zlib, struct
from crop_png import read_png, unfilter, write_png


def load(path):
    ihdr, idat = read_png(path)
    w, h, bd, ct = struct.unpack('>IIBB', ihdr[:10])
    assert bd == 8, bd
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    px = unfilter(zlib.decompress(idat), w, h, bpp)
    return w, h, bpp, px, ct


def save_gray(path, w, h, buf):
    write_png(path, w, h, 1, 0, bytes(buf))


def solve3(A, b):
    """高斯消元解 3x3"""
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-12:
            return None
        M[i], M[p] = M[p], M[i]
        for r in range(3):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, 4):
                    M[r][c] -= f * M[i][c]
    return [M[i][3] / M[i][i] for i in range(3)]


def fit_plane(pts):
    """pts: [(x,y,L)] 返回 (a,b,c) 使 L ≈ a*x+b*y+c"""
    S = [[0.0] * 3 for _ in range(3)]
    T = [0.0] * 3
    basis = lambda x, y: (x, y, 1.0)
    for x, y, L in pts:
        v = basis(x, y)
        for i in range(3):
            T[i] += v[i] * L
            for j in range(3):
                S[i][j] += v[i] * v[j]
    return solve3(S, T)


def lum(px, bpp, w, x, y):
    i = (y * w + x) * bpp
    return (px[i] * 299 + px[i + 1] * 587 + px[i + 2] * 114) / 1000.0


def analyse(path, x0, y0, x1, y1, out_prefix, th_ratio=0.35):
    w, h, bpp, px, ct = load(path)
    # 1) 先粗拟合平面，用低亮度像素（不含字）作为内点
    box = [(x, y, lum(px, bpp, w, x, y)) for y in range(y0, y1) for x in range(x0, x1)]
    plane = fit_plane(box)
    a, b, c = plane
    for _ in range(4):
        inner = [(x, y, L) for (x, y, L) in box if L - (a * x + b * y + c) < 12]
        plane = fit_plane(inner)
        a, b, c = plane
    resid = [L - (a * x + b * y + c) for (x, y, L) in box]
    base = sorted(resid)[len(resid) // 2]
    print('plane', [round(v, 5) for v in plane], 'resid median', round(base, 2))
    print('base lum at center', round(a * ((x0 + x1) / 2) + b * ((y0 + y1) / 2) + c, 2))

    # 2) alpha
    W = x1 - x0
    H = y1 - y0
    alpha = [0.0] * (W * H)
    amax = 0.0
    for y in range(y0, y1):
        for x in range(x0, x1):
            L = lum(px, bpp, w, x, y)
            bg = a * x + b * y + c
            al = (L - bg) / max(1e-6, 255.0 - bg)
            al = max(0.0, min(1.0, al))
            if al < 0.04:
                al = 0.0
            alpha[(y - y0) * W + (x - x0)] = al
            amax = max(amax, al)
    nz = sum(1 for v in alpha if v > 0)
    print('alpha max %.3f  nonzero %d (%.1f%% of box)' % (amax, nz, nz * 100.0 / (W * H)))

    # 3) 保存 alpha 可视化
    vis = bytearray(W * H)
    for i, v in enumerate(alpha):
        vis[i] = min(255, int(v / max(amax, 1e-6) * 255))
    save_gray(out_prefix + '_alpha.png', W, H, vis)
    print('saved', out_prefix + '_alpha.png', W, H)
    return alpha, W, H, (a, b, c), amax


if __name__ == '__main__':
    # 单独调试用；正常重建蒙版请走 rebuild_mask.py
    import sys
    if len(sys.argv) < 2:
        raise SystemExit('用法: python analyze_wm.py <纯底图.png> [输出前缀]')
    src = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else src.rsplit('.', 1)[0] + '_mask'
    from crop_png import read_png
    import struct as _s
    ihdr, _ = read_png(src)
    w, h = _s.unpack('>II', ihdr[:8])
    analyse(src, max(0, w - 144), max(0, h - 84), w, h, prefix)
