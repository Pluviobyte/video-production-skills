"""逐帧元素分类：图形 / 实拍 / 混合。

用途：复刻前先判断每一帧的画面构成，决定走 code-first（CSS/SVG 画）还是
需要从原片裁剪位图。

判据（四个，缺一不可）：
  1. 纯色区占比   —— UI 界面有大片纯色背景
  2. 边缘密度     —— 文字/UI 边框是高频规整边缘
  3. 肤色占比     —— 真人（这是准确率的关键判据）
  4. 边缘方向熵   —— UI 边缘集中在水平/垂直，实拍杂乱

踩坑记录：早期版本没有肤色判据，把 86% 的画面判成实拍，全部错误。
加入肤色后准确率立刻可用 —— 判据的选择比阈值调优重要得多。

用法：
  python classify_frames.py --video src.mp4 --out classify.json
  python classify_frames.py --video src.mp4 --out classify.json --step 0.25
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def skin_ratio(bgr: np.ndarray) -> float:
    """肤色像素占比（YCbCr 阈值）。"""
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    m = ((ycc[:, :, 1] > 133) & (ycc[:, :, 1] < 180)
         & (ycc[:, :, 2] > 77) & (ycc[:, :, 2] < 130))
    return float(m.mean())


def flat_ratio(bgr: np.ndarray, quant: int = 16) -> float:
    """最大单一量化色的占比 —— UI 白底会很高。"""
    q = (bgr // quant).reshape(-1, 3)
    _, cnt = np.unique(q, axis=0, return_counts=True)
    return float(cnt.max() / len(q))


def edge_stats(bgr: np.ndarray) -> tuple[float, float]:
    """返回 (边缘密度, 边缘规整度)。

    UI/文字的边缘集中在水平/垂直方向；实拍的边缘方向杂乱。
    用 Sobel 方向直方图的熵衡量规整度：越低越规整。
    """
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, 92)
    sel = mag > thr
    if sel.sum() < 50:
        return 0.0, 0.0
    ang = (np.degrees(np.arctan2(gy[sel], gx[sel])) % 180).astype(np.int32)
    hist = np.bincount(ang // 10, minlength=18).astype(np.float64)
    hist /= hist.sum()
    ent = -np.sum(hist[hist > 0] * np.log2(hist[hist > 0]))
    return float(sel.mean()), float(ent)


def classify_frame(bgr: np.ndarray, *, flat_hi: float, skin_hi: float,
                   ent_hi: float) -> dict:
    """对单帧给出各判据与结论。"""
    small = cv2.resize(bgr, (480, 270), interpolation=cv2.INTER_AREA)
    flat = flat_ratio(small)
    skin = skin_ratio(small)
    dens, ent = edge_stats(small)

    # 默认阈值实测校准于 UI 宣传片样片：
    #   实拍真人：肤色 > 6% 且 纯色区 < 0.30
    #   UI/图形：纯色区 > 0.25 或（肤色低 且 边缘规整）
    is_live = (skin > skin_hi) and (flat < 0.30)
    is_graphic = (flat > flat_hi) or (skin < 0.02 and ent < ent_hi)

    if is_live and not is_graphic:
        kind = "live"
    elif is_graphic and not is_live:
        kind = "graphic"
    elif is_live and is_graphic:
        kind = "mixed"          # 实拍 + UI 叠层（最常见）
    else:
        kind = "unknown"

    return {"flat": round(flat, 3), "skin": round(skin, 4),
            "edge_density": round(dens, 3), "edge_entropy": round(ent, 3),
            "kind": kind}


def classify_video(video: str, step: float, **thr) -> dict:
    """逐帧分类整条视频，返回时间轴。"""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"打不开视频: {video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = total / src_fps
    stride = max(1, int(round(src_fps * step)))

    rows = []
    idx = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            r = classify_frame(fr, **thr)
            r["t"] = round(idx / src_fps, 3)
            rows.append(r)
        idx += 1
    cap.release()

    # 合并连续同类区间
    segs: list[dict] = []
    for r in rows:
        if segs and segs[-1]["kind"] == r["kind"]:
            segs[-1]["t_end"] = r["t"]
        else:
            segs.append({"kind": r["kind"], "t": r["t"], "t_end": r["t"]})
    for s in segs:
        s["dur"] = round(s["t_end"] - s["t"] + step, 2)

    tally: dict[str, int] = {}
    for r in rows:
        tally[r["kind"]] = tally.get(r["kind"], 0) + 1
    n = len(rows) or 1
    pct = {k: round(v / n * 100, 1) for k, v in tally.items()}

    return {"video": str(video), "duration": round(dur, 3),
            "fps": round(src_fps, 3), "sampled": len(rows), "step": step,
            "tally_pct": pct, "segments": segs, "frames": rows}



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="逐帧分类图形/实拍/混合，决定 code-first 还是裁图")
    p.add_argument("--video", required=True, help="原始视频路径")
    p.add_argument("--out", default="classify.json", help="输出 JSON 路径")
    p.add_argument("--step", type=float, default=0.5, help="采样间隔秒（默认 0.5）")
    p.add_argument("--flat-hi", type=float, default=0.25,
                   help="纯色区占比高于此判为图形（默认 0.25）")
    p.add_argument("--skin-hi", type=float, default=0.06,
                   help="肤色占比高于此判为实拍（默认 0.06）")
    p.add_argument("--ent-hi", type=float, default=3.1,
                   help="边缘方向熵低于此判为图形（默认 3.1）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    res = classify_video(a.video, a.step,
                         flat_hi=a.flat_hi, skin_hi=a.skin_hi, ent_hi=a.ent_hi)

    print(f"视频 {res['duration']}s @ {res['fps']}fps  "
          f"采样 {res['sampled']} 帧（每 {res['step']}s）")
    print(f"\n构成占比: {res['tally_pct']}")
    print("\n时间轴（合并同类）:")
    print(f"{'类型':<9} {'开始':>7} {'结束':>7} {'时长':>6}")
    for s in res["segments"]:
        if s["dur"] >= 0.5:
            print(f"{s['kind']:<9} {s['t']:>7.2f} {s['t_end']:>7.2f} {s['dur']:>6.2f}")

    graphic = res["tally_pct"].get("graphic", 0.0)
    print(f"\n决策: 图形占比 {graphic}% → "
          + ("走 code-first（全部代码画）" if graphic >= 80
             else "仅对实拍元素裁图，其余仍用代码"))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
