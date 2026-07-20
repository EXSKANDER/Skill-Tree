#!/bin/sh
# Web-server smoke test: boots st-web against a throwaway root and exercises
# the static assets, read endpoints, and mutating endpoints over HTTP.
# Prints PASS on success. Requires curl and python3.
set -eu

BIN="$(cd "$(dirname "$0")/../bin" && pwd)"
PATH="$BIN:$PATH"
TMP="$(mktemp -d)"
PORT="${ST_WEB_TEST_PORT:-8894}"
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }
B="http://127.0.0.1:$PORT"
jget() { curl -s "$B$1"; }
jpy() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

export ST_ROOT="$TMP" ST_NO_BROWSER=1 ST_SEED=7
cd "$TMP"

# build a tiny graph and learn two nodes so reviews exist
st init >/dev/null
st graph new demo >/dev/null
st node new demo a --minutes 6 >/dev/null
st node new demo b --minutes 6 >/dev/null
st link add demo b a >/dev/null
ST_TODAY=2026-01-01 st done demo a --all >/dev/null
ST_TODAY=2026-01-01 st done demo b --all >/dev/null

# boot server one day later so both nodes are due
ST_TODAY=2026-01-02 st-web --port "$PORT" --no-browser >"$TMP/server.log" 2>&1 &
SRV=$!
# wait for it to accept connections
i=0
while [ $i -lt 50 ]; do
  if curl -s -o /dev/null "$B/" 2>/dev/null; then break; fi
  i=$((i + 1)); sleep 0.1
done
[ $i -lt 50 ] || fail "server did not start"

# static assets
[ "$(code "$B/")" = 200 ] || fail "index"
[ "$(code "$B/app.js")" = 200 ] || fail "app.js"
[ "$(code "$B/style.css")" = 200 ] || fail "style.css"

# dashboard + graph
[ "$(jget /api/dashboard | jpy "d['graphs'][0]['name']")" = demo ] || fail "dashboard"
[ "$(jget /api/graph/demo | jpy "len(d['nodes'])")" = 2 ] || fail "graph nodes"

# node detail
[ "$(jget /api/node/demo/a | jpy "d['status']")" = learned ] || fail "node status"

# due list: both a and b due
[ "$(jget /api/due/demo | jpy "len(d['due'])")" = 2 ] || fail "due count"

# generate a quiz via POST; b encompasses a -> 1 item
QID=$(curl -s -X POST "$B/api/quiz-new/demo" -H 'Content-Type: application/json' \
  -d '{}' | jpy "d['quiz']['id']")
[ -n "$QID" ] || fail "quiz-new"
[ "$(jget "/api/quiz/demo/$QID" | jpy "len(d['items'])")" = 1 ] || fail "encompass to 1 item"

# grade it good; expect implicit credit message for a
curl -s -X POST "$B/api/quiz-grade/demo/$QID" -H 'Content-Type: application/json' \
  -d '{"item":1,"grade":"good"}' | jpy "'\n'.join(d['messages'])" | grep -q "implicit credit" \
  || fail "implicit credit"

# error handling + traversal guard
[ "$(code "$B/api/node/demo/nope")" = 404 ] || fail "404 on bad node"
[ "$(code "$B/media/demo/../../../etc/passwd")" = 404 ] || fail "traversal guard"

# base64 evidence upload on a fresh graph node
st node new demo c --minutes 4 >/dev/null
EV=$(printf hello | base64)
curl -s -X POST "$B/api/done/demo/c" -H 'Content-Type: application/json' \
  -d "{\"all\":true,\"evidence\":[{\"name\":\"proof.txt\",\"data\":\"$EV\"}]}" \
  | jpy "d['learned']" | grep -q True || fail "done via web"
[ -f "$TMP"/state/demo/evidence/c/_node/proof.txt ] || fail "evidence stored"

# --- authoring (visual builder endpoints) -----------------------------------
# create a fresh subject
curl -s -X POST "$B/api/graph-new" -H 'Content-Type: application/json' \
  -d '{"name":"lang"}' | jpy "d['graph']" | grep -q lang || fail "graph-new"
[ -d "$TMP/graphs/lang/nodes" ] || fail "graph dir created"

# create an entry node with structured content
curl -s -X POST "$B/api/node-new/lang" -H 'Content-Type: application/json' \
  -d '{"id":"alpha","title":"Alphabet","minutes":8,"tags":["a1"],"requires":[],"intro":"letters","kps":[{"name":"vowels","worked":"a e i o u","problems":["name a vowel","spell cat"]}]}' \
  | jpy "d['created']" | grep -q True || fail "node-new"
[ -f "$TMP/graphs/lang/nodes/alpha.md" ] || fail "node file written"

# it round-trips through the parser (CLI agrees)
[ "$(st node list lang | wc -l | tr -d ' ')" = 1 ] || fail "authored node not parseable"
[ "$(st node problems lang alpha | wc -l | tr -d ' ')" = 2 ] || fail "authored problems"

# create a dependent node, then confirm edit-load returns candidates+content
curl -s -X POST "$B/api/node-new/lang" -H 'Content-Type: application/json' \
  -d '{"id":"words","title":"Words","requires":["alpha"],"intro":"x","kps":[{"name":"k","worked":"w","problems":["p"]}]}' \
  | jpy "d['created']" | grep -q True || fail "dependent node-new"
curl -s "$B/api/node-edit/lang/words" | jpy "d['requires'][0]" | grep -q alpha || fail "edit-load requires"
curl -s "$B/api/node-edit/lang/words" | jpy "[c['id'] for c in d['candidates']]" | grep -q alpha || fail "edit-load candidates"

# cycle is rejected and reverted
curl -s -X POST "$B/api/node-save/lang/alpha" -H 'Content-Type: application/json' \
  -d '{"title":"Alphabet","requires":["words"],"intro":"x","kps":[{"name":"k","worked":"w","problems":["p"]}]}' \
  | jpy "d.get('error','')" | grep -qi "loop" || fail "cycle not rejected"
# alpha still has no prereqs after the revert
curl -s "$B/api/node-edit/lang/alpha" | jpy "len(d['requires'])" | grep -q 0 || fail "cycle not reverted"

# unknown prerequisite rejected
curl -s -X POST "$B/api/node-new/lang" -H 'Content-Type: application/json' \
  -d '{"id":"z","title":"Z","requires":["ghost"],"kps":[]}' \
  | jpy "d.get('error','')" | grep -qi "unknown prerequisite" || fail "unknown prereq not rejected"

# delete unlinks dependents
curl -s -X POST "$B/api/node-delete/lang/alpha" -H 'Content-Type: application/json' -d '{}' \
  | jpy "d['unlinked']" | grep -q words || fail "delete unlink"
[ ! -f "$TMP/graphs/lang/nodes/alpha.md" ] || fail "node not deleted"
st check lang >/dev/null 2>&1 || fail "graph invalid after delete"

echo PASS
