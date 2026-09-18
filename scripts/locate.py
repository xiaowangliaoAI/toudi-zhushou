#!/usr/bin/env python3
"""locate —— 截图像素定位（跨平台）。坐标不可复用，每次换机器/分辨率都要重跑。

用法:
    python locate.py info   SHOT.png
    python locate.py button SHOT.png [--color R,G,B] [--tol 40]
    python locate.py cards  SHOT.png X Y0 Y1 [--merge 40] [--min-h 60]
    python locate.py crop   SHOT.png X0 Y0 X1 Y1 OUT.png

坐标约定:
    macOS   : 截图是 Retina 物理像素，输出「逻辑点」= 像素 ÷ 2
    Windows : 输出「物理像素」（与截图 1:1）
    可用 --scale 强制覆盖（例如外接屏非 2x 时）

为什么不能目测:
    把截图交给模型看图时图会被缩放，肉眼估坐标误差可达 5% 以上，
    小按钮必然点空。所以一律按像素算。
"""
import argparse
import os
import sys

from PIL import Image

DEFAULT_SCALE = 2 if sys.platform == 'darwin' else 1


def load(path):
    img = Image.open(path).convert('RGB')
    return img, img.load(), img.size


def near(p, target, tol):
    return all(abs(p[i] - target[i]) < tol for i in range(3))


# ---------------------------------------------------------------- info
def cmd_info(args):
    img, _, (w, h) = load(args.shot)
    scale = args.scale or DEFAULT_SCALE
    print(f'image_px   : {w}x{h}')
    print(f'scale      : {scale}   (--scale 可覆盖)')
    print(f'driver_cs  : {w // scale}x{h // scale}   ← uidrv.py 使用的坐标空间')
    print(f'platform   : {sys.platform}')


# ---------------------------------------------------------------- button
def cmd_button(args):
    img, px, (w, h) = load(args.shot)
    scale = args.scale or DEFAULT_SCALE
    target = tuple(int(v) for v in args.color.split(','))
    tol = args.tol

    mask = [[near(px[x, y], target, tol) for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    boxes = []
    for y0 in range(h):
        for x0 in range(w):
            if mask[y0][x0] and not seen[y0][x0]:
                stack = [(x0, y0)]
                seen[y0][x0] = True
                minx = maxx = x0
                miny = maxy = y0
                n = 0
                while stack:
                    x, y = stack.pop()
                    n += 1
                    if x < minx: minx = x
                    if x > maxx: maxx = x
                    if y < miny: miny = y
                    if y > maxy: maxy = y
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                bw, bh = maxx - minx + 1, maxy - miny + 1
                # 实心块判定：填充率高 + 尺寸像按钮
                if bw > 40 * scale // 2 and bh > 20 * scale // 2 and n > 0.6 * bw * bh:
                    boxes.append((minx, miny, maxx, maxy, bw, bh))

    boxes.sort(key=lambda b: -b[4] * b[5])
    if not boxes:
        print('no solid block found —— 换 --color 试，或用 crop 裁出目标区域人工确认')
        return
    print(f'found {len(boxes)} block(s), color={target}:')
    for minx, miny, maxx, maxy, bw, bh in boxes[:12]:
        print(f'  click=({(minx + maxx) // 2 // scale},{(miny + maxy) // 2 // scale})'
              f'  box=({minx // scale},{miny // scale})-({maxx // scale},{maxy // scale})'
              f'  px={bw}x{bh}')


# ---------------------------------------------------------------- cards
def cmd_cards(args):
    """按「行白像素占比」找列表卡片。

    单列扫描很脆：扫描线一旦落在卡片的空白带上，整段都是白的，
    卡片间隙（通常只有 8–20px）配上一个偏大的 merge 阈值就会把全部卡片糊成一块。
    改成在一个横向带宽内逐行统计白像素占比：卡片行占比高，间隙行（灰底）占比低。
    """
    img, px, (w, h) = load(args.shot)
    scale = args.scale or DEFAULT_SCALE
    x0 = int(args.x) * scale
    x1 = min(x0 + int(args.width) * scale, w)
    y0 = int(args.y0) * scale
    y1 = min(int(args.y1) * scale, h)
    if x1 <= x0:
        print('扫描带宽为 0 —— --width 太小，或 x 超出图像')
        return

    step = 2
    xs = list(range(x0, x1, step))
    ncol = len(xs)

    def is_white(p):
        return p[0] > 244 and p[1] > 244 and p[2] > 244

    rows = []
    for y in range(y0, y1):
        cnt = 0
        for x in xs:
            if is_white(px[x, y]):
                cnt += 1
        rows.append(cnt / ncol)

    # 卡片行判定：占比高于阈值；用滞回（进入/退出阈值不同）避免抖动
    enter, exit_ = args.ratio, args.ratio - 0.15
    raw, cur = [], None
    for i, r in enumerate(rows):
        y = y0 + i
        if cur is None and r >= enter:
            cur = y
        elif cur is not None and r < exit_:
            raw.append([cur, y - 1]); cur = None
    if cur is not None:
        raw.append([cur, y0 + len(rows) - 1])

    merged = []
    for a, b in raw:
        if merged and a - merged[-1][1] <= args.merge * scale:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    n = 0
    heights = []
    for a, b in merged:
        hh = (b - a + 1) // scale
        if hh < args.min_h:
            continue
        n += 1
        heights.append(hh)
        print(f'  card#{n}  click_y={(a + b) // 2 // scale}'
              f'  box_y=({a // scale},{b // scale})  高={hh}')

    if n == 0:
        print(f'no card found —— 当前阈值 ratio={enter}（退出 {exit_:.2f}），带宽 {x1 // scale - x0 // scale}pt。\n'
              '  排查：① X 带宽要落在列表卡片区域内（别扫到右侧详情面板或左侧导航）；'
              '② 卡片底不是纯白时把 --ratio 调低（如 0.5）；'
              '③ 列底色非白（深色主题）时本方法不适用，改用 crop 人工确认。')
        return

    gaps = [(merged[i + 1][0] - merged[i][1]) // scale for i in range(len(merged) - 1)]
    tops = [(merged[i + 1][0] - merged[i][0]) // scale for i in range(len(merged) - 1)]
    print(f'共 {n} 张；卡高中位数≈{sorted(heights)[len(heights) // 2]}pt'
          + (f'；卡片间隙中位数≈{sorted(gaps)[len(gaps) // 2]}pt' if gaps else ''))
    if gaps:
        g = sorted(gaps)[len(gaps) // 2]
        # 只有当「实际间隙 ≤ merge」时才可能被误合并
        if g <= args.merge:
            print(f'  ⚠️ 间隙({g}pt) ≤ merge({args.merge}pt)，相邻卡片可能被糊成一张 —— '
                  f'把 --merge 调到 {max(1, g - 2)} 重跑')
    print(f'  行距≈{sorted(tops)[len(tops) // 2] if tops else 0}pt'
          '（相邻卡片 click_y 之差的中位数，可用来推算下一张卡片位置）')


# ---------------------------------------------------------------- crop
def cmd_crop(args):
    img, _, (w, h) = load(args.shot)
    scale = args.scale or DEFAULT_SCALE
    box = (int(args.x0) * scale, int(args.y0) * scale,
           int(args.x1) * scale, int(args.y1) * scale)
    out = img.crop(box)
    out.save(args.out)
    print(f'saved {args.out}  {out.size[0]}x{out.size[1]}')


def main():
    p = argparse.ArgumentParser(description='截图像素定位')
    p.add_argument('--scale', type=int, default=None, help='强制覆盖缩放比例')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('info'); s.add_argument('shot'); s.set_defaults(fn=cmd_info)

    s = sub.add_parser('button')
    s.add_argument('shot')
    s.add_argument('--color', default='86,187,188',
                   help='目标色 R,G,B（默认青色按钮）')
    s.add_argument('--tol', type=int, default=40)
    s.set_defaults(fn=cmd_button)

    s = sub.add_parser('cards')
    s.add_argument('shot'); s.add_argument('x'); s.add_argument('y0'); s.add_argument('y1')
    s.add_argument('--width', type=int, default=300,
                   help='扫描带宽（逻辑点），从 x 向右取这么宽')
    s.add_argument('--merge', type=int, default=8,
                   help='合并阈值（逻辑点）。卡片间隙通常 8–20pt，别设太大，否则卡片会糊成一块')
    s.add_argument('--ratio', type=float, default=0.6,
                   help='行白像素占比阈值；卡片底非纯白时调低')
    s.add_argument('--min-h', type=int, default=60, help='最小卡高（逻辑点），滤掉表头/分隔行')
    s.set_defaults(fn=cmd_cards)

    s = sub.add_parser('crop')
    s.add_argument('shot'); s.add_argument('x0'); s.add_argument('y0')
    s.add_argument('x1'); s.add_argument('y1'); s.add_argument('out')
    s.set_defaults(fn=cmd_crop)

    args = p.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
