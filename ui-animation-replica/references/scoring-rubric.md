# Scoring Rubric

How to read the five dimensions, what each failure means, and what to change.

## Why Five Dimensions

A single MAE number cannot distinguish an overall color cast from a misplaced
element from a one-frame timing error. Two measured examples:

- A star was actually rotating. MAE reported only "the ending differs by 25",
  and it took four rounds of guessing to find the cause.
- A global one-frame lag raised MAE from 2.47 to 3.32, with nothing in the
  number indicating the problem was timing.

Decomposing into dimensions turns each number into a specific repair.

## The Dimensions

### 1. Global tone

Mean color and luminance delta across the whole frame.

| Reading | Meaning | Action |
| --- | --- | --- |
| Luminance delta under ~5 | Normal | None |
| Luminance delta over ~6 | Overall too bright or dark | Check background color, filters, gamma |
| One channel over ~6 | Color cast | Check for a wrong color constant or a color-space mismatch |

### 2. Temporal alignment

For each frame, MAE against the source's neighboring frames, ±3 by default.
The offset with the lowest MAE is the best match.

| Reading | Meaning | Action |
| --- | --- | --- |
| offset 0 | Aligned | None |
| Consistent +1 or -1 across most frames | Global timing error | Shift the whole timeline; do not tune individual elements |
| Scattered offsets | Some elements move early or late | Fix per element, after the global shift is corrected |

**Critical interaction:** temporal misalignment degrades *every* dimension at
once. If all five look worse than expected, check alignment before touching
anything else.

### 3. Static regions

MAE restricted to regions the source leaves unchanged, identified as the
bottom 75% of frame-to-frame motion.

| Reading | Meaning | Action |
| --- | --- | --- |
| Static MAE ≤ dynamic MAE | Normal | None |
| Static MAE over ~3 and over 1.5x dynamic | Shape, position, or color is systematically wrong | Re-verify measurements; suspect a fixed-coordinate scan or a wrong constant |

### 4. Dynamic regions

MAE restricted to the top 25% of motion.

| Reading | Meaning | Action |
| --- | --- | --- |
| Dynamic MAE ≤ static MAE | Normal | None |
| Dynamic MAE over ~3 and over 1.5x static | Motion or easing does not match | Compare easing curves; check for dropped or duplicated frames |

Dynamic error is also where jitter shows up as elevated error, but jitter is
better confirmed with `diagnose_jitter.py`, since MAE cannot isolate it.

### 5. Edge sharpness

Gradient magnitude at the source's strongest edges, compared at the same
positions in the render.

| Reading | Meaning | Action |
| --- | --- | --- |
| Ratio 0.8-1.4 | Comparable | None |
| Ratio under ~0.65 | Render is blurrier | Check encoding settings, unwanted filters, or imprecise shape geometry |
| Ratio over ~1.5 | Render is too sharp | Check for over-correction or aliasing in generated shapes |

Encoded output reads slightly softer than render frames, so compare the
encoded file against the source for the final verdict.

## Composite Score

The reported overall score is `100 - 4 x mean MAE`, so an MAE of 25 maps to
zero. Treat it as a trend indicator across iterations, not as an absolute
quality claim.

What matters is the direction of movement between versions and the
`worst_frames` list, which names the frames to inspect.

## Reading worst_frames

The five highest-MAE frames ship with their per-dimension verdicts. Use them
as the entry point for every repair pass:

1. If most worst frames show a temporal verdict, fix global timing.
2. If most show a tone verdict, fix the color or background.
3. If most show an edge verdict, fix rendering or geometry.
4. Only when the verdicts are mixed should you debug elements individually.

## Iteration Discipline

The full-sequence score is the only judge.

- Re-run the entire sequence after every change. Never judge from one frame.
- Four impression-driven edits in one project each made things worse
  (frame 147: 28.5 → 89.3 → 86.6).
- Keep a versioned copy of each render and its score. When a change makes
  things worse, compare against the previous version rather than reasoning
  forward from the current state.
- Re-score the encoded file separately. Encoding introduces color shift, so
  the render-frames score is not the deliverable's score.

## When The Score Will Not Improve

When tuning stops helping, strip layers instead of continuing to adjust
parameters. Rendering the background alone, with every foreground element
removed, once overturned every prior assumption about where the error was and
pointed directly at the root cause.

Layer-stripping is more effective than parameter tuning precisely when you do
not know what to suspect.
