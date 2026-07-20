"""Learning actions shared by the CLI and the web server.

These wrap the domain logic (validate, mark problems done, award xp, graduate
a node into spaced repetition) so `st-done` and `skilltree.web` behave
identically. Unlike the CLI helpers in `store`, these raise ActionError on
bad input instead of exiting, so a long-running server can report the error
and keep going.
"""

from . import graph as graphmod
from . import scheduler
from . import store
from . import xp


class ActionError(Exception):
    pass


def resolve_targets(node, done, problems=None, all_=False):
    """Which problem ids to complete now. Raises ActionError on bad input."""
    all_pids = node.problem_ids()
    if all_:
        targets = [p for p in all_pids if p not in done]
        if not targets and all_pids:
            raise ActionError("all problems already complete")
        return targets
    if problems:
        targets = []
        for p in problems:
            if p not in all_pids:
                raise ActionError("no such problem %r (available: %s)"
                                  % (p, ", ".join(all_pids) or "none"))
            if p in done:
                raise ActionError("problem %s already complete" % p)
            targets.append(p)
        return targets
    if not all_pids:
        return []  # a node with no problems: completing the node itself
    remaining = ", ".join(p for p in all_pids if p not in done)
    raise ActionError("say which problems (%s), or complete all" % remaining)


def complete(root, cfg, nodes, progress, graph, node_id,
             problems=None, all_=False, evidence=None, note="",
             force=False, today=None):
    """Complete lesson problems for one node; graduate it if fully done.

    `evidence` is a list of source file paths to copy in (basename kept).
    Mutates `progress`, appends to the xp ledger, and saves progress.
    Returns a result dict: messages, targets, evidence, gained, learned,
    unlocked, srs.
    """
    if today is None:
        today = store.today()
    if node_id not in nodes:
        raise ActionError("no such node: %s" % node_id)
    node = nodes[node_id]
    ns = store.node_state(progress, node_id)

    if store.is_learned(progress, node_id):
        raise ActionError("%s is already learned (review it instead)"
                          % node_id)
    status = graphmod.status_of(nodes, progress)[node_id]
    if status == "not-ready" and not force:
        missing = [r for r in node.requires
                   if not store.is_learned(progress, r)]
        raise ActionError("%s is not ready to learn - unlearned "
                          "prerequisites: %s" % (node_id, ", ".join(missing)))

    done = ns.setdefault("problems_done", {})
    targets = resolve_targets(node, done, problems=problems, all_=all_)

    stored = []
    if evidence:
        pid = targets[0] if len(targets) == 1 else None
        stored = store.copy_evidence(root, graph, node_id, pid, evidence)

    all_pids = node.problem_ids()
    share, remainder = xp.problem_share(node.minutes, len(all_pids))
    result = {"messages": [], "targets": [], "evidence": stored,
              "gained": 0, "learned": False, "unlocked": [], "srs": None}

    for p in targets:
        entry = {"at": store.now_stamp()}
        if note:
            entry["note"] = note
        if stored:
            entry["evidence"] = stored
        done[p] = entry
        xp.award(root, graph, node_id, "problem", share, p)
        result["gained"] += share
        result["targets"].append(p)
        result["messages"].append("done: %s %s (+%d xp)"
                                   % (node_id, p, share))

    if all(p in done for p in all_pids):
        ns["learned_at"] = store.now_stamp()
        ns["srs"] = scheduler.init_srs(today)
        xp.award(root, graph, node_id, "lesson", remainder, "lesson complete")
        result["gained"] += remainder
        result["learned"] = True
        result["srs"] = ns["srs"]
        result["messages"].append(
            "%s learned! first review due %s (+%d xp total)"
            % (node_id, ns["srs"]["due"], result["gained"]))
        statuses = graphmod.status_of(nodes, progress)
        unlocked = sorted(nid for nid, s in statuses.items()
                          if s == "ready" and node_id in nodes[nid].requires)
        result["unlocked"] = unlocked
        if unlocked:
            result["messages"].append("now ready to learn: %s"
                                       % ", ".join(unlocked))

    store.save_progress(root, graph, progress)
    return result
