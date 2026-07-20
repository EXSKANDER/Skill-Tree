"""Local web interface: a thin HTTP layer over the same library the CLI uses.

Zero dependencies (Python stdlib only) and zero outbound network: the server
binds to localhost, and the single-page front-end under web/ is fully
self-contained (no CDNs, no external fonts or scripts). It reads and writes
exactly the same plain files as the `st` tools, so the CLI and the browser
are two front-ends over one source of truth.

Run it with `st web` (see bin/st-web).
"""

import base64
import json
import os
import posixpath
import shutil
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import actions
from . import graph as graphmod
from . import node as nodemod
from . import quiz as quizmod
from . import scheduler
from . import store
from . import xp

WEB_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "web")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav",
    ".mp4": "video/mp4", ".webm": "video/webm", ".m4a": "audio/mp4",
    ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}


class ApiError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


# --- payload builders --------------------------------------------------------

def graph_payload(root, g):
    store.require_graph(root, g)
    nodes, errors = graphmod.load(root, g)
    errors += graphmod.check(nodes)
    progress = store.load_progress(root, g)
    statuses = graphmod.status_of(nodes, progress)
    today = store.today()
    out_nodes = []
    for nid in sorted(nodes):
        n = nodes[nid]
        ns = progress["nodes"].get(nid, {})
        srs = ns.get("srs") or {}
        done = len(ns.get("problems_done", {}))
        total = len(n.problem_ids())
        due = None
        if srs.get("due"):
            due = (scheduler.datetime.date.fromisoformat(srs["due"]) <= today)
        out_nodes.append({
            "id": nid, "title": n.title, "requires": n.requires,
            "minutes": n.minutes, "tags": n.tags, "status": statuses[nid],
            "problems_done": done, "problems_total": total,
            "kps": len(n.kps), "due": srs.get("due"), "is_due": bool(due),
        })
    return {"graph": g, "nodes": out_nodes, "errors": errors}


def node_payload(root, g, nid):
    store.require_graph(root, g)
    path = os.path.join(store.nodes_dir(root, g), nid + ".md")
    if not os.path.exists(path):
        raise ApiError("no such node: %s" % nid, 404)
    n = nodemod.parse(path)
    progress = store.load_progress(root, g)
    nodes, _ = graphmod.load(root, g)
    statuses = graphmod.status_of(nodes, progress)
    ns = progress["nodes"].get(nid, {})
    done = ns.get("problems_done", {})
    kps = []
    for ki, (title, problems) in enumerate(n.kps, 1):
        items = []
        for pi, text in enumerate(problems, 1):
            pid = "%d.%d" % (ki, pi)
            entry = done.get(pid) or {}
            items.append({
                "id": pid, "text": text, "done": pid in done,
                "at": entry.get("at"), "note": entry.get("note"),
                "evidence": entry.get("evidence", []),
            })
        kps.append({"title": title, "problems": items})
    with open(path) as f:
        body = f.read()
    return {
        "id": nid, "graph": g, "title": n.title, "requires": n.requires,
        "minutes": n.minutes, "tags": n.tags, "status": statuses.get(nid),
        "learned_at": ns.get("learned_at"), "srs": ns.get("srs"),
        "raw": body, "kps": kps,
        "requires_status": {r: statuses.get(r, "unknown") for r in n.requires},
    }


def dashboard_payload(root):
    cfg = store.config(root)
    graphs = []
    for g in store.list_graphs(root):
        nodes, _ = graphmod.load(root, g)
        progress = store.load_progress(root, g)
        statuses = graphmod.status_of(nodes, progress)
        counts = {"ready": 0, "learned": 0, "not-ready": 0}
        for s in statuses.values():
            counts[s] = counts.get(s, 0) + 1
        due = len(quizmod.due_list(nodes, progress, store.today()))
        graphs.append({"name": g, "total": len(nodes), "counts": counts,
                       "due": due})
    return {
        "graphs": graphs,
        "xp": xp.summary(root, cfg, store.today()),
        "config": cfg,
    }


def due_payload(root, g):
    store.require_graph(root, g)
    nodes, _ = graphmod.load(root, g)
    progress = store.load_progress(root, g)
    out = []
    for nid, overdue in quizmod.due_list(nodes, progress, store.today()):
        srs = progress["nodes"][nid]["srs"]
        out.append({"id": nid, "title": nodes[nid].title,
                    "due": srs["due"], "overdue": overdue})
    return {"graph": g, "due": out}


def quizzes_payload(root, g):
    store.require_graph(root, g)
    out = []
    for qid in quizmod.list_quizzes(root, g):
        q = quizmod.load_quiz(root, g, qid)
        graded = sum(1 for i in q["items"] if i["grade"] is not None)
        out.append({"id": qid, "graded": graded, "total": len(q["items"]),
                    "done": q["done"]})
    return {"graph": g, "quizzes": out}


# --- action handlers ---------------------------------------------------------

def save_uploads(uploads, tmpdir):
    """Write [{name, data(base64)}] into tmpdir; return list of paths."""
    paths = []
    for up in uploads or []:
        name = os.path.basename(up.get("name") or "evidence")
        data = base64.b64decode(up.get("data", ""))
        path = os.path.join(tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        paths.append(path)
    return paths


def do_done(root, g, nid, body):
    cfg = store.config(root)
    nodes, _ = graphmod.load(root, g)
    progress = store.load_progress(root, g)
    tmpdir = tempfile.mkdtemp(prefix="st-web-")
    try:
        evidence = save_uploads(body.get("evidence"), tmpdir)
        result = actions.complete(
            root, cfg, nodes, progress, g, nid,
            problems=body.get("problems") or None,
            all_=bool(body.get("all")), evidence=evidence,
            note=body.get("note", ""), force=bool(body.get("force")))
    except actions.ActionError as e:
        raise ApiError(str(e))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return result


def do_quiz_new(root, g, body):
    cfg = store.config(root)
    nodes, _ = graphmod.load(root, g)
    progress = store.load_progress(root, g)
    encompass = body.get("encompass")
    q, sheet = quizmod.make(root, g, nodes, progress, cfg, store.today(),
                            max_items=body.get("max"),
                            encompass=encompass if encompass is not None
                            else None)
    if q is None:
        raise ApiError(sheet)
    return {"quiz": q, "sheet": sheet}


def do_quiz_grade(root, g, qid, body):
    cfg = store.config(root)
    nodes, _ = graphmod.load(root, g)
    progress = store.load_progress(root, g)
    q = quizmod.load_quiz(root, g, qid)
    item = int(body["item"])
    grade = body["grade"]
    if grade not in scheduler.GRADES:
        raise ApiError("bad grade: %s" % grade)
    it = next((i for i in q["items"] if i["n"] == item), None)
    if it is None:
        raise ApiError("no such item %d" % item, 404)
    tmpdir = tempfile.mkdtemp(prefix="st-web-")
    try:
        uploads = save_uploads(body.get("evidence"), tmpdir)
        if uploads:
            store.copy_evidence(root, g, it["node"],
                                "quiz-%s-%d" % (qid, item), uploads)
        msgs = quizmod.grade_item(root, g, nodes, progress, q, item, grade,
                                  store.today(), cfg)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {"messages": msgs, "quiz": q}


def do_review(root, g, nid, body):
    cfg = store.config(root)
    nodes, _ = graphmod.load(root, g)
    progress = store.load_progress(root, g)
    grade = body["grade"]
    if grade not in scheduler.GRADES:
        raise ApiError("bad grade: %s" % grade)
    if nid not in nodes:
        raise ApiError("no such node: %s" % nid, 404)
    msgs, gained = quizmod.apply_review(root, g, nodes, progress, nid, grade,
                                        store.today(), cfg)
    store.save_progress(root, g, progress)
    return {"messages": msgs, "gained": gained}


def do_goal(root, body):
    cfg = store.config(root)
    cfg["daily_goal"] = int(body["value"])
    store.save_config(root, cfg)
    return {"daily_goal": cfg["daily_goal"]}


# --- HTTP plumbing -----------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "skilltree-web"

    @property
    def root(self):
        return self.server.st_root

    def log_message(self, fmt, *args):
        if self.server.st_verbose:
            super().log_message(fmt, *args)

    def _send(self, code, ctype, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj).encode("utf-8"))

    def _error(self, code, message):
        self._json({"error": message}, code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("invalid JSON body")

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        try:
            if path in STATIC:
                return self._serve_static(path)
            if path.startswith("/media/"):
                return self._serve_media(path)
            if path.startswith("/api/"):
                return self._api_get(path)
        except ApiError as e:
            return self._error(e.code, str(e))
        except Exception as e:  # noqa: keep server alive on any handler bug
            return self._error(500, "%s" % e)
        self._error(404, "not found: %s" % path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)
        try:
            body = self._read_body()
            result = self._api_post(path, body)
            return self._json(result)
        except ApiError as e:
            return self._error(e.code, str(e))
        except Exception as e:  # noqa: keep server alive on any handler bug
            return self._error(500, "%s" % e)

    # --- routing ---

    def _api_get(self, path):
        parts = path.strip("/").split("/")[1:]  # drop leading 'api'
        if parts == ["dashboard"]:
            return self._json(dashboard_payload(self.root))
        if len(parts) == 2 and parts[0] == "graph":
            return self._json(graph_payload(self.root, parts[1]))
        if len(parts) == 3 and parts[0] == "node":
            return self._json(node_payload(self.root, parts[1], parts[2]))
        if len(parts) == 2 and parts[0] == "due":
            return self._json(due_payload(self.root, parts[1]))
        if len(parts) == 2 and parts[0] == "quizzes":
            return self._json(quizzes_payload(self.root, parts[1]))
        if len(parts) == 3 and parts[0] == "quiz":
            return self._json(quizmod.load_quiz(self.root, parts[1], parts[2]))
        raise ApiError("unknown endpoint: %s" % path, 404)

    def _api_post(self, path, body):
        parts = path.strip("/").split("/")[1:]
        if len(parts) == 3 and parts[0] == "done":
            return do_done(self.root, parts[1], parts[2], body)
        if len(parts) == 2 and parts[0] == "quiz-new":
            return do_quiz_new(self.root, parts[1], body)
        if len(parts) == 3 and parts[0] == "quiz-grade":
            return do_quiz_grade(self.root, parts[1], parts[2], body)
        if len(parts) == 3 and parts[0] == "review":
            return do_review(self.root, parts[1], parts[2], body)
        if parts == ["goal"]:
            return do_goal(self.root, body)
        raise ApiError("unknown endpoint: %s" % path, 404)

    # --- static + media ---

    def _serve_static(self, path):
        name, ctype = STATIC[path]
        full = os.path.join(WEB_DIR, name)
        try:
            with open(full, "rb") as f:
                self._send(200, ctype, f.read())
        except OSError:
            self._error(404, "missing asset: %s" % name)

    def _serve_media(self, path):
        # /media/<graph>/<relpath>
        rest = path[len("/media/"):]
        graph_name, _, rel = rest.partition("/")
        base = os.path.join(store.graph_dir(self.root, graph_name), "media")
        safe = _safe_join(base, rel)
        if safe is None or not os.path.isfile(safe):
            return self._error(404, "no such media: %s" % rel)
        ext = os.path.splitext(safe)[1].lower()
        with open(safe, "rb") as f:
            self._send(200, MEDIA_TYPES.get(ext, "application/octet-stream"),
                       f.read())


def _safe_join(base, rel):
    """Join base+rel, refusing anything that escapes base (traversal guard)."""
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, rel.lstrip("/")))
    if target == base or target.startswith(base + os.sep):
        return target
    return None


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, root, verbose=False):
        super().__init__(addr, Handler)
        self.st_root = root
        self.st_verbose = verbose


def serve(root, host="127.0.0.1", port=8777, verbose=False):
    httpd = Server((host, port), root, verbose=verbose)
    return httpd
