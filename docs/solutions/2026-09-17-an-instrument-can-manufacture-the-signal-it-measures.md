<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/figment/docs/solutions/2026-09-17-an-instrument-can-manufacture-the-signal-it-measures.md
     commit: d30f2f0
     Do not edit here; fix at the origin and re-copy. -->

---
title: An instrument can manufacture the signal it is measuring
date: 2026-09-17
category: docs/solutions
module: figment/plugins/scorer
problem_type: data_integrity
component: measurement
severity: high
root_cause: measurement_artifact
resolution_type: verification_method
applies_when:
  - "Changing how a thing is rendered, lit, framed or sampled before it is scored"
  - "A heuristic scorer starts returning higher numbers after a capture change"
  - "Choosing settings that make output look better to a human"
  - "A detector fires on inputs that should contain nothing to detect"
  - "About to trust a fitness function that has never been shown a negative control"
symptoms:
  - "A scorer returns a high score for an input containing none of what it detects"
  - "Scores move when render resolution or lighting changes but the subject does not"
  - "The same structure scores 0.610 at one resolution and 0.302 at another"
  - "A signal improves right after a capture-side change rather than a subject-side one"
  - "Fitness climbs steadily while the artefacts look no better to a person"
related_components:
  - pareidolia_scorer
  - blender_renderer
---

# An instrument can manufacture the signal it is measuring

**Date:** 2026-09-17
**Area:** figment scorer / render rig

## The trap

Figment scores sculptures for face-likeness from rendered images. Three times
the score went up for reasons that had nothing to do with the sculptures.

**The background became the eyes.** A cavity was defined as any dark region
inside the figure's bounding box, which for a tall narrow shape includes the
empty space to its left and right. Two regions, always level, always far apart,
always similar in size — a perfect eye pair by the heuristic's own definition. An
entire 458-cell overnight archive had been climbing that gradient, which is why
it filled with pillars. A 301-brick lattice scored 0.91 on "eyes" while having
none.

**Raking light turned studs into eyes.** Lower, more dramatic lighting was
proposed to make indents read as eye sockets, and it does — an indented block
scored 0.85. But the *same block with no indents at all* scored **0.98**, because
the light rakes across the LEGO studs and every stud shadow reads as a cavity.
Fourteen of them on a featureless wall. Chosen for looking better, it would have
made the scorer measure surface texture and call it faces.

**Three of four signals moved with resolution.** The same structure scored 0.610
at 160px and 0.302 at 512px; eyes and mouth collapsed to exactly 0.000 above
320px; the Haar cascade swung fourfold with no change to the subject. 65% of the
fitness weight rode on signals that were partly reporting render settings.

## The rule

**Before trusting a detector, show it something that contains nothing to detect.
If it fires, it is measuring the instrument.**

A negative control is one image and it would have caught all three:

- a plain pillar → "eyes" must be 0.00 (it was 0.91)
- a featureless block → "eyes" must be 0.00 (it was 0.98 under raking light)
- the same subject at 160/320/512px → scores must agree (they did not)

Each is now a test. The second one is why the lights stay high even though the
low ones look better: *the render is a measuring instrument, not a portrait.*
Under flat, fixed light the scorer measures the arrangement of black and white
brick, which is a property of the object that survives any lighting. Under
dramatic light it measures arrangement plus shadow, and the shadow depends on
where the lamp happens to be.

Two supporting habits:

1. **Draw what the scorer sees.** `scorer.overlay()` paints cavities, the chosen
   eye pair, the mouth and the predicted positions onto the image it scored. Both
   scorer bugs were obvious in one picture each and invisible in the numbers —
   the number said 0.873 and a human looking at the same image saw a lattice.

2. **Separate the questions the instrument answers.** One brightness threshold
   was deciding both "where is the object" and "what is dark", and could not do
   either reliably. Where the object is now comes from the alpha channel — exact,
   no threshold, immune to lighting and resolution — and darkness is judged only
   within it.

This is the same shape as `fallbacks-must-not-impersonate-real-signal` in the
sunset repo: a path that produces plausible numbers when it should produce none
is worse than a path that fails, because nothing downstream can tell.
