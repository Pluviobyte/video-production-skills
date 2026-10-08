"""五维度打分：把一个 MAE 数字拆成"差在哪、去改什么"。

为什么必须拆（实测教训）：
  单一 MAE 会说"平均 2.10"，但说不出是整体偏色、元素位置错、还是时序错一帧。
  - 星形其实在旋转，MAE 只报"片尾差了 25"，猜了 4 轮才找到原因
  - 时序整体晚一帧时 MAE 从 2.47 涨到 3.32，但看不出是"时序"问题

五个维度：
  1. 全局色调   —— 平均色/亮度偏差（整体偏色）
  2. 时序对齐   —— 最佳匹配偏移几帧（晚了还是早了）
  3. 静态区域   —— 不动的部分差多少（形状/位置/颜色有系统偏差）
  4. 动态区域   —— 变化的部分差多少（动效/缓动不匹配）
  5. 边缘锐度   —— 过渡带梯度对比（糊了还是过锐）

失效边界：本打分依赖帧对齐。偏移一帧会让所有维度同时变差 ——
看到"所有维度一起变差"时，先检查时序对齐，不要逐维调参。

用法：
  python score_dimensions.py --orig frames/ --render render_v1/ --out score.json
  python score_dimensions.py --orig frames/ --render render_v1/ --every 1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def _load(p: str | Path) -> np.ndarray | None:
    img = cv2.imread(str(p))
    return None if img is None else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())


def dim_global_tone(o: np.ndarray, r: np.ndarray) -> dict:
    """维度1：全局色调。整幅的色偏与亮度偏。"""
    om = o.reshape(-1, 3).mean(axis=0)
    rm = r.reshape(-1, 3).mean(axis=0)
    d = rm - om
    lum_o = float(0.299 * om[0] + 0.587 * om[1] + 0.114 * om[2])
    lum_r = float(0.299 * rm[0] + 0.587 * rm[1] + 0.114 * rm[2])
    verdict = "正常"
    if abs(lum_r - lum_o) > 6:
        verdict = f"整体偏{'亮' if lum_r > lum_o else '暗'} {abs(lum_r - lum_o):.1f}"
    elif np.abs(d).max() > 6:
        j = int(np.argmax(np.abs(d)))
        verdict = f"整体偏{['R', 'G', 'B'][j]} {d[j]:+.1f}"
    return {"delta_rgb": [round(float(x), 2) for x in d],
            "delta_lum": round(lum_r - lum_o, 2),
            "verdict": verdict}


def dim_temporal(neighbors: list[np.ndarray], r: np.ndarray,
                 radius: int = 3, thresh: float = 0.8) -> dict:
    """维度2：时序对齐。用相邻原片帧做匹配，看是否偏移。"""
    scores = [_mae(o, r) for o in neighbors]
    best = int(np.argmin(scores))
    off = best - radius
    same = scores[radius]
    lead = same - scores[best]
    verdict = "对齐正确"
    if off != 0 and lead > thresh:
        verdict = (f"整体{'晚' if off < 0 else '早'} {abs(off)} 帧"
                   f"（需{'提前' if off < 0 else '延后'}）")
    return {"best_offset": off, "mae_at_best": round(scores[best], 3),
            "mae_at_zero": round(same, 3), "lead": round(lead, 3),
            "profile": [round(s, 3) for s in scores], "verdict": verdict}


def dim_static_dynamic(o_pair, r_pair) -> dict:
    """维度3/4：静态 vs 动态区域。

    用相邻帧的"原片差异图"划分：原片里变化小的区域=静态，变化大的=动态。
    """
    o1, o2 = o_pair
    r1, r2 = r_pair
    if o1.shape != o2.shape:
        return {"static_mae": None, "dynamic_mae": None,
                "static_px_pct": None, "verdict": "尺寸不一致"}
    motion = np.abs(o1.astype(np.int16) - o2.astype(np.int16)).mean(axis=2)
    thr = float(np.percentile(motion, 75))
    dyn = motion >= thr
    sta = ~dyn
    d = np.abs(o1.astype(np.int16) - r1.astype(np.int16)).mean(axis=2)
    smae = float(d[sta].mean()) if sta.sum() else 0.0
    dmae = float(d[dyn].mean()) if dyn.sum() else 0.0
    notes = []
    if smae > dmae * 1.5 and smae > 3:
        notes.append("静态区更差 → 形状/位置/颜色有系统偏差")
    if dmae > smae * 1.5 and dmae > 3:
        notes.append("动态区更差 → 动效/缓动不匹配")
    return {"static_mae": round(smae, 2), "dynamic_mae": round(dmae, 2),
            "static_px_pct": round(float(sta.mean() * 100), 1),
            "verdict": "；".join(notes) or "两区相当"}


def dim_edge_sharpness(o: np.ndarray, r: np.ndarray,
                       band_pct: float = 0.02) -> dict:
    """维度5：边缘锐度。取原片梯度最强的一批像素，比较同位置复刻的梯度。"""
    go = cv2.cvtColor(o, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gr = cv2.cvtColor(r, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mo = np.hypot(cv2.Sobel(go, cv2.CV_32F, 1, 0), cv2.Sobel(go, cv2.CV_32F, 0, 1))
    mr = np.hypot(cv2.Sobel(gr, cv2.CV_32F, 1, 0), cv2.Sobel(gr, cv2.CV_32F, 0, 1))
    thr = float(np.percentile(mo, 100 * (1 - band_pct)))
    sel = mo >= thr
    if sel.sum() < 20:
        return {"edge_grad_o": None, "edge_grad_r": None,
                "ratio": None, "verdict": "无明显边缘"}
    eo, er = float(mo[sel].mean()), float(mr[sel].mean())
    ratio = er / max(eo, 1e-6)
    verdict = "锐度相当"
    if ratio < 0.65:
        verdict = f"复刻偏糊（锐度仅原片 {ratio * 100:.0f}%）"
    elif ratio > 1.5:
        verdict = f"复刻过锐（{ratio * 100:.0f}%）"
    return {"edge_grad_o": round(eo, 1), "edge_grad_r": round(er, 1),
            "ratio": round(ratio, 3), "verdict": verdict}


def score_pair(o, r, neighbors=None, o_next=None, r_next=None) -> dict:
    if o.shape != r.shape:
        r = cv2.resize(r, (o.shape[1], o.shape[0]))
    out = {"mae": round(_mae(o, r), 3), "tone": dim_global_tone(o, r)}
    if neighbors:
        out["temporal"] = dim_temporal(neighbors, r)
    if o_next is not None and r_next is not None:
        if r_next.shape != o_next.shape:
            r_next = cv2.resize(r_next, (o_next.shape[1], o_next.shape[0]))
        out["static_dynamic"] = dim_static_dynamic((o, o_next), (r, r_next))
    out["edge"] = dim_edge_sharpness(o, r)
    return out


def score_video(orig_frames: list[Path], repl_frames: list[Path],
                sample_every: int = 3, radius: int = 3) -> dict:
    n = min(len(orig_frames), len(repl_frames))
    if n == 0:
        return {"error": "无可比较帧"}
    per_frame = []
    for i in range(0, n, sample_every):
        o = _load(orig_frames[i])
        r = _load(repl_frames[i])
        if o is None or r is None:
            continue
        nbrs = []
        for off in range(-radius, radius + 1):
            j = i + off
            a = _load(orig_frames[j]) if 0 <= j < n else None
            nbrs.append(a if a is not None else o)
        o_next = _load(orig_frames[min(i + radius, n - 1)])
        r_next = _load(repl_frames[min(i + radius, n - 1)])
        s = score_pair(o, r, nbrs, o_next, r_next)
        s["frame"] = i + 1
        per_frame.append(s)

    if not per_frame:
        return {"error": "无可比较帧"}

    maes = np.array([p["mae"] for p in per_frame])
    tones = np.array([abs(p["tone"]["delta_lum"]) for p in per_frame])
    offs = [p["temporal"]["best_offset"] for p in per_frame if "temporal" in p]
    smae = np.array([p["static_dynamic"]["static_mae"] for p in per_frame
                     if p.get("static_dynamic", {}).get("static_mae") is not None])
    dmae = np.array([p["static_dynamic"]["dynamic_mae"] for p in per_frame
                     if p.get("static_dynamic", {}).get("dynamic_mae") is not None])
    ratios = np.array([p["edge"]["ratio"] for p in per_frame
                       if p["edge"].get("ratio") is not None])

    overall = max(0.0, 100.0 - float(maes.mean()) * 4.0)

    c = Counter(offs)
    dom_off, dom_n = c.most_common(1)[0] if offs else (0, 0)
    issues: list[str] = []
    if float(np.mean(tones)) > 5:
        issues.append(f"整体色调偏差 {np.mean(tones):.1f}（检查背景色/滤镜）")
    if dom_off != 0 and dom_n > len(offs) * 0.5:
        issues.append(f"{dom_n}/{len(offs)} 帧时序偏移 {dom_off:+d}"
                      "（先调整整体时间偏移，再谈其他维度）")
    if len(smae) and len(dmae):
        if smae.mean() > dmae.mean() * 1.5 and smae.mean() > 3:
            issues.append(f"静态区误差 {smae.mean():.1f} > 动态区 {dmae.mean():.1f}"
                          "（形状/位置/颜色）")
        if dmae.mean() > smae.mean() * 1.5 and dmae.mean() > 3:
            issues.append(f"动态区误差 {dmae.mean():.1f} > 静态区 {smae.mean():.1f}"
                          "（动效/缓动）")
    if len(ratios) and ratios.mean() < 0.7:
        issues.append(f"边缘偏糊（锐度 {ratios.mean() * 100:.0f}%），"
                      "检查渲染/编码或形状精度")
    if not issues:
        issues.append("各维度均在阈值内")

    return {
        "overall_score": round(overall, 1),
        "mae_mean": round(float(maes.mean()), 3),
        "mae_max": round(float(maes.max()), 3),
        "frames_scored": len(per_frame),
        "dimensions": {
            "tone_delta_lum_mean": round(float(np.mean(tones)), 2),
            "temporal_offset_mode": int(dom_off),
            "temporal_misaligned_pct": round(
                sum(1 for o in offs if o != 0) / max(1, len(offs)) * 100, 1),
            "static_mae_mean": round(float(smae.mean()), 2) if len(smae) else None,
            "dynamic_mae_mean": round(float(dmae.mean()), 2) if len(dmae) else None,
            "edge_sharpness_ratio": round(float(ratios.mean()), 3) if len(ratios) else None,
        },
        "issues": issues,
        "worst_frames": [
            {"frame": p["frame"], "mae": p["mae"],
             "tone": p["tone"]["verdict"],
             "temporal": p.get("temporal", {}).get("verdict"),
             "edge": p["edge"]["verdict"]}
            for p in sorted(per_frame, key=lambda q: -q["mae"])[:5]],
        "per_frame": per_frame,
    }



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="五维度打分：说清差在哪、去改什么")
    p.add_argument("--orig", required=True, help="原片帧目录（或单个 PNG/MP4 目录）")
    p.add_argument("--render", required=True, help="复刻帧目录（或单个 PNG/MP4 目录）")
    p.add_argument("--out", default="dim_score.json", help="输出 JSON 路径")
    p.add_argument("--every", type=int, default=3,
                   help="每 N 帧采样一次（默认 3；编码后验收建议 1）")
    p.add_argument("--radius", type=int, default=3,
                   help="时序匹配半径帧数（默认 3）")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    od, rd = Path(a.orig), Path(a.render)
    of = sorted(od.glob("*.png"))
    rf = sorted(rd.glob("*.png"))
    if not of or not rf:
        raise SystemExit(f"帧不足: {od}={len(of)}  {rd}={len(rf)}")

    res = score_video(of, rf, a.every, a.radius)
    if "error" in res:
        raise SystemExit(res["error"])

    print(f"综合分 {res['overall_score']}/100   "
          f"MAE 平均 {res['mae_mean']} 最大 {res['mae_max']}  "
          f"({res['frames_scored']} 帧)")
    print("\n五维度:")
    for k, v in res["dimensions"].items():
        print(f"  {k:<28} {v}")
    print("\n诊断建议:")
    for i in res["issues"]:
        print(f"  · {i}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
