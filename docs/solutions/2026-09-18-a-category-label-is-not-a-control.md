---
title: A category label is not a control
date: 2026-09-18
kind: measurement
status: active
applies_to: any negative control assembled from tagged, scraped or crowd-labelled images
---

# A category label is not a control

## What happened

The cloud prototype built its negative control from Wikimedia Commons categories named
Skies, Haze, Fog and Stratus, on the reasonable guess that those would be featureless
sky. Welkin's picker ran its first negative control on that pool and failed: the
"flat sky" images scored higher on texture than the clouds did. Looking at the top
scorers explained it in seconds. They were a tree canopy, a foggy field with bare trees,
and a cirrus-streaked blue sky. The category was true of each photograph and irrelevant
to what the control needed.

The prototype had noticed the pool was not reliably flat and fixed it by keeping the 20
flattest files as ranked by the very texture score under test. That makes the control
pass by construction. It is the lesson from figment's "an instrument can manufacture the
signal it measures" and sunset's "a gap at the top of a selected set is not an effect",
arriving from a third direction: selecting the *control* by the instrument is the same
mistake as selecting the *treatment* by it.

## The rule

A control set is defined by what is in the images, not by what they are tagged. Before
using any tagged, scraped or crowd-labelled pool as a control:

1. Look at the ten highest-scoring members under the instrument you are testing. If they
   are not what the control is supposed to be, the pool is not a control.
2. Never trim a control with the instrument under test. Trim it by hand, by a different
   instrument, or by how the images were made.
3. The strongest control is one whose content you produced: a lens cap, a wall, the
   camera's own sky on a clear day. Prefer it over anything downloaded.

## Where it applies in Welkin

`docs/controls.md` records every control run. `welkin-control` prints the top-scoring
control files by name so rule 1 is one glance away. The picker's real control is the
deployed camera's own frames, not any Commons pool.
