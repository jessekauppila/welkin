---
title: An LLM judge of agreement has a chance floor and an unstable sign
date: 2026-09-18
kind: measurement
status: active
origin: cloud prototype notebook 03 (~/GitHub/pareidolia-hub/apps/cloud-pareidolia/notebooks, commit be5c86a); written new for Welkin from the recorded finding
applies_to: scoring human-vs-AI agreement, cross-run "convergence", any metric where a model decides whether two free-text answers mean the same thing
---

# An LLM judge of agreement has a chance floor and an unstable sign

## What happened

The cloud prototype's first score for "is this a good cloud" was *convergence*: read
the same image several times, ask a second model to cluster the readings, and count
how often independent runs agreed. Notebook 03 measured it properly and it fell apart:

- **A chance floor of about 25 %.** Readings of *unrelated* clouds "agreed" a quarter of
  the time, because the model draws from one small vocabulary (whale, wave, dog, dragon)
  and any two lists from that vocabulary overlap.
- **A sign that flips between runs.** The judge's rank correlation with a second model
  was -0.38 on one run and +0.07 on another, on identical inputs. The judge itself is
  nondeterministic, and the metric inherits it.
- **Cross-model agreement fell to 37 %,** barely above the floor.

The model's one-shot `structure` scalar, by contrast, ranked the same images at
Spearman +0.80 across two models. It replaced convergence as the score. Multi-run
readings were kept only for display.

## The rule

**Do not score human-versus-AI agreement with an LLM judge.** Store both answers, with
the frame they were about, and compare by hand first. If a metric is ever needed:

1. Measure its chance floor on deliberately mismatched pairs before reading any real
   number against it.
2. Run the judge twice on identical inputs. If the ranking moves, the metric is
   measuring the judge.
3. Prefer a scalar the model emits once about one image over a comparison the model
   makes between texts.

## Where it applies in Welkin

The station stores the child's words and strokes and the seer's readings in separate
tables joined by frame. Nothing computes an agreement score. When Jesse compares them,
he does it by eye over a sitting's worth of frames, and writes down what he sees before
any number is proposed.
