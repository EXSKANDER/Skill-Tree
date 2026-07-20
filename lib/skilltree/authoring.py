"""Content authoring: create graphs, write/delete nodes, manage edges.

Used by the web builder (and available to any future CLI). Every function
writes the same plain files the rest of the toolkit reads, and validates
the graph stays sound (known prerequisites, no self-edges, no cycles),
reverting the change if it would not.

Raises ActionError (from skilltree.actions) on bad input so callers can
report the message without the process exiting.
"""

import os

from . import actions
from . import graph as graphmod
from . import node as nodemod
from . import store

ActionError = actions.ActionError


def create_graph(root, name):
    name = (name or "").strip()
    if not nodemod.ID_RE.match(name):
        raise ActionError("bad graph name %r (use lowercase letters, "
                          "digits, and hyphens)" % name)
    if os.path.isdir(store.graph_dir(root, name)):
        raise ActionError("graph %s already exists" % name)
    os.makedirs(store.nodes_dir(root, name))
    os.makedirs(os.path.join(store.graph_dir(root, name), "media"))
    return {"graph": name}


def _validate_requires(nodes, nid, requires):
    seen = []
    for r in requires:
        r = r.strip()
        if not r or r in seen:
            continue
        if r == nid:
            raise ActionError("a lesson cannot be its own prerequisite")
        if r not in nodes:
            raise ActionError("unknown prerequisite: %s" % r)
        seen.append(r)
    return seen


def save_node(root, graph, data, creating):
    """Create or overwrite one node from a structured dict (node.render).

    On create, fails if the id is taken. Validates prerequisites exist and
    that the resulting graph is acyclic, reverting the file otherwise.
    Returns {id, created, warnings}.
    """
    store.require_graph(root, graph)
    nid = (data.get("id") or "").strip()
    if not nodemod.ID_RE.match(nid):
        raise ActionError("bad lesson id %r (use lowercase letters, digits, "
                          "and hyphens, e.g. adding-fractions)" % nid)
    path = os.path.join(store.nodes_dir(root, graph), nid + ".md")
    existed = os.path.exists(path)
    if creating and existed:
        raise ActionError("a lesson with id %r already exists" % nid)
    if not creating and not existed:
        raise ActionError("no such lesson: %s" % nid)

    nodes, _ = graphmod.load(root, graph)
    data = dict(data)
    data["requires"] = _validate_requires(nodes, nid, data.get("requires", []))
    text = nodemod.render(data)  # raises NodeError on a bad id

    prior = None
    if existed:
        with open(path) as f:
            prior = f.read()
    store.write_atomic(path, text)

    # revalidate the whole graph; revert if this write broke it
    nodes2, errors = graphmod.load(root, graph)
    errors += graphmod.check(nodes2)
    cyclic = [e for e in errors if "cycle" in e]
    if cyclic:
        if prior is None:
            os.remove(path)
        else:
            store.write_atomic(path, prior)
        raise ActionError("that would create a prerequisite loop (%s); "
                          "change reverted" % cyclic[0])
    warnings = [e for e in errors if nid in e]
    return {"id": nid, "created": not existed, "warnings": warnings}


def delete_node(root, graph, nid):
    """Delete a node, strip it from other nodes' prerequisites, and drop its
    progress. Returns {deleted, unlinked: [ids whose edges were removed]}."""
    store.require_graph(root, graph)
    path = os.path.join(store.nodes_dir(root, graph), nid + ".md")
    if not os.path.exists(path):
        raise ActionError("no such lesson: %s" % nid)

    nodes, _ = graphmod.load(root, graph)
    unlinked = []
    for other_id, other in nodes.items():
        if other_id != nid and nid in other.requires:
            nodemod.set_requires(other.path,
                                 [r for r in other.requires if r != nid])
            unlinked.append(other_id)

    os.remove(path)
    progress = store.load_progress(root, graph)
    if nid in progress["nodes"]:
        del progress["nodes"][nid]
        store.save_progress(root, graph, progress)
    return {"deleted": nid, "unlinked": sorted(unlinked)}
