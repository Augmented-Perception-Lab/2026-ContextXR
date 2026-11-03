// Context factor analysis (paper §4.1, Fig. 4). For each facet placed in at least two layouts,
// lift_d = P(facet in both layouts | the pair shares d) / P(facet in both | any pair), for d in
// user, task, environment (contextxr/tasks/factor_analysis.py). Three linked views:
//   - the dominant-factor counts (Fig. 4 left) as a proportional bar that filters the others,
//   - a triangle with one dot per facet, placed by the share of its lift on each factor,
//   - a list of every facet's lift profile (Fig. 4 right), grouped by dominant factor.
(function () {
  "use strict";

  const D = window.MINEXRPP;
  const root = document.getElementById("factors");
  if (!D || !D.factors || !root) return;

  const F = D.factors;
  const KINDS = [
    { id: "user", label: "User", short: "U", tiny: "User" },
    { id: "task", label: "Task", short: "T", tiny: "Task" },
    { id: "environment", label: "Environment", short: "E", tiny: "Env" },
    { id: "mixed", label: "Mixed", short: "", tiny: "Mix" },
    { id: "none", label: "No lift", short: "", tiny: "None" },
  ];
  const DIMS = KINDS.slice(0, 3);
  const prettyName = (s) => (s === s.toLowerCase() ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : s);
  const apps = new Map(D.apps.map((a) => [a.id, { ...a, name: prettyName(a.name) }]));
  const facets = new Map(D.facets.map((f) => [f.id, f]));
  const isEntry = (fid) => apps.get(facets.get(fid).app).entry === fid;
  const facetLabel = (fid) => (isEntry(fid) ? "Open Section" : facets.get(fid).name);
  const appName = (fid) => apps.get(facets.get(fid).app).name;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const fmt = (x) => x.toFixed(2);
  const $ = (sel) => root.querySelector(sel);

  // The representative facets of Fig. 4, labelled directly on the triangle.
  const EXAMPLES = ["duolingo.complete_lesson", "books.browse_library", "netflix.browse_content", "reminders.browse_task_lists"];
  const items = F.facets.filter((f) => facets.has(f.id)).map((f) => ({ ...f, top: Math.max(...f.lift) }));
  const state = { filter: null, hover: null };

  // ---------- lift profile: one bar per factor, scaled to the facet's highest lift ----------
  function bars(f) {
    const max = Math.max(f.top, 1);
    const one = (1 / max) * 100;
    return `<div class="fa-bars">${DIMS.map((d, i) => {
      const v = f.lift[i];
      return `<span class="fa-d">${d.short}</span><span class="fa-track"><i class="${d.id}" style="width:${(v / max) * 100}%"></i>` +
        `<s style="left:${one}%" title="lift 1: as often as any pair"></s></span><b class="${v === f.top && f.dominant !== "none" ? "top" : ""}">${fmt(v)}</b>`;
    }).join("")}</div>`;
  }

  // ---------- counts bar (Fig. 4 left), also the filter ----------
  function renderCounts() {
    const total = items.length;
    $("#fa-counts").innerHTML = KINDS.map((k) => {
      const n = F.counts[k.id] || 0;
      return `<button type="button" class="fa-seg ${k.id}${state.filter === k.id ? " on" : ""}" data-kind="${k.id}" style="flex:${n} 1 0" aria-pressed="${state.filter === k.id}" title="${n} ${k.label.toLowerCase()}${k.id === "none" || k.id === "mixed" ? "" : "-dominant"} facets">` +
        `<i></i><span><b>${n}</b> <em class="lg">${k.label}</em><em class="sm">${k.tiny}</em></span></button>`;
    }).join("");
    $("#fa-total").textContent = `${total} facets placed in at least 2 layouts`;
  }

  // ---------- triangle ----------
  const VB = { w: 560, h: 520 };
  const C = { user: [280, 44], task: [52, 420], environment: [508, 420] };
  const STRIP_Y = 486;
  const radius = (f) => 3.5 + 1.35 * Math.sqrt(f.n);
  const pt = (w) => [0, 1].map((k) => DIMS.reduce((s, d, i) => s + w[i] * C[d.id][k], 0));

  // Where each dominance region ends: the top lift is at least `dominanceRatio` times the second.
  function regions() {
    const r = F.dominanceRatio;
    return DIMS.map((d, i) => {
      const [j, k] = [0, 1, 2].filter((x) => x !== i);
      const corner = [0, 0, 0]; corner[i] = 1;
      const edgeJ = [0, 0, 0]; edgeJ[i] = r / (r + 1); edgeJ[j] = 1 / (r + 1);
      const mid = [0, 0, 0]; mid[i] = r / (r + 2); mid[j] = 1 / (r + 2); mid[k] = 1 / (r + 2);
      const edgeK = [0, 0, 0]; edgeK[i] = r / (r + 1); edgeK[k] = 1 / (r + 1);
      return `<path class="fa-region ${d.id}" d="M${[corner, edgeJ, mid, edgeK].map((v) => pt(v).map((x) => x.toFixed(1)).join(" ")).join(" L")}Z"/>`;
    }).join("");
  }

  // Dots start at their barycentric position and are nudged apart so none hides another.
  function layout() {
    const lifted = items.filter((f) => f.dominant !== "none");
    for (const f of lifted) {
      const s = f.lift.reduce((a, b) => a + b, 0);
      [f.tx, f.ty] = pt(f.lift.map((v) => v / s));
      [f.x, f.y] = [f.tx, f.ty];
      f.r = radius(f);
    }
    const inside = (f) => {
      // keep the dot within the triangle (shrunk by its radius) by clamping its barycentric weights
      const [ax, ay] = C.user, [bx, by] = C.task, [cx, cy] = C.environment;
      const det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      let l1 = ((by - cy) * (f.x - cx) + (cx - bx) * (f.y - cy)) / det;
      let l2 = ((cy - ay) * (f.x - cx) + (ax - cx) * (f.y - cy)) / det;
      let l3 = 1 - l1 - l2;
      const m = 0.01;
      [l1, l2, l3] = [l1, l2, l3].map((l) => Math.max(m, l));
      const s = l1 + l2 + l3;
      [f.x, f.y] = pt([l1 / s, l2 / s, l3 / s]);
    };
    for (let it = 0; it < 260; it++) {
      for (let a = 0; a < lifted.length; a++) {
        for (let b = a + 1; b < lifted.length; b++) {
          const p = lifted[a], q = lifted[b];
          let dx = q.x - p.x, dy = q.y - p.y;
          let d = Math.hypot(dx, dy);
          const min = p.r + q.r + 1.5;
          if (d >= min) continue;
          if (d < 1e-6) { dx = Math.cos(a * 2.4 + b); dy = Math.sin(a * 2.4 + b); d = 1; }
          const push = (min - d) / 2;
          p.x -= (dx / d) * push; p.y -= (dy / d) * push;
          q.x += (dx / d) * push; q.y += (dy / d) * push;
        }
      }
      // pull toward the true position, less so at the end so the last passes only separate
      const pull = it < 160 ? 0.04 : 0;
      for (const f of lifted) { f.x += (f.tx - f.x) * pull; f.y += (f.ty - f.y) * pull; if (it % 4 === 0 || it > 200) inside(f); }
    }
    // Facets with no lift above 1 go in a strip below, largest first.
    const none = items.filter((f) => f.dominant === "none").sort((a, b) => b.n - a.n);
    let x = 120;
    for (const f of none) { f.r = radius(f); f.x = x + f.r; f.y = STRIP_Y; x += 2 * f.r + 4; }
  }

  function renderTriangle() {
    const [U, T, E] = [C.user, C.task, C.environment];
    const label = (f) => {
      const right = f.x < VB.w / 2;
      return `<text class="fa-ex" x="${(f.x + (right ? f.r + 6 : -f.r - 6)).toFixed(1)}" y="${(f.y + 4).toFixed(1)}" text-anchor="${right ? "start" : "end"}">${esc(appName(f.id))}: ${esc(facetLabel(f.id))}</text>`;
    };
    const dots = items.map((f) => `<circle class="fa-dot ${f.dominant}" data-fid="${esc(f.id)}" cx="${f.x.toFixed(1)}" cy="${f.y.toFixed(1)}" r="${f.r.toFixed(1)}"/>`).join("");
    $("#fa-tri").innerHTML =
      `<svg viewBox="0 0 ${VB.w} ${VB.h}" role="img" aria-label="Each facet placed by the share of its lift on user, task and environment">` +
      regions() +
      `<path class="fa-frame" d="M${U.join(" ")} L${T.join(" ")} L${E.join(" ")}Z"/>` +
      `<text class="fa-corner" x="${U[0]}" y="${U[1] - 16}" text-anchor="middle">User</text>` +
      `<text class="fa-corner" x="${T[0] - 6}" y="${T[1] + 26}" text-anchor="start">Task</text>` +
      `<text class="fa-corner" x="${E[0] + 6}" y="${E[1] + 26}" text-anchor="end">Environment</text>` +
      `<text class="fa-mid" x="${(U[0] + T[0] + E[0]) / 3}" y="${(U[1] + T[1] + E[1]) / 3 + 46}" text-anchor="middle">mixed</text>` +
      `<text class="fa-strip" x="0" y="${STRIP_Y + 4}">No lift</text>` +
      dots + items.filter((f) => EXAMPLES.includes(f.id)).map(label).join("") + `</svg>`;
  }

  // ---------- list of profiles ----------
  function renderList() {
    const q = ($("#fa-q").value || "").trim().toLowerCase();
    const match = (f) => !q || `${appName(f.id)} ${facetLabel(f.id)}`.toLowerCase().includes(q);
    $("#fa-list").innerHTML = KINDS.filter((k) => !state.filter || state.filter === k.id).map((k) => {
      const rows = items.filter((f) => f.dominant === k.id && match(f)).sort((a, b) => b.top - a.top || b.n - a.n);
      if (!rows.length) return "";
      return `<div class="fa-group"><h4><i class="${k.id}"></i>${k.label}${k.id === "none" || k.id === "mixed" ? "" : "-dominant"} <span>${rows.length}</span></h4>` +
        rows.map((f) => `<button type="button" class="fa-row" data-fid="${esc(f.id)}"><span class="fa-name"><small>${esc(appName(f.id))}</small>${esc(facetLabel(f.id))}</span>` +
          `<span class="fa-n" title="placed in ${f.n} layouts">${f.n}</span>${bars(f)}</button>`).join("") + `</div>`;
    }).join("") || `<p class="fa-empty">No facet matches.</p>`;
  }

  // ---------- filter, hover, click ----------
  function applyFilter() {
    root.classList.toggle("fa-filtered", !!state.filter);
    root.querySelectorAll(".fa-dot").forEach((c) => c.classList.toggle("dim", !!state.filter && !c.classList.contains(state.filter)));
    renderCounts();
    renderList();
  }
  $("#fa-counts").addEventListener("click", (ev) => {
    const b = ev.target.closest(".fa-seg");
    if (!b) return;
    state.filter = state.filter === b.dataset.kind ? null : b.dataset.kind;
    applyFilter();
  });
  $("#fa-q").addEventListener("input", renderList);

  const tip = $("#fa-tip");
  function showTip(fid, anchor) {
    const f = items.find((x) => x.id === fid);
    if (!f) return;
    const kind = KINDS.find((k) => k.id === f.dominant);
    tip.innerHTML = `<div class="fa-tip-mk"></div><div class="fa-tip-h"><small>${esc(appName(fid))}</small> ${esc(facetLabel(fid))}</div>` +
      `<div class="fa-tip-k"><i class="${f.dominant}"></i>${kind.label}${f.dominant === "none" || f.dominant === "mixed" ? "" : "-dominant"} · placed in ${f.n} layouts</div>${bars(f)}` +
      `<div class="fa-tip-m">Click to open the panel</div>`;
    const mk = window.FacetMockup && FacetMockup.render(fid, { appName: appName(fid), facetName: isEntry(fid) ? "Home" : "" });
    if (mk) tip.querySelector(".fa-tip-mk").appendChild(mk); else tip.querySelector(".fa-tip-mk").remove();
    tip.classList.add("show");
    const r = anchor.getBoundingClientRect(), tr = tip.getBoundingClientRect();
    let left = r.right + 12;
    if (left + tr.width > window.innerWidth - 8) left = r.left - tr.width - 12;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.min(Math.max(8, r.top + r.height / 2 - tr.height / 2), window.innerHeight - tr.height - 8) + "px";
  }
  function setHover(fid, anchor) {
    root.querySelectorAll(".fa-dot.hot, .fa-row.hot").forEach((x) => x.classList.remove("hot"));
    if (!fid) { tip.classList.remove("show"); return; }
    root.querySelectorAll(`[data-fid="${CSS.escape(fid)}"]`).forEach((x) => x.classList.add("hot"));
    showTip(fid, anchor);
  }
  root.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest(".fa-dot, .fa-row");
    if (el) setHover(el.dataset.fid, el);
  });
  root.addEventListener("pointerout", (ev) => {
    const el = ev.target.closest(".fa-dot, .fa-row");
    if (el && !(ev.relatedTarget && el.contains(ev.relatedTarget))) setHover(null);
  });
  root.addEventListener("click", (ev) => {
    const el = ev.target.closest(".fa-dot, .fa-row");
    if (el && window.ContextXRSuggest) { setHover(null); ContextXRSuggest.detail(el.dataset.fid, false); }
  });
  root.addEventListener("pointerleave", () => setHover(null));
  window.addEventListener("scroll", () => tip.classList.remove("show"), { passive: true });

  layout();
  renderTriangle();
  applyFilter();
})();
