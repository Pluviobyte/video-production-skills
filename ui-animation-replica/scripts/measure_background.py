"""背景逐帧网格采样：掩掉前景后按有效像素面积加权降采样，空格子邻域扩散补齐。

为什么必须采样而不能猜模型（实测教训）：
  渐变用"模糊色团"建模 → MAE 45；改为逐帧网格采样 → MAE 1.8。差 26 倍。

流程：
  1. 对每帧构造前景掩码（暗于背景、有梯度、有色度、过亮的都算前景）
  2. 在被掩掉前景后剩下的像素上做 48x27 网格的面积加权降采样
  3. 空格子用邻域扩散补齐（反复迭代直到铺满）
  4. 时间维 3 帧轻度平滑，抑制部分遮挡格子的抖动

输出：
  --out-npy  逐帧网格数值（T×GY×GX×3，float32），供 Remotion 侧转成背景图
  --out-json 每帧网格的 MAE 报告与统计

用法：
  python measure_background.py --frames frames/ --out-npy bg.npy --out-json bg.json
  python measure_background.py --frames frames/ --gx 48 --gy 27 --out-npy bg.npy
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def lum(bgr_float: np.ndarray) -> np.ndarray:
    return 0.114 * bgr_float[..., 0] + 0.587 * bgr_float[..., 1] + 0.299 * bgr_float[..., 2]


def load_frames(d: Path) -> np.ndarray:
    files = sorted(d.glob("*.png"))
    if not files:
        raise SystemExit(f"{d} 下没有 PNG 帧")
    arrs = []
    for p in files:
        im = cv2.imread(str(p))
        if im is None:
            continue
        arrs.append(im)
    if not arrs:
        raise SystemExit(f"{d} 下没有可读的 PNG 帧")
    return np.stack(arrs)


def fg_mask(im: np.ndarray, bg_lum: float, right_cut: int | None) -> np.ndarray:
    """前景掩码：亮度偏离背景、有梯度、有色度、或过亮的像素。

    right_cut：右侧多少列起一律当背景（用于避开固定的右侧内容区）。
    """
    L = lum(im.astype(np.float32))
    g = cv2.GaussianBlur(L, (0, 0), 1.0)
    gm = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0),
                  cv2.Sobel(g, cv2.CV_32F, 0, 1)) / 8
    f = im.astype(np.int16)
    chroma = f.max(-1) - f.min(-1)
    m = (L < bg_lum - 20) | (gm > 3) | (chroma > 40) | (L > bg_lum + 8)
    if right_cut is not None:
        m[:, right_cut:] = True          # 右侧固定内容区：不参与背景采样
    return cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0


def grid_down(im: np.ndarray, valid: np.ndarray,
              gx: int, gy: int) -> np.ndarray:
    """有效像素的面积加权降采样。"""
    w = valid.astype(np.float32)
    rgb = im[..., ::-1].astype(np.float32)
    ws = cv2.resize(w, (gx, gy), interpolation=cv2.INTER_AREA)
    s = cv2.resize(rgb * w[..., None], (gx, gy), interpolation=cv2.INTER_AREA)
    known = ws > 0.15
    out = np.zeros_like(s)
    out[known] = s[known] / ws[known][:, None]
    k = known.copy()
    for _ in range(200):
        if k.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros((gy, gx), np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0),
                       (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sh = np.roll(np.roll(out * k[..., None], dy, 0), dx, 1)
            sk = np.roll(np.roll(k.astype(np.float32), dy, 0), dx, 1)
            if dy == 1:
                sh[0] = 0
                sk[0] = 0
            if dy == -1:
                sh[-1] = 0
                sk[-1] = 0
            if dx == 1:
                sh[:, 0] = 0
                sk[:, 0] = 0
            if dx == -1:
                sh[:, -1] = 0
                sk[:, -1] = 0
            acc += sh
            cnt += sk
        new = (~k) & (cnt > 0)
        out[new] = acc[new] / cnt[new][:, None]
        k = k | new
    return out



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="背景逐帧网格采样（不猜模型）")
    p.add_argument("--frames", required=True, help="全帧 PNG 目录")
    p.add_argument("--out-npy", default="bg_grids.npy",
                   help="输出网格数值 npy 路径")
    p.add_argument("--out-json", default="bg_report.json",
                   help="输出报告 JSON 路径")
    p.add_argument("--gx", type=int, default=48, help="网格宽（默认 48）")
    p.add_argument("--gy", type=int, default=27, help="网格高（默认 27）")
    p.add_argument("--bg-lum", type=float, default=234.0,
                   help="背景基准亮度（默认 234，浅灰底）")
    p.add_argument("--right-cut", type=int, default=None,
                   help="此列起一律当背景（避开右侧固定内容区）")
    p.add_argument("--smooth", type=int, default=1,
                   help="时间平滑半径帧数，0 关闭（默认 1 = 3 帧均值）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    F = load_frames(Path(a.frames))
    T, H, W, _ = F.shape
    print(f"载入 {T} 帧 {W}x{H}")

    grids, maes, flats = [], [], []
    for t in range(T):
        im = F[t]
        m = fg_mask(im, a.bg_lum, a.right_cut)
        g = grid_down(im, ~m, a.gx, a.gy)
        grids.append(g)
        up = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)
        v = ~m
        rgb = im[..., ::-1].astype(np.float32)
        maes.append(float(np.abs(up - rgb)[v].mean()))
        flats.append(float(np.abs(a.bg_lum - rgb)[v].mean()))

    g_arr = np.stack(grids)
    sm = g_arr.copy()
    if a.smooth >= 1:
        for k in range(1, a.smooth + 1):
            sm[k:-k] = (g_arr[:-2 * k] + g_arr[k:-k] + g_arr[2 * k:]) / 3

    Path(a.out_npy).parent.mkdir(parents=True, exist_ok=True)
    np.save(a.out_npy, sm)

    print(f"\n背景可见像素上的 MAE:")
    print(f"  网格采样  mean {np.mean(maes):.2f}  max {np.max(maes):.2f}")
    print(f"  纯色常量  mean {np.mean(flats):.2f}  max {np.max(flats):.2f}")
    print(f"  → 网格相对纯色提升 {(np.mean(flats) / max(np.mean(maes), 1e-6)):.1f}x")
    print("\n每 25 帧 (网格/纯色):",
          " ".join(f"{maes[t]:.2f}/{flats[t]:.2f}" for t in range(0, T, 25)))

    rep = {"frames": T, "size": [W, H], "grid": [a.gx, a.gy],
           "bg_lum": a.bg_lum, "smooth": a.smooth,
           "mae_grid": {"mean": round(float(np.mean(maes)), 3),
                        "max": round(float(np.max(maes)), 3)},
           "mae_flat": {"mean": round(float(np.mean(flats)), 3),
                        "max": round(float(np.max(flats)), 3)},
           "per_frame_mae_grid": [round(v, 3) for v in maes]}
    Path(a.out_json).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"\n已存 {a.out_npy} 和 {a.out_json}")
    print("下一步: 把 npy 里每帧的网格上采样成 PNG，再由 Remotion 逐帧引用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
