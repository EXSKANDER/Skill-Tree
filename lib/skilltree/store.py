"""Data layout and persistence.

Everything lives in plain files under a single root directory:

    .skilltree/config.json      tool configuration
    graphs/<graph>/nodes/*.md   content: one markdown file per topic node
    graphs/<graph>/media/       media referenced by lessons
    state/<graph>/progress.json per-node learning + scheduling state
    state/<graph>/quizzes/      generated review quizzes (sheet + manifest)
    state/<graph>/evidence/     submitted proof-of-work files
    state/xp.tsv                append-only xp ledger

Content under graphs/ is the shareable course; everything under state/ is
one learner's progress. Both are plain text and tracked by git.
"""

import datetime
import json
import os
import shutil
import sys

MARKER = ".skilltree"

DEFAULT_CONFIG = {
    "daily_goal": 30,       # xp per day (1 xp ~= 1 focused minute)
    "review_minutes": 2,    # base xp for one review problem
    "quiz_max": 8,          # max items per review quiz
    "encompass": True,      # collapse due prereqs into due descendants
    "default_minutes": 20,  # default xp value of a new node's lesson
}


def die(msg, code=1):
    print("error: %s" % msg, file=sys.stderr)
    sys.exit(code)


def today():
    """Current date; override with ST_TODAY=YYYY-MM-DD (used by tests)."""
    t = os.environ.get("ST_TODAY")
    if t:
        return datetime.date.fromisoformat(t)
    return datetime.date.today()


def now_stamp():
    return "%sT%s" % (today().isoformat(),
                      datetime.datetime.now().strftime("%H:%M:%S"))


def find_root():
    """Locate the skill-tree root: $ST_ROOT, or walk up from cwd."""
    env = os.environ.get("ST_ROOT")
    if env:
        p = os.path.abspath(env)
        if os.path.isdir(os.path.join(p, MARKER)):
            return p
        die("ST_ROOT=%s is not a skill-tree root (missing %s/)" % (env, MARKER))
    d = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(d, MARKER)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            die("not inside a skill tree (run `st init` first)")
        d = parent


def config(root):
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(root, MARKER, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


def save_config(root, cfg):
    write_atomic(os.path.join(root, MARKER, "config.json"),
                 json.dumps(cfg, indent=2, sort_keys=True) + "\n")


def graph_dir(root, graph):
    return os.path.join(root, "graphs", graph)


def nodes_dir(root, graph):
    return os.path.join(graph_dir(root, graph), "nodes")


def state_dir(root, graph):
    return os.path.join(root, "state", graph)


def list_graphs(root):
    gdir = os.path.join(root, "graphs")
    if not os.path.isdir(gdir):
        return []
    return sorted(g for g in os.listdir(gdir)
                  if os.path.isdir(os.path.join(gdir, g, "nodes")))


def require_graph(root, graph):
    if not os.path.isdir(nodes_dir(root, graph)):
        die("no such graph: %s (try `st graph list`)" % graph)


def node_files(root, graph):
    ndir = nodes_dir(root, graph)
    if not os.path.isdir(ndir):
        return []
    return sorted(os.path.join(ndir, f) for f in os.listdir(ndir)
                  if f.endswith(".md"))


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def load_progress(root, graph):
    path = os.path.join(state_dir(root, graph), "progress.json")
    if not os.path.exists(path):
        return {"nodes": {}}
    with open(path) as f:
        return json.load(f)


def save_progress(root, graph, progress):
    path = os.path.join(state_dir(root, graph), "progress.json")
    write_atomic(path, json.dumps(progress, indent=2, sort_keys=True) + "\n")


def node_state(progress, nid):
    return progress["nodes"].setdefault(nid, {})


def is_learned(progress, nid):
    return bool(progress["nodes"].get(nid, {}).get("learned_at"))


# --- xp ledger: one TSV row per event, append-only ---------------------------

LEDGER_COLS = ("at", "graph", "node", "event", "xp", "note")


def ledger_path(root):
    return os.path.join(root, "state", "xp.tsv")


def append_ledger(root, graph, node, event, amount, note=""):
    path = ledger_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("\t".join(LEDGER_COLS) + "\n")
        row = (now_stamp(), graph, node or "-", event, str(amount),
               note.replace("\t", " "))
        f.write("\t".join(row) + "\n")


def read_ledger(root):
    path = ledger_path(root)
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        header = f.readline()
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            out.append({
                "at": parts[0], "graph": parts[1], "node": parts[2],
                "event": parts[3], "xp": int(parts[4]),
                "note": parts[5] if len(parts) > 5 else "",
            })
    return out


# --- evidence ----------------------------------------------------------------

def copy_evidence(root, graph, node, problem, files):
    """Copy proof-of-work files (any media type) into the state tree.

    Returns the list of stored paths, relative to root.
    """
    sub = problem if problem else "_node"
    dest = os.path.join(state_dir(root, graph), "evidence", node, sub)
    os.makedirs(dest, exist_ok=True)
    stored = []
    for src in files:
        if not os.path.isfile(src):
            die("evidence file not found: %s" % src)
        name = os.path.basename(src)
        target = os.path.join(dest, name)
        if os.path.exists(target):
            stem, ext = os.path.splitext(name)
            n = 1
            while os.path.exists(target):
                target = os.path.join(dest, "%s.%d%s" % (stem, n, ext))
                n += 1
        shutil.copy2(src, target)
        stored.append(os.path.relpath(target, root))
    return stored
