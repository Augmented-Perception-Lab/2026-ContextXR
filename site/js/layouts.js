// MineXR++ contextual layouts: one participant's ground-truth layout for one scenario, placed in
// the participant's view. The widgets start by tier: primary in the centre, peripheral in columns
// on the left and right, ambient in the outermost columns (a single row along the bottom when the
// view is too narrow). Scenarios are picked by room, then from the room's layouts grouped by task category.
// Widgets can be dragged anywhere (positions are kept per scenario until "Reset layout"), and a
// click opens the panel with the capabilities the participant's widgets exposed.
(function () {
  "use strict";

  const D = window.MINEXRPP;
  const root = document.getElementById("layouts");
  if (!D || !root) return;

  const DEFAULT_SCENARIO = "P003_Kitchen_CookingSolo";
  const TIERS = ["primary", "peripheral", "ambient"];
  const prettyName = (s) => (s === s.toLowerCase() ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : s);
  const apps = new Map(D.apps.map((a) => [a.id, { ...a, name: prettyName(a.name) }]));
  const facets = new Map(D.facets.map((f) => [f.id, f]));
  const scenarios = new Map(D.scenarios.map((s) => [s.id, s]));
  const isEntry = (fid) => apps.get(facets.get(fid).app).entry === fid;
  const facetLabel = (fid) => (isEntry(fid) ? "Open Section" : facets.get(fid).name);
  const appName = (fid) => apps.get(facets.get(fid).app).name;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  const $ = (sel) => root.querySelector(sel);
  const xr = $("#ly-xr");

  const state = { scenario: scenarios.has(DEFAULT_SCENARIO) ? DEFAULT_SCENARIO : D.scenarios[0].id };
  // scenario id → Map(fid → {x, y}) as fractions of the view, so a resize keeps the layout.
  const moved = new Map();
  let top = 10;

  // ---------- picker: room tabs, then the room's layouts grouped by task category ----------
  const inRoom = (env) => D.scenarios.filter((sc) => sc.env === env)
    .sort((a, b) => a.user.length - b.user.length || a.user.localeCompare(b.user) || a.task.localeCompare(b.task));

  function renderPicker() {
    const cur = scenarios.get(state.scenario);
    const tabs = $("#ly-rooms");
    tabs.innerHTML = "";
    for (const env of D.environments) {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", String(env === cur.env));
      b.textContent = env;
      b.addEventListener("click", () => env !== cur.env && pickRoom(env));
      tabs.appendChild(b);
    }
    const list = inRoom(cur.env);
    $("#ly-groups").innerHTML = D.taskCategories.map((cat) => {
      const group = list.filter((sc) => sc.taskCat === cat);
      if (!group.length) return "";
      return `<div class="ly-group"><span class="ly-cat">${esc(cat)}</span><div class="gt-scenarios">` +
        group.map((sc) => `<button type="button" class="gt-scen${sc.id === cur.id ? " on" : ""}" data-id="${esc(sc.id)}" ` +
          `title="${esc(plural(Object.keys(sc.targets).length, "target facet"))} · ${esc(plural(sc.widgets.length, "widget"))}"><b>${esc(sc.user)}</b> ${esc(sc.task)}</button>`).join("") +
        `</div></div>`;
    }).join("");
  }
  $("#ly-groups").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-id]");
    if (b) { state.scenario = b.dataset.id; renderPicker(); render(); }
  });

  // Switching rooms keeps what can be kept: the same user on the same kind of task, else the
  // same kind of task, else the same user.
  function pickRoom(env) {
    const cur = scenarios.get(state.scenario), list = inRoom(env);
    const next = list.find((sc) => sc.user === cur.user && sc.taskCat === cur.taskCat) ||
      list.find((sc) => sc.taskCat === cur.taskCat) || list.find((sc) => sc.user === cur.user) || list[0];
    state.scenario = next.id;
    renderPicker();
    render();
  }

  // ---------- the view ----------
  function panel(fid, tier, width) {
    const el = document.createElement("div");
    el.className = "xr-p gt ly-p " + tier;
    el.dataset.facet = fid;
    el.tabIndex = 0;
    el.style.width = width + "px";
    el.title = `${appName(fid)} · ${facetLabel(fid)} (${tier}). Drag to move, click to open.`;
    el.innerHTML = `<span class="xr-badge">${width >= 100 ? tier : ""}</span><div class="xr-frame" style="max-height:${Math.round(width * 1.12)}px"></div><span class="xr-name">${esc(isEntry(fid) ? appName(fid) : facetLabel(fid))}</span>`;
    const mk = window.FacetMockup && FacetMockup.render(fid, { appName: appName(fid), facetName: isEntry(fid) ? "Home" : "" });
    if (mk) { mk.style.zoom = (width / 340).toFixed(3); el.querySelector(".xr-frame").appendChild(mk); }
    return el;
  }

  // Default placement in pixels, by tier: primary widgets in a centred block, peripheral ones in
  // columns on both sides, ambient ones in the outermost columns. The result says whether it fits.
  function tierLayout(items, W, H) {
    const M = 16, TOP = 70, GAP = 14;
    const avail = H - TOP - M;
    const of = (tier) => items.filter((it) => it.tier === tier);
    // Alternate between the sides, always adding to the shorter one, so both stay balanced.
    const split = (list) => {
      const sides = [[], []], h = [0, 0];
      for (const it of list) { const k = h[0] <= h[1] ? 0 : 1; sides[k].push(it); h[k] += it.h + GAP; }
      return sides;
    };
    // A side's widgets stack in columns no taller than the view.
    const columns = (list) => {
      const cols = [];
      let h = 0;
      for (const it of list) {
        if (!cols.length || h + GAP + it.h > avail) { cols.push([]); h = -GAP; }
        cols[cols.length - 1].push(it);
        h += GAP + it.h;
      }
      return cols;
    };
    const [ambL, ambR] = split(of("ambient"));
    const [perL, perR] = split(of("peripheral"));
    // Columns from the edge inwards: ambient outermost, then peripheral.
    const left = [...columns(ambL), ...columns(perL)];
    const right = [...columns(ambR), ...columns(perR)];
    const pos = new Map();
    const colWidth = (col) => Math.max(...col.map((it) => it.w));
    const colHeight = (col) => col.reduce((s, it) => s + it.h, 0) + GAP * (col.length - 1);
    // Each column is centred vertically, at eye level of the view's usable band.
    const stack = (col, x, align) => {
      const w = colWidth(col);
      let y = TOP + (avail - colHeight(col)) / 2;
      for (const it of col) { pos.set(it.fid, { x: align === "right" ? x + w - it.w : x, y }); y += it.h + GAP; }
      return w;
    };
    let x0 = M;
    for (const col of left) x0 += stack(col, x0, "right") + GAP;
    let x1 = W - M;
    for (const col of right) { const w = colWidth(col); stack(col, x1 - w, "left"); x1 -= w + GAP; }
    // Primary widgets: rows centred in the band between the side columns, block near the top.
    const band = x1 - x0;
    const rows = [[]];
    let rw = 0;
    for (const it of of("primary")) {
      if (rw && rw + GAP + it.w > band) { rows.push([]); rw = 0; }
      rows[rows.length - 1].push(it);
      rw += (rw ? GAP : 0) + it.w;
    }
    const heights = rows.map((row) => (row.length ? Math.max(...row.map((it) => it.h)) : 0));
    const blockH = heights.reduce((s, h) => s + h, 0) + GAP * (rows.length - 1);
    // The primary block sits high in the view, above the table.
    let y = TOP + (avail - blockH) * 0.12;
    rows.forEach((row, i) => {
      const total = row.reduce((s, it) => s + it.w, 0) + GAP * (row.length - 1);
      // Centred on the view, unless that would push the row into a side column.
      let x = Math.min(Math.max(W / 2 - total / 2, x0), x1 - total);
      for (const it of row) { pos.set(it.fid, { x, y: y + (heights[i] - it.h) / 2 }); x += it.w + GAP; }
      y += heights[i] + GAP;
    });
    const fits =
      band > 0 &&
      rows.every((row) => row.reduce((s, it) => s + it.w, 0) + GAP * (row.length - 1) <= band) &&
      blockH <= avail &&
      [...left, ...right].every((col) => colHeight(col) <= avail);
    return { pos, fits };
  }

  // Fallback for narrow views: one centred row along the bottom (primary first), wrapping upwards.
  // The result says how tall the view must be.
  function rowLayout(items, W, H) {
    const M = 16, TOP = 70, GAP = 14;
    const pos = new Map();
    const lines = [[]];
    let lw = 0;
    for (const it of items) {
      if (lw && lw + GAP + it.w > W - 2 * M) { lines.push([]); lw = 0; }
      lines[lines.length - 1].push(it);
      lw += (lw ? GAP : 0) + it.w;
    }
    const heights = lines.map((line) => Math.max(...line.map((it) => it.h)));
    const need = TOP + heights.reduce((s, h) => s + h, 0) + GAP * (lines.length - 1) + M;
    let y = Math.max(H, need) - M;
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i];
      const total = line.reduce((s, it) => s + it.w, 0) + GAP * (line.length - 1);
      let x = W / 2 - total / 2;
      // widgets sit on a common baseline
      for (const it of line) { pos.set(it.fid, { x, y: y - it.h }); x += it.w + GAP; }
      y -= heights[i] + GAP;
    }
    return { pos, fits: need <= H, height: need };
  }

  function render() {
    const sc = scenarios.get(state.scenario);
    const W = xr.clientWidth || 1200;
    const fids = Object.keys(sc.targets).sort((a, b) => TIERS.indexOf(sc.targets[a]) - TIERS.indexOf(sc.targets[b]) || appName(a).localeCompare(appName(b)));
    const n = fids.length;
    // The bottom-row fallback starts from the width at which every widget fits in one row.
    const base0 = Math.max(72, Math.min(W < 700 ? 110 : 170, (W - 32 - 14 * (n - 1)) / (n * 1.05)));
    const count = TIERS.map((t) => `${fids.filter((f) => sc.targets[f] === t).length} ${t}`).join(" · ");

    // Top to bottom: the view, the method's suggestions (linked straight up to the widgets), one
    // footer row (the layout's tiers, or the method's outcomes and cost while a method is being
    // tested), then the method bar.
    xr.innerHTML = `<div class="xr-view ly-view">
        <div class="xr-bg">${window.XRScenes ? XRScenes.svg(sc.env, sc.taskCat, sc.task) : ""}</div><div class="xr-lens"></div>
        <div class="xr-hud xr-ctx"><span>${esc(sc.user)}</span><span>${esc(sc.env)}</span><span>${esc(sc.task)}</span></div>
        <div class="xr-hud xr-pov">${esc(sc.user)}’s view</div>
        <div class="ly-layer"></div>
      </div>
      <svg class="xr-links" aria-hidden="true"></svg>
      <div class="sg-out"></div>
      <div class="ly-foot">
        <span class="xr-label">Participant's layout · ${n} facet${n === 1 ? "" : "s"} (${count})</span>
        <span class="ly-key"><i class="primary"></i>primary <i class="peripheral"></i>peripheral <i class="ambient"></i>ambient</span>
        <span class="ly-hint">Drag to move · click to open</span>
      </div>
      <div class="sg-bar"></div>
      <div class="xr-pop" role="tooltip"></div>`;
    const view = xr.querySelector(".ly-view"), layer = xr.querySelector(".ly-layer");
    let H = view.clientHeight;
    // Shrink the widgets until the default layout fits in the view.
    const build = (base) => {
      const width = { primary: base * 1.15, peripheral: base, ambient: base * 0.78 };
      layer.innerHTML = "";
      const list = fids.map((fid) => {
        const tier = sc.targets[fid] || "peripheral";
        const el = panel(fid, tier, Math.round(width[tier]));
        layer.appendChild(el);
        return { fid, tier, el };
      });
      for (const it of list) { it.w = it.el.offsetWidth; it.h = it.el.offsetHeight; }
      return list;
    };
    // Shrink the widgets until the tiered layout fits; on narrow views fall back to the bottom row.
    let items, auto;
    for (let base = W < 700 ? 110 : 170; base >= 72; base *= 0.92) {
      items = build(base);
      auto = tierLayout(items, W, H);
      if (auto.fits) break;
    }
    if (!auto.fits) {
      for (let k = 0, base = base0; k < 5; k++, base *= 0.88) {
        items = build(base);
        auto = rowLayout(items, W, H);
        if (auto.fits) break;
      }
      // Still too crowded (phones): let the view grow.
      if (!auto.fits) { H = auto.height; view.style.height = H + "px"; }
    }
    auto = auto.pos;
    const saved = moved.get(sc.id);
    for (const it of items) {
      const p = saved && saved.get(it.fid) ? { x: saved.get(it.fid).x * W, y: saved.get(it.fid).y * H } : auto.get(it.fid);
      place(it.el, p.x, p.y, W, H);
    }
    // The suggestion test below the view (js/suggest.js).
    if (window.ContextXRSuggest) ContextXRSuggest.update(sc.id, xr);

    $("#ly-raw").innerHTML = `<summary>Placed widgets (${sc.widgets.length}) · task label “${esc(sc.task)}”</summary><div class="gt-wtable">` +
      sc.widgets.map((w) => {
        const app = apps.get(w.app);
        return `<div class="gt-w"><span class="gt-wa">${esc(app ? app.name : w.app || "–")}</span>` +
          `<span class="gt-wf">${esc(w.facet && facets.has(w.facet) ? facetLabel(w.facet) : "unresolved")}</span>` +
          `<span class="gt-wd">${esc(w.desc || w.screen || "")}</span></div>`;
      }).join("") + "</div>";
  }

  function place(el, x, y, W, H) {
    x = Math.max(0, Math.min(W - el.offsetWidth, x));
    y = Math.max(0, Math.min(H - el.offsetHeight, y));
    el.style.transform = `translate(${x}px, ${y}px)`;
    el.dataset.x = x; el.dataset.y = y;
  }

  function remember(el) {
    const view = xr.querySelector(".ly-view");
    if (!moved.has(state.scenario)) moved.set(state.scenario, new Map());
    moved.get(state.scenario).set(el.dataset.facet, { x: +el.dataset.x / view.clientWidth, y: +el.dataset.y / view.clientHeight });
  }
  const openPanel = (el) => window.ContextXRSuggest && ContextXRSuggest.detail(el.dataset.facet, state.scenario);

  // ---------- dragging (a press without movement is a click) ----------
  let drag = null;
  xr.addEventListener("pointerdown", (ev) => {
    const el = ev.target.closest(".ly-p");
    if (!el || ev.button !== 0) return;
    ev.preventDefault();
    el.focus({ preventScroll: true });
    drag = { el, id: ev.pointerId, x0: ev.clientX, y0: ev.clientY, dx: ev.clientX - +el.dataset.x, dy: ev.clientY - +el.dataset.y, moved: false };
    const view = xr.querySelector(".ly-view");
    drag.W = view.clientWidth; drag.H = view.clientHeight;
    el.setPointerCapture(ev.pointerId);
    el.style.zIndex = ++top;
  });
  xr.addEventListener("pointermove", (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    if (!drag.moved && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 4) return;
    if (!drag.moved) {
      drag.moved = true;
      drag.el.classList.add("dragging");
      xr.classList.remove("focus");
      xr.querySelector(".xr-pop")?.classList.remove("show");
    }
    place(drag.el, ev.clientX - drag.dx, ev.clientY - drag.dy, drag.W, drag.H);
    if (window.ContextXRSuggest) ContextXRSuggest.redraw();
  });
  const drop = (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    const { el, moved: wasMoved } = drag;
    drag = null;
    el.classList.remove("dragging");
    if (wasMoved) remember(el);
    else if (ev.type === "pointerup") openPanel(el);
  };
  xr.addEventListener("pointerup", drop);
  xr.addEventListener("pointercancel", drop);

  // Arrow keys move a focused widget; Enter opens it.
  xr.addEventListener("keydown", (ev) => {
    const el = ev.target.closest(".ly-p");
    if (!el) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openPanel(el); return; }
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[ev.key];
    if (!d) return;
    ev.preventDefault();
    const view = xr.querySelector(".ly-view"), step = ev.shiftKey ? 40 : 10;
    place(el, +el.dataset.x + d[0] * step, +el.dataset.y + d[1] * step, view.clientWidth, view.clientHeight);
    remember(el);
    if (window.ContextXRSuggest) ContextXRSuggest.redraw();
  });

  // ---------- controls ----------
  $("#ly-reset").addEventListener("click", () => { moved.delete(state.scenario); render(); });

  let resizeTimer = 0;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 150); });

  renderPicker();
  render();
  window.ContextXRLayouts = {
    show: (sid) => {
      const sc = scenarios.get(sid);
      if (sc) {
        state.scenario = sid;
        renderPicker();
        render();
      }
      root.scrollIntoView({ behavior: "smooth" });
    },
  };
})();
