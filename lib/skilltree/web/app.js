"use strict";

// ---- tiny helpers -----------------------------------------------------------
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null) continue;
    n.append(kid.nodeType ? kid : document.createTextNode(kid));
  }
  return n;
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const apiGet = (p) => api(p);
const apiPost = (p, body) =>
  api(p, { method: "POST", headers: { "Content-Type": "application/json" },
           body: JSON.stringify(body || {}) });

let toastTimer;
function toast(msg, isErr) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = "toast"), isErr ? 5000 : 3200);
}

function fileToUpload(file) {
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve({ name: file.name,
      data: r.result.split(",")[1] });
    r.readAsDataURL(file);
  });
}

// ---- minimal markdown renderer (self-contained, no deps) --------------------
function mdInline(s) {
  s = esc(s);
  s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (m, alt, src) =>
    `<img alt="${alt}" src="${mediaUrl(src)}">`);
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  return s;
}
function mediaUrl(src) {
  // lesson media is written relative, e.g. ../media/foo.png
  const m = src.match(/media\/(.+)$/);
  if (m && state.graph) return `/media/${encodeURIComponent(state.graph)}/${m[1]}`;
  return src;
}
function renderMarkdown(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  let html = "", i = 0, inFront = false;
  const listStack = [];
  const closeLists = (toDepth = 0) => {
    while (listStack.length > toDepth) html += `</${listStack.pop()}>`;
  };
  // strip leading front matter block
  if (lines[0] && lines[0].trim() === "---") {
    inFront = true; i = 1;
    for (; i < lines.length; i++) { if (lines[i].trim() === "---") { i++; break; } }
  }
  for (; i < lines.length; i++) {
    let line = lines[i];
    if (/^\s*```/.test(line)) {
      closeLists(); const buf = [];
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) buf.push(lines[i]);
      html += `<pre>${esc(buf.join("\n"))}</pre>`;
      continue;
    }
    // indented code block (4 spaces) -> preformatted (used for math columns)
    if (/^ {4}\S/.test(line)) {
      closeLists(); const buf = [];
      for (; i < lines.length && (/^ {4}/.test(lines[i]) || lines[i].trim() === ""); i++) {
        if (lines[i].trim() === "" && !(lines[i + 1] && /^ {4}/.test(lines[i + 1]))) break;
        buf.push(lines[i].replace(/^ {4}/, ""));
      }
      i--; html += `<pre>${esc(buf.join("\n"))}</pre>`;
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) { closeLists(); html += `<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`; continue; }
    const ol = line.match(/^(\s*)\d+[.)]\s+(.*)$/);
    const ul = line.match(/^(\s*)[-*]\s+(.*)$/);
    if (ol || ul) {
      const kind = ol ? "ol" : "ul";
      if (!listStack.length || listStack[listStack.length - 1] !== kind) {
        closeLists(); html += `<${kind}>`; listStack.push(kind);
      }
      html += `<li>${mdInline((ol || ul)[2])}</li>`;
      continue;
    }
    if (line.trim() === "") { closeLists(); continue; }
    closeLists();
    html += `<p>${mdInline(line)}</p>`;
  }
  closeLists();
  return html;
}

// ---- global state -----------------------------------------------------------
const state = { graph: null, dashboard: null, view: "tree" };

// ---- data loads -------------------------------------------------------------
async function loadDashboard() {
  state.dashboard = await apiGet("/api/dashboard");
  renderXpMini();
  const sel = $("#graph-select");
  const names = state.dashboard.graphs.map((g) => g.name);
  if (!state.graph || !names.includes(state.graph)) state.graph = names[0] || null;
  sel.innerHTML = "";
  for (const g of state.dashboard.graphs) {
    sel.append(el("option", { value: g.name }, `${g.name} (${g.due} due)`));
  }
  if (state.graph) sel.value = state.graph;
}

function renderXpMini() {
  const x = state.dashboard.xp;
  $("#xp-mini").innerHTML = "";
  $("#xp-mini").append(
    el("div", { class: "chip" }, el("b", {}, `${x.today}/${x.goal}`), el("span", {}, "today xp")),
    el("div", { class: "chip" }, el("b", {}, `🔥 ${x.streak}`), el("span", {}, "day streak")),
    el("div", { class: "chip" }, el("b", {}, `${x.total}`), el("span", {}, "total xp")),
  );
}

// ---- view: skill tree (SVG) -------------------------------------------------
async function renderTree() {
  const root = $("#view-tree");
  root.innerHTML = "";
  if (!state.graph) { root.append(el("div", { class: "empty" }, "No graphs yet. Create one with `st graph new`.")); return; }
  const data = await apiGet(`/api/graph/${encodeURIComponent(state.graph)}`);
  root.append(
    el("h2", { class: "view-title" }, `Skill tree: ${state.graph}`),
    el("p", { class: "view-sub" }, "Nodes flow left→right along prerequisites. Click a node to open its lesson."),
    legend(),
  );
  if (data.errors && data.errors.length)
    root.append(el("div", { class: "errbar" }, "⚠ " + data.errors.join(" · ")));
  if (!data.nodes.length) { root.append(el("div", { class: "empty" }, "This graph has no nodes yet.")); return; }
  root.append(buildTreeSvg(data.nodes));
}

function legend() {
  return el("div", { class: "legend" },
    el("span", {}, el("i", { class: "dot ready" }), "ready to learn"),
    el("span", {}, el("i", { class: "dot learned" }), "learned"),
    el("span", {}, el("i", { class: "dot not-ready" }), "not ready"),
    el("span", {}, el("i", { class: "dot due" }), "review due"),
  );
}

function computeLayers(nodes) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const depth = {};
  const visiting = new Set();
  const calc = (id) => {
    if (depth[id] !== undefined) return depth[id];
    if (visiting.has(id)) return 0; // cycle guard
    visiting.add(id);
    const reqs = (byId[id]?.requires || []).filter((r) => byId[r]);
    const d = reqs.length ? 1 + Math.max(...reqs.map(calc)) : 0;
    visiting.delete(id);
    return (depth[id] = d);
  };
  nodes.forEach((n) => calc(n.id));
  return depth;
}

function buildTreeSvg(nodes) {
  const depth = computeLayers(nodes);
  const layers = {};
  nodes.forEach((n) => (layers[depth[n.id]] ||= []).push(n));
  const W = 210, H = 62, GAPX = 90, GAPY = 26, PADX = 30, PADY = 30;
  const pos = {};
  const maxLayer = Math.max(...Object.keys(layers).map(Number));
  let maxRows = 0;
  for (let d = 0; d <= maxLayer; d++) {
    const col = (layers[d] || []).sort((a, b) => a.title.localeCompare(b.title));
    maxRows = Math.max(maxRows, col.length);
    col.forEach((n, r) => {
      pos[n.id] = { x: PADX + d * (W + GAPX), y: PADY + r * (H + GAPY) };
    });
  }
  const svgW = PADX * 2 + (maxLayer + 1) * W + maxLayer * GAPX;
  const svgH = PADY * 2 + maxRows * (H + GAPY);
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "tree");
  svg.setAttribute("width", svgW);
  svg.setAttribute("height", svgH);
  svg.setAttribute("viewBox", `0 0 ${svgW} ${svgH}`);

  // edges first
  for (const n of nodes) {
    for (const r of n.requires) {
      if (!pos[r] || !pos[n.id]) continue;
      const a = pos[r], b = pos[n.id];
      const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
      const mx = (x1 + x2) / 2;
      const path = document.createElementNS(NS, "path");
      path.setAttribute("class", "edge");
      path.setAttribute("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
      path.dataset.from = r; path.dataset.to = n.id;
      svg.append(path);
    }
  }
  // nodes
  for (const n of nodes) {
    const p = pos[n.id];
    const g = document.createElementNS(NS, "g");
    g.setAttribute("class", `gnode ${n.status}`);
    g.setAttribute("transform", `translate(${p.x},${p.y})`);
    g.dataset.id = n.id;
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("width", W); rect.setAttribute("height", H);
    g.append(rect);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("class", "t"); t.setAttribute("x", 12); t.setAttribute("y", 24);
    t.textContent = n.title.length > 26 ? n.title.slice(0, 25) + "…" : n.title;
    g.append(t);
    const sub = document.createElementNS(NS, "text");
    sub.setAttribute("class", "s"); sub.setAttribute("x", 12); sub.setAttribute("y", 44);
    sub.setAttribute("fill", "var(--text-faint)");
    let info = n.status.replace("-", " ");
    if (n.status === "learned") info += n.is_due ? " · review due" : ` · next ${n.due || "-"}`;
    else info += ` · ${n.problems_done}/${n.problems_total} done · ${n.minutes}xp`;
    sub.textContent = info;
    g.append(sub);
    if (n.is_due) {
      const dot = document.createElementNS(NS, "circle");
      dot.setAttribute("class", "duebadge");
      dot.setAttribute("cx", W - 14); dot.setAttribute("cy", 14); dot.setAttribute("r", 5);
      g.append(dot);
    }
    g.addEventListener("mouseenter", () => highlightEdges(svg, n.id, true));
    g.addEventListener("mouseleave", () => highlightEdges(svg, n.id, false));
    g.addEventListener("click", () => openNode(n.id));
    svg.append(g);
  }
  const wrap = el("div", { class: "tree-wrap" });
  wrap.append(svg);
  return wrap;
}

function highlightEdges(svg, id, on) {
  $$(".edge", svg).forEach((e) => {
    if (e.dataset.from === id || e.dataset.to === id)
      e.classList.toggle("hot", on);
  });
}

// ---- view: lessons list -----------------------------------------------------
async function renderLessons() {
  const root = $("#view-lessons");
  root.innerHTML = "";
  if (!state.graph) { root.append(el("div", { class: "empty" }, "No graph selected.")); return; }
  const data = await apiGet(`/api/graph/${encodeURIComponent(state.graph)}`);
  root.append(
    el("h2", { class: "view-title" }, "Lessons"),
    el("p", { class: "view-sub" }, `${data.nodes.length} topics · ${data.nodes.filter(n=>n.status==="ready").length} ready · ${data.nodes.filter(n=>n.status==="learned").length} learned`),
    legend(),
  );
  const order = { ready: 0, learned: 1, "not-ready": 2 };
  const sorted = [...data.nodes].sort((a, b) =>
    (order[a.status] - order[b.status]) || a.title.localeCompare(b.title));
  const grid = el("div", { class: "grid" });
  for (const n of sorted) grid.append(lessonCard(n));
  root.append(grid);
}

function lessonCard(n) {
  const pct = n.problems_total ? Math.round(100 * n.problems_done / n.problems_total) : 0;
  const badges = [el("span", { class: `badge ${n.status}` }, n.status.replace("-", " "))];
  if (n.is_due) badges.push(el("span", { class: "badge due" }, "review due"));
  return el("div", { class: `card ${n.status}`, onclick: () => openNode(n.id) },
    el("h3", {}, n.title),
    el("div", { class: "meta" }, ...badges,
      el("span", {}, `${n.kps} KPs`), el("span", {}, `${n.minutes} xp`),
      n.status !== "learned" ? el("span", {}, `${n.problems_done}/${n.problems_total} problems`) : null),
    n.status !== "learned" && n.problems_total
      ? el("div", { class: "progressbar" }, el("i", { style: `width:${pct}%` })) : null,
  );
}

// ---- node drawer ------------------------------------------------------------
async function openNode(id) {
  const data = await apiGet(`/api/node/${encodeURIComponent(state.graph)}/${encodeURIComponent(id)}`);
  const p = $("#drawer-panel");
  p.innerHTML = "";
  p.append(el("button", { class: "drawer-close", onclick: closeDrawer, title: "close" }, "×"));
  p.append(el("h2", {}, data.title));
  const meta = el("div", { class: "detail-meta" },
    el("span", { class: `badge ${data.status}` }, data.status.replace("-", " ")),
    el("span", {}, `${data.minutes} xp`),
    data.learned_at ? el("span", {}, `learned ${data.learned_at.slice(0, 10)}`) : null,
    data.srs ? el("span", {}, `next review ${data.srs.due} (ivl ${data.srs.ivl}d)`) : null,
  );
  p.append(meta);

  if (data.requires.length) {
    const reqs = el("div", { class: "reqs" });
    reqs.append(el("span", { class: "muted" }, "Requires: "));
    for (const r of data.requires) {
      const st = data.requires_status[r];
      reqs.append(el("span", { class: "req" },
        el("i", { class: `dot ${st}`, style: `background:var(--${st === "not-ready" ? "notready" : st})` }),
        el("a", { href: "#", onclick: (e) => { e.preventDefault(); openNode(r); } }, r)));
    }
    p.append(reqs);
  }

  // practice / actions
  if (data.status === "learned") {
    p.append(reviewBlock(data));
  } else {
    p.append(practiceBlock(data));
  }

  // lesson body
  const lesson = el("section", { class: "block" },
    el("h4", {}, "Lesson"),
    el("div", { class: "lesson", html: renderMarkdown(data.raw) }));
  p.append(lesson);

  openDrawer();
}

function practiceBlock(data) {
  const canDo = data.status !== "not-ready";
  const sec = el("section", { class: "block" }, el("h4", {}, "Practice"));
  if (!canDo)
    sec.append(el("p", { class: "muted" }, "Not ready — finish the prerequisites above first. (You can still read the lesson.)"));
  for (const kp of data.kps) {
    sec.append(el("div", { class: "kp-title" }, kp.title));
    for (const pr of kp.problems) {
      const evi = el("input", { type: "file", multiple: "" });
      const row = el("div", { class: "problem" + (pr.done ? " done" : "") },
        el("span", { class: "pid" }, pr.id),
        el("div", { class: "ptext", html: mdInline(pr.text) }));
      const actions = el("div", { class: "pactions" });
      if (pr.done) {
        actions.append(el("span", { class: "badge learned" }, "done"));
      } else if (canDo) {
        actions.append(evi, el("button", { class: "btn sm",
          onclick: () => completeProblem(data.id, pr.id, evi) }, "Mark done"));
      }
      row.append(actions);
      if (pr.evidence && pr.evidence.length)
        row.append(el("div", { class: "evi" }, "📎 " + pr.evidence.map((e) => e.split("/").pop()).join(", ")));
      sec.append(row);
    }
  }
  if (canDo && data.kps.length) {
    sec.append(el("div", { style: "margin-top:14px" },
      el("button", { class: "btn ghost", onclick: () => completeAll(data.id) },
        "Complete all remaining problems")));
  }
  return sec;
}

function reviewBlock(data) {
  const sec = el("section", { class: "block" }, el("h4", {}, "Spaced repetition review"));
  const due = data.srs && new Date(data.srs.due) <= new Date();
  sec.append(el("p", { class: "muted" },
    due ? "This node is due for review. Grade your recall:"
        : `Not due until ${data.srs?.due}. You can still review early:`));
  const evi = el("input", { type: "file", multiple: "" });
  const row = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px" });
  for (const gr of ["again", "hard", "good", "easy"]) {
    row.append(el("button", { class: `grade ${gr}`,
      onclick: () => reviewNode(data.id, gr, evi) }, gr));
  }
  sec.append(row, el("div", {}, evi));
  return sec;
}

async function completeProblem(nid, pid, fileInput) {
  try {
    const evidence = await Promise.all([...(fileInput?.files || [])].map(fileToUpload));
    const r = await apiPost(`/api/done/${enc(state.graph)}/${enc(nid)}`, { problems: [pid], evidence });
    afterMutation(r.messages);
    openNode(nid);
  } catch (e) { toast(e.message, true); }
}
async function completeAll(nid) {
  try {
    const r = await apiPost(`/api/done/${enc(state.graph)}/${enc(nid)}`, { all: true });
    afterMutation(r.messages);
    openNode(nid);
  } catch (e) { toast(e.message, true); }
}
async function reviewNode(nid, grade, fileInput) {
  try {
    const evidence = await Promise.all([...(fileInput?.files || [])].map(fileToUpload));
    const r = await apiPost(`/api/review/${enc(state.graph)}/${enc(nid)}`, { grade, evidence });
    afterMutation(r.messages);
    openNode(nid);
  } catch (e) { toast(e.message, true); }
}

const enc = encodeURIComponent;

async function afterMutation(messages) {
  toast((messages || []).join("\n") || "done");
  await loadDashboard();
  refreshCurrentView();
}

function openDrawer() { const d = $("#drawer"); d.classList.add("open"); d.setAttribute("aria-hidden", "false"); }
function closeDrawer() { const d = $("#drawer"); d.classList.remove("open"); d.setAttribute("aria-hidden", "true"); }

// ---- view: review -----------------------------------------------------------
async function renderReview() {
  const root = $("#view-review");
  root.innerHTML = "";
  if (!state.graph) { root.append(el("div", { class: "empty" }, "No graph selected.")); return; }
  root.append(el("h2", { class: "view-title" }, "Review"),
    el("p", { class: "view-sub" }, "Spaced-repetition quizzes interleave everything currently due."));

  const [due, quizzes] = await Promise.all([
    apiGet(`/api/due/${enc(state.graph)}`),
    apiGet(`/api/quizzes/${enc(state.graph)}`),
  ]);

  // due + generate
  const genPanel = el("div", { class: "panel" },
    el("h3", {}, `${due.due.length} topic${due.due.length === 1 ? "" : "s"} due for review`));
  if (due.due.length) {
    for (const d of due.due)
      genPanel.append(el("div", { class: "due-row" },
        el("span", {}, d.title),
        el("span", { class: "od" }, d.overdue > 0 ? `${d.overdue}d overdue` : "due today")));
    genPanel.append(el("div", { style: "margin-top:14px" },
      el("button", { class: "btn", onclick: newQuiz }, "Generate interleaved quiz")));
  } else {
    genPanel.append(el("p", { class: "muted" }, "Nothing due right now — come back when reviews come up."));
  }
  root.append(genPanel);

  // open (ungraded) quizzes
  const open = quizzes.quizzes.filter((q) => !q.done);
  for (const q of open) {
    const full = await apiGet(`/api/quiz/${enc(state.graph)}/${enc(q.id)}`);
    root.append(quizPanel(full));
  }
  const done = quizzes.quizzes.filter((q) => q.done);
  if (done.length) {
    const p = el("div", { class: "panel" }, el("h3", {}, "Completed quizzes"));
    for (const q of done) p.append(el("div", { class: "due-row" },
      el("span", {}, q.id), el("span", { class: "muted" }, `${q.total} items`)));
    root.append(p);
  }
}

async function newQuiz() {
  try {
    const r = await apiPost(`/api/quiz-new/${enc(state.graph)}`, {});
    toast(`quiz ${r.quiz.id} generated (${r.quiz.items.length} items)`);
    await loadDashboard();
    renderReview();
  } catch (e) { toast(e.message, true); }
}

function quizPanel(q) {
  const panel = el("div", { class: "panel" },
    el("h3", {}, `Quiz ${q.id}`),
    el("p", { class: "muted" }, "Items are unlabelled and in mixed order. Work each, then grade your recall."));
  for (const it of q.items) {
    const item = el("div", { class: "quiz-item" + (it.grade ? " graded" : "") });
    item.append(el("div", { class: "quiz-q" },
      el("span", { class: "n" }, `${it.n}.`),
      el("div", { html: mdInline(it.text) })));
    if (it.grade) {
      item.append(el("div", { class: "muted" }, `graded: ${it.grade}`));
    } else {
      const evi = el("input", { type: "file", multiple: "" });
      const row = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;align-items:center" });
      for (const gr of ["again", "hard", "good", "easy"])
        row.append(el("button", { class: `grade ${gr}`,
          onclick: () => gradeQuiz(q.id, it.n, gr, evi) }, gr));
      row.append(evi);
      item.append(row);
    }
    panel.append(item);
  }
  return panel;
}

async function gradeQuiz(qid, n, grade, fileInput) {
  try {
    const evidence = await Promise.all([...(fileInput?.files || [])].map(fileToUpload));
    const r = await apiPost(`/api/quiz-grade/${enc(state.graph)}/${enc(qid)}`, { item: n, grade, evidence });
    toast((r.messages || []).join("\n"));
    await loadDashboard();
    renderReview();
  } catch (e) { toast(e.message, true); }
}

// ---- view: progress ---------------------------------------------------------
async function renderProgress() {
  const root = $("#view-progress");
  root.innerHTML = "";
  const x = state.dashboard.xp;
  root.append(el("h2", { class: "view-title" }, "Progress"),
    el("p", { class: "view-sub" }, "1 xp ≈ 1 minute of focused, productive work."));

  root.append(el("div", { class: "stat-row" },
    stat(x.total, "total xp"),
    stat(`${x.today}/${x.goal}`, "today"),
    stat(`🔥 ${x.streak}`, "day streak"),
    goalStat(x.goal)));

  // last-7-days bar chart
  const max = Math.max(x.goal, ...x.last7.map((d) => d[1]), 1);
  const bars = el("div", { class: "bars" });
  for (const [day, val] of x.last7) {
    const met = val >= x.goal;
    bars.append(el("div", { class: "day" + (met ? " met" : "") },
      el("div", { class: "val" }, String(val)),
      el("div", { class: "bar", style: `height:${Math.round(100 * val / max)}%` }),
      el("div", { class: "lbl" }, day.slice(5))));
  }
  root.append(el("div", { class: "panel" },
    el("h3", {}, "Last 7 days"), bars));

  // per-graph summary
  const gp = el("div", { class: "panel" }, el("h3", {}, "Graphs"));
  const tbl = el("table", { class: "ledger" });
  tbl.append(el("tr", {}, el("th", {}, "graph"), el("th", {}, "learned"),
    el("th", {}, "ready"), el("th", {}, "not ready"), el("th", {}, "due")));
  for (const g of state.dashboard.graphs) {
    tbl.append(el("tr", {},
      el("td", {}, g.name),
      el("td", { class: "n" }, String(g.counts.learned || 0)),
      el("td", { class: "n" }, String(g.counts.ready || 0)),
      el("td", { class: "n" }, String(g.counts["not-ready"] || 0)),
      el("td", { class: "n" }, String(g.due))));
  }
  gp.append(tbl);
  root.append(gp);
}

function stat(value, label) {
  return el("div", { class: "stat" }, el("b", {}, String(value)), el("span", {}, label));
}
function goalStat(goal) {
  const input = el("input", { class: "goal", type: "number", min: "1", value: goal });
  const s = el("div", { class: "stat" },
    el("div", { style: "display:flex;gap:8px;align-items:center" }, input,
      el("button", { class: "btn sm", onclick: async () => {
        try { await apiPost("/api/goal", { value: Number(input.value) });
          toast("daily goal updated"); await loadDashboard(); renderProgress(); }
        catch (e) { toast(e.message, true); }
      } }, "set")),
    el("span", {}, "daily goal"));
  return s;
}

// ---- view switching ---------------------------------------------------------
function refreshCurrentView() {
  ({ tree: renderTree, lessons: renderLessons, review: renderReview, progress: renderProgress }[state.view])();
}
function switchView(v) {
  state.view = v;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${v}`));
  refreshCurrentView();
}

// ---- boot -------------------------------------------------------------------
async function boot() {
  $$("#tabs button").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("#graph-select").addEventListener("change", (e) => {
    state.graph = e.target.value;
    refreshCurrentView();
  });
  $$("[data-close]").forEach((n) => n.addEventListener("click", closeDrawer));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
  try {
    await loadDashboard();
    switchView("tree");
  } catch (e) {
    $("#main").innerHTML = `<div class="errbar">Failed to load: ${esc(e.message)}</div>`;
  }
}
boot();
