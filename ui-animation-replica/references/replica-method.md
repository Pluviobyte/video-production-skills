# Reference Video Replica Method

The pipeline behind `ui-animation-replica`. Each step exists because an
earlier, simpler approach failed in a measurable way.

## One-Line Summary

**Classify first, then segment, then decide per element; measure with code
instead of a model; score by dimension instead of one number.**

## Role Boundaries

| Role | Does | Does not |
| --- | --- | --- |
| Python / OpenCV | Precise measurement, per-frame scoring, pixel-level judgment | Understand semantics |
| VLM (optional) | Read structure, hear audio, say "this part looks off" | Make precise measurements |
| Remotion | Render | Decide geometry |

Measured VLM accuracy: it correctly identified three beeps at seconds 2/5/9
with the fifth loudest, and correctly located narration at 4.0-6.5s.
It also confidently reported a "downbeat at 32.5s" that measured *below*
average. Output is a lead, not a fact.

## Step 1-2: Spec And Frame Extraction

`ffprobe` reads the spec, `ffmpeg` writes every frame as lossless PNG. All
later measurement uses that batch. Re-reading the video risks decoder
differences that look like element movement.

## Step 3: Frame Classification

Per-frame `graphic` / `live` / `mixed`, from four criteria:

| Criterion | What it catches |
| --- | --- |
| Flat-color ratio | UI has large single-color areas |
| **Skin ratio** | **Real people cannot hide from it** |
| Edge density | Text and UI borders are high-frequency regular edges |
| Edge-direction entropy | UI edges cluster on horizontal/vertical; live footage is scattered |

On a test promo this produced 79% graphic / 18% live, matching a manual
frame-by-frame check.

**Failure record:** earlier versions omitted the skin criterion and classified
86% of the frames as live footage. Adding skin made it immediately usable.
Criterion selection matters far more than threshold tuning.

## Step 4: Shot Segmentation

| Rule | Purpose |
| --- | --- |
| Hard cuts split scenes | Works well for live footage and edited material |
| Segments over 8s split at frame-difference peaks | The fallback for continuous one-takes |
| Fragments under 1.2s merge | Prevents flash-frame false positives |
| Pad 0.5s on each side | Transitions often straddle two segments |

**Failure boundary:** for purely gradual or continuous one-take video, all
three cut detectors return 0-1 cut points (a gradient-only test video
returned zero). Only frame-difference fallback applies, and the script must
say so rather than silently emitting one segment.

## Step 5: Element Inventory

The single most important improvement over naive approaches. The rule comes
from the "code-first, crop-last" pattern: do not ask whether a *shot* can be
replicated, ask whether *one element* can be expressed in code.

```
expressible in code -> CSS/SVG (text, UI borders, shapes, icons, cursors,
                      gradients, motion)
not expressible     -> crop a bitmap from the source (logo, mascot,
                      real-person photo)
```

Implementation: identify the background color from the frame border, search
only non-background connected components, then classify geometrically into
`rect` (capsule/card), `shape` (icon), `region` (color block), each with a
stated way to draw it.

**Why this rule is strong (measured lesson):** on one shot the presence of a
real person led to declaring the whole segment unreplicable and dropping 5.67
seconds. Under code-first, only the *person* is dropped — the capsule input
field in the same shot should still be rebuilt, and it later was, just the
long way around.

**Failure record:** without background exclusion the detector reported the
entire frame `[0,0,1920,1080]` at 51% coverage, which is useless.

On a test promo: 42 elements, 100% recommended for code; 47.5s (80% of the
video) code-replicable with only 10s needing placeholders. The earlier
whole-shot judgment concluded "only a button is replicable" — an order of
magnitude off, because the method was wrong.

## Step 6: Export And Semantic Timeline

Rule borrowed from the SVML design: **anchor to words, not seconds**.

Writing absolute frame numbers means every upstream change (new asset,
different duration, new language) invalidates every timestamp. Instead each
element records a semantic anchor, and absolute time resolves from one cue
table:

```python
t.cue("capsule_appear", 1.67)                      # measured value
t.cue_after("exit_start", "capsule_appear", 3.16)  # relative, no repeated number
```

A global shift is then one call, `t.shift(seconds)`, and every relative
relationship holds. Export to `timeline.ts` for Remotion to query.

## Per-Element Measurement

Precision requirements differ per element class:

- **Background**: per-frame grid sampling. A fitted gradient model scored MAE
  45; grid sampling scored 1.8. The gap is 26x.
- **Moving UI elements**: per-frame subpixel centroids, then fit the group
  transform. See `measurement-contract.md` for the cross-validation protocol.
- **Camera track**: `screen = diag(sx,sy) . layout + (tx,ty)`. Opening shots
  are often *anisotropic* — sx and sy differ early and converge later — so a
  single uniform zoom is the wrong model.
- **Cards**: transitions are frequently non-rigid. A "best single offset"
  diagnostic may fit rigidly at the start of an entry and break down later.
  Each card should expose its own clip box per frame.

## Scoring

Single MAE cannot distinguish an overall color cast from a misplaced element
from a one-frame timing error. A rotating star once scored "end differs by
25" and took four guesses to diagnose. A global one-frame lag raised MAE from
2.47 to 3.32 while revealing nothing about timing.

Output five dimensions with actionable verdicts: global tone, temporal
alignment, static regions, dynamic regions, edge sharpness. See
`scoring-rubric.md`.

## Hard Rules

### 1. Never guess a model when you can sample

A fitted gradient model scored MAE 45; per-frame grid sampling scored 1.8.

### 2. The measurement method itself must be validated

Four of six methods used in practice produced systematic errors:

| Method | Error |
| --- | --- |
| Saturation-threshold mask | Radius measured half size (0.28 vs true 0.535) |
| Arithmetic mean of angles | Invented a spurious constant 44.75 degrees |
| Fixed-threshold luminance profile | Flipped light/dark polarity, measuring a different object |
| Fixed-coordinate scan | Walked off-screen after the subject moved (made 3 times) |

Only cross-validation across methods plus post-render MAE is reliable.

### 3. Full-sequence MAE is the only judge

Four impression-driven edits each made things worse (frame 147: 28.5 → 89.3
→ 86.6). Run the whole sequence after every change.

### 4. Layer-stripping beats continued tuning

Rendering "background only" once overturned every prior assumption and
pointed straight at the root cause. When you do not know what to suspect,
strip layers.

## Known Failure Boundaries

| Stage | How it fails |
| --- | --- |
| Classification | Strong motion blur misjudges (a corridor shot was); heavy-texture UI too |
| Segmentation | Continuous one-takes yield no cuts |
| VLM | Timestamps off by about 0.5s, some points misremembered |
| Dimension scoring | Depends on frame alignment; a one-frame offset degrades every dimension at once |
| VLM judgment | States wrong conclusions confidently (a third party measured three models all misjudging "becomes 3D after 7.5s" when it was 3D throughout) |

The last entry comes from a published field report whose conclusion matches
this one: **a human frame check must be a mandatory step before any model
conclusion enters production.**

## Sources

- [crafter-station/remotion-clone-video](https://github.com/crafter-station/remotion-clone-video) — code-first rule, eight-step flow, motion recipe library
- [hypit-ai/hypit](https://github.com/hypit-ai/hypit) — SVML semantic timing, 64-way concurrent rendering
- [mimic-mcp](https://lobehub.com/mcp/pouyashahrdami-mimic-mcp) — `review_render` dimension scoring
- [Alan-Lucena/Frameloop](https://github.com/Alan-Lucena/Frameloop) — motion parameter extraction (curve fitter usable; tracking architecture is not)
- [agent-swarm.dev field report](https://www.agent-swarm.dev/blog/linear-loops-video-replica) — VLM misjudgment and human verification
