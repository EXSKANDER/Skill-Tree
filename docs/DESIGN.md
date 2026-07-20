# Design

Skill-Tree ports the structure of *The Math Academy Way* — mastery learning
over a prerequisite knowledge graph — to any subject, as a suite of small
UNIX tools operating on plain text.

## UNIX philosophy, applied

| Principle | How it shows up here |
|---|---|
| Do one thing well | one `st-*` program per job; `st` only dispatches |
| Text streams as interface | list commands emit TSV; pipe them to `grep`, `awk`, `sort` |
| Plain-text data | nodes are Markdown, state is JSON, the xp ledger is TSV |
| No captive interfaces | quizzes are printed sheets, not interactive sessions; grade when done |
| Leverage existing tools | git *is* the change tracker; `$EDITOR` *is* the content editor; `xdg-open` opens media |
| Store data in flat files | the whole system is a directory you can `rsync`, diff, and version |

There is no daemon, no database, no lock-in: delete `bin/` and `lib/` and
your course and progress are still readable files.

## Data model

```
root/
  .skilltree/config.json      knobs (daily goal, quiz size, ...)
  graphs/<graph>/nodes/*.md   CONTENT - one file per topic node
  graphs/<graph>/media/       images/audio/video embedded by lessons
  state/<graph>/progress.json STATE - per-node learning + SM-2 record
  state/<graph>/quizzes/      generated quiz sheets + manifests
  state/<graph>/evidence/     submitted proof-of-work files
  state/xp.tsv                append-only xp ledger
```

Content and state are deliberately separate trees: a graph can be shared,
forked, or regenerated without touching anyone's progress, and progress can
be reset by deleting one directory.

A **node** is one lesson: front matter (`id`, `title`, `requires`,
`minutes`, `tags`) plus a body of **knowledge points** (`##` headings),
each with a worked example and blocked practice problems. Worked examples
are Markdown, so media embedding is just `![x](../media/x.png)` — evidence
and media are ordinary files. Edges live only in `requires:`; there is no
second edge store to drift out of sync. `st check` validates parseability,
unknown/self references, and cycles (Kahn's algorithm).

## Mastery statuses

Statuses are always derived, never stored:

* **learned** — `progress.json` has `learned_at` (every lesson problem was
  completed via `st done`);
* **ready** — not learned, all `requires` learned (this set is the
  *knowledge frontier*);
* **not-ready** — some prerequisite unlearned. `st done` refuses these
  without `--force`, which is mastery learning enforced mechanically.

## Spaced repetition

`lib/skilltree/scheduler.py` implements Anki 2.1's open-source SM-2 variant
(v2 scheduler, default deck options) at day granularity — constants and
formulas are documented in that file's docstring. Two deliberate
deviations, both documented in code: sub-day learning steps are collapsed
(finishing a lesson graduates the node straight to a 1-day interval), and
interval fuzz is removed so scheduling is deterministic and diffable.
Reviews target whole nodes, not flashcards: one review = one problem from
that node's pool.

## Review quizzes and interleaving

The hard design question: Math Academy interleaves *within review tasks*
while lessons stay blocked. The manual-phase answer, implemented in
`lib/skilltree/quiz.py`:

1. **Due** — collect learned nodes whose SM-2 date has arrived, most
   overdue first.
2. **Encompass** — advanced skills implicitly practice their
   prerequisites, so any due node that is a transitive prerequisite of
   another due node is dropped and "covered" by it. The quiz becomes the
   *smallest set of tasks encompassing all due review* (TMAW [42]).
   `--no-encompass` disables this.
3. **Pick** — one problem per surviving node, avoiding the problem served
   at the previous review of that node (randomised, seedable via
   `ST_SEED`).
4. **Interleave** — shuffle under the constraint that adjacent items never
   come from graph-adjacent nodes: mixed practice, no obvious order, and
   conceptually similar material never runs back-to-back
   (non-interference). The sheet does not label which topic an item
   drills, so retrieval has to start from the problem itself.
5. **Grade** — each item is `again|hard|good|easy` and feeds SM-2 for its
   node. A passing grade propagates to covered prerequisites *capped at
   "good"* and with no xp (implicit credit shouldn't compound faster than
   explicit practice); a failing grade leaves them due. Failing the same
   node twice in a row queues its direct prerequisites for immediate
   remedial review (TMAW [41]).

On macro vs micro interleaving (your notes question on [278–279]): mixing
problems from *different topics* across the quiz is macro-interleaving,
and that is what step 4 does; micro-interleaving (mixing variant forms
within a single topic's practice) is approximated by step 3 rotating which
problem a node serves each time it comes due.

Because quizzes are plain sheets plus a JSON manifest, the workflow
survives the manual phase unchanged: work anywhere (paper, editor), then
grade item-by-item. Nothing needs a UI to exist.

## XP

1 xp ≈ 1 focused minute (TMAW [309]). A node's `minutes` pays out across
its lesson problems (remainder on completion); reviews pay
performance-graded xp (easy = base+1, good = base, hard = half, again = 0);
a perfect quiz pays a +25% bonus; `st xp add -5 ...` records penalties.
The ledger is append-only TSV — totals, daily-goal progress, and streaks
are always recomputed from it, so it is auditable and git-mergeable.

## Evidence

`st done ... -e file` (and `st quiz grade ... -e file`) copies any media
file into `state/<graph>/evidence/<node>/<problem>/` and records it against
the completion. For now that is the whole verification story, by design:
the slot where automated checking will later sit is a single code path.

## Deferred features and where they plug in

* **Adaptive diagnostic exam** — needs finished graphs; will live in a new
  `st-diagnose` that binary-searches the graph using encompassment
  (`graph.ancestors` already provides the machinery) and writes
  `learned_at` for everything below the measured frontier.
* **Knowledge frontier view** — already implicitly present:
  `st status <g> --only ready` *is* the frontier; a richer visualisation
  can be a formatter over the same TSV.
* **Automated verification of evidence** — replaces the trust-based mark
  in `st done`; the storage layout already keys evidence to problems.
* **Graph visualisation** — emit DOT from `st link list` and let
  `graphviz` do the work (one small future tool, `st-dot`).
