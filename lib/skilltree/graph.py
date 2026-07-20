"""Knowledge-graph operations: loading, validation, mastery statuses.

Edges live in each node's `requires:` front matter (single source of truth).
A node's status is derived, never stored:

    learned    the learner completed its lesson (progress has learned_at)
    ready      not learned, and every prerequisite is learned
    not-ready  not learned, and some prerequisite is not learned
"""

import sys

from . import node as nodemod
from . import store


def load(root, graph):
    """Parse every node file. Returns (nodes: {id: Node}, errors: [str])."""
    nodes, errors = {}, []
    for path in store.node_files(root, graph):
        try:
            n = nodemod.parse(path)
        except nodemod.NodeError as e:
            errors.append("%s: %s" % (path, e))
            continue
        if n.id in nodes:
            errors.append("%s: duplicate id %s" % (path, n.id))
            continue
        nodes[n.id] = n
    return nodes, errors


def load_or_die(root, graph):
    store.require_graph(root, graph)
    nodes, errors = load(root, graph)
    for e in errors:
        print("error: %s" % e, file=sys.stderr)
    if errors:
        store.die("graph %s has invalid node files" % graph)
    return nodes


def check(nodes):
    """Structural validation. Returns a list of error strings."""
    errors = []
    for n in nodes.values():
        for r in n.requires:
            if r == n.id:
                errors.append("%s: requires itself" % n.id)
            elif r not in nodes:
                errors.append("%s: requires unknown node %r" % (n.id, r))
    # cycle detection via Kahn's algorithm on known edges
    indeg = {nid: 0 for nid in nodes}
    for n in nodes.values():
        for r in n.requires:
            if r in nodes and r != n.id:
                indeg[n.id] += 1
    queue = [nid for nid, d in indeg.items() if d == 0]
    seen = 0
    dependents = build_dependents(nodes)
    while queue:
        nid = queue.pop()
        seen += 1
        for child in dependents.get(nid, []):
            indeg[child] -= 1
            if indeg[child] == 0:
                queue.append(child)
    if seen < len(nodes):
        cyclic = sorted(nid for nid, d in indeg.items() if d > 0)
        errors.append("dependency cycle involving: %s" % ", ".join(cyclic))
    return errors


def build_dependents(nodes):
    """Map prereq id -> [ids of nodes that require it]."""
    out = {}
    for n in nodes.values():
        for r in n.requires:
            out.setdefault(r, []).append(n.id)
    return out


def ancestors(nodes, nid):
    """Transitive prerequisites of nid (excluding nid itself)."""
    seen = set()
    stack = [r for r in nodes[nid].requires if r in nodes]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(r for r in nodes[cur].requires
                     if r in nodes and r not in seen)
    return seen


def adjacent(nodes, a, b):
    """True if a and b share a direct prerequisite edge (either direction)."""
    return b in nodes[a].requires or a in nodes[b].requires


def status_of(nodes, progress):
    """Return {id: 'learned' | 'ready' | 'not-ready'}."""
    out = {}
    for nid, n in nodes.items():
        if store.is_learned(progress, nid):
            out[nid] = "learned"
        elif all(store.is_learned(progress, r) for r in n.requires):
            out[nid] = "ready"
        else:
            out[nid] = "not-ready"
    return out
