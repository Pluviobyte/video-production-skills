"""镜头轨重建：用亚像素质心拟合一组元素的组变换 (s, tx, ty)。

为什么必须用质心而不是阈值边界（实测教训）：
  用"阈值墨迹框"的整数边界拟合 → 带 ~1px 量化噪声
  （实测 ty 加速度 RMS 0.84，而原片元素本身只有 0.027）→ 渲染出来就是轻微晃动。
  质心是灰度加权一阶矩，亚像素精度，噪声低一个量级。

模型：screen = diag(s, s) . layout + (tx, ty)
  即整体等比缩放 + 平移（UI 镜头的常见形式）。

拟合流程：
  1. 在参考帧上测出 N 个元素的质心，作为 layout 基准
  2. 从参考帧向两侧逐帧跟踪：按预测位置认领元素 → 对 (refY, cy) 做最小二乘解 s 和 ty
  3. tx 只用"已知静止"的元素（默认可由 --tx-only 指定）取中位数，
     因为激活/过渡中的元素字距和缩进都在变，其质心不反映镜头平移
  4. 空缺帧沿用上一帧值；内部区间做 5 点二次 SG 平滑
  5. 报告平滑前后的加速度 RMS，用于确认抖动是否被消除

用法：
  python fit_camera_track.py --frames frames/ --roi 40 350 40 414 \
      --ref-frame 100 --bands 4 --out camera.json
  python fit_camera_track.py --frames frames/ --roi 40 350 40 414 \
      --ref-frame 100 --bands 4 --tx-only 0 2 3 --out camera.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def bands(im: np.ndarray, x0: int, x1: int, y0: int, y1: int,
          cut: float, soft: float, min_h: int, max_h: int,
          min_mass: float, gap: int = 6) -> list[tuple[float, float, float]]:
    """返回 [(cx, cy, mass)]，亚像素质心。

    权重 w = clip((cut - L)/soft, 0, 1) * (饱和度低)：
    亮背景权重 0（不被当文字），未激活文字权重中低，激活文字权重 1.0，
    抗锯齿边缘平滑过渡 —— 这正是亚像素精度的来源。
    """
    sub = im[y0:y1, x0:x1].astype(np.float32)
    L = 0.114 * sub[..., 0] + 0.587 * sub[..., 1] + 0.299 * sub[..., 2]
    sat = sub.max(-1) - sub.min(-1)
    dark = np.clip((cut - L) / soft, 0, 1.0) * (sat < 16)

    rows = dark.sum(1) > 2.5
    raw, a = [], None
    for i, v in enumerate(list(rows) + [False]):
        if v and a is None:
            a = i
        elif not v and a is not None:
            raw.append((a, i))
            a = None

    # 合并间隔 <= gap 行的小断口（字母之间、升部与降部之间的小缝）
    merged: list[tuple[int, int]] = []
    for s0, s1 in raw:
        if merged and s0 - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], s1)
        else:
            merged.append((s0, s1))

    out = []
    for a, b in merged:
        if min_h <= b - a <= max_h:
            y0b, y1b = max(0, a - 3), min(dark.shape[0], b + 3)
            w = dark[y0b:y1b]
            m = w.sum()
            if m > min_mass:
                hh, ww = w.shape
                yy = np.repeat((np.arange(y0b, y0b + hh)[:, None] + y0).astype(np.float32),
                               ww, axis=1)
                xx = np.repeat((np.arange(x0, x0 + ww)[None, :]).astype(np.float32),
                               hh, axis=0)
                out.append((float((w * xx).sum() / m),
                            float((w * yy).sum() / m), float(m)))
    return out


def rms2(a: np.ndarray, lo: int, hi: int) -> float:
    """二阶差分（加速度）均方根。原片平滑运动约 <0.05，>0.3 就是可见晃动。"""
    v = np.asarray(a[lo:hi], float)
    if len(v) < 3:
        return 0.0
    d2 = v[2:] - 2 * v[1:-1] + v[:-2]
    return float(np.sqrt((d2 ** 2).mean()))



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="用亚像素质心拟合镜头组变换 (s,tx,ty)")
    p.add_argument("--frames", required=True, help="全帧 PNG 目录")
    p.add_argument("--out", default="camera.json", help="输出 JSON 路径")
    p.add_argument("--roi", type=int, nargs=4, required=True,
                   metavar=("X0", "X1", "Y0", "Y1"),
                   help="元素所在区域")
    p.add_argument("--ref-frame", type=int, required=True,
                   help="参考帧（该帧上测 layout 基准，取元素清晰静止的一帧）")
    p.add_argument("--bands", type=int, default=4, help="预期元素个数（默认 4）")
    p.add_argument("--tx-only", type=int, nargs="*", default=None,
                   help="只用于拟合 tx 的元素下标（已知整段时间都静止的那些）")
    p.add_argument("--cut", type=float, default=195.0,
                   help="墨迹亮度上限（默认 195）")
    p.add_argument("--soft", type=float, default=45.0,
                   help="墨迹权重过渡带宽（默认 45）")
    p.add_argument("--min-h", type=int, default=18, help="元素最小高度像素")
    p.add_argument("--max-h", type=int, default=70, help="元素最大高度像素")
    p.add_argument("--min-mass", type=float, default=60.0, help="最小墨迹量")
    p.add_argument("--s-lo", type=float, default=0.9, help="缩放合理下界")
    p.add_argument("--s-hi", type=float, default=1.8, help="缩放合理上界")
    p.add_argument("--fit-lo", type=int, default=None,
                   help="重建区间起点帧（默认 0）")
    p.add_argument("--fit-hi", type=int, default=None,
                   help="重建区间终点帧（默认末帧）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    x0, x1, y0, y1 = a.roi

    files = sorted(Path(a.frames).glob("*.png"))
    if not files:
        raise SystemExit(f"{a.frames} 下没有 PNG 帧")
    ims = [cv2.imread(str(p)) for p in files]
    T = len(ims)
    if not (0 <= a.ref_frame < T):
        raise SystemExit(f"--ref-frame {a.ref_frame} 超出范围 0..{T - 1}")

    kw = dict(x0=x0, x1=x1, y0=y0, y1=y1, cut=a.cut, soft=a.soft,
              min_h=a.min_h, max_h=a.max_h, min_mass=a.min_mass)
    meas = [bands(im, **kw) for im in ims]

    ref = meas[a.ref_frame]
    if len(ref) != a.bands:
        print(f"警告: 参考帧只测到 {len(ref)} 个元素，期望 {a.bands} 个。"
              f"请检查 --roi / --bands / --cut / --min-mass。")
        return 1
    # 按 y 从上到下排序，作为稳定的元素身份
    ref_sorted = sorted(ref, key=lambda b: b[1])
    REF_X = [round(b[0], 3) for b in ref_sorted]
    REF_Y = [round(b[1], 3) for b in ref_sorted]
    print(f"参考帧 t={a.ref_frame} 质心基准:")
    for i in range(a.bands):
        print(f"  [{i}] cx={REF_X[i]:>8.3f}  cy={REF_Y[i]:>8.3f}")

    n = a.bands
    s = np.full(T, np.nan)
    tx = np.full(T, np.nan)
    ty = np.full(T, np.nan)
    s[a.ref_frame], tx[a.ref_frame], ty[a.ref_frame] = 1.0, 0.0, 0.0

    def fit_frame(t: int, s_prev: float, tx_prev: float, ty_prev: float):
        bs = [b for b in meas[t] if b[2] > a.min_mass]
        used, pairs = set(), []
        for cx, cy, _m in bs:
            pred = [s_prev * REF_Y[i] + ty_prev for i in range(n)]
            cand = [(abs(cy - pred[i]), i) for i in range(n) if i not in used]
            if not cand:
                continue
            d, i = min(cand)
            if d < 25:                       # 认领半径：只接受就近匹配
                used.add(i)
                pairs.append((i, cx, cy))
        if len(pairs) < 2:
            return None
        Y = np.array([REF_Y[i] for i, _, _ in pairs])
        y = np.array([cy for _, _, cy in pairs])
        A = np.vstack([Y, np.ones_like(Y)]).T
        ss, tt = np.linalg.lstsq(A, y, rcond=None)[0]
        if not (a.s_lo < ss < a.s_hi):
            return None
        # tx：只用已知静止的元素下标
        idxs = set(a.tx_only) if a.tx_only else set(range(n))
        inact = [(i, cx) for i, cx, _ in pairs if i in idxs]
        ttx = (float(np.median([cx - ss * REF_X[i] for i, cx in inact]))
               if inact else tx_prev)
        return float(ss), ttx, float(tt)

    # 从参考帧向两侧跟踪
    for direction in (1, -1):
        prev = (1.0, 0.0, 0.0)
        rng = (range(a.ref_frame + 1, T) if direction > 0
               else range(a.ref_frame - 1, -1, -1))
        for t in rng:
            r = fit_frame(t, *prev)
            if r is None:
                continue
            s[t], tx[t], ty[t] = r
            prev = r

    raw_s, raw_tx, raw_ty = s.copy(), tx.copy(), ty.copy()

    # 空缺帧沿用最近的有效值（先向前填，再向后填）
    for arr in (s, tx, ty):
        last = None
        for t in range(T):
            if np.isnan(arr[t]):
                if last is not None:
                    arr[t] = last
            else:
                last = arr[t]
        last = None
        for t in range(T - 1, -1, -1):
            if np.isnan(arr[t]):
                if last is not None:
                    arr[t] = last
            else:
                last = arr[t]

    lo = a.fit_lo if a.fit_lo is not None else 0
    hi = a.fit_hi if a.fit_hi is not None else T
    SG = np.array([-3.0, 12.0, 17.0, 12.0, -3.0]) / 35.0   # 5 点二次
    for arr in (s, tx, ty):
        src = arr.copy()
        for t in range(lo + 2, hi - 1):
            arr[t] = float((src[t - 2:t + 3] * SG).sum())

    print(f"\n重建区间 t{lo}-{hi} 的加速度 RMS（越小越平滑）:")
    for name, new, old in (("s", s, raw_s), ("tx", tx, raw_tx), ("ty", ty, raw_ty)):
        print(f"  {name:<3} 平滑前 {rms2(old, lo, hi):.4f} → 平滑后 {rms2(new, lo, hi):.4f}")

    usable = int(np.sum(~np.isnan(raw_s[lo:hi])))
    print(f"\n拟合成功帧: {usable}/{hi - lo}"
          + ("（偏少 —— 检查 --roi 是否覆盖了元素，或 --cut 是否合适）"
             if usable < (hi - lo) * 0.5 else ""))

    res = {"frames": T, "roi": [x0, x1, y0, y1], "ref_frame": a.ref_frame,
           "bands": a.bands, "tx_only": a.tx_only,
           "ref_centroids": [{"i": i, "x": REF_X[i], "y": REF_Y[i]} for i in range(n)],
           "camera": [[round(float(s[t]), 4), round(float(tx[t]), 3),
                       round(float(ty[t]), 3)] for t in range(T)],
           "rms2": {"s": round(rms2(s, lo, hi), 4),
                    "tx": round(rms2(tx, lo, hi), 4),
                    "ty": round(rms2(ty, lo, hi), 4)},
           "fit_ok_frames": usable}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}")
    print("下一步: 把 camera 数组按帧喂给 Remotion —— "
          "transform: translate(tx, ty) scale(s)，且 willChange 必须在同一元素上")
    return 0


if __name__ == "__main__":
    sys.exit(main())
