#!/bin/sh
# End-to-end smoke test. Runs in a throwaway directory; prints PASS on success.
set -eu

BIN="$(cd "$(dirname "$0")/../bin" && pwd)"
PATH="$BIN:$PATH"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"

fail() { echo "FAIL: $1" >&2; exit 1; }
col() { awk -F'\t' -v k="$1" -v c="$2" '$1==k{print $c}'; }

export ST_SEED=42

# --- init, graph, nodes, links ----------------------------------------------
st init --git >/dev/null
st graph new demo >/dev/null
st node new demo counting --minutes 9 >/dev/null
st node new demo addition --minutes 9 >/dev/null
st link add demo addition counting >/dev/null
st check demo >/dev/null || fail "check"
[ "$(st link list demo)" = "addition	counting" ] || fail "link list"

# cycle detection
st link add demo counting addition >/dev/null 2>cycle.err || true
grep -q cycle cycle.err || fail "cycle warning"
st link rm demo counting addition >/dev/null

# --- mastery statuses --------------------------------------------------------
[ "$(st status demo | col counting 2)" = "ready" ] || fail "counting ready"
[ "$(st status demo | col addition 2)" = "not-ready" ] || fail "addition not-ready"

# mastery learning is enforced
st done demo addition --all >/dev/null 2>&1 && fail "not-ready was completable"

# --- learn with evidence -----------------------------------------------------
export ST_TODAY=2026-01-01
echo "photo bytes" > proof.jpg
st done demo counting 1.1 -e proof.jpg >/dev/null
ls state/demo/evidence/counting/1.1/proof.jpg >/dev/null || fail "evidence file"
st done demo counting --all >/dev/null
[ "$(st status demo | col counting 2)" = "learned" ] || fail "counting learned"
[ "$(st status demo | col addition 2)" = "ready" ] || fail "addition ready"
st done demo addition --all >/dev/null

# lesson xp: 9 minutes over 3 template problems = 3+3+3
[ "$(st xp | col total 2)" = "18" ] || fail "lesson xp, got $(st xp | col total 2)"

# --- SM-2 schedule (Anki defaults, deterministic) ---------------------------
[ "$(st status demo | col counting 3)" = "2026-01-02" ] || fail "graduating ivl"
export ST_TODAY=2026-01-02
[ "$(st due demo | wc -l)" = "2" ] || fail "two due"
st review demo counting good >/dev/null
# ivl 1, ease 2.5, delay 0 -> good = max(round(2.5), hard+1=3) = 3
[ "$(st status demo | col counting 3)" = "2026-01-05" ] || fail "good ivl 3"
[ "$(st due demo | wc -l)" = "1" ] || fail "one due after review"

# --- quiz: encompassment + grading ------------------------------------------
export ST_TODAY=2026-01-05
# both due (addition overdue since 01-02, counting due today);
# counting is a prereq of addition -> quiz collapses to 1 item
st quiz new demo > sheet.txt 2>covered.txt || fail "quiz new"
QID="2026-01-05-1"
[ "$(st quiz list demo | col "$QID" 2)" = "0/1 graded" ] || fail "quiz has 1 item"
grep -q "implicitly covered" covered.txt || fail "encompass note"
st quiz grade demo "$QID" 1 good > grade.txt
grep -q "implicit credit: counting" grade.txt || fail "implicit credit"
grep -q "perfect" grade.txt || fail "perfect bonus"
[ -z "$(st due demo)" ] || fail "nothing due after quiz"

# --- remedial: failing twice queues prereq review ---------------------------
st review demo addition again >/dev/null
st review demo addition again > remedial.txt
grep -q "remedial review due now for: counting" remedial.txt || fail "remedial"
st due demo | col counting 1 >/dev/null || fail "counting due after remedial"

# --- xp ledger and manual adjustment ----------------------------------------
st xp add -5 blew off practice >/dev/null
st xp log | tail -1 | grep -q -- "-5" || fail "penalty logged"
TOTAL="$(st xp | col total 2)"
# 18 lesson + 2 review(good) + 2 quiz item(good) + 1 perfect bonus + 0 + 0 - 5
[ "$TOTAL" = "18" ] || fail "xp total, got $TOTAL"

# --- import bundle -----------------------------------------------------------
cat > bundle.txt <<'EOF'
<<<node subtraction>>>
---
id: subtraction
title: Subtraction
requires: [counting]
minutes: 10
---

# Introduction

Taking away.

## KP 1: Single digits

### Worked Example

5 - 2 = 3.

### Problems

1. 7 - 4
2. 9 - 3
<<<end>>>
EOF
st import demo bundle.txt >/dev/null
[ "$(st node problems demo subtraction | wc -l)" = "2" ] || fail "import problems"
st check demo >/dev/null || fail "check after import"

# --- change tracking ---------------------------------------------------------
st sync -m "smoke" >/dev/null
git -C . log --oneline | grep -q smoke || fail "sync commit"

echo PASS
