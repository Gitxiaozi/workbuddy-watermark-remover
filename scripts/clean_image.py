"""clean_image.py —— 去除生成图右下角水印

两种模式：
  crop  ：把底部包含水印的那一条整体切掉（构图要求底部有留白）
  erase ：按已知 alpha 蒙版做反混合，把水印"揭掉"、保留完整画布
  auto  ：默认 erase；若检测不到水印或反混合后仍有残影，自动改用 crop

依赖：crop_png.py（纯标准库 PNG 读写）；蒙版 wm_alpha_ref.png 由 analyze_wm.py 生成。

用法：
  python clean_image.py 图.png                 # auto
  python clean_image.py 图.png --mode erase
  python clean_image.py 图.png --mode crop --safety 8
"""
import os
import sys
import zlib
import struct

from crop_png import read_png, unfilter, write_png

REF_W = 1024           # 蒙版基准宽度
SAFETY = 8             # crop 模式额外多切的像素
HERE = os.path.dirname(os.path.abspath(__file__))
_CANDS = [
    os.path.join(HERE, os.pardir, 'assets', 'wm_alpha_ref.png'),
    os.path.join(HERE, 'wm_alpha_ref.png'),
]
MASK = next((os.path.abspath(p) for p in _CANDS if os.path.exists(p)), os.path.abspath(_CANDS[0]))


# ---------- 基础 IO ----------

def load(path):
    ihdr, idat = read_png(path)
    w, h, bd, ct = struct.unpack('>IIBB', ihdr[:10])
    assert bd == 8, 'only 8bit png supported, got %d' % bd
    assert ct in (0, 2, 4, 6), 'unsupported colortype %d' % ct
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    px = unfilter(zlib.decompress(idat), w, h, bpp)
    return w, h, bpp, ct, px


def save(path, w, h, bpp, ct, px):
    write_png(path, w, h, bpp, ct, px)


def load_mask():
    w, h, bpp, ct, px = load(MASK)
    a = [px[i] / 255.0 for i in range(0, len(px), bpp)]
    return w, h, a


# ---------- 定位 ----------

def place(img_w, img_h, mw, mh):
    """蒙版锚定在右下角，返回左上角坐标"""
    return img_w - mw, img_h - mh


def score(px, bpp, w, mx, my, mw, mh, alpha, dx=0, dy=0):
    """蒙版位置的匹配分：窗口内"字迹区"与"空白区"的亮度差。

    自归一化，不依赖整图底色，渐变背景也不受影响。
    """
    x0, y0 = mx + dx, my + dy
    fg = bg = 0.0
    nf = nb = 0
    for y in range(0, mh, 2):
        for x in range(0, mw, 2):
            a = alpha[y * mw + x]
            if a > 0.25:
                i = ((y0 + y) * w + (x0 + x)) * bpp
                fg += (px[i] * 299 + px[i + 1] * 587 + px[i + 2] * 114) / 1000.0
                nf += 1
            elif a < 0.04:
                i = ((y0 + y) * w + (x0 + x)) * bpp
                bg += (px[i] * 299 + px[i + 1] * 587 + px[i + 2] * 114) / 1000.0
                nb += 1
    if not nf or not nb:
        return 0.0
    return fg / nf - bg / nb


def detect(px, bpp, w, h, mw, mh, alpha):
    """返回 (dx, dy, 置信度)。在右下角小范围搜索最佳对齐。"""
    mx, my = place(w, h, mw, mh)
    best = None

    def inside(ddx, ddy):
        return (mx + ddx >= 0 and my + ddy >= 0
                and mx + ddx + mw <= w and my + ddy + mh <= h)

    for dy in range(-24, 25, 4):
        for dx in range(-24, 25, 4):
            if not inside(dx, dy):
                continue
            s = score(px, bpp, w, mx, my, mw, mh, alpha, dx, dy)
            if best is None or s > best[2]:
                best = (dx, dy, s)
    if best is None:
        return 0, 0, 0.0
    dx, dy, s = best
    for ddy in range(dy - 3, dy + 4):
        for ddx in range(dx - 3, dx + 4):
            if not inside(ddx, ddy):
                continue
            ss = score(px, bpp, w, mx, my, mw, mh, alpha, ddx, ddy)
            if ss > s:
                dx, dy, s = ddx, ddy, ss
    return dx, dy, s


# ---------- 擦除 ----------

def erase(px, bpp, w, mx, my, mw, mh, alpha, white=255.0):
    """反混合：orig = (C - white*a) / (1-a)"""
    x0, y0 = mx, my
    for y in range(mh):
        row = y * mw
        for x in range(mw):
            a = alpha[row + x]
            if a < 0.03:
                continue
            i = ((y0 + y) * w + (x0 + x)) * bpp
            inv = 1.0 - a
            for c in range(min(3, bpp)):
                v = (px[i + c] - white * a) / inv
                px[i + c] = 0 if v < 0 else (255 if v > 255 else int(v + 0.5))
    return px


def smooth_patch(px, bpp, w, mx, my, mw, mh, alpha, strength=0.55):
    """在 alpha 高的地方做一次 3x3 邻域平均，压掉反混合放大的噪点"""
    src = bytearray(px)
    x0, y0 = mx, my
    for y in range(1, mh - 1):
        for x in range(1, mw - 1):
            a = alpha[y * mw + x]
            if a < 0.12:
                continue
            k = min(0.85, a * strength * 2.2)
            i = ((y0 + y) * w + (x0 + x)) * bpp
            for c in range(min(3, bpp)):
                acc = 0
                for oy in (-1, 0, 1):
                    for ox in (-1, 0, 1):
                        j = ((y0 + y + oy) * w + (x0 + x + ox)) * bpp + c
                        acc += src[j]
                avg = acc / 9.0
                px[i + c] = int(src[i + c] * (1 - k) + avg * k + 0.5)
    return px


# ---------- 裁切 ----------

def crop_rows(px, w, h, bpp, cut):
    nh = h - cut
    return px[:nh * w * bpp], nh


def glyph_top(alpha, mw, mh, th=0.06):
    for y in range(mh):
        for x in range(mw):
            if alpha[y * mw + x] > th:
                return y
    return mh


# ---------- 主流程 ----------

def clean(path, mode='auto', safety=SAFETY, out_dir=None, force=False):
    w, h, bpp, ct, px = load(path)
    mw, mh, alpha = load_mask()
    if w < mw + 4 or h < mh + 4:
        raise SystemExit('图片太小，无处理意义')

    dx, dy, conf = detect(px, bpp, w, h, mw, mh, alpha)
    mx, my = place(w, h, mw, mh)
    mx += dx
    my += dy
    print('图片 %dx%d  水印位置偏移 (%d,%d)  置信度 %.1f' % (w, h, dx, dy, conf))

    base = os.path.splitext(os.path.basename(path))[0]
    odir = out_dir or os.path.dirname(os.path.abspath(path))

    if conf < 3.0 and not force:
        print('  未检测到水印（置信度低于 3.0），跳过；确认有水印可加 --force')
        return None, 'skip'

    ok = conf > 6.0
    if not ok and mode == 'auto':
        print('  水印痕迹偏弱，模式降级为 crop')
        mode = 'crop'

    if mode == 'erase' or (mode == 'auto' and ok):
        out_px = bytearray(px)
        erase(out_px, bpp, w, mx, my, mw, mh, alpha)
        smooth_patch(out_px, bpp, w, mx, my, mw, mh, alpha)
        dst = os.path.join(odir, base + '_clean.png')
        save(dst, w, h, bpp, ct, out_px)
        print('  已擦除水印，画布不变 ->', dst)
        return dst, 'erase'

    cut = mh - glyph_top(alpha, mw, mh) + safety
    if cut >= h - 8:
        print('  裁切量异常（%d），放弃' % cut)
        return None, 'skip'
    out_px, nh = crop_rows(px, w, h, bpp, cut)
    dst = os.path.join(odir, base + '_cropped.png')
    save(dst, w, nh, bpp, ct, out_px)
    print('  已切底部 %dpx -> %s (%dx%d)' % (cut, dst, w, nh))
    return dst, 'crop'


def zoom(path, x, y, ww, hh, scale, dst):
    """截取局部放大，便于肉眼验收"""
    w, h, bpp, ct, px = load(path)
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    ww = min(ww, w - x)
    hh = min(hh, h - y)
    ow, oh = ww * scale, hh * scale
    out = bytearray(ow * oh * bpp)
    for oy in range(oh):
        sy = y + oy // scale
        for ox in range(ow):
            sx = x + ox // scale
            i = (sy * w + sx) * bpp
            j = (oy * ow + ox) * bpp
            out[j:j + bpp] = px[i:i + bpp]
    save(dst, ow, oh, bpp, ct, out)
    return dst


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    mode = 'auto'
    safety = SAFETY
    force = False
    if '--force' in args:
        force = True
        args.remove('--force')
    if '--mode' in args:
        mode = args[args.index('--mode') + 1]
        args.remove(mode)
        args.remove('--mode')
    if '--safety' in args:
        safety = int(args[args.index('--safety') + 1])
        args.remove(str(safety))
        args.remove('--safety')

    targets = []
    for p in args:
        if os.path.isdir(p):
            for fn in sorted(os.listdir(p)):
                if fn.lower().endswith('.png') and not fn.endswith(('_clean.png', '_cropped.png')):
                    targets.append(os.path.join(p, fn))
        else:
            targets.append(p)

    for p in targets:
        try:
            clean(p, mode=mode, safety=safety, force=force)
        except SystemExit as e:
            print('  跳过：%s' % e)
        print()
