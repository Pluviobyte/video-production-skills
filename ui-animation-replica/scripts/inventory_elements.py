"""逐元素清单：找出画面里的可复刻元素，逐个给出 code / crop 决策。

核心规则（code-first, crop-last）：
  不问"这一段能不能复刻"，只问"这一个元素能不能用代码表达"。
    能用代码 → 代码画（文字、UI 边框、形状、图标、光标、渐变、运动）
    不能     → 从原片裁剪位图（logo、吉祥物、真人照片）

踩坑记录（为什么必须排除背景）：
  不排除背景时，检测器会把整幅画面当成一个元素
  （实测输出 [0,0,1920,1080] 占 51%，毫无用处）。
  正确做法：先识别背景色（画面边缘区域的主色），再只找"非背景"的连通块。

踩坑记录（为什么按元素而非按段判断）：
  看到"实拍真人"就把整段判为不可复刻，放弃了 5.67 秒。
  按 code-first 应该只放弃"真人"这个元素，同段的胶囊输入框仍应复刻。

用法：
  python inventory_elements.py --video src.mp4 --out inventory.json
  python inventory_elements.py --video src.mp4 --out inventory.json --times 1 3 5 7
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def find_flat_regions(bgr: np.ndarray, min_area_pct: float = 0.4,
                      tol: int = 2, exclude_background: bool = True) -> list[dict]:
    """找画面里的前景元素（UI 按钮、卡片、图标、遮罩）。"""
    h, w = bgr.shape[:2]
    if exclude_background:
        # 背景色 = 四条边框区域的主色（画面边缘通常是背景）
        edge = np.concatenate([
            bgr[:12].reshape(-1, 3), bgr[-12:].reshape(-1, 3),
            bgr[:, :12].reshape(-1, 3), bgr[:, -12:].reshape(-1, 3)])
        eq = (edge // 12).astype(np.int32)
        u, c = np.unique(eq, axis=0, return_counts=True)
        bg_q = u[int(np.argmax(c))]
        dist = np.abs((bgr // 12).astype(np.int32) - bg_q[None, None, :]).sum(axis=2)
        fg_mask = (dist > tol).astype(np.uint8) * 255
    else:
        fg_mask = np.full((h, w), 255, np.uint8)

    q = (bgr // 12).astype(np.int32)
    q[fg_mask == 0] = -1                      # 背景像素排除
    flat = q.reshape(-1, 3)
    valid = flat[:, 0] >= 0
    if not valid.any():
        return []
    uniq, inv, cnt = np.unique(flat[valid], axis=0,
                               return_inverse=True, return_counts=True)
    full_inv = np.full(len(flat), -1, np.int32)
    full_inv[valid] = inv
    inv = full_inv
    order = np.argsort(-cnt)

    out: list[dict] = []
    min_area = h * w * min_area_pct / 100.0
    for k in order[:6]:                       # 只看前 6 种主色
        if cnt[k] < min_area:
            break
        mask = (inv == k).reshape(h, w).astype(np.uint8) * 255
        mask[fg_mask == 0] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
        nl, lbl = cv2.connectedComponents(mask)
        for i in range(1, nl):
            comp = lbl == i
            a = int(comp.sum())
            if a < min_area:
                continue
            ys, xs = np.nonzero(comp)
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            bw, bh = int(x1 - x0 + 1), int(y1 - y0 + 1)
            col = bgr[comp].mean(axis=0)
            fill = a / max(1, bw * bh)
            ar = bw / max(1, bh)
            if fill > 0.82 and ar > 2.6:
                kind = "rect"                  # 胶囊/长条按钮
            elif fill > 0.82 and 0.6 < ar < 1.7:
                kind = "rect"                  # 方卡片
            elif 0.35 < fill <= 0.82:
                kind = "shape"                 # 不规则图形/图标
            else:
                kind = "region"
            out.append({
                "bbox": [int(x0), int(y0), bw, bh],
                "area_px": a, "area_pct": round(a / (h * w) * 100, 2),
                "bgr": [int(v) for v in col],
                "hex": "#%02x%02x%02x" % (int(col[2]), int(col[1]), int(col[0])),
                "fill": round(float(fill), 3), "aspect": round(float(ar), 2),
                "kind": kind,
            })

    # 去重（重叠的大块只留最大的）
    out.sort(key=lambda d: -d["area_px"])
    kept: list[dict] = []
    for d in out:
        x0, y0, w0, h0 = d["bbox"]
        dup = False
        for e in kept:
            x1, y1, w1, h1 = e["bbox"]
            ix = max(0, min(x0 + w0, x1 + w1) - max(x0, x1))
            iy = max(0, min(y0 + h0, y1 + h1) - max(y0, y1))
            if ix * iy > 0.6 * min(w0 * h0, w1 * h1):
                dup = True
                break
        if not dup:
            kept.append(d)
    return kept


def decide(d: dict) -> dict:
    """对单个元素给出复刻决策（code-first 规则）。"""
    kind = d["kind"]
    if kind in ("rect", "shape", "region"):
        how = {
            "rect": "CSS/SVG 圆角矩形或胶囊（border-radius）",
            "shape": "SVG 路径（按轮廓采样）",
            "region": "CSS 渐变或纯色块",
        }[kind]
        return {"method": "code", "how": how,
                "reason": f"{kind}，纯色区可精确参数化"}
    return {"method": "crop", "how": "从原片裁剪为透明 PNG（border flood-fill）",
            "reason": "边界复杂/含位图内容，裁剪保真度更高"}


def inventory(video: str, times: list[float] | None) -> dict:
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"打不开视频: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = total / fps
    if not times:
        step = max(0.5, dur / 12)
        times = [round(step * (i + 0.5), 2) for i in range(12)]

    per_time = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, fr = cap.read()
        if not ok:
            continue
        regs = find_flat_regions(fr)
        for r in regs:
            r["decision"] = decide(r)
        per_time.append({"t": round(t, 2), "regions": regs})
    cap.release()

    shapes: Counter = Counter()
    for p in per_time:
        for r in p["regions"]:
            if r["area_pct"] > 3:
                shapes[(r["kind"], r["hex"])] += 1

    n_code = sum(1 for p in per_time for r in p["regions"]
                 if r["decision"]["method"] == "code")
    n_crop = sum(1 for p in per_time for r in p["regions"]
                 if r["decision"]["method"] == "crop")

    return {"video": str(video), "duration": round(dur, 2),
            "fps": round(fps, 3), "sampled_times": times,
            "per_time": per_time,
            "tally": {"code": n_code, "crop": n_crop},
            "recurring": [{"kind": k[0], "hex": k[1], "count": v}
                          for k, v in shapes.most_common(10)]}



def _utf8_stdout() -> None:
    """Windows 控制台默认 CP936，中文输出会乱码；强制 UTF-8。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="逐元素 code/crop 决策（code-first, crop-last）")
    p.add_argument("--video", required=True, help="原始视频路径")
    p.add_argument("--out", default="element_inventory.json",
                   help="输出 JSON 路径")
    p.add_argument("--times", type=float, nargs="*", default=None,
                   help="指定采样时间点（秒）；省略则自动均匀取 12 个")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    a = parse_args(argv)
    res = inventory(a.video, a.times)

    print(f"视频 {res['duration']}s   采样 {len(res['per_time'])} 个时间点")
    print(f"\n反复出现的元素形态（出现 ≥2 次说明是持久 UI）:")
    for r in res["recurring"]:
        if r["count"] >= 2:
            print(f"  {r['kind']:<8} {r['hex']}  出现 {r['count']} 次")
    print(f"\n各时间点的元素清单（只列面积 >3% 的）:")
    for p in res["per_time"]:
        big = [r for r in p["regions"] if r["area_pct"] > 3]
        if not big:
            continue
        print(f"\n  t={p['t']}s:")
        for r in big[:5]:
            print(f"    {r['kind']:<7} {r['hex']}  {r['bbox']}  "
                  f"{r['area_pct']}%  → {r['decision']['method']}")

    t = res["tally"]
    print(f"\n决策统计: code {t['code']} 个 / crop {t['crop']} 个")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"\n已存 {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
