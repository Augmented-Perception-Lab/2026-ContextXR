// Functionality suggestion test (initial facet suggestion, paper §3.4), inside the contextual
// layouts section. For the layout shown there and a chosen method, shows which needed facets the
// suggestions hit exactly, which the simulated user reaches by hopping from a same-app suggestion,
// and which it must find manually (app list → app → facet path), with the navigation & search cost
// of each. The suggestions sit below the participant's view, linked to the widgets they serve.
// Also owns the facet detail dialog used across the page.
(function () {
  "use strict";

  const D = window.MINEXRPP, RES = window.MINEXRPP_RESULTS;
  const root = document.getElementById("layouts");
  if (!D || !RES || !root) return;

  // Method chips: the three baselines, then the few-shot LLM by which context it draws examples from.
  const CHIP = {
    popularity: "Popularity", relational: "Relational", zero_shot_llm: "Zero-shot LLM",
    "few_shot_llm[user]": "User", "few_shot_llm[task]": "Task", "few_shot_llm[environment]": "Environment",
    "few_shot_llm[user+task]": "User + Task", "few_shot_llm[user+env]": "User + Env", "few_shot_llm[task+env]": "Task + Env",
  };
  const TIER_LABEL = { primary: "primary", peripheral: "peripheral", ambient: "ambient" };

  // ---------- model ----------
  const prettyName = (s) => (s === s.toLowerCase() ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : s);
  const apps = new Map(D.apps.map((a) => [a.id, { ...a, name: prettyName(a.name) }]));
  const facets = new Map(D.facets.map((f) => [f.id, f]));
  const scenarios = new Map(D.scenarios.map((s) => [s.id, s]));
  const methods = RES.methods;
  const methodById = new Map(methods.map((m) => [m.id, m]));
  const isEntry = (fid) => apps.get(facets.get(fid).app).entry === fid;
  const facetLabel = (fid) => (isEntry(fid) ? "Open Section" : facets.get(fid).name);
  const appName = (fid) => apps.get(facets.get(fid).app).name;

  const out = new Map(), und = new Map();
  const push = (m, k, v) => (m.get(k) || m.set(k, []).get(k)).push(v);
  for (const [s, t, cap] of D.edges) {
    if (s === t) continue;
    push(out, s, { to: t, cap });
    push(und, s, { to: t, cap, fwd: true });
    push(und, t, { to: s, cap, fwd: false });
  }
  // Shortest path as [{id, cap?, fwd?}] from `from` to `to`.
  function bfs(adj, from, to) {
    const prev = new Map([[from, null]]);
    const q = [from];
    for (const u of q) {
      if (u === to) break;
      for (const e of adj.get(u) || []) if (!prev.has(e.to)) { prev.set(e.to, { u, e }); q.push(e.to); }
    }
    if (!prev.has(to)) return null;
    const path = [];
    for (let v = to; v !== from; v = prev.get(v).u) path.unshift({ id: v, cap: prev.get(v).e.cap, fwd: prev.get(v).e.fwd });
    path.unshift({ id: from });
    return path;
  }

  // Evidence: in how many *other* MineXR layouts with the same user / room / task category the
  // facet is a target. Grouped labels as on the rest of the site (methods see raw labels).
  function evidence(sc, fid) {
    const res = {};
    for (const [key, dim] of [["user", "user"], ["env", "env"], ["task", "taskCat"]]) {
      const pool = D.scenarios.filter((o) => o.id !== sc.id && o[dim] === sc[dim]);
      res[key] = { k: pool.filter((o) => fid in o.targets).length, n: pool.length };
    }
    return res;
  }


  // ---------- state ----------
  // scenario: the layout shown in the section; method: null until the reader picks one.
  const state = { scenario: null, method: null };
  let xr = null, view = null; // the layouts view, set on every update()

  // ---------- DOM helpers ----------
  const $ = (sel) => root.querySelector(sel);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const fmt = (x) => (Math.round(x * 10) / 10).toString();
  const pct = (a, b) => (a ? Math.round(((b - a) / a) * 100) : 0);

  function miniPanel(fid, opts = {}) {
    const wrap = document.createElement("button");
    wrap.type = "button";
    wrap.className = "cx-mini" + (opts.cls ? " " + opts.cls : "");
    wrap.dataset.facet = fid;
    const mk = window.FacetMockup && FacetMockup.render(fid, { appName: appName(fid), facetName: isEntry(fid) ? "Home" : "" });
    const f = facets.get(fid);
    const body = mk || Object.assign(document.createElement("div"), {
      className: "cx-nomk",
      innerHTML: `<b>${esc(appName(fid))}</b>${f.caps.map((c) => `<span>${esc(c)}</span>`).join("")}`,
    });
    const frame = document.createElement("div");
    frame.className = "cx-frame";
    frame.appendChild(body);
    wrap.innerHTML = `<span class="cx-mini-top">${opts.badge || ""}<span class="chip facet">${esc(facetLabel(fid))}</span></span>`;
    wrap.appendChild(frame);
    if (opts.foot) wrap.insertAdjacentHTML("beforeend", `<span class="cx-mini-foot">${opts.foot}</span>`);
    return wrap;
  }

  const chipFor = (fid, cls = "") => `<span class="cx-step ${cls}"><small>${esc(appName(fid))}</small>${esc(facetLabel(fid))}</span>`;
  const arrow = (cap, back) => `<span class="cx-arrow${back ? " back" : ""}">${cap ? `<em>${esc(cap)}</em>` : ""}</span>`;

  // ---------- render ----------
  function update(sid, xrEl) {
    state.scenario = sid;
    xr = xrEl;
    view = xr.querySelector(".ly-view");
    renderBar();
    render();
  }

  function render() {
    const sc = scenarios.get(state.scenario);
    const m = state.method && methodById.get(state.method);
    const r = m && m.scenarios[sc.id];
    const details = $("#sg-details");
    xr.classList.toggle("testing", !!m);
    details.hidden = !m || !r || !!r.skip;
    if (!m) return renderSuggest(sc, null, null, []);
    if (!r || r.skip) {
      renderSuggest(sc, m, null, []);
      xr.querySelector(".sg-out").innerHTML = `<div class="cx-skip"><b>${esc(m.label)}</b> made no suggestion for this layout (${esc(r ? r.skip.replace(/_/g, " ") : "not evaluated")}). Few-shot conditions need at least one other layout that shares the condition's context, e.g. the same user and task.</div>`;
      return;
    }
    const rows = r.targets.map(([fid, outcome, source, hops, appScan, nav, adjust]) => ({ fid, outcome, source, hops, appScan, nav, adjust, manual: appScan + nav }));
    renderCost(sc, m, r, rows);
    renderTakeaways(sc, m, r, rows);
    const body = $("#cx-body");
    body.innerHTML = "";
    renderBoard(sc, m, r, rows, body);
    renderSuggest(sc, m, r, rows);
  }

  // The question and the method chips, each with its cost change for this layout.
  function renderBar() {
    const sc = scenarios.get(state.scenario);
    const chip = (m) => {
      const r = m.scenarios[sc.id];
      const d = r && !r.skip ? pct(r.cost[0], r.cost[1]) : null;
      return `<button type="button" class="sg-m${m.id === state.method ? " on" : ""}" data-method="${esc(m.id)}" aria-pressed="${m.id === state.method}">${esc(CHIP[m.id] || m.label)}` +
        `<span class="${d == null ? "na" : d <= 0 ? "good" : "bad"}">${d == null ? "—" : `${d > 0 ? "+" : ""}${d}%`}</span></button>`;
    };
    xr.querySelector(".sg-bar").innerHTML =
      `<div class="sg-q">Functionality suggestion for <span class="sg-ctx"><b>${esc(sc.user)}</b>, <b>${esc(sc.env)}</b>, <b>${esc(sc.task)}</b></span>` +
      `<small>${state.method ? "Its suggestions are above, linked to the widgets they serve." : "Pick a method to test it on this layout."}</small></div>` +
      `<div class="sg-ms" role="group" aria-label="Suggestion method">` +
      `<button type="button" class="sg-m sg-none${state.method ? "" : " on"}" aria-pressed="${!state.method}">None</button>${methods.slice(0, 3).map(chip).join("")}` +
      `<span class="sg-grp">Few-shot LLM</span>${methods.slice(3).map(chip).join("")}` +
      `</div>`;
  }

  function renderCost(sc, m, r, rows) {
    const [manual, suggest, scan] = r.cost;
    const max = Math.max(manual, suggest);
    const seg = (w, cls, title, fid) => (w > 0 ? `<span class="cx-seg ${cls}" style="flex:${w} 0 0"${fid ? ` data-fid="${esc(fid)}"` : ""} title="${esc(title)}"></span>` : "");
    const manualSegs = rows.map((t) => seg(t.manual, "man", `${appName(t.fid)} · ${facetLabel(t.fid)}: ${fmt(t.manual)} manually`, t.fid)).join("");
    const order = { H: 0, A: 1, M: 2 };
    const sugSegs = seg(scan, "scan", `Scanning the ${r.suggestions.length} suggestions: 0.5 × ${rows.length} needed facets`) +
      rows.slice().sort((a, b) => order[a.outcome] - order[b.outcome]).map((t) =>
        t.outcome === "A" ? seg(t.adjust, "A", `${facetLabel(t.fid)}: ${t.hops} hop${t.hops === 1 ? "" : "s"} from a suggestion`, t.fid)
          : t.outcome === "M" ? seg(t.manual, "M", `${facetLabel(t.fid)}: missed, ${fmt(t.manual)} manually`, t.fid) : "").join("");
    const d = pct(manual, suggest);
    $("#cx-cost").innerHTML =
      `<div class="cx-bar-row"><span class="cx-bar-l">Manual access</span><span class="cx-bar" style="width:${(manual / max) * 100}%">${manualSegs}</span><b>${fmt(manual)}</b></div>` +
      `<div class="cx-bar-row"><span class="cx-bar-l">With ${esc(m.label)}</span><span class="cx-bar" style="width:${(suggest / max) * 100}%">${sugSegs}</span><b>${fmt(suggest)}</b><span class="cx-delta ${d <= 0 ? "good" : "bad"}">${d > 0 ? "+" : ""}${d}%</span></div>` +
      `<div class="cx-legend"><i><span class="scan"></span>scanning the suggestions</i><i><span class="A"></span>hop from a suggestion</i><i><span class="M"></span>missed: app list + navigation</i><i><span class="man"></span>one needed facet, manually</i></div>`;
  }

  // A few-shot example is a scenario id; show it as the site names that layout.
  const byLowerId = new Map(D.scenarios.map((x) => [x.id.toLowerCase(), x]));
  const exampleLabel = (sid) => { const x = byLowerId.get(sid.toLowerCase()); return x ? `${x.user} · ${x.env} · ${x.task}` : sid; };

  function renderTakeaways(sc, m, r, rows) {
    const H = rows.filter((t) => t.outcome === "H"), A = rows.filter((t) => t.outcome === "A"), M = rows.filter((t) => t.outcome === "M");
    const used = new Set(rows.map((t) => t.source).filter(Boolean));
    const unused = r.suggestions.filter((f) => !used.has(f));
    const notes = [];
    notes.push(`<b>${H.length + A.length} of ${rows.length}</b> needed facets were reachable from the suggestions: ${H.length} exactly${A.length ? `, ${A.length} by a short hop from a same-app suggestion` : ""}. ${M.length ? `${M.length} had to be found manually.` : "None had to be found manually."}`);
    // Misses the data could have predicted, and misses nothing could have predicted.
    const strong = M.map((t) => ({ t, ev: evidence(sc, t.fid) })).sort((a, b) => b.ev.user.k / (b.ev.user.n || 1) - a.ev.user.k / (a.ev.user.n || 1));
    const signal = strong.find((x) => x.ev.user.k > 0 && x.ev.user.k / (x.ev.user.n || 1) >= 0.5);
    if (signal) notes.push(`<b>Missed ${esc(appName(signal.t.fid))} › ${esc(facetLabel(signal.t.fid))}</b>, though ${sc.user} placed it in ${signal.ev.user.k} of their ${signal.ev.user.n} other layouts. Weighting the user's history more would catch it.`);
    const novel = M.filter((t) => { const e = evidence(sc, t.fid); return e.user.k + e.env.k + e.task.k === 0; });
    if (novel.length) notes.push(`${novel.map((t) => `<b>${esc(appName(t.fid))} › ${esc(facetLabel(t.fid))}</b>`).join(", ")} ${novel.length === 1 ? "appears" : "appear"} in no other layout of this user, room, or task category, so ${novel.length === 1 ? "it is" : "they are"} hard for any method to predict.`);
    const nearMiss = M.filter((t) => r.suggestions.some((f) => !used.has(f) && facets.get(f).app === facets.get(t.fid).app));
    if (nearMiss.length) notes.push(`For ${nearMiss.map((t) => `<b>${esc(facetLabel(t.fid))}</b>`).join(", ")}, a suggestion from the same app was on screen but navigating from it was no cheaper than the app list.`);
    if (unused.length) {
      const pop = unused.map((f) => ({ f, ev: evidence(sc, f) })).sort((a, b) => b.ev.env.k / (b.ev.env.n || 1) - a.ev.env.k / (a.ev.env.n || 1))[0];
      notes.push(`${unused.length} of ${r.suggestions.length} suggestions went unused.` + (pop && pop.ev.env.k ? ` The most plausible one, <b>${esc(appName(pop.f))} › ${esc(facetLabel(pop.f))}</b>, is in ${pop.ev.env.k} of ${pop.ev.env.n} other ${esc(sc.env.toLowerCase())} layouts, but not this one.` : ""));
    }
    $("#cx-takeaways").innerHTML = (r.summary ? `<p class="cx-quote"><span>Model's rationale</span>“${esc(r.summary)}”</p>` : "") +
      (r.examples && r.examples.length ? `<p class="cx-examples">Few-shot examples in the prompt: ${r.examples.map((e) => `<button type="button" class="cx-ex" data-sid="${esc(e)}">${esc(exampleLabel(e))}</button>`).join(" ")}</p>` : "") +
      `<ul>${notes.map((n) => `<li>${n}</li>`).join("")}</ul>`;
    for (const b of root.querySelectorAll(".cx-ex")) b.addEventListener("click", () => {
      const id = [...scenarios.keys()].find((k) => k.toLowerCase() === b.dataset.sid.toLowerCase());
      if (id && window.ContextXRLayouts) ContextXRLayouts.show(id);
    });
  }

  function evidenceLine(sc, fid) {
    const e = evidence(sc, fid);
    const part = (lbl, x) => `<span class="${x.k ? "on" : ""}" title="${x.k} of ${x.n} other layouts">${lbl} ${x.k}/${x.n}</span>`;
    return `<span class="cx-ev">${part(sc.user, e.user)}${part(sc.env, e.env)}${part(sc.taskCat, e.task)}</span>`;
  }

  function renderBoard(sc, m, r, rows, body) {
    const rank = (fid) => r.suggestions.indexOf(fid) + 1;
    const reason = (fid) => (r.reasons && r.reasons[fid] ? `<span class="cx-reason">“${esc(r.reasons[fid][0])}”</span>` : "");
    const tier = (fid) => `<span class="cx-tier ${sc.targets[fid]}">${TIER_LABEL[sc.targets[fid]] || ""}</span>`;
    const section = (title, sub, cls) => {
      const s = document.createElement("section");
      s.className = "cx-sec " + cls;
      s.innerHTML = `<h4>${title}</h4>${sub ? `<p>${sub}</p>` : ""}`;
      body.appendChild(s);
      return s;
    };

    const H = rows.filter((t) => t.outcome === "H"), A = rows.filter((t) => t.outcome === "A"), M = rows.filter((t) => t.outcome === "M");
    const servedBy = new Map(rows.filter((t) => t.source).map((t) => [t.source, t.fid]));
    if (H.length) {
      const s = section(`Exact hits <span>${H.length}</span>`, "Suggested and needed. The user only scans the suggestion list (0.5 each).", "H");
      const strip = document.createElement("div");
      strip.className = "cx-strip";
      for (const t of H) strip.appendChild(miniPanel(t.fid, { badge: `<span class="cx-rank H">#${rank(t.fid)}</span>`, foot: tier(t.fid) + reason(t.fid) }));
      s.appendChild(strip);
    }
    if (A.length) {
      const s = section(`Reached from a nearby suggestion <span>${A.length}</span>`, "Not suggested, but a suggestion from the same app is a few hops away in the facet graph.", "A");
      for (const t of A) {
        const path = bfs(und, t.source, t.fid) || [{ id: t.source }, { id: t.fid }];
        const steps = path.map((p, i) => (i ? arrow(p.cap, p.fwd === false) : "") + chipFor(p.id, i === 0 ? "src" : i === path.length - 1 ? "dst" : "")).join("");
        s.appendChild(flowRow(
          miniPanel(t.source, { badge: `<span class="cx-rank A">#${rank(t.source)}</span>`, foot: reason(t.source) }),
          `${steps}`, `<b>${fmt(t.adjust)}</b> step${t.adjust === 1 ? "" : "s"}<small>manual ${fmt(t.manual)}</small>`,
          miniPanel(t.fid, { foot: tier(t.fid) + evidenceLine(sc, t.fid) })));
      }
    }
    if (M.length) {
      const s = section(`Missed <span>${M.length}</span>`, "No usable suggestion. The user opens the app list, finds the app, and navigates from its entry facet.", "M");
      for (const t of M) {
        const app = facets.get(t.fid).app;
        const path = bfs(out, apps.get(app).entry, t.fid) || [{ id: t.fid }];
        const pos = RES.appPositions[app];
        const steps = `<span class="cx-step list"><small>App list</small>page ${t.appScan} · #${pos}</span>` +
          path.map((p, i) => arrow(i ? p.cap : "") + chipFor(p.id, i === path.length - 1 ? "dst" : i === 0 ? "entry" : "")).join("");
        // Each suggestion serves at most one needed facet (paper §3.4.1).
        const same = r.suggestions.filter((f) => facets.get(f).app === app);
        const free = same.filter((f) => !servedBy.has(f));
        const pick = free[0] || same[0];
        const note = !same.length ? "" : free.length ? "Same app, but no closer than the app list" : `Same app, but already used for ${esc(facetLabel(servedBy.get(pick)))}`;
        const left = same.length
          ? miniPanel(pick, { cls: "dim", badge: `<span class="cx-rank">#${rank(pick)}</span>`, foot: `<span class="cx-note">${note}</span>` })
          : Object.assign(document.createElement("div"), { className: "cx-none", textContent: `No ${appName(t.fid)} suggestion` });
        s.appendChild(flowRow(left, steps, `<b>${fmt(t.manual)}</b> steps<small>app ${fmt(t.appScan)} + nav ${fmt(t.nav)}</small>`,
          miniPanel(t.fid, { cls: "miss", foot: tier(t.fid) + evidenceLine(sc, t.fid) })));
      }
    }
    const used = new Set(rows.map((t) => t.source).filter(Boolean));
    const unused = r.suggestions.filter((f) => !used.has(f));
    if (unused.length) {
      const s = section(`Suggested but not needed <span>${unused.length}</span>`, "Not in this participant's layout. Evidence shows how often it appears in other layouts with the same user, room, or task.", "U");
      const strip = document.createElement("div");
      strip.className = "cx-strip";
      for (const f of unused) strip.appendChild(miniPanel(f, { cls: "dim", badge: `<span class="cx-rank">#${rank(f)}</span>`, foot: reason(f) + evidenceLine(sc, f) }));
      s.appendChild(strip);
    }
  }

  function flowRow(left, steps, cost, right) {
    const row = document.createElement("div");
    row.className = "cx-flow";
    const mid = document.createElement("div");
    mid.className = "cx-path";
    mid.innerHTML = `<div class="cx-steps">${steps}</div><div class="cx-pcost">${cost}</div>`;
    row.append(left, mid, right);
    return row;
  }



  function pathHTML(t, r, sc) {
    if (t.outcome === "A") {
      const path = bfs(und, t.source, t.fid) || [{ id: t.source }, { id: t.fid }];
      return path.map((p, i) => (i ? arrow(p.cap, p.fwd === false) : "") + chipFor(p.id, i === 0 ? "src" : i === path.length - 1 ? "dst" : "")).join("");
    }
    if (t.outcome === "M") {
      const app = facets.get(t.fid).app;
      const path = bfs(out, apps.get(app).entry, t.fid) || [{ id: t.fid }];
      return `<span class="cx-step list"><small>App list</small>page ${t.appScan} · #${RES.appPositions[app]}</span>` +
        path.map((p, i) => arrow(i ? p.cap : "") + chipFor(p.id, i === path.length - 1 ? "dst" : i === 0 ? "entry" : "")).join("");
    }
    return chipFor(t.fid, "dst");
  }

  function xrPanel(fid, cls, badge, width) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "xr-p " + cls;
    el.dataset.facet = fid;
    el.style.width = width + "px";
    el.innerHTML = `<span class="xr-badge">${badge}</span><div class="xr-frame" style="max-height:${Math.round(width * 1.12)}px"></div><span class="xr-name" title="${esc(appName(fid))} · ${esc(facetLabel(fid))}">${esc(isEntry(fid) ? appName(fid) : facetLabel(fid))}</span>`;
    const mk = window.FacetMockup && FacetMockup.render(fid, { appName: appName(fid), facetName: isEntry(fid) ? "Home" : "" });
    if (mk) { mk.style.zoom = (width / 340).toFixed(3); el.querySelector(".xr-frame").appendChild(mk); }
    return el;
  }

  // Suggestions below the view, outcome badges on the participant's widgets, and links between them.
  let sceneArgs = null;
  function renderSuggest(sc, m, r, rows) {
    sceneArgs = r ? [sc, m, r, rows] : null;
    const outBox = xr.querySelector(".sg-out");
    const byFid = new Map(rows.map((t) => [t.fid, t]));
    const rank = (fid) => (r ? r.suggestions.indexOf(fid) + 1 : 0);
    // Outcome on each widget of the layout (the tier badge comes back when no method is chosen).
    for (const el of view.querySelectorAll(".ly-p")) {
      const t = byFid.get(el.dataset.facet);
      el.classList.remove("H", "A", "M");
      const badge = el.querySelector(".xr-badge");
      if (!badge.dataset.tier) badge.dataset.tier = badge.textContent;
      if (!t) { badge.textContent = badge.dataset.tier; continue; }
      el.classList.add(t.outcome);
      badge.textContent = t.outcome === "H" ? `✓ #${rank(t.fid)}` : t.outcome === "A" ? `${fmt(t.adjust)} step${t.adjust === 1 ? "" : "s"}` : `✗ ${fmt(t.manual)}`;
    }
    if (!m) { outBox.innerHTML = ""; drawLinks([]); return; }
    if (!r) { drawLinks([]); return; }
    const W = xr.clientWidth || 1200;
    const gap = W < 700 ? 8 : 16;
    const sw = Math.max(64, Math.min(128, Math.floor((W - 2 * (W < 700 ? 12 : 28) - 24 - gap * 9) / 10)));
    outBox.innerHTML = `<div class="xr-row xr-sug"></div>
      <div class="xr-foot">
        <span class="xr-label">Suggested · ${esc(m.label)}</span>
        <span class="xr-key"><i class="H"></i>exact hit <i class="A"></i>reached from a suggestion <i class="M"></i>missed <i class="U"></i>not needed</span>
        <span class="xr-score"><span>Manual <b>${fmt(r.cost[0])}</b></span><span>→ with suggestions <b>${fmt(r.cost[1])}</b></span><em class="${r.cost[1] <= r.cost[0] ? "good" : "bad"}">${pct(r.cost[0], r.cost[1])}%</em></span>
      </div>`;
    const sugBox = outBox.querySelector(".xr-sug");
    sugBox.style.gap = gap + "px";
    const servedBy = new Map(rows.filter((t) => t.source).map((t) => [t.source, t]));
    // Suggestions that serve a needed widget follow the widgets from left to right, so links
    // cross as little as possible; unused ones go last, in rank order. The badge keeps the rank.
    const cx = (fid) => { const el = view.querySelector(`.ly-p[data-facet="${CSS.escape(fid)}"]`); return el ? +el.dataset.x + el.offsetWidth / 2 : 0; };
    const pos = (fid) => (servedBy.has(fid) ? cx(servedBy.get(fid).fid) : 1e6 + rank(fid));
    for (const fid of r.suggestions.slice().sort((a, b) => pos(a) - pos(b))) {
      const t = servedBy.get(fid);
      sugBox.appendChild(xrPanel(fid, "sug " + (t ? t.outcome : "U"), `#${rank(fid)}`, sw));
    }
    requestAnimationFrame(() => drawLinks(rows));
  }

  function drawLinks(rows) {
    const svg = xr && xr.querySelector(".xr-links");
    if (!svg) return;
    if (!rows) rows = sceneArgs ? sceneArgs[3] : [];
    const box = xr.getBoundingClientRect();
    svg.setAttribute("width", box.width);
    svg.setAttribute("height", box.height);
    const at = (sel, fid) => xr.querySelector(`${sel}[data-facet="${CSS.escape(fid)}"] .xr-frame`);
    svg.innerHTML = rows.filter((t) => t.source).map((t) => {
      const a = at(".ly-p", t.fid), b = at(".xr-p.sug", t.source);
      if (!a || !b) return "";
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      const x1 = ra.left + ra.width / 2 - box.left, y1 = ra.bottom - box.top + 24;
      const x2 = rb.left + rb.width / 2 - box.left, y2 = rb.top - box.top - 26;
      const my = (y1 + y2) / 2;
      const label = t.outcome === "A" ? `<g class="xr-hop" transform="translate(${(x1 + x2) / 2} ${my})"><rect x="-26" y="-11" width="52" height="22" rx="11"/><text y="4">${t.hops} hop${t.hops === 1 ? "" : "s"}</text></g>` : "";
      return `<g class="xr-link ${t.outcome}" data-fid="${esc(t.fid)}" data-src="${esc(t.source)}"><path d="M${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}"/>${label}</g>`;
    }).join("");
  }

  // Hover: popover with how the simulated user reaches the facet, and highlight its link.
  root.addEventListener("pointerover", (ev) => {
    const p = ev.target.closest(".xr .xr-p");
    if (!p || !sceneArgs || root.querySelector(".ly-p.dragging")) return;
    const [sc, m, r, rows] = sceneArgs;
    const fid = p.dataset.facet, isGt = p.classList.contains("gt");
    const t = isGt ? rows.find((x) => x.fid === fid) : rows.find((x) => x.source === fid);
    const rk = r ? r.suggestions.indexOf(isGt ? (t && t.source) || fid : fid) + 1 : 0;
    let head, body = "";
    if (isGt && !t) head = `<b>${esc(facetLabel(fid))}</b> · needed (${sc.targets[fid]})`;
    else if (isGt && t.outcome === "H") { head = `<span class="xr-o H">Exact hit</span> suggested at #${rk}`; body = `Just scan the suggestions: <b>0.5</b> instead of <b>${fmt(t.manual)}</b> manually.`; }
    else if (isGt && t.outcome === "A") { head = `<span class="xr-o A">Reached from suggestion #${rk}</span>`; body = `<div class="cx-steps">${pathHTML(t, r, sc)}</div><b>${fmt(t.adjust)}</b> step${t.adjust === 1 ? "" : "s"} (+0.5 scan) instead of <b>${fmt(t.manual)}</b> manually.`; }
    else if (isGt) { head = `<span class="xr-o M">Missed</span> found manually`; body = `<div class="cx-steps">${pathHTML(t, r, sc)}</div>App list ${fmt(t.appScan)} + navigation ${fmt(t.nav)} = <b>${fmt(t.manual)}</b> steps.`; }
    else if (t) { head = `<span class="xr-o ${t.outcome}">#${rk}</span> ${t.outcome === "H" ? "is needed: exact hit" : `leads to <b>${esc(facetLabel(t.fid))}</b> in ${t.hops} hop${t.hops === 1 ? "" : "s"}`}`; }
    else head = `<span class="xr-o U">#${rk} not needed</span> in this layout`;
    if (isGt && t !== undefined) body += `<div class="xr-ev">${sc.targets[fid]} · ${evidenceLine(sc, fid)}</div>`;
    if (!isGt) {
      if (r && r.reasons && r.reasons[fid]) body += `<div class="cx-reason">“${esc(r.reasons[fid][0])}”</div>`;
      body += `<div class="xr-ev">${evidenceLine(sc, fid)}</div>`;
    }
    const pop = xr.querySelector(".xr-pop");
    pop.innerHTML = `<div class="xr-pop-h"><small>${esc(appName(fid))}</small> ${esc(facetLabel(fid))}</div><div>${head}</div>${body}`;
    pop.classList.add("show");
    const box = xr.getBoundingClientRect(), pr = p.getBoundingClientRect(), qr = pop.getBoundingClientRect();
    const left = Math.min(Math.max(8, pr.left - box.left + pr.width / 2 - qr.width / 2), box.width - qr.width - 8);
    const top = pr.top - box.top - qr.height - 8;
    pop.style.left = left + "px";
    pop.style.top = Math.max(8, top) + "px";
    // Highlight the pair and its link.
    const partner = t ? (isGt ? t.source : t.fid) : null;
    xr.classList.add("focus");
    xr.querySelectorAll(".xr-p").forEach((x) => x.classList.toggle("on", x === p || (!!partner && x.dataset.facet === partner && x.classList.contains(isGt ? "sug" : "ly-p"))));
    xr.querySelectorAll(".xr-link").forEach((l) => l.classList.toggle("on", !!t && l.dataset.fid === t.fid));
  });
  root.addEventListener("pointerout", (ev) => {
    const p = ev.target.closest(".xr .xr-p");
    if (!p || (ev.relatedTarget && p.contains(ev.relatedTarget))) return;
    xr.classList.remove("focus");
    xr.querySelector(".xr-pop")?.classList.remove("show");
    xr.querySelectorAll(".xr-p.on, .xr-link.on").forEach((x) => x.classList.remove("on"));
  });
  // The layout's own widgets open on click in js/layouts.js (a press that is not a drag).
  root.addEventListener("click", (ev) => {
    const p = ev.target.closest(".xr-p.sug");
    if (p) openDetail(p.dataset.facet);
  });

  // ---------- detail dialog (Fig. 2 style capability callouts) ----------
  const dlg = document.getElementById("cx-dialog");
  root.addEventListener("click", (ev) => {
    const card = ev.target.closest(".cx-mini");
    if (card) openDetail(card.dataset.facet);
  });
  root.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest("[data-fid]");
    root.querySelectorAll(".cx-hot").forEach((x) => x.classList.remove("cx-hot"));
    if (el) root.querySelectorAll(`.cx-mini[data-facet="${CSS.escape(el.dataset.fid)}"], [data-fid="${CSS.escape(el.dataset.fid)}"]`).forEach((x) => x.classList.add("cx-hot"));
  });

  // scenarioId: a MineXR layout to show what its widgets exposed; false: the facet alone.
  function openDetail(fid, scenarioId) {
    const sc = scenarioId === false ? null : scenarios.get(scenarioId || state.scenario);
    const f = facets.get(fid);
    const exposed = (sc && sc.caps && sc.caps[fid]) || {};
    // The chosen method's suggestion and reason, when the dialog is about the layout being tested.
    const r = sc && state.method && sc.id === state.scenario ? methodById.get(state.method).scenarios[sc.id] || {} : {};
    const status = !sc ? `${f.caps.length} capabilities` : fid in sc.targets ? `Needed in this layout (${sc.targets[fid]})` : "Not in this layout";
    const rk = r.suggestions ? r.suggestions.indexOf(fid) + 1 : 0;
    dlg.innerHTML = `<form method="dialog" class="cx-dlg-x"><button aria-label="Close">×</button></form>
      <div class="cx-dlg-head"><span class="chip facet">${esc(facetLabel(fid))}</span><span>${esc(appName(fid))}</span></div>
      <p class="cx-dlg-desc">${esc(f.desc)}</p>
      <p class="cx-dlg-meta">${esc(status)}${rk ? ` · suggested at #${rk} by ${esc(methodById.get(state.method).label)}` : ""}${Object.keys(exposed).length ? ` · <span class="exp">capabilities the participant's widgets exposed</span>` : ""}</p>
      ${r.reasons && r.reasons[fid] ? `<p class="cx-reason big">“${esc(r.reasons[fid][0])}”</p>` : ""}
      <div class="cx-annot"><div class="cx-annot-panel"></div><svg class="cx-annot-lines"></svg><div class="cx-annot-labels"></div></div>
      <div class="cx-map-h">Where it sits in the ${esc(appName(fid))} facet graph</div>
      <div class="cx-map">${appMapHTML(fid)}</div>`;
    const panel = window.FacetMockup && FacetMockup.render(fid, { appName: appName(fid), facetName: isEntry(fid) ? "Home" : "" });
    const host = dlg.querySelector(".cx-annot-panel");
    if (panel) host.appendChild(panel);
    const labels = dlg.querySelector(".cx-annot-labels");
    labels.innerHTML = f.caps.map((c) => `<span class="chip cap${c.startsWith("open_") ? " nav" : ""}${c in exposed ? " exposed" : ""}" data-c="${esc(c)}">${esc(c)}</span>`).join("");
    dlg.querySelectorAll(".cx-map [data-facet]").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.facet !== fid) openDetail(b.dataset.facet, scenarioId);
    }));
    if (!dlg.open) dlg.showModal();
    dlg.scrollTop = 0;
    requestAnimationFrame(() => { layoutCallouts(dlg, panel); drawAppMap(dlg, fid); });
  }

  // The facet's own app as a small graph: the app (its entry facet) on the left, then one column
  // per navigation depth. The facet and the shortest way to it from the app's entry are marked.
  function appDepths(app) {
    const entry = apps.get(app).entry;
    const depth = new Map([[entry, 0]]);
    const q = [entry];
    for (const u of q) for (const e of out.get(u) || []) {
      if (!depth.has(e.to) && facets.get(e.to).app === app) { depth.set(e.to, depth.get(u) + 1); q.push(e.to); }
    }
    const max = Math.max(...depth.values());
    for (const f of D.facets) if (f.app === app && !depth.has(f.id)) depth.set(f.id, max + 1);
    return depth;
  }
  function appMapHTML(fid) {
    const app = facets.get(fid).app;
    const depth = appDepths(app);
    const path = new Set((bfs(out, apps.get(app).entry, fid) || []).map((p) => p.id));
    const cols = [];
    for (const [id, d] of depth) (cols[d] = cols[d] || []).push(id);
    const node = (id) => {
      const cls = (id === fid ? " cur" : path.has(id) ? " path" : "");
      return isEntry(id)
        ? `<button type="button" class="chip app on${cls}" data-facet="${esc(id)}" title="${esc(appName(id))} · Open Section">${esc(appName(id))}</button>`
        : `<button type="button" class="chip facet${cls}" data-facet="${esc(id)}">${esc(facets.get(id).name)}</button>`;
    };
    return `<svg class="cx-map-lines"></svg><div class="cx-map-cols">${cols.filter(Boolean).map((c) => `<div class="cx-map-col">${c.map(node).join("")}</div>`).join("")}</div>`;
  }
  function drawAppMap(dlg, fid) {
    const box = dlg.querySelector(".cx-map"), svg = dlg.querySelector(".cx-map-lines");
    if (!box) return;
    const app = facets.get(fid).app;
    const depth = appDepths(app);
    const path = bfs(out, apps.get(app).entry, fid) || [];
    const onPath = new Set(path.slice(1).map((p, i) => path[i].id + ">" + p.id));
    const b = box.getBoundingClientRect();
    const at = (id) => box.querySelector(`[data-facet="${CSS.escape(id)}"]`).getBoundingClientRect();
    const inner = box.querySelector(".cx-map-cols");
    svg.setAttribute("width", inner.scrollWidth); svg.setAttribute("height", inner.scrollHeight);
    let lines = "", hot = "";
    for (const [s, t] of D.edges) {
      if (s === t || facets.get(s).app !== app || facets.get(t).app !== app || depth.get(t) <= depth.get(s)) continue;
      const a = at(s), c = at(t);
      const x1 = a.right - b.left + box.scrollLeft, y1 = a.top + a.height / 2 - b.top;
      const x2 = c.left - b.left + box.scrollLeft - 3, y2 = c.top + c.height / 2 - b.top;
      const mx = (x1 + x2) / 2;
      const d = `<path d="M${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}"/>`;
      if (onPath.has(s + ">" + t)) hot += d; else lines += d;
    }
    svg.innerHTML = `<g class="dim">${lines}</g><g class="hot">${hot}</g>`;
    // keep the facet in view when the app's graph is wider than the dialog
    const cur = box.querySelector(".cur");
    if (cur && box.scrollWidth > box.clientWidth) box.scrollLeft = Math.max(0, cur.offsetLeft - box.clientWidth / 2);
  }

  function layoutCallouts(dlg, panel) {
    const box = dlg.querySelector(".cx-annot"), svg = dlg.querySelector(".cx-annot-lines");
    const labels = [...dlg.querySelectorAll(".cx-annot-labels .chip")];
    if (!panel) return;
    const b = box.getBoundingClientRect();
    const items = labels.map((lab) => {
      const el = [...panel.querySelectorAll("[data-cap]")].find((x) => x.dataset.cap.split(" ").includes(lab.dataset.c));
      const r = el ? el.getBoundingClientRect() : null;
      return { lab, el, y: r ? r.top + r.height / 2 - b.top : 0, x: r ? r.right - b.left : 0 };
    }).sort((a, b2) => a.y - b2.y);
    let prev = -Infinity;
    const H = 24;
    for (const it of items) { it.ly = Math.max(it.y - H / 2, prev + 4); prev = it.ly + H; }
    const lx = panel.offsetWidth + 56;
    svg.setAttribute("width", b.width); svg.setAttribute("height", Math.max(prev, panel.offsetHeight) + 8);
    box.style.height = Math.max(prev, panel.offsetHeight) + 8 + "px";
    svg.innerHTML = items.map((it) => {
      it.lab.style.transform = `translate(${lx}px, ${it.ly}px)`;
      if (!it.el) return "";
      const y2 = it.ly + H / 2;
      return `<circle cx="${it.x - 6}" cy="${it.y}" r="3" class="dot${it.lab.classList.contains("nav") ? " nav" : ""}"/><path d="M${it.x - 6} ${it.y} C ${it.x + 24} ${it.y}, ${lx - 24} ${y2}, ${lx} ${y2}" class="${it.lab.classList.contains("nav") ? "nav" : ""}"/>`;
    }).join("");
    for (const it of items) {
      it.lab.addEventListener("pointerenter", () => it.el && it.el.classList.add("hover"));
      it.lab.addEventListener("pointerleave", () => it.el && it.el.classList.remove("hover"));
    }
  }

  dlg.addEventListener("click", (ev) => { if (ev.target === dlg) dlg.close(); });

  // ---------- controls ----------
  root.addEventListener("click", (ev) => {
    const b = ev.target.closest(".sg-m");
    if (!b || !xr) return;
    state.method = b.classList.contains("sg-none") ? null : b.dataset.method;
    // The suggestions open above the bar; scroll with them so the bar stays under the pointer.
    const y0 = xr.querySelector(".sg-bar").getBoundingClientRect().top;
    renderBar();
    render();
    const dy = xr.querySelector(".sg-bar").getBoundingClientRect().top - y0;
    if (window.ContextXREmbed) ContextXREmbed.scrollBy(dy); else window.scrollBy(0, dy);
  });

  window.ContextXRSuggest = { update, redraw: () => drawLinks(), detail: openDetail };
})();
