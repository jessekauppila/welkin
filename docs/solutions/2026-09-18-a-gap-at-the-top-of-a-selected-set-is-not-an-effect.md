<!-- Copied near-verbatim into Welkin, 2026-09-18.
     origin: ~/GitHub/figment/docs/solutions/2026-09-18-a-gap-at-the-top-of-a-selected-set-is-not-an-effect.md
     commit: 89e1971
     Do not edit here; fix at the origin and re-copy. -->

---
title: A gap measured at the top of a selected set is not an effect
date: 2026-09-18
category: docs/solutions
module: figment/core/evolve
problem_type: data_integrity
component: experiment_design
severity: high
root_cause: selection_bias
resolution_type: verification_method
applies_when:
  - "Comparing with-feature against without-feature on the best results of a search"
  - "A feature measured as useless looks obviously useful on the winners"
  - "Quoting an improvement computed from elites, top-N, or anything ranked"
  - "An archive or leaderboard stores the score that decided what it kept"
  - "About to keep a feature because the best outputs all have it"
symptoms:
  - "A controlled ablation says no effect while the top results show a large gap"
  - "Rebuilding winners without a feature makes them much worse"
  - "The effect size grows the further up the ranking you look"
  - "A feature looks essential on elites and neutral on random samples"
related_components:
  - map_elites
  - guidance_field
  - ablation
---

# A gap measured at the top of a selected set is not an effect

**Date:** 2026-09-18
**Area:** figment guidance field / reading an archive

## The trap

A paired ablation had already answered whether the near-miss guidance field
helps: **200 trials, same genome and same seed played twice, delta +0.0005, 95%
CI [-0.0048, +0.0062], and 142 of 200 pairs exactly tied.** Guidance does
nothing, on average, to a random genome.

Then a separate bug forced the two best elites of a 4,585-game night to be
rebuilt both ways:

| | rebuilt without guidance | with guidance |
| --- | --- | --- |
| best elite | 0.625 | **0.785** |
| second best | 0.643 | **0.777** |

A gap of ~0.15 on the winners, against ~0.000 in the controlled experiment. It is
tempting to conclude the ablation was too blunt and guidance matters after all.

It is the opposite. **The archive kept those genomes *because* their guided score
was high.** Conditioning on "scored well with guidance on" selects precisely the
cases where guidance happened to help — the noise that guidance adds is part of
what got them selected. Rebuild them without it and they fall back, exactly as
the winner's curse predicts. The 0.15 is the size of the selection, not the size
of the effect.

The paired ablation remains the honest estimate, because it fixes the genome and
seed *before* seeing the outcome, and both arms have the same chance to be lucky.

## The rule

**Never measure a feature's effect on items that were selected using that
feature. The comparison is guaranteed to flatter it, by an amount that grows the
further up the ranking you look.**

The tell is the disagreement itself: a controlled experiment saying "no effect"
and a top-N comparison saying "large effect" is not a contradiction to be
resolved by trusting the bigger number. It is the signature of selection, and the
controlled number is the one to keep.

Two practical consequences:

1. **An archive's stored scores are selected quantities.** Anything computed from
   them — mean elite fitness, "our best is 0.785", a before/after on elites —
   inherits the bias. They are fine for *steering* a search, which is what they
   are for, and unreliable as *measurements* of anything.

2. **If you want to know whether a feature earns its cost, pay for the paired
   trial.** It is more expensive than reading numbers already lying in the
   archive, and that is the whole reason the archive's numbers cannot answer it.

The same reasoning applies to the geometry: elites also look denser, more
symmetric and more cavity-rich than random games, and for the same reason. The
archive is a record of what the scorer rewarded, not a sample of what the rules
produce.
