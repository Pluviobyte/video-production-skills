# Remotion Pitfalls

Rendering constructs that produce visible jitter, and the constructs that do
not. Everything here was isolated with a controlled test composition that
rendered the same motion several ways and measured frame-to-frame
acceleration noise.

## The Core Rule

Any element that moves smoothly across subpixel distances must be:

1. an **HTML element** (not SVG text, not SVG group transform), and
2. moved by **CSS `transform: translate(...)`**, and
3. carrying **`will-change: transform` on the same DOM node**.

If any of those three is missing, the element snaps to whole pixels.

## Measured Comparison

The test measured the same slow horizontal move several ways. "Acceleration
noise" is the RMS of the second difference of the measured position, in
pixels — the source's own labels measured 0.027.

| Construct | Result |
| --- | --- |
| HTML element, `transform` + `will-change` on same node | Smooth fractional movement, noise 0.052 ✓ |
| SVG `<text>` | Snapped to integers, per-frame deltas 0/0/-1/0, noise 0.48 ✗ |
| SVG `<g transform>` | Snapped to integers ✗ |
| CSS `left` / `top` | Snapped to integers ✗ |
| `transform` on child, `will-change` on parent | Snapped to integers ✗ |

The SVG and `left`/`top` cases are about 18x noisier than a correct HTML
transform, and that difference is what reads as "the elements are slightly
shaky".

## Fixes In Practice

### Text that moves

Do not animate SVG `<text>`. Lay out text as HTML `<div>` inside a wrapper
that carries the camera transform:

```tsx
<div style={{
  position: "absolute", inset: 0,
  transform: `translate(${tx}px, ${ty}px) scale(${s})`,
  transformOrigin: "0 0",
  willChange: "transform",
}}>
  {labels.map(/* plain <div> children */)}
</div>
```

Subpixel movement inside this wrapper stays smooth because the transform
carries it, and the text itself never changes its own position.

### Placing text precisely

To land a text element's *ink* bounding box at a target position, measure the
font's ink offsets once and convert to a CSS box position. Emitting raw
coordinates into `left`/`top` and then animating those coordinates is the
construct that snaps.

### Boxes and cards

Same pattern: `transform: translate(...)` plus `willChange`, never animated
`left`/`top`. A card clip wrapper that moves should be a transformed HTML
node, with the card's contents positioned inside it at fixed coordinates.

### Cursor sprites

Position with `translate`, and when rotation or scale about a hotspot is
needed, order the operations explicitly:

```tsx
transformOrigin: "0 0",
transform: `translate(${x + hx}px, ${y + hy}px) rotate(${rot}rad)
            scale(${sx}, ${sy}) translate(${-hx}px, ${-hy}px)`,
```

### Zoomed containers

When applying a blur to a container that is also scaled, divide the blur
radius by the scale so the visual blur matches the source:

```tsx
filter: `blur(${sigma / s}px)`
```

## Detecting Jitter

Per-frame MAE cannot detect it. MAE asks "does this frame resemble the
reference", while jitter is unevenness *between* frames. Use
`scripts/diagnose_jitter.py`, which compares the acceleration RMS of the
source against the render for the same elements.

Rough thresholds:

| Acceleration RMS | Reading |
| --- | --- |
| Under ~0.1 | As smooth as typical source motion |
| 0.1 - 0.25 | Slight, may be visible on slow movement |
| Above 0.25 with a 2x ratio versus source | Visible jitter — investigate |

## Root Causes Beyond The Construct

If the construct is correct and jitter persists, the data is the problem:

1. **Quantized measurements.** Threshold-based integer edges carry about 1px
   of noise. Refit using intensity centroids.
2. **Camera track contamination.** If `tx` was fitted from elements that were
   mid-transition, their changing letter-spacing leaks into the camera path.
   Restrict `tx` to elements that stay strictly static across the window.
3. **Unsigned wraparound.** Interpolating a value that jumps discontinuously
   creates single-frame spikes. Check the raw series before smoothing.
4. **Insufficient smoothing of a noisy fit.** A 5-point quadratic
   Savitzky-Golay pass over the fitted track removes single-frame noise
   without flattening real motion, as long as the fit itself is sound.

## Order Of Operations For A Suspected Jitter Bug

1. Run `diagnose_jitter.py` on a window where the element is otherwise static.
   A static window isolates jitter from real motion.
2. Identify which element and which axis is flagged.
3. Check that element's construct against the table above.
4. If the construct is correct, inspect the driving data series — plot or
   print the raw values and look for single-frame spikes.
5. Refit the data from subpixel measurements, restrict the fit's inputs, then
   smooth.
6. Re-render and re-run the diagnostic. Never declare a jitter fix from a
   single still frame.
