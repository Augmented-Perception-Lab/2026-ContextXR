// Interactive MineXR++ facet graphs (paper Fig. 2, top).
// Apps sit in a column on the left. Expanding an app lays out its facet graph in columns by
// BFS depth from the app's entry facet (Open Section). Expanding a facet lists its capabilities;
// edges then start at the navigational capability (open_<facet>) that opens the target facet.
// The "MineXR layouts" view overlays the ground truth: for a chosen context (any mix of user,
// environment and task category) it shows the target facets of the matching scenarios.
(function () {
  "use strict";

  const DATA = window.MINEXRPP;

  const PAD_X = 22, PAD_Y = 18;
  const APP_H = 24, APP_GAP = 6, BAND_PAD = 14;
  const FACET_H = 24, NODE_GAP = 12;
  const CAP_H = 19, CAP_GAP = 4, CAP_INDENT = 10, CAPS_TOP = 6;
  const APP_TO_COL = 64, COL_GAP = 72;
  const DURATION = 420;

  // ---------- model ----------
  const prettyName = (s) => (s === s.toLowerCase() ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : s);
  const prettyDomain = (s) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  const apps = DATA.apps.map((a) => ({ ...a, name: prettyName(a.name), facets: [] }));
  const appById = new Map(apps.map((a) => [a.id, a]));
  const facetById = new Map();
  for (const f of DATA.facets) {
    const nav = f.caps.filter((c) => c.startsWith("open_"));
    const facet = { ...f, caps: f.caps.filter((c) => !c.startsWith("open_")).concat(nav), out: [], in: [], depth: Infinity };
    facetById.set(f.id, facet);
    const app = appById.get(f.app);
    if (f.id !== app.entry) app.facets.push(facet);
  }
  const edges = [];
  for (const [s, t, cap] of DATA.edges) {
    if (s === t) continue; // self-loops: the capability chip alone says enough
    const e = { s, t, cap, back: false };
    edges.push(e);
    facetById.get(s).out.push(e);
    facetById.get(t).in.push(e);
  }
  for (const app of apps) {
    const entry = facetById.get(app.entry);
    entry.depth = 0;
    const queue = [entry];
    for (const f of queue) {
      for (const e of f.out) {
        const g = facetById.get(e.t);
        if (g.depth === Infinity) { g.depth = f.depth + 1; queue.push(g); }
      }
    }
    app.maxDepth = Math.max(0, ...app.facets.map((f) => f.depth));
  }
  for (const e of edges) e.back = facetById.get(e.t).depth <= facetById.get(e.s).depth;

  // Order the first column to reduce crossings with the second (a few barycenter sweeps).
  // Later columns are ordered by the y of their incoming edges at layout time.
  for (const app of apps) {
    const c1 = app.facets.filter((f) => f.depth === 1);
    const c2 = app.facets.filter((f) => f.depth === 2);
    if (!c2.length) { app.col1 = c1; continue; }
    const fwd = (f) => f.out.filter((e) => !e.back).map((e) => e.t);
    let order1 = c1.slice(), order2 = c2.slice();
    for (let round = 0; round < 4; round++) {
      const i1 = new Map(order1.map((f, i) => [f.id, i]));
      const parents = (g) => g.in.filter((e) => !e.back && i1.has(e.s)).map((e) => i1.get(e.s));
      const bary2 = new Map(order2.map((g, i) => { const p = parents(g); return [g.id, p.length ? p.reduce((a, b) => a + b, 0) / p.length : i]; }));
      order2.sort((a, b) => bary2.get(a.id) - bary2.get(b.id));
      const i2 = new Map(order2.map((g, i) => [g.id, i]));
      const scale = (order1.length - 1) / Math.max(1, order2.length - 1);
      const bary1 = new Map(order1.map((f, i) => {
        const k = fwd(f).filter((id) => i2.has(id)).map((id) => i2.get(id) * scale);
        return [f.id, k.length ? k.reduce((a, b) => a + b, 0) / k.length : i];
      }));
      order1.sort((a, b) => bary1.get(a.id) - bary1.get(b.id));
    }
    app.col1 = order1;
  }

  // ---------- state ----------
  const state = {
    sort: "uses",
    query: "",
    openApps: new Set(["instagram", "recipes"].filter((id) => appById.has(id))),
    openFacets: new Set(["recipes.view_recipe", "recipes.cook_recipe"].filter((id) => facetById.has(id))),
    hover: null, // {kind: "facet"|"cap"|"app", id, cap?}
  };
  let search = null; // {apps:Set visible, autoApps:Set, autoFacets:Set, matches:Set of node keys}

  const isAppOpen = (id) => state.openApps.has(id) || !!(search && search.autoApps.has(id));
  const isFacetOpen = (id) => state.openFacets.has(id) || !!(search && search.autoFacets.has(id));
  const isAppVisible = (id) => (!search || search.apps.has(id));

  // ---------- DOM ----------
  const canvas = document.getElementById("fg-canvas");
  const svg = document.getElementById("fg-edges");
  const tip = document.getElementById("fg-tip");
  const scroller = document.getElementById("fg-scroll");
  const SVGNS = "http://www.w3.org/2000/svg";

  const nodes = new Map(); // key -> {el, w, cur:{x,y,o}, to:{x,y,o}}
  const keyApp = (id) => "a:" + id;
  const keyFacet = (id) => "f:" + id;
  const keyCap = (fid, cap) => "c:" + fid + "|" + cap;

  function addNode(key, el) {
    canvas.appendChild(el);
    nodes.set(key, { el, w: 0, cur: { x: 0, y: 0, o: 0 }, to: { x: 0, y: 0, o: 0 } });
  }
  function chip(tag, cls, text) {
    const el = document.createElement(tag);
    el.className = "chip " + cls;
    el.textContent = text;
    if (tag === "button") el.type = "button";
    return el;
  }

  for (const app of apps) {
    const el = chip("button", "app", app.name);
    el.dataset.app = app.id;
    addNode(keyApp(app.id), el);
    for (const f of app.facets) {
      const fe = chip("button", "facet", f.name);
      fe.dataset.facet = f.id;
      addNode(keyFacet(f.id), fe);
      for (const c of f.caps) {
        const nav = c.startsWith("open_");
        const ce = chip(nav ? "button" : "span", nav ? "cap nav" : "cap", c);
        ce.dataset.facet = f.id;
        ce.dataset.cap = c;
        addNode(keyCap(f.id, c), ce);
      }
    }
  }
  for (const e of edges) {
    const g = document.createElementNS(SVGNS, "g");
    g.setAttribute("class", "e" + (e.back ? " back" : ""));
    const line = document.createElementNS(SVGNS, "path");
    line.setAttribute("class", "line");
    const head = document.createElementNS(SVGNS, "path");
    head.setAttribute("class", "head");
    g.append(line, head);
    svg.appendChild(g);
    e.el = g; e.line = line; e.head = head;
    e.cur = 0; e.to = 0;
  }
  const empty = document.createElement("div");
  empty.className = "fg-empty";
  empty.textContent = "No apps, facets, or capabilities match.";
  empty.hidden = true;
  canvas.appendChild(empty);

  // ---------- layout ----------
  function sortedApps() {
    const list = apps.slice();
    const byName = (a, b) => a.name.localeCompare(b.name);
    if (state.sort === "name") list.sort(byName);
    else if (state.sort === "facets") list.sort((a, b) => b.facets.length - a.facets.length || byName(a, b));
    else list.sort((a, b) => b.uses - a.uses || byName(a, b));
    return list;
  }

  const facetHeight = (f) => FACET_H + (isFacetOpen(f.id) ? CAPS_TOP + f.caps.length * (CAP_H + CAP_GAP) - CAP_GAP : 0);
  const facetWidth = (f) => {
    let w = nodes.get(keyFacet(f.id)).w;
    if (isFacetOpen(f.id)) for (const c of f.caps) w = Math.max(w, CAP_INDENT + nodes.get(keyCap(f.id, c)).w);
    return w;
  };

  function layout() {
    const appColW = Math.max(...apps.map((a) => nodes.get(keyApp(a.id)).w));
    const colX0 = PAD_X + appColW + APP_TO_COL;
    let y = PAD_Y, right = colX0;
    let prevOpen = false, any = false;

    const set = (key, x, y, o) => { const n = nodes.get(key); n.to = { x, y, o }; };
    const hideApp = (app, x, y) => {
      for (const f of app.facets) {
        set(keyFacet(f.id), x, y, 0);
        for (const c of f.caps) set(keyCap(f.id, c), x, y, 0);
      }
    };

    for (const app of sortedApps()) {
      if (!isAppVisible(app.id)) {
        set(keyApp(app.id), PAD_X, y, 0);
        hideApp(app, PAD_X, y);
        continue;
      }
      any = true;
      if (!isAppOpen(app.id)) {
        if (prevOpen) y += BAND_PAD;
        set(keyApp(app.id), PAD_X, y, 1);
        hideApp(app, PAD_X + 8, y);
        y += APP_H + APP_GAP;
        prevOpen = false;
        continue;
      }

      // Expanded band.
      const top = y + (y > PAD_Y && !prevOpen ? BAND_PAD : 0);
      const cols = [];
      for (const f of app.facets) (cols[f.depth] ||= []).push(f);
      const colX = [];
      let x = colX0;
      for (let d = 1; d <= app.maxDepth; d++) {
        colX[d] = x;
        x += Math.max(0, ...(cols[d] || []).map(facetWidth)) + COL_GAP;
      }
      right = Math.max(right, x - COL_GAP);

      const placed = new Map(); // facet id -> top y
      let appY = top;
      const anchorY = (e) => {
        if (e.s === app.entry) return appY + APP_H / 2;
        const f = facetById.get(e.s);
        const fy = placed.get(e.s);
        if (isFacetOpen(e.s)) {
          const i = f.caps.indexOf(e.cap);
          if (i >= 0) return fy + FACET_H + CAPS_TOP + i * (CAP_H + CAP_GAP) + CAP_H / 2;
        }
        return fy + FACET_H / 2;
      };

      // Column 1 stacks from the top; the app chip centres on it.
      let cy = top, bottom = top + APP_H;
      for (const f of app.col1) {
        placed.set(f.id, cy);
        cy += facetHeight(f) + NODE_GAP;
      }
      const col1Bottom = cy - NODE_GAP;
      appY = Math.max(top, (top + col1Bottom) / 2 - APP_H / 2);
      bottom = Math.max(bottom, col1Bottom, appY + APP_H);

      // Later columns: place each facet near the mean height of its incoming edges, then
      // resolve overlaps by merging clusters (each cluster sits at its members' mean wish).
      for (let d = 2; d <= app.maxDepth; d++) {
        const col = (cols[d] || []).map((f) => {
          const ins = f.in.filter((e) => !e.back && placed.has(e.s));
          const want = ins.length ? ins.reduce((s, e) => s + anchorY(e), 0) / ins.length - FACET_H / 2 : top;
          return { f, want, h: facetHeight(f) };
        });
        col.sort((a, b) => a.want - b.want);
        const clusters = [];
        for (const item of col) {
          clusters.push({ items: [item], top: Math.max(top, item.want), h: item.h });
          while (clusters.length > 1) {
            const b = clusters.pop(), a = clusters[clusters.length - 1];
            if (a.top + a.h + NODE_GAP <= b.top) { clusters.push(b); break; }
            a.items.push(...b.items);
            a.h += NODE_GAP + b.h;
            let off = 0, sum = 0;
            for (const it of a.items) { sum += it.want - off; off += it.h + NODE_GAP; }
            a.top = Math.max(top, sum / a.items.length);
          }
        }
        for (const c of clusters) {
          let yy = c.top;
          for (const it of c.items) { placed.set(it.f.id, yy); yy += it.h + NODE_GAP; }
          bottom = Math.max(bottom, yy - NODE_GAP);
        }
      }

      set(keyApp(app.id), PAD_X, appY, 1);
      for (const f of app.facets) {
        const fx = colX[f.depth], fy = placed.get(f.id);
        set(keyFacet(f.id), fx, fy, 1);
        const open = isFacetOpen(f.id);
        f.caps.forEach((c, i) => {
          if (open) set(keyCap(f.id, c), fx + CAP_INDENT, fy + FACET_H + CAPS_TOP + i * (CAP_H + CAP_GAP), 1);
          else set(keyCap(f.id, c), fx + CAP_INDENT, fy + 3, 0);
        });
      }
      y = bottom + BAND_PAD + APP_GAP;
      prevOpen = true;
    }

    for (const e of edges) e.to = isAppVisible(facetById.get(e.s).app) && isAppOpen(facetById.get(e.s).app) ? 1 : 0;
    empty.hidden = any;
    return { width: right + PAD_X + 40, height: Math.max(y + PAD_Y - APP_GAP, any ? 0 : 80) };
  }

  // ---------- drawing ----------
  const rectOf = (key) => nodes.get(key).cur;

  function sourceAnchor(e) {
    const s = facetById.get(e.s);
    if (e.s === appById.get(s.app).entry) {
      const n = nodes.get(keyApp(s.app));
      return [n.cur.x + n.w, n.cur.y + APP_H / 2];
    }
    const n = nodes.get(keyFacet(e.s));
    let x = n.cur.x + n.w, y = n.cur.y + FACET_H / 2;
    const c = nodes.get(keyCap(e.s, e.cap));
    if (c && c.cur.o > 0) {
      const k = c.cur.o; // blend from label to capability chip as the chip fades in
      x += (c.cur.x + c.w - x) * k;
      y += (c.cur.y + CAP_H / 2 - y) * k;
    }
    return [x, y];
  }

  function targetBox(e) {
    const t = facetById.get(e.t);
    if (e.t === appById.get(t.app).entry) {
      const n = nodes.get(keyApp(t.app));
      return { x: n.cur.x, y: n.cur.y, w: n.w, h: APP_H };
    }
    const n = nodes.get(keyFacet(e.t));
    return { x: n.cur.x, y: n.cur.y, w: n.w, h: FACET_H };
  }

  const r1 = (v) => Math.round(v * 10) / 10;

  function drawEdge(e) {
    e.el.style.opacity = e.cur;
    if (e.cur <= 0) return;
    const [sx, sy] = sourceAnchor(e);
    const t = targetBox(e);
    if (!e.back) {
      const tx = t.x - 1, ty = t.y + t.h / 2, ex = tx - 6;
      const dx = Math.max(24, (ex - sx) * 0.5);
      e.line.setAttribute("d", `M${r1(sx + 2)} ${r1(sy)}C${r1(sx + dx)} ${r1(sy)} ${r1(ex - dx)} ${r1(ty)} ${r1(ex)} ${r1(ty)}`);
      e.head.setAttribute("d", `M${r1(tx)} ${r1(ty)}L${r1(tx - 7)} ${r1(ty - 3.5)}L${r1(tx - 7)} ${r1(ty + 3.5)}Z`);
    } else {
      // Back edge: leave to the right, arc over, and drop onto the target from above.
      const cx = t.x + Math.min(t.w / 2, 40), ty = t.y - 1, ey = ty - 6;
      const lift = 28 + Math.abs(sy - ty) * 0.12;
      e.line.setAttribute("d", `M${r1(sx + 2)} ${r1(sy)}C${r1(sx + 56)} ${r1(sy - 6)} ${r1(cx)} ${r1(ey - lift)} ${r1(cx)} ${r1(ey)}`);
      e.head.setAttribute("d", `M${r1(cx)} ${r1(ty)}L${r1(cx - 3.5)} ${r1(ty - 7)}L${r1(cx + 3.5)} ${r1(ty - 7)}Z`);
    }
  }

  function applyNode(n) {
    n.el.style.transform = `translate(${r1(n.cur.x)}px, ${r1(n.cur.y)}px)`;
    n.el.style.opacity = n.cur.o;
  }

  let anim = null, size = { width: 0, height: 0 };

  function render(animate) {
    const from = new Map();
    for (const [k, n] of nodes) from.set(k, { ...n.cur });
    const edgeFrom = edges.map((e) => e.cur);
    const sizeFrom = { ...size };
    const sizeTo = layout();

    for (const n of nodes.values()) {
      const live = n.to.o > 0;
      n.el.style.pointerEvents = live ? "" : "none";
      n.el.tabIndex = live ? 0 : -1;
      n.el.setAttribute("aria-hidden", live ? "false" : "true");
    }
    updateClasses();
    canvas.style.width = Math.max(sizeTo.width, sizeFrom.width) + "px";

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (anim) cancelAnimationFrame(anim);
    const start = performance.now();
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    const frame = (now) => {
      const t = !animate || reduce ? 1 : Math.min(1, (now - start) / DURATION);
      const k = ease(t);
      for (const [key, n] of nodes) {
        const a = from.get(key), b = n.to;
        if (a.x === b.x && a.y === b.y && a.o === b.o && t > 0 && t < 1) continue;
        n.cur = { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, o: a.o + (b.o - a.o) * k };
        applyNode(n);
      }
      edges.forEach((e, i) => { e.cur = edgeFrom[i] + (e.to - edgeFrom[i]) * k; drawEdge(e); });
      size = { width: sizeFrom.width + (sizeTo.width - sizeFrom.width) * k, height: sizeFrom.height + (sizeTo.height - sizeFrom.height) * k };
      canvas.style.height = size.height + "px";
      svg.setAttribute("width", Math.max(size.width, sizeTo.width));
      svg.setAttribute("height", size.height);
      if (t < 1) anim = requestAnimationFrame(frame);
      else { anim = null; canvas.style.width = sizeTo.width + "px"; }
    };
    if (!animate || reduce) frame(start);
    else anim = requestAnimationFrame(frame);
  }

  // ---------- highlight / classes ----------
  function updateClasses() {
    for (const app of apps) nodes.get(keyApp(app.id)).el.classList.toggle("on", isAppOpen(app.id));
    for (const f of facetById.values()) {
      const n = nodes.get(keyFacet(f.id));
      if (n) n.el.classList.toggle("open", isFacetOpen(f.id));
    }
    for (const [k, n] of nodes) n.el.classList.toggle("match", !!(search && search.matches.has(k)));
    updateHover();
    const allOpen = [...facetById.values()].every((f) => f.depth === 0 || state.openFacets.has(f.id));
    capsBtn.setAttribute("aria-pressed", String(allOpen));
  }

  function updateHover() {
    for (const n of nodes.values()) n.el.classList.remove("hot");
    const h = state.hover;
    let hot = null;
    if (h && h.kind === "facet") {
      const f = facetById.get(h.id);
      hot = new Set([...f.in, ...f.out]);
      for (const e of hot) {
        for (const id of [e.s, e.t]) nodes.get(keyFacet(id))?.el.classList.add("hot");
      }
    } else if (h && h.kind === "cap") {
      hot = new Set(facetById.get(h.id).out.filter((e) => e.cap === h.cap));
      for (const e of hot) nodes.get(keyFacet(e.t))?.el.classList.add("hot");
    } else if (h && h.kind === "app") {
      hot = new Set(facetById.get(appById.get(h.id).entry).out);
    }
    for (const e of edges) {
      const isHot = !!hot && hot.has(e);
      e.el.classList.toggle("hot", isHot);
      e.el.classList.toggle("show", isHot);
      e.el.classList.toggle("dim", !!hot && !isHot);
    }
  }

  // ---------- tooltip ----------
  function showTip(el, html, fid) {
    tip.innerHTML = html;
    const f = fid && facetById.get(fid);
    const mk = f && window.FacetMockup && FacetMockup.render(fid, { appName: appById.get(f.app).name });
    if (mk) {
      const frame = document.createElement("div");
      frame.className = "tip-mk";
      frame.appendChild(mk);
      tip.prepend(frame);
    }
    tip.classList.add("show");
    const r = el.getBoundingClientRect(), tr = tip.getBoundingClientRect();
    let left = Math.min(Math.max(8, r.left), window.innerWidth - tr.width - 8);
    let top = r.top - tr.height - 8;
    if (top < 8) top = r.bottom + 8;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  const hideTip = () => tip.classList.remove("show");
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;

  function tipFor(el) {
    if (el.dataset.app) {
      const a = appById.get(el.dataset.app);
      return `<div class="t">${esc(a.name)}</div><div>${esc(prettyDomain(a.domain))}</div>` +
        `<div class="m">${plural(a.facets.length, "facet")} · placed in ${a.uses}/${DATA.stats.scenarios} scenarios</div>`;
    }
    const f = facetById.get(el.dataset.facet);
    if (el.dataset.cap) {
      const e = f.out.find((x) => x.cap === el.dataset.cap);
      if (!e) return null;
      const t = facetById.get(e.t);
      return `<div>opens <b>${esc(t.depth === 0 ? appById.get(t.app).name + " (Open Section)" : t.name)}</b></div>`;
    }
    const nav = f.caps.filter((c) => c.startsWith("open_")).length;
    return `<div class="t">${esc(f.name)}</div><div>${esc(f.desc)}</div>` +
      `<div class="m">${plural(f.caps.length - nav, "capability", "capabilities")} · ${nav} navigational<br>` +
      `placed in ${plural(f.uses, "scenario")}</div>` +
      `<div class="m">Click: show capabilities · <span class="tip-open">⤢</span> open the panel</div>`;
  }

  // ---------- events ----------
  canvas.addEventListener("click", (ev) => {
    const el = ev.target.closest(".chip");
    if (!el) return;
    if (el.dataset.app) {
      const id = el.dataset.app;
      if (isAppOpen(id)) { state.openApps.delete(id); search?.autoApps.delete(id); }
      else state.openApps.add(id);
      render(true);
    } else if (el.dataset.cap) {
      const e = facetById.get(el.dataset.facet).out.find((x) => x.cap === el.dataset.cap);
      const t = e && facetById.get(e.t);
      if (!t) return;
      const target = t.depth === 0 ? nodes.get(keyApp(t.app)).el : nodes.get(keyFacet(t.id)).el;
      target.classList.remove("flash");
      void target.offsetWidth;
      target.classList.add("flash");
    } else if (el.dataset.facet) {
      const id = el.dataset.facet;
      if (isFacetOpen(id)) { state.openFacets.delete(id); search?.autoFacets.delete(id); }
      else state.openFacets.add(id);
      render(true);
    }
  });

  // A small button beside the hovered facet opens its panel with every capability annotated.
  const openBtn = document.createElement("button");
  openBtn.type = "button";
  openBtn.className = "fg-open";
  openBtn.setAttribute("aria-label", "Open the panel with its capabilities");
  openBtn.title = "Open the panel with its capabilities";
  openBtn.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M9.5 2.5h4v4M13.5 2.5 9 7M6.5 13.5h-4v-4M2.5 13.5 7 9"/></svg>`;
  canvas.appendChild(openBtn);
  let openTimer = 0;
  const hideOpen = () => { clearTimeout(openTimer); openBtn.classList.remove("show"); };
  // a short grace period lets the pointer cross the gap from the facet to the button
  const hideOpenSoon = () => { clearTimeout(openTimer); openTimer = setTimeout(hideOpen, 300); };
  openBtn.addEventListener("pointerenter", () => clearTimeout(openTimer));
  function showOpen(el) {
    clearTimeout(openTimer);
    const c = canvas.getBoundingClientRect(), r = el.getBoundingClientRect();
    openBtn.style.transform = `translate(${r.right - c.left + 4}px, ${r.top - c.top}px)`;
    openBtn.dataset.facet = el.dataset.facet;
    openBtn.classList.add("show");
  }
  openBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    hideTip();
    hideOpen();
    if (window.ContextXRSuggest) ContextXRSuggest.detail(openBtn.dataset.facet, false);
  });
  openBtn.addEventListener("pointerleave", (ev) => {
    if (!(ev.relatedTarget && ev.relatedTarget.closest && ev.relatedTarget.closest(".chip.facet"))) hideOpenSoon();
  });

  canvas.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest(".chip");
    if (!el) return;
    if (el.dataset.facet && !el.dataset.cap) showOpen(el); else hideOpen();
    if (el.dataset.app) state.hover = { kind: "app", id: el.dataset.app };
    else if (el.dataset.cap) state.hover = el.classList.contains("nav") ? { kind: "cap", id: el.dataset.facet, cap: el.dataset.cap } : null;
    else state.hover = { kind: "facet", id: el.dataset.facet };
    updateHover();
    const html = tipFor(el);
    if (!html) return hideTip();
    const fid = el.dataset.app ? null : !el.dataset.cap ? el.dataset.facet : null;
    showTip(el, html, fid);
  });
  canvas.addEventListener("pointerout", (ev) => {
    const el = ev.target.closest(".chip");
    if (!el || (ev.relatedTarget && el.contains(ev.relatedTarget))) return;
    if (ev.relatedTarget !== openBtn && !openBtn.contains(ev.relatedTarget)) hideOpenSoon();
    state.hover = null;
    updateHover();
    hideTip();
  });
  canvas.addEventListener("focusin", (ev) => ev.target.dispatchEvent(new PointerEvent("pointerover", { bubbles: true })));
  canvas.addEventListener("focusout", (ev) => ev.target.dispatchEvent(new PointerEvent("pointerout", { bubbles: true })));
  scroller.addEventListener("scroll", hideTip, { passive: true });
  window.addEventListener("scroll", hideTip, { passive: true });

  for (const b of document.querySelectorAll(".fg-seg button")) {
    b.addEventListener("click", () => {
      state.sort = b.dataset.sort;
      for (const o of document.querySelectorAll(".fg-seg button")) o.classList.toggle("on", o === b);
      render(true);
    });
  }
  const capsBtn = document.getElementById("fg-caps");
  capsBtn.addEventListener("click", () => {
    if (capsBtn.getAttribute("aria-pressed") === "true") state.openFacets.clear();
    else for (const f of facetById.values()) if (f.depth > 0) state.openFacets.add(f.id);
    render(true);
  });
  document.getElementById("fg-expand").addEventListener("click", () => {
    for (const a of apps) state.openApps.add(a.id);
    render(true);
  });
  document.getElementById("fg-collapse").addEventListener("click", () => {
    state.openApps.clear();
    state.openFacets.clear();
    if (search) { search.autoApps.clear(); search.autoFacets.clear(); }
    render(true);
  });

  const norm = (s) => s.toLowerCase().replace(/_/g, " ");
  let searchTimer = 0;
  document.getElementById("fg-query").addEventListener("input", (ev) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = norm(ev.target.value.trim());
      search = q ? runSearch(q) : null;
      render(true);
    }, 120);
  });

  function runSearch(q) {
    const s = { apps: new Set(), autoApps: new Set(), autoFacets: new Set(), matches: new Set() };
    for (const app of apps) {
      if (norm(app.name).includes(q) || norm(app.domain).includes(q)) {
        s.apps.add(app.id);
        s.matches.add(keyApp(app.id));
      }
      for (const f of app.facets) {
        if (norm(f.name).includes(q)) {
          s.apps.add(app.id); s.autoApps.add(app.id);
          s.matches.add(keyFacet(f.id));
        }
        for (const c of f.caps) {
          if (norm(c).includes(q)) {
            s.apps.add(app.id); s.autoApps.add(app.id); s.autoFacets.add(f.id);
            s.matches.add(keyCap(f.id, c));
          }
        }
      }
    }
    return s;
  }

  // ---------- boot ----------
  const st = DATA.stats;
  document.getElementById("fg-stats").innerHTML =
    `<span><b>${st.apps}</b>apps</span><span><b>${st.facets}</b>facets</span>` +
    `<span><b>${st.capabilities.toLocaleString()}</b>capabilities</span><span><b>${st.edges}</b>navigational edges</span>` +
    `<span><b>${st.scenarios}</b>scenarios</span>`;
  document.getElementById("fg-version").textContent = DATA.benchmark_version;

  const ready = document.fonts && document.fonts.load
    ? Promise.all([document.fonts.load('700 13.5px "Roboto Mono"'), document.fonts.load('400 11.5px "Roboto Mono"')]).catch(() => {})
    : Promise.resolve();
  ready.then(() => {
    for (const n of nodes.values()) n.w = n.el.offsetWidth;
    render(false);
  });
})();
