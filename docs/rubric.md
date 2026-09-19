# Rubric v0

What the station asks of a person, and what the words in the data mean. This is
version `v0`. Every sitting is stamped with the version it ran under, and numbers from
two versions are never added together. Change anything here and it becomes `v1`.

## The question

The station shows one frozen frame of the sky and asks, in this order:

1. **Draw on it.** "Trace what you see." Finger or stylus, any number of strokes, any
   colour the station offers. Strokes are stored as polylines in frame coordinates.
2. **Name it.** "What do you see?" A free-text box, one line, may be left empty if the
   drawing says it.
3. **Commit.** One button. Nothing about the seer is shown before it is pressed.
4. **See the seer.** The seer's readings for the same frame appear beside the drawing:
   each *thing* it saw, roughly *where*, and how strongly it read. Or, if the seer could
   not look, the words "the seer could not look".
5. **Again.** A button that offers the next frozen frame.

## What counts as a committed response

A drawing with at least one stroke, or at least one word, or both. Whitespace alone is
not a response. The station refuses the rest.

## What is *not* asked in v0

- No rating of the cloud. No stars, no "was this a good one".
- No agreement question about the seer's reading. Whether the person agrees with the
  seer is read off the two answers by a human later, never asked, and never scored by a
  model (`docs/solutions/2026-09-18-an-llm-judge-of-agreement-has-a-chance-floor.md`).
- No identity beyond an optional `rater` the operator sets for the sitting. In M1 that
  is `jesse` or blank.

## Anchors

What a "good cloud to see something in" looks like, with example frames, so two
operators would freeze the same kind of frame. To be filled from the first real frames
off the deployed camera. Figment shows what happens when this waits: a scorer gets
trusted before anyone has written down what it is supposed to find.

| anchor | description | example frame |
|---|---|---|
| nothing to see | flat blue, uniform overcast, black | _(fill in)_ |
| texture only | mackerel sky, haze, streaks with no figure | _(fill in)_ |
| something there | one isolated lump with a silhouette | _(fill in)_ |
| very like a whale | a figure a stranger would name unprompted | _(fill in)_ |

## The seer's side

The seer runs prompt `cloud-prototype-v1` on `claude-opus-5` (`src/welkin/seer.py`). It
is asked to look "the way a child watching clouds would", to report only what genuinely
reads, and that an empty list is a good answer. Its `strength` is how strongly a shape
reads, not confidence that it is real. Its readings are shown after commit, never before
(the prototype's reason: "showing them first would anchor you").
