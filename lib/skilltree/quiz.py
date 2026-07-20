"""Review quizzes: spaced repetition + encompassment + interleaving.

How a quiz is built (the manual-phase answer to Math Academy's review system):

  1. DUE       collect every learned node whose SM-2 due date has arrived,
               most overdue first.
  2. ENCOMPASS advanced skills implicitly practice their prerequisites, so
               if a due node is a (transitive) prerequisite of another due
               node, drop it and let the advanced node "cover" it. The quiz
               is the smallest set of tasks encompassing all due review.
  3. PICK      take ONE problem per surviving node, avoiding the problem
               used at that node's previous review.
  4. INTERLEAVE order the items so that no two adjacent problems come from
               directly-linked nodes (non-interference: mixed practice with
               no obvious order). This is macro-interleaving across topics;
               lessons keep their minimal doses of blocked practice.
  5. GRADE     each item is answered again/hard/good/easy and feeds SM-2
               for its node. A passing grade also gives implicit credit
               (capped at "good", no xp) to every node the item covers; a
               failing grade leaves covered nodes due. Failing the same
               node twice in a row queues remedial review of its direct
               prerequisites (due immediately).

The quiz is written as a plain markdown sheet (do it on paper, in an editor,
wherever) plus a JSON manifest that maps item numbers back to nodes, so the
sheet itself never reveals which topic an item drills.
"""

import datetime
import json
import os
import random

from . import graph as graphmod
from . import scheduler
from . import store
from . import xp


def quizzes_dir(root, g):
    return os.path.join(store.state_dir(root, g), "quizzes")


def quiz_path(root, g, qid):
    return os.path.join(quizzes_dir(root, g), qid + ".json")


def load_quiz(root, g, qid):
    path = quiz_path(root, g, qid)
    if not os.path.exists(path):
        store.die("no such quiz: %s (try `st quiz list %s`)" % (qid, g))
    with open(path) as f:
        return json.load(f)


def save_quiz(root, g, quiz):
    store.write_atomic(quiz_path(root, g, quiz["id"]),
                       json.dumps(quiz, indent=2, sort_keys=True) + "\n")


def list_quizzes(root, g):
    d = quizzes_dir(root, g)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def due_list(nodes, progress, today):
    """[(nid, days_overdue)] for learned nodes due today or earlier."""
    out = []
    for nid in nodes:
        srs = progress["nodes"].get(nid, {}).get("srs")
        if not srs:
            continue
        due = datetime.date.fromisoformat(srs["due"])
        if due <= today:
            out.append((nid, (today - due).days))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def collapse(nodes, due_ids):
    """Minimal covering set: drop due nodes encompassed by due descendants.

    Returns (kept_ids, {kept_id: [covered_ids...]}). Most advanced nodes
    (largest prerequisite closure) are kept in preference.
    """
    anc = {d: graphmod.ancestors(nodes, d) for d in due_ids}
    order = sorted(due_ids, key=lambda d: (-len(anc[d]), d))
    kept, covers = [], {}
    for d in order:
        host = next((k for k in kept if d in anc[k]), None)
        if host is not None:
            covers.setdefault(host, []).append(d)
        else:
            kept.append(d)
    return kept, covers


def pick_problem(node, srs, rng):
    """One problem id+text; avoids the problem served last time."""
    pids = node.problem_ids()
    if not pids:
        return None, ("From memory, demonstrate the core skill of "
                      "“%s” with an example of your own." % node.title)
    avoid = srs.get("last_problem")
    candidates = [p for p in pids if p != avoid] or pids
    pid = rng.choice(candidates)
    return pid, node.problem_text(pid)


def interleave(items, nodes, rng):
    """Shuffle with the constraint that adjacent items are not neighbours
    in the graph (no shared prerequisite edge), so similar material never
    runs back-to-back."""
    remaining = items[:]
    rng.shuffle(remaining)
    out = []
    prev = None
    while remaining:
        if prev is None:
            candidates = remaining
        else:
            candidates = [it for it in remaining
                          if not graphmod.adjacent(nodes, it["node"],
                                                   prev["node"])]
            if not candidates:
                candidates = remaining
        pick = candidates[0]
        out.append(pick)
        remaining.remove(pick)
        prev = pick
    return out


def make(root, g, nodes, progress, cfg, today, max_items=None,
         encompass=None, rng=None):
    """Build a new quiz. Returns (quiz, sheet_text) or (None, reason)."""
    if rng is None:
        seed = os.environ.get("ST_SEED")
        rng = random.Random(seed if seed else None)
    if max_items is None:
        max_items = int(cfg.get("quiz_max", 8))
    if encompass is None:
        encompass = bool(cfg.get("encompass", True))

    due = due_list(nodes, progress, today)
    if not due:
        return None, "nothing is due for review"
    overdue = dict(due)
    due_ids = [d for d, _ in due]

    if encompass:
        kept, covers = collapse(nodes, due_ids)
    else:
        kept, covers = due_ids[:], {}
    kept.sort(key=lambda n: (-overdue[n], n))
    kept = kept[:max_items]
    covers = {k: sorted(covers.get(k, [])) for k in kept}

    items = []
    for nid in kept:
        srs = store.node_state(progress, nid)["srs"]
        pid, text = pick_problem(nodes[nid], srs, rng)
        srs["last_problem"] = pid
        items.append({"node": nid, "problem": pid, "text": text,
                      "covers": covers[nid], "grade": None})
    items = interleave(items, nodes, rng)
    for n, it in enumerate(items, 1):
        it["n"] = n

    seq = 1
    while "%s-%d" % (today.isoformat(), seq) in list_quizzes(root, g):
        seq += 1
    quiz = {
        "id": "%s-%d" % (today.isoformat(), seq),
        "graph": g,
        "created": today.isoformat(),
        "items": items,
        "done": False,
    }
    sheet = render_sheet(quiz)
    save_quiz(root, g, quiz)
    store.write_atomic(os.path.join(quizzes_dir(root, g),
                                    quiz["id"] + ".md"), sheet)
    store.save_progress(root, g, progress)
    return quiz, sheet


def render_sheet(quiz):
    lines = [
        "# Review quiz %s (graph: %s)" % (quiz["id"], quiz["graph"]),
        "",
        "Mixed practice: items are in no particular order and their topics",
        "are deliberately not labelled. Work each one without looking back",
        "at the lessons unless completely stuck.",
        "",
    ]
    for it in quiz["items"]:
        lines.append("%d. %s" % (it["n"], it["text"]))
        lines.append("")
    lines += [
        "---",
        "Grade each item when done:",
        "",
        "    st quiz grade %s %s <item> <again|hard|good|easy>"
        % (quiz["graph"], quiz["id"]),
        "",
    ]
    return "\n".join(lines)


def apply_review(root, g, nodes, progress, nid, grade, today, cfg,
                 give_xp=True, source="review"):
    """Grade one node review: SM-2 update, history, xp, remedial check.

    Returns (messages, xp_gained). Caller saves progress.
    """
    ns = store.node_state(progress, nid)
    srs = ns.get("srs")
    if not srs:
        store.die("%s is not learned yet - nothing to review" % nid)
    scheduler.review(srs, grade, today)
    ns.setdefault("history", []).append({
        "at": today.isoformat(), "grade": grade,
        "ivl": srs["ivl"], "source": source,
    })
    msgs = ["%s: %s -> next review %s (interval %dd, ease %.2f)"
            % (nid, grade, srs["due"], srs["ivl"], srs["ease"])]
    gained = 0
    if give_xp:
        gained = xp.review_award(cfg, grade)
        xp.award(root, g, nid, "review", gained, "%s (%s)" % (grade, source))

    if srs.get("consec_again", 0) >= 2:
        remedial = [r for r in nodes[nid].requires
                    if r in nodes and store.is_learned(progress, r)]
        for r in remedial:
            store.node_state(progress, r)["srs"]["due"] = today.isoformat()
        srs["consec_again"] = 0
        if remedial:
            msgs.append("%s failed twice in a row -> remedial review due "
                        "now for: %s" % (nid, ", ".join(remedial)))
    return msgs, gained


def grade_item(root, g, nodes, progress, quiz, item_no, grade, today, cfg):
    """Grade quiz item item_no; propagates implicit credit to covered nodes."""
    it = next((i for i in quiz["items"] if i["n"] == item_no), None)
    if it is None:
        store.die("quiz %s has no item %d" % (quiz["id"], item_no))
    if it["grade"] is not None:
        store.die("item %d is already graded (%s)" % (item_no, it["grade"]))

    msgs, _ = apply_review(root, g, nodes, progress, it["node"], grade,
                           today, cfg, source="quiz:%s" % quiz["id"])
    it["grade"] = grade

    for covered in it.get("covers", []):
        if grade == "again":
            msgs.append("%s: no implicit credit (covering item failed), "
                        "still due" % covered)
            continue
        capped = "good" if grade == "easy" else grade
        m, _ = apply_review(root, g, nodes, progress, covered, capped, today,
                            cfg, give_xp=False,
                            source="quiz:%s implicit via %s"
                            % (quiz["id"], it["node"]))
        msgs.append("implicit credit: " + m[0])
        msgs.extend(m[1:])

    if all(i["grade"] is not None for i in quiz["items"]):
        quiz["done"] = True
        grades = [i["grade"] for i in quiz["items"]]
        item_total = sum(xp.review_award(cfg, gr) for gr in grades)
        if all(gr in ("good", "easy") for gr in grades):
            bonus = xp.quiz_bonus(item_total)
            xp.award(root, g, None, "quiz-bonus", bonus,
                     "perfect quiz %s" % quiz["id"])
            msgs.append("quiz %s complete - perfect! +%d bonus xp"
                        % (quiz["id"], bonus))
        else:
            msgs.append("quiz %s complete" % quiz["id"])

    save_quiz(root, g, quiz)
    store.save_progress(root, g, progress)
    return msgs
