# Negative controls

Every scorer in Welkin runs on images that should score *nothing* before its output is
trusted on a single sitting. This file records each run: the instrument, the control set,
the numbers, and the verdict. Numbers here are measured, not asserted. Re-run with
`welkin-control` and append; never edit an old entry.

## 2026-09-18 — picker `texture` v0 on the prototype's Commons pools

**Instrument.** `welkin.picker.texture_score`: std of a Laplacian over the greyscale
image, resized to a 1024 px long side. Ported verbatim from the cloud prototype.

**Sets.** The cloud prototype's `data/raw/flat_sky` (38 Commons photos from the
categories Skies, Haze, Fog, Stratus) as the control, and `data/raw/clouds` (39 Commons
photos across 8 cloud genera) as the positive set.

**Numbers.**

| set | n | min | median | q3 | max |
|---|---|---|---|---|---|
| flat_sky, whole image | 38 | 2.78 | 18.07 | 34.65 | 81.24 |
| clouds, whole image | 39 | 3.73 | 15.96 | | 43.46 |
| flat_sky, top 40 % crop | 38 | 0.66 | 11.06 | 24.11 | 87.28 |
| clouds, top 40 % crop | 39 | 2.08 | 7.58 | | 31.53 |

All 39 clouds score at or below the control maximum, in both crops. 22 of 38 controls
score at or above the cloud median.

**Verdict: fail.** The control does not sit below the clouds. It sits above them.

**Why, from looking at the images.** The three highest-scoring "flat sky" files are a
bare tree canopy against sky, a field with leafless trees in fog, and a blue sky streaked
with cirrus. They are landscape photographs whose Commons category happens to be Haze
or Fog. The two lowest-scoring "clouds" are a pier under a dramatic sky and a mammatus
field: the mammatus is the most drawable cloud in the pool, and it scores low because
its edges are soft. The texture score measures high-frequency edges. Trees and horizons
have them; cumulus and mammatus mostly do not.

**What this means.**

1. The Commons flat-sky pool is not a control. A category label is a claim about the
   photograph, not a measurement of it. The prototype handled this by keeping only the
   20 flattest files *as ranked by texture_score*, which selects the control by the
   instrument under test. That is the circular move the figment and sunset lessons warn
   about, in a new costume.
2. `texture` v0 is an "is anything in frame" detector, not a drawability picker. It stays
   in the repo as the placeholder the brief asked for, but it has **not** passed a
   negative control on real photographs and must not be described as validated.
3. The only control that counts for Welkin is the camera's own sky: a lens-cap frame, a
   frame of the ceiling, a clear blue day, a uniform overcast day, all from the deployed
   Pi. Those frames do not exist until firmware issue #14 lands. This entry is to be
   superseded by one measured on them.
4. For a fixed sky-up camera, ground clutter (a roofline, a tree) is the same in every
   frame, so its texture is a per-camera constant. A picker that compares a frame to the
   camera's own recent minimum, rather than to an absolute number, would cancel it. Not
   built; noted for when real frames exist.

**Synthetic controls (pass, weak evidence).** A flat grey frame scores 0.00, a smooth
vertical gradient 0.91, a black frame 0.00; hard-edged blobs score above 10. These are
pinned in `tests/test_picker.py`. They show the arithmetic is right, not that the picker
is.

**Command.**

```bash
.venv/bin/welkin-control ~/sky/repos/cloud/data/raw/flat_sky --clouds ~/sky/repos/cloud/data/raw/clouds
.venv/bin/welkin-control ~/sky/repos/cloud/data/raw/flat_sky --clouds ~/sky/repos/cloud/data/raw/clouds --sky-crop 0.40
```

## 2026-09-18 — seer `claude-opus-5`, prompt `cloud-prototype-v1`, two-image smoke

**Purpose.** Confirm the ported call works end to end and that a featureless frame gets
the empty answer. Two images, not a control run.

| image | readings | structure | note (abridged) | cost |
|---|---|---|---|---|
| synthetic black frame (lens cap) | 0 | 0.00 | "A completely black frame with no tone, texture or edge to read anything into." | $0.008 |
| Commons mammatus photo | 3 | 0.65 | "Dense mammatus in sunset gold and bruised violet, full of rounded lobes and pouches" | $0.021 |

The mammatus is the same photograph the texture picker scored second-lowest of 39
clouds. The seer and the picker disagree about the most drawable cloud in the pool, and
the seer is right.

**Verdict: smoke pass.** Empty is returned as a real answer for a black frame, and a
structured reading comes back for a real cloud. Not a control: two images.

**Still to run on Welkin frames.** The prototype's own measurement on the same Commons pools
(notebook 02): flat sky gave an empty `readings` list 40 % of the time, mean 1.07 readings,
mean `structure` 0.15; clouds gave 0 % empty, 3.45 readings, 0.50. That is a separation
the texture score does not have, but it was measured on the pool shown above to be a
landscape set, so read it as "the model describes trees less eagerly than clouds", not as
a clean flat-sky result. To be re-run on lens-cap, ceiling and real flat-sky frames from
the deployed camera, with `welkin-seer --control DIR`.
