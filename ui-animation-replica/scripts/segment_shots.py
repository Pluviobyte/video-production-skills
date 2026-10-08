"""镜头分段：硬切 + 帧间色差兜底 + 过短合并 + 前后补足。

四条规则：
  1. 硬切：ContentDetector 在原生帧率下检测（需 scenedetect，缺失则跳过）
  2. 超长段：> MAX_LEN 秒的段，用帧间色差找变化点再切 —— 一镜到底的兜底
  3. 过短段：< MIN_LEN 秒的段向相邻合并，防快闪误判
  4. 前后各补 PAD 秒：转场常跨在两段之间

失效边界：纯渐变、一镜到底的视频，三种镜头检测器都只给 0~1 个切点。
这时只能靠帧间色差兜底 —— 本脚本会明确报告"沿用整段"。

用法：
  python segment_shots.py --video src.mp4 --out segments.json
  python segment_shots.py --video src.mp4 --out segments.json --max-len 6
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

MIN_LEN = 1.2      # 短于此合并
MAX_LEN = 8.0      # 长于此再切
PAD = 0.5          # 前后补足


def probe(video: str) -> tuple[float, float, int]:
    """返回 (总时长秒, fps, 帧数)。"""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"打不开视频: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n / fps, fps, n


def detect_hard_cuts(video: str) -> tuple[list[tuple[float, float]], float, float]:
    """原生帧率下的硬切检测。scenedetect 缺失时返回单段。"""
    total, fps, _ = probe(video)
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector
    except ImportError:
        print("提示: 未安装 scenedetect，跳过硬切检测，改用帧间色差兜底。")
        print("      安装: pip install scenedetect[opencv]")
        return [(0.0, total)], total, fps

    v = open_video(video)
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=18))
    sm.detect_scenes(v)
    scenes = [(a.get_seconds(), b.get_seconds()) for a, b in sm.get_scene_list()]

    # 兜底：修正超过总时长的边界
    fixed: list[tuple[float, float]] = []
    for a, b in scenes:
        a = max(0.0, min(a, total))
        b = max(0.0, min(b, total))
        if b - a > 0.05:
            fixed.append((a, b))
    if not fixed or fixed[0][0] > 0.05:
        fixed.insert(0, (0.0, fixed[0][0] if fixed else total))
    if fixed and fixed[-1][1] < total - 0.05:
        fixed.append((fixed[-1][1], total))
    return fixed, total, fps


def frame_diffs(video: str, fps: float, thresh_pct: float = 96.0,
                quiet: float = 0.6) -> list[float]:
    """逐帧色差（降采样提速），返回剧变时刻的秒数。"""
    cap = cv2.VideoCapture(video)
    prev = None
    diffs: list[tuple[float, float]] = []
    idx = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        small = cv2.resize(fr, (160, 90),
                           interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev is not None:
            diffs.append((idx / fps, float(np.abs(small - prev).mean())))
        prev = small
        idx += 1
    cap.release()
    if not diffs:
        return []

    vals = np.array([d for _, d in diffs])
    thr = np.percentile(vals, thresh_pct)
    peaks: list[float] = []
    for i in range(1, len(diffs) - 1):
        t, d = diffs[i]
        if d >= thr and d >= diffs[i - 1][1] and d >= diffs[i + 1][1]:
            if not peaks or t - peaks[-1] > quiet:
                peaks.append(t)
    return peaks


def merge_short(segs: list[tuple[float, float]], min_len: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in segs:
        if out and (b - a) < min_len:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    merged: list[tuple[float, float]] = []
    for s in out:
        if merged and (s[1] - s[0]) < min_len:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(s)
    return merged


def split_long(segs: list[tuple[float, float]], peaks: list[float],
               max_len: float, min_len: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in segs:
        if b - a <= max_len:
            out.append((a, b))
            continue
        cands = [t for t in peaks if a + min_len < t < b - min_len]
        cur = a
        while b - cur > max_len and cands:
            target = cur + max_len
            pick = min(cands, key=lambda t: abs(t - target))
            out.append((cur, pick))
            cands = [t for t in cands if t > pick]
            cur = pick
        out.append((cur, b))
    return out


def add_pad(segs: list[tuple[float, float]], total: float,
            pad: float) -> list[tuple[float, float]]:
    return [(max(0.0, a - pad), min(total, b + pad)) for a, b in segs]



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="镜头分段：硬切 + 色差兜底 + 合并 + 补足")
    p.add_argument("--video", required=True, help="原始视频路径")
    p.add_argument("--out", default="segments.json", help="输出 JSON 路径")
    p.add_argument("--min-len", type=float, default=MIN_LEN,
                   help=f"短于此秒数合并（默认 {MIN_LEN}）")
    p.add_argument("--max-len", type=float, default=MAX_LEN,
                   help=f"长于此秒数再切（默认 {MAX_LEN}）")
    p.add_argument("--pad", type=float, default=PAD,
                   help=f"前后补足秒数（默认 {PAD}）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)

    hard, total, fps = detect_hard_cuts(a.video)
    print(f"视频 {total:.2f}s @ {fps:.1f}fps")
    print(f"\n硬切检测: {len(hard)} 段")
    for i, (x, y) in enumerate(hard):
        print(f"  {i + 1:>2}. {x:>6.2f} - {y:>6.2f}s  ({y - x:>5.2f}s)")

    peaks = frame_diffs(a.video, fps)
    print(f"\n帧间色差剧变点 ({len(peaks)} 个): "
          + "  ".join(f"{t:.2f}s" for t in peaks[:25]))

    if len(hard) <= 1 and not peaks:
        print("\n警告: 没有检测到切点 —— 疑似纯渐变或一镜到底。"
              "本片只能作为单段处理，或在关键变化点手工指定切点。")

    m = merge_short(hard, a.min_len)
    print(f"\n合并过短段后: {len(m)} 段")
    s = split_long(m, peaks, a.max_len, a.min_len)
    print(f"细分超长段后: {len(s)} 段")
    p = add_pad(s, total, a.pad)
    print(f"补足转场余量后: {len(p)} 段\n")
    print(f"{'#':>3} {'开始':>7} {'结束':>7} {'时长':>6}")
    for i, (x, y) in enumerate(p):
        print(f"{i + 1:>3} {x:>7.2f} {y:>7.2f} {y - x:>6.2f}")

    res = {"video": str(a.video),
           "total": round(float(total), 3), "fps": round(float(fps), 3),
           "params": {"min_len": a.min_len, "max_len": a.max_len, "pad": a.pad},
           "hard_cuts": [[round(float(x), 3), round(float(y), 3)] for x, y in hard],
           "peaks": [round(float(t), 3) for t in peaks],
           "segments": [[round(float(x), 3), round(float(y), 3)] for x, y in p]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}（{len(p)} 段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
