"""晃动诊断：比较原片与渲染的"帧间二阶差分"，把"感觉有点晃"变成一个数。

原理：
  原片的运动是平滑的（加速度 RMS 通常在 0.03-0.1）。
  如果渲染的加速度 RMS 明显更大，说明抖动来自我们的数据或渲染方式，而不是原片。

  注意：逐帧 MAE 检测不出晃动 —— 它只看"每帧像不像"，
  而晃动是"帧间不均匀"，必须看帧序列的二阶差分。

测量项（可用 --roi 指定区域，默认适配左侧文字列表 + 右侧卡片）：
  bandN     —— 第 N 个文字带的墨迹框 (x0, x1, yc)
  edgeL     —— 区域左边缘 x
  edgeT     —— 区域上边缘 y

判据：倍数 > 2 且渲染 RMS > 0.25 时标记 ←

用法：
  python diagnose_jitter.py --orig frames/ --render render_v1/ --windows 50:66 94:118
  python diagnose_jitter.py --orig frames/ --render render_v1/ --roi 0 355 40 414
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def text_bands(im: np.ndarray, x0: int, x1: int, y0: int, y1: int,
               lum_thr: float, bg: float) -> list[tuple[int, int, float]]:
    """返回文字带的 [(x_left, x_right, y_center)]。"""
    sub = im[y0:y1, x0:x1].astype(np.int16)
    L = 0.114 * sub[..., 0] + 0.587 * sub[..., 1] + 0.299 * sub[..., 2]
    sat = sub.max(-1) - sub.min(-1)
    m = (L < lum_thr) & (sat < 16)
    rows = m.sum(1) >= 2
    out = []
    a = None
    for i, v in enumerate(list(rows) + [False]):
        if v and a is None:
            a = i
        elif not v and a is not None:
            if 18 <= i - a <= 70:
                cols = np.where(m[a:i].any(0))[0]
                if len(cols) > 20:
                    out.append((x0 + int(cols[0]), x0 + int(cols[-1]) + 1,
                                y0 + (a + i - 1) / 2))
            a = None
    return out


def edges(im: np.ndarray, bg: float, thr: float,
          rows: tuple[int, ...], col_band: tuple[int, int]):
    """返回 (左边缘 x, 上边缘 y)。"""
    d = np.abs(im.astype(np.int16) - bg).max(-1) > thr
    left = None
    for r in rows:
        row = d[r, :]
        idx = next((x for x in range(len(row) - 6) if row[x:x + 6].all()), None)
        if idx is not None:
            left = idx if left is None else min(left, idx)
    col = d[:, col_band[0]:col_band[1]].mean(1) > 0.7
    top = next((y for y in range(0, min(300, d.shape[0])) if col[y:y + 4].all()), None)
    return left, top


def _clean(vals):
    a = np.array([v for v in vals if v is not None], float)
    return a if len(a) >= 4 else None


def rms2(vals) -> tuple[float | None, int]:
    a = _clean(vals)
    if a is None:
        return None, 0
    d2 = a[2:] - 2 * a[1:-1] + a[:-2]
    return float(np.sqrt((d2 ** 2).mean())), len(a)


def rms1(vals) -> tuple[float | None, int]:
    a = _clean(vals)
    if a is None or len(a) < 3:
        return None, 0
    d1 = np.diff(a, axis=0)
    return float(np.sqrt((d1 ** 2).mean())), len(a)



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="晃动诊断：帧间二阶差分对比")
    p.add_argument("--orig", required=True, help="原片全帧目录")
    p.add_argument("--render", required=True, help="复刻渲染帧目录")
    p.add_argument("--out", default="jitter.json", help="输出 JSON 路径")
    p.add_argument("--windows", nargs="*", default=None,
                   help="检查窗口，格式 start:end（帧号）。省略则整片")
    p.add_argument("--roi", type=int, nargs=4, default=[0, 355, 40, 414],
                   metavar=("X0", "X1", "Y0", "Y1"), help="文字列表区域")
    p.add_argument("--edge-rows", type=int, nargs="*", default=[240],
                   help="测左边缘的扫描行")
    p.add_argument("--edge-cols", type=int, nargs=2, default=[450, 650],
                   metavar=("C0", "C1"), help="测上边缘的扫描列区间")
    p.add_argument("--lum-thr", type=float, default=215.0, help="文字亮度阈值")
    p.add_argument("--bg", type=float, default=234.0, help="背景基准亮度")
    p.add_argument("--edge-thr", type=float, default=14.0, help="边缘检测阈值")
    p.add_argument("--ratio-hi", type=float, default=2.0, help="倍数告警线")
    p.add_argument("--rms-hi", type=float, default=0.25, help="渲染 RMS 告警线")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    x0, x1, y0, y1 = a.roi

    op = sorted(Path(a.orig).glob("*.png"))
    rp = sorted(Path(a.render).glob("*.png"))
    if not op or not rp:
        raise SystemExit(f"帧不足: orig={len(op)} render={len(rp)}")
    n = min(len(op), len(rp))
    orig = [cv2.imread(str(p)) for p in op[:n]]
    rend = [cv2.imread(str(p)) for p in rp[:n]]
    print(f"比较 {n} 帧（原片 {len(op)} / 渲染 {len(rp)}，取较短）")

    tb = lambda im: text_bands(im, x0, x1, y0, y1, a.lum_thr, a.bg)
    ed = lambda im: edges(im, a.bg, a.edge_thr, tuple(a.edge_rows),
                          tuple(a.edge_cols))

    if a.windows:
        wins = []
        for w in a.windows:
            lo, hi = (int(v) for v in w.split(":"))
            wins.append((f"帧 {lo}-{hi}", lo, min(hi, n)))
    else:
        wins = [("整片", 0, n)]

    measures = [
        ("标签x0", lambda im: [b[0] for b in tb(im)] or None),
        ("标签x1", lambda im: [b[1] for b in tb(im)] or None),
        ("标签yc", lambda im: [b[2] for b in tb(im)] or None),
        ("左边缘", lambda im: ed(im)[0]),
        ("上边缘", lambda im: ed(im)[1]),
    ]

    print(f"\n{'窗口':<16} {'元素':<8} {'原片RMS':>9} {'渲染RMS':>9} {'倍数':>7}")
    print("-" * 56)
    flagged: list[dict] = []
    for name, lo, hi in wins:
        for label, fn in measures:
            so = [fn(im) for im in orig[lo:hi]]
            sr = [fn(im) for im in rend[lo:hi]]
            o2, _ = rms2(so)
            r2, _ = rms2(sr)
            if o2 is None or r2 is None:
                continue
            ratio = r2 / o2 if o2 > 1e-9 else float("inf")
            bad = ratio > a.ratio_hi and r2 > a.rms_hi
            print(f"{name:<16} {label:<8} {o2:>9.3f} {r2:>9.3f} "
                  f"{ratio:>7.2f}{'  ←' if bad else ''}")
            if bad:
                flagged.append({"window": name, "element": label,
                                "orig_rms2": round(o2, 4),
                                "render_rms2": round(r2, 4),
                                "ratio": round(ratio, 3)})

    print("\n也报告一阶差分（速度）RMS，用于区分「位移跳变」和「速度跳变」:")
    for name, lo, hi in wins[:2]:
        for label, fn in measures[:3]:
            v1o, _ = rms1([fn(im) for im in orig[lo:hi]])
            v1r, _ = rms1([fn(im) for im in rend[lo:hi]])
            if v1o is None or v1r is None:
                continue
            print(f"  {name:<14} {label:<8} 原片 {v1o:.3f}  渲染 {v1r:.3f}")

    print("\n结论:")
    if flagged:
        for f in flagged:
            print(f"  ← {f['window']} 的 {f['element']} 渲染抖动是原片的 "
                  f"{f['ratio']} 倍（RMS {f['render_rms2']}）")
        print("\n  修复顺序:")
        print("   1. 该元素是否用了 CSS left/top 或 SVG <text> 做位移？"
              " → 改成 HTML + transform: translate()")
        print("   2. willChange: 'transform' 是否和 transform 在同一个 DOM 节点？"
              " → 合并到同一元素")
        print("   3. 镜头轨道是否混入了过渡帧？"
              " → 用 fit_camera_track.py 重建，tx 只取严格静止元素")
    else:
        print("  未发现明显抖动（所有元素倍数均低于告警线）")
        print("  若肉眼看仍有轻微晃动，请降低 --ratio-hi 到 1.5 再审一遍。")

    res = {"frames_compared": n, "windows": [w[0] for w in wins],
           "roi": [x0, x1, y0, y1], "flagged": flagged}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
