"""Topic-node file format.

A node is one markdown file: graphs/<graph>/nodes/<id>.md

    ---
    id: add-two-digit
    title: Adding Two-Digit Whole Numbers
    requires: [add-one-digit, place-value]
    minutes: 25
    tags: [arithmetic]
    ---

    # Introduction
    ...

    ## KP 1: <knowledge point name>
    ### Worked Example
    ...text, or media: ![carrying](../media/carrying.png)...
    ### Problems
    1. first blocked practice problem
    2. second blocked practice problem

    ## KP 2: ...

Structure rules (kept deliberately small so files stay hand-writable):
  * front matter is the block between the first two `---` lines; values are
    strings, integers, or [a, b] lists -- nothing else
  * every `## ` heading starts a knowledge point (KP)
  * inside a KP, a `### Problems` heading starts its problem list
  * each numbered (`1.`) or bulleted (`- `) item is one problem; indented or
    following non-blank lines belong to it
  * problem ids are <kp>.<n>, both 1-based: the 2nd problem of KP 1 is "1.2"
"""

import os
import re

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROBLEM_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+")
KP_NUM_RE = re.compile(r"^KP\s*\d+\s*:\s*", re.IGNORECASE)
LIST_KEYS = ("requires", "tags")
INT_KEYS = ("minutes",)


class NodeError(Exception):
    pass


class Node:
    def __init__(self, nid, title, requires, minutes, tags, path, kps, body):
        self.id = nid
        self.title = title
        self.requires = requires
        self.minutes = minutes
        self.tags = tags
        self.path = path
        self.kps = kps          # list of (kp_title, [problem_text, ...])
        self.body = body

    def problem_ids(self):
        out = []
        for ki, (_, problems) in enumerate(self.kps, 1):
            for pi in range(1, len(problems) + 1):
                out.append("%d.%d" % (ki, pi))
        return out

    def problem_text(self, pid):
        try:
            ki, pi = (int(x) for x in pid.split("."))
            return self.kps[ki - 1][1][pi - 1]
        except (ValueError, IndexError):
            raise NodeError("%s has no problem %s" % (self.id, pid))


def _parse_value(key, raw):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        items = [x.strip().strip("'\"") for x in inner.split(",")] if inner else []
        return [x for x in items if x]
    raw = raw.strip("'\"")
    if key in INT_KEYS:
        try:
            return int(raw)
        except ValueError:
            raise NodeError("front matter: %s must be an integer, got %r"
                            % (key, raw))
    if key in LIST_KEYS:  # allow bare single value for a list key
        return [raw] if raw else []
    return raw


def split_front_matter(text):
    """Return (front_matter_lines, body_lines); raises NodeError if absent."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise NodeError("missing front matter (file must start with ---)")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], lines[i + 1:]
    raise NodeError("unterminated front matter (no closing ---)")


def parse_kps(body_lines):
    kps = []
    in_problems = False
    current_item = None
    for line in body_lines:
        if line.startswith("## "):
            kps.append((line[3:].strip(), []))
            in_problems = False
            current_item = None
        elif line.startswith("### "):
            in_problems = bool(kps) and \
                line[4:].strip().lower().startswith("problem")
            current_item = None
        elif in_problems and PROBLEM_ITEM_RE.match(line):
            current_item = [PROBLEM_ITEM_RE.sub("", line).rstrip()]
            kps[-1][1].append(current_item)
        elif in_problems and current_item is not None and line.strip():
            current_item.append(line.strip())
        elif not line.strip():
            current_item = None
    return [(title, [" ".join(item) for item in problems])
            for title, problems in kps]


def parse_meta(fm_lines):
    meta = {}
    for line in fm_lines:
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise NodeError("bad front matter line: %r" % line)
        key, _, raw = line.partition(":")
        meta[key.strip()] = _parse_value(key.strip(), raw)
    return meta


def parse(path):
    with open(path) as f:
        text = f.read()
    fm_lines, body_lines = split_front_matter(text)
    meta = parse_meta(fm_lines)

    nid = meta.get("id", "")
    stem = os.path.splitext(os.path.basename(path))[0]
    if not nid:
        raise NodeError("missing id in front matter")
    if not ID_RE.match(nid):
        raise NodeError("bad id %r (use lowercase letters, digits, -)" % nid)
    if nid != stem:
        raise NodeError("id %r does not match filename %r" % (nid, stem))

    return Node(
        nid=nid,
        title=meta.get("title", nid),
        requires=meta.get("requires", []),
        minutes=meta.get("minutes", 0),
        tags=meta.get("tags", []),
        path=path,
        kps=parse_kps(body_lines),
        body="\n".join(body_lines),
    )


def _split_sections(body_lines):
    """Split a node body into (intro_text, [(kp_heading, [kp_body_lines])])."""
    intro, kps = [], []
    target = intro
    for line in body_lines:
        if line.startswith("## "):
            kps.append([line[3:].strip(), []])
            target = kps[-1][1]
        elif line.startswith("# ") and not kps:
            continue  # the "# Introduction" heading itself
        else:
            target.append(line)
    return "\n".join(intro).strip(), kps


def _extract_worked_and_problems(kp_body):
    """From one KP's body lines pull (worked_example_text, [problem, ...])."""
    worked, problems = [], []
    mode = "worked"
    current = None
    for line in kp_body:
        if line.startswith("### "):
            head = line[4:].strip().lower()
            mode = "problems" if head.startswith("problem") else "worked"
            current = None
            continue
        if mode == "problems":
            if PROBLEM_ITEM_RE.match(line):
                current = [PROBLEM_ITEM_RE.sub("", line).rstrip()]
                problems.append(current)
            elif current is not None and line.strip():
                current.append(line.strip())
            elif not line.strip():
                current = None
        else:
            worked.append(line)
    return ("\n".join(worked).strip(),
            [" ".join(p) for p in problems])


def parse_editable(path):
    """Parse a node into a structured dict the visual editor round-trips.

    Returns {id, title, requires, minutes, tags, intro,
             kps: [{name, worked, problems: [str, ...]}, ...]}.
    The "KP N:" numbering prefix is stripped from names on load and
    re-applied by render(), so knowledge points stay auto-numbered.
    """
    with open(path) as f:
        text = f.read()
    fm_lines, body_lines = split_front_matter(text)
    meta = parse_meta(fm_lines)
    intro, raw_kps = _split_sections(body_lines)
    kps = []
    for heading, kp_body in raw_kps:
        worked, problems = _extract_worked_and_problems(kp_body)
        kps.append({"name": KP_NUM_RE.sub("", heading).strip(),
                    "worked": worked, "problems": problems})
    return {
        "id": meta.get("id", ""),
        "title": meta.get("title", ""),
        "requires": meta.get("requires", []),
        "minutes": meta.get("minutes", 0),
        "tags": meta.get("tags", []),
        "intro": intro,
        "kps": kps,
    }


def render(data):
    """Serialize a structured node dict (see parse_editable) to markdown."""
    nid = (data.get("id") or "").strip()
    if not ID_RE.match(nid):
        raise NodeError("bad id %r (use lowercase letters, digits, -)" % nid)
    requires = [r.strip() for r in data.get("requires", []) if r.strip()]
    tags = [t.strip() for t in data.get("tags", []) if t.strip()]
    minutes = int(data.get("minutes") or 0)
    out = [
        "---",
        "id: %s" % nid,
        "title: %s" % (data.get("title") or nid).strip(),
        "requires: [%s]" % ", ".join(requires),
        "minutes: %d" % minutes,
        "tags: [%s]" % ", ".join(tags),
        "---",
        "",
        "# Introduction",
        "",
        (data.get("intro") or "").strip(),
    ]
    for i, kp in enumerate(data.get("kps", []), 1):
        name = (kp.get("name") or "").strip()
        heading = "## KP %d: %s" % (i, name) if name else "## KP %d" % i
        out += ["", heading, "", "### Worked Example", "",
                (kp.get("worked") or "").strip()]
        problems = [p.strip() for p in kp.get("problems", []) if p.strip()]
        if problems:
            out += ["", "### Problems", ""]
            out += ["%d. %s" % (n, p) for n, p in enumerate(problems, 1)]
    return "\n".join(out).rstrip() + "\n"


def set_requires(path, requires):
    """Rewrite the requires: line of a node file in place."""
    with open(path) as f:
        text = f.read()
    fm_lines, body_lines = split_front_matter(text)
    new_line = "requires: [%s]" % ", ".join(requires)
    replaced = False
    out = []
    for line in fm_lines:
        if line.split(":", 1)[0].strip() == "requires":
            out.append(new_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(new_line)
    new_text = "\n".join(["---"] + out + ["---"] + body_lines)
    from . import store
    store.write_atomic(path, new_text)


def template(nid, title, requires, minutes):
    return """---
id: %s
title: %s
requires: [%s]
minutes: %d
tags: []
---

# Introduction

(One short paragraph: what this topic is, and how it builds on its
prerequisites.)

## KP 1: (name the most basic case of this skill)

### Worked Example

(Show one fully worked example. Text, or embed media:
![diagram](../media/%s.png))

### Problems

1. (blocked practice problem, same shape as the worked example)
2. (blocked practice problem)

## KP 2: (name the next, slightly harder case)

### Worked Example

(worked example for this case)

### Problems

1. (blocked practice problem)
""" % (nid, title, ", ".join(requires), minutes, nid)
