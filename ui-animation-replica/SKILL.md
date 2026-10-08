---
name: ui-animation-replica
description: >
  Replicate a UI/product promo video into a code-first Remotion composition
  aligned to the reference. Use when the user asks to "复刻这个视频",
  "还原这个动效", "照着这个 UI 动画做一个", "这个宣传片能用代码做吗",
  or wants a UI animation, toggle, card carousel, label list, or product
  demo video rebuilt from a reference MP4 with measured geometry instead of
  eyeballed values. Covers frame classification, shot segmentation,
  per-element code/crop decisions, subpixel measurement, camera-track
  fitting, five-dimension scoring, and jitter diagnosis. Do not use for
  style-level creation from a brief (use dark-saas-magic-video) or for
  QC of an already-built replica (use reference-video-replica-qc).
---

# UI Animation Replica

## Role

Turn a reference UI/product animation video into a code-first Remotion
composition whose geometry is measured from the source frames, not guessed.
Every moving element gets a measurement, every change gets a score, and any
visual shakiness gets traced to a specific CSS/SVG construct.

Read [replica-method.md](references/replica-method.md) before starting.
It defines the eight-step pipeline and the rules behind each decision point.

## Canonical Showcase

- Human display name: UI 开关 + 卡片轮播复刻成片
- Reference: 9.2s UI animation promo, 736x414, 25fps, 230 frames
- Result: three shots (toggle opening, card carousel with label highlights,
  ending 3D push), fully code-rendered except photo plates
- The whole composition renders from measured per-frame arrays; no element
  position is hand-tuned by eye

## Operating Modes

- **Full replica**: reference in, aligned MP4 out. Run steps 1-8 in order.
- **Measurement-only**: produce the classification, segmentation, inventory,
  and camera tracks; stop before building components.
- **Repair loop**: an existing replica is misaligned or shaky. Start at
  step 7 (jitter diagnosis) or step 6 (scoring), not at step 1.

## Prerequisites

```bash
pip install opencv-python numpy
pip install scenedetect[opencv]   # optional, enables hard-cut detection
```

`ffmpeg` / `ffprobe` on PATH. Remotion available via `npx remotion`.

## Workflow

### 1. Lock The Spec And Extract Frames

Probe width, height, fps, duration, and total frames. Extract every frame as
lossless PNG and measure from **that batch only** — never re-read the video,
because decoder differences corrupt comparisons.

```bash
ffprobe -v quiet -print_format json -show_streams "<video>"
ffmpeg -i "<video>" -start_number 1 "<out>/frames/full_%04d.png"
```

**Complete when:** frame count matches `round(fps x duration)` and the first
and last frames are visually the intended start/end.

### 2. Classify Frames

```bash
python scripts/classify_frames.py --video "<video>" --out "<out>/classify.json"
```

Four criteria decide `graphic` / `live` / `mixed` per sampled frame: flat-color
ratio, **skin ratio**, edge density, and edge-direction entropy.

The skin criterion is not optional. An earlier version omitted it and
classified 86% of a pure-UI video as live footage. Criterion choice matters
far more than threshold tuning.

**Decision gate:** graphic share >= 80% → code-first for all elements.
Otherwise → crop bitmaps **per element**, never per shot.

**Complete when:** the reported timeline matches what you see when you scrub
the video, and any `live`/`mixed` stretch is confirmed by eye on one frame.

### 3. Segment Shots

```bash
python scripts/segment_shots.py --video "<video>" --out "<out>/segments.json"
```

Applies hard-cut detection, then frame-difference fallback for long segments,
then merges sub-1.2s fragments, then pads 0.5s on each side.

**Known failure boundary:** gradient-only or continuous one-take videos yield
0-1 cut points from every detector. The script says so explicitly. In that
case treat the video as one segment or place cut points by hand.

**Complete when:** each segment boundary corresponds to a real visual change,
verified on the boundary frame.

### 4. Build The Element Inventory

```bash
python scripts/inventory_elements.py --video "<video>" --out "<out>/inventory.json"
```

The core rule is **code-first, crop-last**: do not ask "can this shot be
replicated", ask "can *this element* be expressed in code".

- code → text, UI borders, shapes, icons, cursors, gradients, motion
- crop → logos, mascots, real-people photos, textures

Background must be excluded before connected-component search, or the whole
frame registers as one element.

**Complete when:** every element above 3% area has a code/crop decision and
the recurring elements (appearing 2+ times) are all accounted for.

### 5. Measure Each Element

Measure only what needs code. Two generic tools cover the common cases:

**Background** — never model a gradient, sample it per frame:

```bash
python scripts/measure_background.py --frames "<out>/frames/" \
    --out-npy "<out>/bg.npy" --out-json "<out>/bg.json"
```

A fitted gradient model scored MAE 45; per-frame grid sampling scored 1.8.
That is a 26x difference, and it is why this step is not optional.

**Camera track** — fit `screen = diag(s,s) . layout + (tx,ty)` from subpixel
intensity centroids:

```bash
python scripts/fit_camera_track.py --frames "<out>/frames/" \
    --roi <x0> <x1> <y0> <y1> --ref-frame <n> --bands <k> \
    --tx-only <indices that stay static> --out "<out>/camera.json"
```

Threshold-based integer edges carry about 1px of quantization noise
(measured ty acceleration RMS 0.84 versus 0.027 in the source) and that noise
*is* the visible shakiness. Centroids are one order of magnitude cleaner.

For `tx`, use only elements that stay strictly static. An element mid
transition has changing letter-spacing and indent, so its centroid moves for
reasons unrelated to camera panning.

**Measurement must be cross-validated.** Four of six measurement methods used
in practice produced systematic errors: saturation-threshold masks halved a
radius, arithmetic averaging of angles invented a constant 44.75 degrees,
fixed-threshold luminance profiles flipped light/dark polarity, and
fixed-coordinate scanning walked off-screen once the subject moved (that
mistake was made three times). Validate any new measurement on a frame whose
answer you already know.

**Complete when:** each measurement has been re-run against at least one
frame with a known value, and the fitted track's acceleration RMS is near the
source's.

### 6. Build The Remotion Skeleton

Create `SPEC = { width, height, fps, durationInFrames }` from step 1, then
render the background, then add one component per code element.

Before writing any moving element, read
[remotion-pitfalls.md](references/remotion-pitfalls.md). The short version:
slow-moving elements **must** be HTML with `transform: translate(...)` and
`willChange: "transform"` **on the same DOM node**. SVG `<text>`, SVG
`<g transform>`, and CSS `left`/`top` all snap to whole pixels and will
produce visible jitter.

Cards must export both `cardXBox(frame)` — the visible clip box covering
entry, rest, and exit — and `CardX({ frame })` rendering in the card's own
rest coordinates.

**Complete when:** a still render at one known frame matches the source frame
and no element relies on `left`/`top` for motion.

### 7. Score And Diagnose

```bash
python scripts/score_dimensions.py --orig "<out>/frames/" \
    --render "<out>/render_vN/" --out "<out>/score_vN.json"
```

Five dimensions: global tone, temporal alignment, static regions, dynamic
regions, edge sharpness. Each returns a verdict naming what to change.

Treat the score as the only judge. Four rounds of "this looks better" edits
all made things worse (frame 147: 28.5 → 89.3 → 86.6). Re-run the full
sequence after every change; never judge from a single frame.

If the user reports visible shakiness:

```bash
python scripts/diagnose_jitter.py --orig "<out>/frames/" \
    --render "<out>/render_vN/" --out "<out>/jitter.json"
```

This compares frame-to-frame acceleration RMS between source and render.
Single-frame MAE cannot detect jitter — it only asks "does this frame look
right", while jitter is unevenness *between* frames.

**Complete when:** flagged elements are zero, or every remaining flag has a
written explanation.

### 8. Render And Re-Verify

```bash
npx remotion render <composition> --output="<out>/ui_replica.mp4"
ffmpeg -i "<out>/ui_replica.mp4" -i "<video>" \
    -map 0:v -map 1:a -c copy -shortest "<out>/ui_replica_with_audio.mp4"
```

Then score the encoded file again at `--every 1`. Encoding introduces color
shift, so the pre-encode score is not the deliverable's score.

**Complete when:** the encoded MP4's score is reported and the jitter check
passes on the decoded file, not the render frames.

## Hard Rules

1. **Never guess a model when you can sample.** Gradient models scored 26x
   worse than per-frame sampling.
2. **Validate the measurement method itself.** Prefer two independent methods
   agreeing over one method tuned until it looks right.
3. **The full-sequence score is the only judge.** Single frames and
   impressions are not evidence.
4. **Layer-stripping beats parameter tuning.** Rendering "background only"
   once overturned several rounds of assumptions and pointed at the real
   root cause. When unsure what to suspect, strip layers.
5. **Human frame check is mandatory before any model conclusion enters
   production.** VLM output misjudges confidently; treat it as a hint and
   verify key points with a script.

## Known Failure Boundaries

| Stage | How it fails | Handling |
| --- | --- | --- |
| Classification | Motion-blurred shots and heavy-texture UI | Verify suspect frames by eye |
| Segmentation | Continuous one-take, gradient-only | Frame-difference fallback; state the limit |
| Dimension scoring | Depends on frame alignment; a one-frame offset worsens every dimension at once | Fix temporal alignment first |
| VLM judgment | Misreads 3D/2D and timestamps | Always verify against a frame |
| Measurement | Fixed-coordinate scanning misses moved subjects | Re-derive the ROI per segment |

## Files

| File | Purpose |
| --- | --- |
| `scripts/classify_frames.py` | Per-frame graphic/live/mixed classification |
| `scripts/segment_shots.py` | Shot segmentation with fallbacks |
| `scripts/inventory_elements.py` | Per-element code/crop decisions |
| `scripts/measure_background.py` | Per-frame background grid sampling |
| `scripts/fit_camera_track.py` | Subpixel camera track fitting |
| `scripts/score_dimensions.py` | Five-dimension scoring with diagnostics |
| `scripts/diagnose_jitter.py` | Frame-to-frame jitter diagnosis |
| `references/replica-method.md` | The full eight-step pipeline and its rationale |
| `references/remotion-pitfalls.md` | Rendering constructs that cause jitter, and the fixes |
| `references/measurement-contract.md` | Measurement validation and cross-check protocol |
| `references/scoring-rubric.md` | How to read the five dimensions and act on them |
