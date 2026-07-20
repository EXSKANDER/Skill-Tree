# Skill-Tree

Mastery learning for any subject, the Math Academy way, as a suite of small
UNIX tools: prerequisite knowledge graphs of hand-written lessons, enforced
mastery statuses, Anki-formula spaced repetition, interleaved review
quizzes, proof-of-work evidence, and an xp ledger — all stored as plain
Markdown/JSON/TSV files and versioned with git.

No daemon, no database, no dependencies beyond Python 3 and git.

## Install

```sh
git clone <this repo> && cd Skill-Tree
export PATH="$PWD/bin:$PATH"        # add to your shell rc to keep it
sh tests/smoke.sh                   # prints PASS
```

## Five-minute tour (using the bundled example)

```sh
cd example
st status arithmetic                     # ready / learned / not-ready
st node show arithmetic add-two-digit    # read a lesson (pipe to a pager)
st node problems arithmetic add-two-digit

st done arithmetic place-value --all     # complete a lesson's problems
st done arithmetic add-one-digit 1.1 -e photo-of-my-work.jpg
st done arithmetic add-one-digit --all   # node -> learned, review scheduled

st due arithmetic                        # what spaced repetition wants back
st quiz new arithmetic                   # interleaved review sheet
st quiz grade arithmetic 2026-07-21-1 1 good
st xp                                    # totals, daily goal, streak
st sync -m "today's session"             # git commit content + state
```

Start your own tree in any empty directory: `st init --git`, then
`st graph new <subject>` and `st node new <subject> <topic-id>`.

## Visual interface

Prefer clicking to typing? Launch the local web UI — same files, same logic,
a browser front-end instead of the terminal:

```sh
cd example
st web            # opens http://127.0.0.1:8777 in your browser
```

It has four views: an interactive **skill tree** (nodes laid out along their
prerequisites, coloured by status, with review-due badges), a **lessons**
grid, a per-topic **lesson drawer** (rendered worked examples + a practice
checklist where you mark problems done and attach evidence files), a
**review** view (see what's due, generate an interleaved quiz, grade items),
and a **progress** dashboard (XP totals, streak, daily goal, 7-day chart).

The server is Python-stdlib-only, binds to `127.0.0.1`, makes no outbound
network calls, and the page bundles all its own CSS/JS — nothing is fetched
from a CDN. It reads and writes the very same plain files as the `st`
commands, so you can mix the browser and the terminal freely.

## Commands

| command | job |
|---|---|
| `st init` | create a skill-tree root (`--git` to also `git init`) |
| `st graph new/list` | create / list knowledge graphs |
| `st node new/list/show/problems/edit` | scaffold and inspect topic nodes |
| `st link add/rm/list` | edit prerequisite edges (`add g topic prereq`) |
| `st check` | validate graphs: parse errors, bad edges, cycles |
| `st status` | every node as `ready` / `learned` / `not-ready` |
| `st done` | complete lesson problems (`-e file` attaches evidence) |
| `st due` | learned nodes whose review date has arrived |
| `st quiz new/show/grade/list` | interleaved, encompassment-aware review |
| `st review` | grade a single node directly (the primitive under quizzes) |
| `st xp` | totals, daily goal, streak, ledger, manual adjustments |
| `st import` | ingest an LLM-generated node bundle (see docs/PROMPT.md) |
| `st sync` | convenience `git add + commit` of content and state |
| `st web` | serve the local browser interface (stdlib only, localhost) |

Every list command emits TSV — compose with `grep`, `awk`, `sort`, `wc`.
`st status g --only ready` is your current knowledge frontier.

## How it maps to The Math Academy Way

| TMAW concept | here |
|---|---|
| knowledge graph, prerequisite edges | `graphs/<g>/nodes/*.md`, `requires:` front matter |
| topic = lesson of scaffolded knowledge points | `##` KP sections: worked example + blocked problems |
| mastery: not-ready / ready / learned | derived statuses; `st done` refuses not-ready nodes |
| spaced repetition, widening gaps | Anki 2.1 SM-2 formulas, day granularity (`lib/skilltree/scheduler.py`) |
| interleaved review, minimal encompassing task set | `st quiz new`: due → encompass-collapse → one problem per node → constraint-shuffled order |
| remedial review after repeated failure | two consecutive `again` on a node queues its prereqs due-now |
| xp: 1 xp ≈ 1 focused minute | append-only `state/xp.tsv`; goals, streaks, penalties |
| diagnostic exam, knowledge frontier | deferred until graphs are complete — plug-in points in docs/DESIGN.md |

Design rationale and data formats: [docs/DESIGN.md](docs/DESIGN.md).
LLM prompt formula for generating graph regions: [docs/PROMPT.md](docs/PROMPT.md).

## Layout

```
bin/          st dispatcher + one st-* program per job (git-style)
lib/skilltree Python 3 stdlib-only library shared by the tools
              (web.py + web/ hold the browser UI: server + self-contained page)
docs/         DESIGN.md, PROMPT.md
example/      a ready-made root: arithmetic graph, five lessons
tests/        smoke.sh (CLI) + web-smoke.sh (HTTP API), both deterministic
```

Your own learning data lives wherever you ran `st init` — this repo is
just the toolset (plus the example). Content (`graphs/`) and personal
state (`state/`) are separate trees, so courses can be shared without
sharing progress.
