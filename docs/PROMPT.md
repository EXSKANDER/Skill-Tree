# LLM Node-Generation Prompt Formula

A repeatable prompt for getting an LLM to draft one *region* of a subject's
knowledge graph (5–12 nodes at a time — never whole graphs). The output is
a bundle that `st import <graph>` ingests directly, so generation → review →
import is one pipeline:

```
llm < prompt.txt > bundle.txt      # whatever LLM CLI/chat you use
$EDITOR bundle.txt                 # YOU are the editor-in-chief: fix, cut, tighten
st import <graph> bundle.txt
st check <graph>
```

Fill the five SLOTS, paste, send. Keep the RULES and OUTPUT FORMAT sections
verbatim — they are what make results consistent between runs.

---

## The formula

```text
You are an expert curriculum designer building a Math Academy-style mastery
learning system: a prerequisite knowledge graph of topic nodes, where each
node is one scaffolded lesson broken into knowledge points.

SUBJECT: {1: subject and level, e.g. "Spanish grammar, A2 level"}

REGION TO BUILD: {2: the specific area, e.g. "regular preterite tense",
and any scope notes: what is explicitly OUT of scope}

TARGET: {3: N} new topic nodes.

LEARNER PROFILE: {4: who is learning; what they can already do in one or
two sentences}

EXISTING BOUNDARY NODES — the only prerequisites outside this batch you may
reference:
{5: one line per node, exactly:  id — title — one-line summary of what a
learner who finished it can do. If the region has no prerequisites, write
"none: these are entry nodes".}

RULES
1. GRANULARITY. One node = one lesson of 20–30 focused minutes. If a topic
   needs more, split it into a prerequisite chain. Every node must teach
   exactly one new skill or concept, stated in its title.
2. SCAFFOLDING. Each node has 2–4 knowledge points (KPs). KP 1 is the
   simplest possible case of the skill; each later KP adds exactly one new
   wrinkle. A learner who can do KP n is one small step from KP n+1.
3. KP CONTENT. Every KP contains one fully worked example (show every
   step, minimal cognitive load) and 2–4 blocked practice problems of the
   same shape as the worked example, hardest last. Problems must be
   self-contained and answerable without the lesson in front of you.
4. DEPENDENCIES. `requires:` may list only boundary-node ids and ids of
   other nodes in this batch. No cycles. A requires B means "this lesson
   is incomprehensible without B" — not merely "related to B". Keep the
   list minimal; let transitivity do the work.
5. ENCOMPASSMENT. Where natural, make later nodes' problems implicitly
   exercise their prerequisites, so reviewing an advanced node covers the
   basics beneath it.
6. METADATA. `minutes:` is an honest estimate of focused lesson time
   including problems. Ids are stable lowercase-hyphen slugs. `tags:` may
   mark the region name.
7. NO FILLER. No motivational padding, no summaries, no "in this lesson
   you will". Introduction = 2–3 sentences on what the skill is and what
   it builds on.

OUTPUT FORMAT — emit exactly this, one block per node, no commentary
outside the blocks, no markdown fences around the blocks:

<<<node example-id>>>
---
id: example-id
title: Example Title
requires: [some-boundary-id]
minutes: 25
tags: [region-name]
---

# Introduction

...

## KP 1: Simplest Case

### Worked Example

...

### Problems

1. ...
2. ...

## KP 2: One New Wrinkle

### Worked Example

...

### Problems

1. ...
<<<end>>>

BEFORE ANSWERING, SELF-CHECK:
[ ] every node teaches exactly one new thing
[ ] KP 1 of each node is doable by someone who only knows the requires
[ ] no forward references: nothing assumes a node later in the batch
[ ] every requires id is a boundary id or a batch id; no cycles
[ ] every problem is the same shape as its KP's worked example
[ ] output parses: front matter keys id/title/requires/minutes/tags only
```

---

## Follow-up critique pass (optional, recommended)

After the first response, in the same conversation:

```text
Audit your batch against the RULES. For each node report: (a) the one new
skill it teaches, (b) any KP that jumps more than one wrinkle, (c) any
requires that is "related" rather than load-bearing, (d) any problem not
answerable from memory of the lesson. Then output the corrected bundle in
the same OUTPUT FORMAT.
```

## Practical notes

* **Regions, not graphs.** Boundary nodes pin the batch to what already
  exists; generating thousands of nodes at once produces mush. Grow the
  graph outward region by region, importing and `st check`-ing each batch.
* **You are the mastery gate.** The LLM drafts; you verify every worked
  example and problem before learners see it. `st import` only validates
  structure, not truth.
* **Media.** LLMs can't ship images; where a diagram is essential have it
  write `![description](../media/<node-id>-<n>.png)` and produce the file
  yourself into `graphs/<graph>/media/`.
* **Slot 5 is copy-pasteable.** Build the boundary list from your live
  graph: `st node list <graph>` gives ids/titles; add the one-line summary
  by hand (it is the highest-leverage sentence in the whole prompt).
