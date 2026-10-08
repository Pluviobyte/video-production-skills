# Measurement Contract

How to measure UI elements from source frames so the numbers are trustworthy.
Read this before writing any measurement script.

## The Two Failure Modes

Every measurement error observed in practice fell into one of two buckets:

**1. The method is systematically wrong.** It returns a consistent, confident,
incorrect answer. Saturation-threshold masks halved a capsule's radius
(0.28 measured vs 0.535 true). Arithmetic averaging of angle samples invented
a constant 44.75 degrees that was never in the data.

**2. The method tracks the wrong thing.** It works on the frame it was
developed against and silently measures something else later.
Fixed-coordinate scanning walked off-screen once the subject moved — this
mistake was made three separate times in one project. A fixed-threshold
luminance profile flipped light/dark polarity mid-video and began measuring
the background instead of the object.

Neither failure is visible in a single inspection. Both are visible in a
cross-check.

## Mandatory Protocol

For every new measurement:

1. **Measure a frame whose answer you already know.** Render a synthetic test
   frame, or pick a source frame where the value is unambiguous by eye. If a
   known circle of radius 50 measures as 28, the method is wrong — stop tuning
   thresholds and change the approach.
2. **Apply two independent methods.** A geometric method (bounding box,
   fitted circle) and an intensity method (centroid, weighted moments) should
   agree. Disagreement means one of them is measuring a different object.
3. **Bound the valid frames.** State explicitly which frames the measurement
   is valid for. Activation transitions, occlusions, and camera moves change
   what is being measured.
4. **Verify against the render.** After building the component, measure the
   same quantity on the rendered frame and compare. Residual error should be
   near the source's own frame-to-frame noise, not larger.

## Choosing A Method

| Target | Method | Notes |
| --- | --- | --- |
| Background color | Per-frame grid sampling on non-foreground pixels | Never fit a gradient model — measured 26x worse |
| Element position | Intensity-weighted centroid | Subpixel accurate; one order of magnitude cleaner than edge thresholds |
| Element size | Edge detection cross-checked against centroid span | Validate on a known-size shape |
| Element color | Masked mean over the element's own pixels | Do not sample a fixed coordinate |
| Text ink extent | Font metric measurement, calibrated against the render | Depends on font, weight, and letter-spacing |
| Camera transform | Least-squares fit of centroids across multiple elements | Needs at least 2 elements; guard the scale range |
| Card motion | Per-frame clip box, possibly non-rigid | A single static offset often fails partway through a transition |

## Subpixel Centroids

The intensity-weighted centroid is the workhorse. Weight by a soft function
rather than a hard threshold, so anti-aliased edges contribute fractionally:

```
w = clip((cut - luminance) / soft, 0, 1)
```

- `cut` sits above the ink's luminance and below the background's
- `soft` controls the transition band; around 40-50 works for dark text on
  a light background
- zero out pixels with high saturation if the background glows or is tinted

A hard threshold quantizes the centroid and reintroduces exactly the noise
this method exists to avoid.

## Handling Multiple Elements

When several similar elements move together, fit one shared transform rather
than tracking each independently:

1. Measure all element centroids on a reference frame where everything is
   still and clear. These become the layout basis.
2. From the reference frame, work outward in both directions. Predict each
   element's position from the previous frame's transform, and claim the
   nearest measurement within a tolerance.
3. Fit the transform by least squares across all claimed elements.
4. Guard against bad fits with a plausible range (for scale, roughly
   0.9-1.8 for a UI shot).
5. Leave gaps as gaps, then fill them from the nearest valid frame, then
   smooth. Do not let a failed fit silently become a value.

## Choosing Elements For The Translation Term

Fit the translation term only from elements that stay **strictly static**
across the measurement window. An element mid-transition changes its
letter-spacing and indent, so its centroid moves for reasons unrelated to
camera translation. Including such elements produced jumps of about 20px in
the fitted path.

Define "strictly static" with a threshold: for each candidate frame, check
the element's activation and position strength over a window of about
±6 frames, and reject it if either exceeds roughly 0.02.

## Smoothing

After fitting, apply a short Savitzky-Golay pass (5-point quadratic) across
the valid interior range. This removes single-frame noise without flattening
genuine motion.

Report the acceleration RMS before and after. If smoothing changes the motion
materially, the fit is too noisy and the inputs need fixing — smoothing is
not a substitute for a sound fit.

## What Not To Do

- Do not tune a threshold until one frame looks right. That is how the
  saturation-mask and polarity failures were introduced.
- Do not sample a fixed pixel coordinate across time.
- Do not average angles arithmetically; average unit vectors, or work in
  complex form.
- Do not smooth a series before checking it for single-frame spikes. Smoothing
  hides them instead of fixing them.
- Do not trust a measurement that has never been checked against a known
  value.
