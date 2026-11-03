// Facet mockups: draws a facet as a small XR panel whose elements are exactly its capabilities
// (specs: site/mockups/*.json, format: site/mockups/SCHEMA.md). Every capability-bearing element
// carries data-cap="<capability> …" so views can highlight or annotate capabilities.
//
//   FacetMockup.render(facetId, {appName, facetName}) -> HTMLElement (.mk) or null
//   FacetMockup.has(facetId)
(function () {
  "use strict";

  const M = window.MINEXRPP_MOCKUPS || { apps: {}, facets: {}, icons: {} };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const attrs = (o) => Object.entries(o).map(([k, v]) => `${k}="${esc(v)}"`).join(" ");

  function icon(name, size = 16, cls = "") {
    const node = M.icons[name];
    const inner = node ? node.map(([tag, a]) => `<${tag} ${attrs(a)}/>`).join("") : '<circle cx="12" cy="12" r="9"/>';
    return `<svg class="mk-i ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  }

  const capAttr = (b) => {
    const caps = [b.cap, ...(b.caps || [])].filter(Boolean);
    return caps.length ? ` data-cap="${esc(caps.join(" "))}"` : "";
  };
  const isNav = (cap) => !!cap && cap.startsWith("open_");
  const tint = (h, a = 72, b = 52) => `linear-gradient(135deg, hsl(${h} 70% ${a}%), hsl(${(h + 28) % 360} 62% ${b}%))`;
  const label = (b) => (b.label && !["toggle", "slider", "stepper", "select", "progress", "link", "button"].includes(b.type) ? `<div class="mk-label">${esc(b.label)}</div>` : "");

  const R = {};

  R.header = (b) => `<div class="mk-header">${b.thumb ? `<div class="mk-thumb" style="background:${tint(b.thumb.hue ?? 210)}">${icon(b.thumb.icon || "image", 18)}</div>` : ""}<div><div class="mk-title">${esc(b.title)}</div>${b.subtitle ? `<div class="mk-sub">${esc(b.subtitle)}</div>` : ""}</div></div>`;
  R.text = (b) => `<p class="mk-text mk-${b.size || "md"}${b.muted ? " mk-muted" : ""}">${esc(b.text)}</p>`;
  R.list = (b) => `<div class="mk-list mk-list-${b.style || "plain"}">${b.items.map((it, i) => {
    const lead = b.style === "check" ? `<span class="mk-check${it.done ? " on" : ""}">${it.done ? icon("check", 11) : ""}</span>`
      : b.style === "numbered" ? `<span class="mk-num">${i + 1}</span>`
      : b.style === "thumbs" || it.hue != null ? `<span class="mk-sq" style="background:${tint(it.hue ?? 210)}">${it.icon ? icon(it.icon, 13) : ""}</span>`
      : it.avatar ? `<span class="mk-av" style="background:${tint(it.hue ?? (it.title.length * 37) % 360, 66, 50)}">${esc(it.title[0])}</span>`
      : it.icon ? `<span class="mk-li">${icon(it.icon, 15)}</span>` : "";
    const act = it.action ? `<span class="mk-act${isNav(it.action.cap) ? " nav" : ""}" data-cap="${esc(it.action.cap)}">${icon(it.action.icon, 15)}</span>` : "";
    return `<div class="mk-row">${lead}<div class="mk-rt"><div class="mk-r1${it.done ? " done" : ""}">${esc(it.title)}</div>${it.meta ? `<div class="mk-r2">${esc(it.meta)}</div>` : ""}</div>${it.trailing ? `<span class="mk-trail">${esc(it.trailing)}</span>` : ""}${act}</div>`;
  }).join("")}</div>`;
  R.kv = (b) => `<div class="mk-kv">${b.items.map(([k, v]) => `<div><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("")}</div>`;
  R.media = (b) => {
    const kind = b.kind || "photo";
    const extra = kind === "video" ? `<span class="mk-play">${icon("play", 18)}</span><span class="mk-vbar"><i style="width:38%"></i></span>${b.duration ? `<span class="mk-dur">${esc(b.duration)}</span>` : ""}`
      : kind === "camera" ? `<span class="mk-cam"></span>` : "";
    const bg = kind === "doc" ? "#f1f3f5" : kind === "camera" ? "linear-gradient(160deg,#495057,#212529)" : tint(b.hue ?? 210);
    return `<div class="mk-media mk-${b.aspect || "wide"} mk-${kind}" style="background:${bg}">${b.icon ? icon(b.icon, 30, "mk-mi") : kind === "doc" ? '<span class="mk-doclines"><i></i><i></i><i></i><i></i></span>' : ""}${extra}</div>${b.caption ? `<div class="mk-cap-t">${esc(b.caption)}</div>` : ""}`;
  };
  R.player = (b) => `<div class="mk-player"><div class="mk-bar"><i style="width:${(b.progress ?? 0.35) * 100}%"></i><b style="left:${(b.progress ?? 0.35) * 100}%"></b></div><div class="mk-times"><span>${esc(b.elapsed || "1:12")}</span><span>${esc(b.total || "3:20")}</span></div></div>`;
  R.controls = (b) => `<div class="mk-controls">${b.items.map((it) => `<span class="mk-ctl${it.primary ? " primary" : ""}${isNav(it.cap) ? " nav" : ""}" data-cap="${esc(it.cap)}" title="${esc(it.label || it.cap)}">${icon(it.icon, it.primary ? 20 : 17)}</span>`).join("")}</div>`;
  const btn = (it) => `<span class="mk-btn mk-${it.style || (isNav(it.cap) ? "primary" : "primary")}${isNav(it.cap) ? " nav" : ""}"${it.cap && it._item ? ` data-cap="${esc(it.cap)}"` : ""}>${it.icon && (it.style === "secondary" || it.style === "ghost" || /left/.test(it.icon)) ? icon(it.icon, 15) : ""}<span>${esc(it.label)}</span>${it.icon && !(it.style === "secondary" || it.style === "ghost" || /left/.test(it.icon)) ? icon(it.icon, 15) : ""}</span>`;
  R.button = (b) => btn(b);
  R.buttons = (b) => `<div class="mk-buttons">${b.items.map((it) => btn({ ...it, _item: true })).join("")}</div>`;
  R.link = (b) => `<div class="mk-link${isNav(b.cap) ? " nav" : ""}">${b.icon ? icon(b.icon, 15) : ""}<span>${esc(b.label)}</span>${b.meta ? `<em>${esc(b.meta)}</em>` : ""}${icon("chevron-right", 15)}</div>`;
  R.tabs = (b) => `<div class="mk-tabs">${b.items.map((it, i) => `<span class="mk-tab${i === (b.selected ?? -1) ? " on" : ""}" data-cap="${esc(it.cap)}">${icon(it.icon, 18)}<span>${esc(it.label)}</span></span>`).join("")}</div>`;
  R.toggle = (b) => `<div class="mk-setting"><div><div class="mk-r1">${esc(b.label)}</div>${b.desc ? `<div class="mk-r2">${esc(b.desc)}</div>` : ""}</div><span class="mk-switch${b.on ? " on" : ""}"><i></i></span></div>`;
  R.slider = (b) => `<div class="mk-slider">${b.icon ? icon(b.icon, 15) : ""}<span class="mk-sl-l">${esc(b.label)}</span><div class="mk-bar"><i style="width:${(b.value ?? 0.5) * 100}%"></i><b style="left:${(b.value ?? 0.5) * 100}%"></b></div>${b.display ? `<span class="mk-sl-v">${esc(b.display)}</span>` : ""}</div>`;
  R.stepper = (b) => `<div class="mk-setting"><div class="mk-r1">${esc(b.label)}</div><span class="mk-stepper"><i>${icon("minus", 13)}</i><b>${esc(b.value)}</b><i>${icon("plus", 13)}</i></span></div>`;
  R.input = (b) => `<div class="mk-input${b.multiline ? " multi" : ""}">${b.icon ? icon(b.icon, 15) : ""}<span class="${b.value ? "v" : "ph"}">${esc(b.value || b.placeholder || "")}</span>${b.trailing ? icon(b.trailing, 15, "mk-tr") : ""}</div>`;
  const sel = (b, i) => (Array.isArray(b.selected) ? b.selected.includes(i) : b.selected === i);
  R.chips = (b) => `<div class="mk-chips">${b.items.map((t, i) => `<span class="${sel(b, i) ? "on" : ""}">${esc(t)}</span>`).join("")}</div>`;
  R.segmented = (b) => `<div class="mk-seg">${b.items.map((t, i) => `<span class="${sel(b, i) ? "on" : ""}">${esc(t)}</span>`).join("")}</div>`;
  R.select = (b) => `<div class="mk-setting"><div class="mk-r1">${esc(b.label)}</div><span class="mk-select">${esc(b.value)}${icon("chevron-down", 13)}</span></div>`;
  R.stat = (b) => `<div class="mk-stat">${b.icon ? icon(b.icon, 22, "mk-si") : ""}<div><div class="mk-sv">${esc(b.value)}<small>${esc(b.unit || "")}</small></div>${b.label || b.delta ? `<div class="mk-r2">${esc(b.label || "")}${b.delta ? ` <b class="${String(b.delta).startsWith("-") || String(b.delta).startsWith("−") ? "dn" : "up"}">${esc(b.delta)}</b>` : ""}</div>` : ""}</div></div>`;
  R.progress = (b) => `<div class="mk-progress">${b.label || b.display ? `<div class="mk-pl"><span>${esc(b.label || "")}</span><span>${esc(b.display || "")}</span></div>` : ""}<div class="mk-bar thick"><i style="width:${(b.value ?? 0.5) * 100}%"></i></div></div>`;
  R.timer = (b) => `<div class="mk-timer"><div>${esc(b.display)}</div>${b.label ? `<span>${esc(b.label)}</span>` : ""}</div>`;
  R.grid = (b) => `<div class="mk-grid" style="grid-template-columns:repeat(${b.cols || 3},1fr)">${b.items.map((it) => `<div class="mk-tile"${it.hue != null ? ` style="background:${tint(it.hue, 86, 74)}"` : ""}>${it.icon ? icon(it.icon, 18) : ""}<span>${esc(it.label)}</span></div>`).join("")}</div>`;
  R.cards = (b) => `<div class="mk-cards">${b.items.map((it) => `<div class="mk-card"><div class="mk-ci" style="background:${tint(it.hue ?? 210)}">${it.icon ? icon(it.icon, 18) : ""}</div><div class="mk-r1">${esc(it.title)}</div>${it.meta ? `<div class="mk-r2">${esc(it.meta)}</div>` : ""}</div>`).join("")}</div>`;
  R.map = (b) => {
    const kind = b.kind || "pins";
    const route = kind === "route" ? '<path d="M40 120 C 90 110, 80 60, 140 58 S 230 40, 280 30" stroke="#3478f7" stroke-width="5" fill="none" stroke-linecap="round"/><circle cx="40" cy="120" r="6" fill="#fff" stroke="#3478f7" stroke-width="3"/>' : "";
    const area = kind === "area" ? '<circle cx="160" cy="76" r="44" fill="#3478f733" stroke="#3478f7" stroke-width="2"/><circle cx="160" cy="76" r="7" fill="#3478f7" stroke="#fff" stroke-width="3"/>' : "";
    const pins = kind === "pins" ? [[90, 60], [190, 92], [250, 46]].map(([x, y]) => `<path d="M${x} ${y}c-7-9-11-14-11-19a11 11 0 0 1 22 0c0 5-4 10-11 19z" fill="#e03131"/><circle cx="${x}" cy="${y - 19}" r="4" fill="#fff"/>`).join("") : kind === "route" ? '<path d="M280 30c-7-9-11-14-11-19a11 11 0 0 1 22 0c0 5-4 10-11 19z" fill="#e03131"/>' : "";
    return `<div class="mk-map"><svg viewBox="0 0 320 140" preserveAspectRatio="xMidYMid slice"><rect width="320" height="140" fill="#eef1e6"/><path d="M0 95 L320 70" stroke="#fff" stroke-width="10"/><path d="M120 0 L150 140" stroke="#fff" stroke-width="8"/><path d="M230 0 L210 140" stroke="#fff" stroke-width="6"/><rect x="250" y="95" width="60" height="38" rx="6" fill="#d3ecd0"/><path d="M0 30 Q 60 20 110 40" stroke="#c5dcf5" stroke-width="12" fill="none"/>${route}${area}${pins}</svg>${b.label ? `<span class="mk-maplabel">${esc(b.label)}</span>` : ""}</div>`;
  };
  R.chart = (b) => {
    const v = b.values && b.values.length > 1 ? b.values : [3, 4, 3.6, 5, 4.4, 6, 5.6, 7];
    const mn = Math.min(...v), mx = Math.max(...v), W = 300, H = 70;
    const pts = v.map((y, i) => [(i / (v.length - 1)) * W, H - 6 - ((y - mn) / (mx - mn || 1)) * (H - 14)]);
    const body = (b.kind || "line") === "bars"
      ? v.map((y, i) => { const w = W / v.length - 6, h = 8 + ((y - mn) / (mx - mn || 1)) * (H - 14); return `<rect x="${i * (W / v.length) + 3}" y="${H - h}" width="${w}" height="${h}" rx="3" fill="#3478f7" opacity="${0.45 + 0.55 * (i / v.length)}"/>`; }).join("")
      : `<path d="M${pts.map((p) => p.join(" ")).join(" L")} L${W} ${H} L0 ${H}Z" fill="#3478f71f"/><path d="M${pts.map((p) => p.join(" ")).join(" L")}" stroke="#3478f7" stroke-width="2.5" fill="none" stroke-linejoin="round"/>`;
    return `<div class="mk-chart">${b.label ? `<div class="mk-r2">${esc(b.label)}</div>` : ""}<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${body}</svg></div>`;
  };
  R.calendar = (b) => {
    const kind = b.kind || "month";
    if (kind === "agenda" || kind === "week") {
      const items = b.items || [{ time: "10:00", title: "Team standup" }, { time: "13:30", title: "Design review" }];
      return `<div class="mk-agenda">${items.map((it, i) => `<div><span class="t">${esc(it.time)}</span><span class="e" style="--h:${it.hue ?? [210, 140, 30, 280][i % 4]}">${esc(it.title)}</span></div>`).join("")}</div>`;
    }
    const days = Array.from({ length: 35 }, (_, i) => i - 2);
    return `<div class="mk-month"><div class="mk-mh">${esc(b.month || "October 2026")}</div><div class="mk-mg">${"SMTWTFS".split("").map((d) => `<b>${d}</b>`).join("")}${days.map((d) => `<span class="${d === 23 ? "today" : [7, 14, 28].includes(d) ? "ev" : ""}">${d > 0 && d <= 31 ? d : ""}</span>`).join("")}</div></div>`;
  };
  R.chat = (b) => `<div class="mk-chat">${b.items.map((m) => `<div class="mk-msg ${m.from === "me" ? "me" : "them"}">${m.name && m.from !== "me" ? `<b>${esc(m.name)}</b>` : ""}${esc(m.text)}</div>`).join("")}</div>`;
  R.keypad = (b) => `<div class="mk-keypad">${(b.keys || ["C", "±", "%", "÷", "7", "8", "9", "×", "4", "5", "6", "−", "1", "2", "3", "+", "0", ".", "⌫", "="]).map((k) => `<span class="${/[÷×−+=]/.test(k) ? "op" : ""}">${esc(k)}</span>`).join("")}</div>`;
  R.avatar = (b) => `<div class="mk-avatar"><span class="mk-av lg" style="background:${tint(b.hue ?? (b.name.length * 47) % 360, 66, 50)}">${esc(b.name[0])}</span><div><div class="mk-r1">${esc(b.name)}</div>${b.status ? `<div class="mk-r2">${esc(b.status)}</div>` : ""}</div></div>`;
  R.badge = (b) => `<span class="mk-badge ${b.tone || "gray"}">${esc(b.label)}</span>`;
  R.notice = (b) => `<div class="mk-notice ${b.tone || "blue"}">${b.icon ? icon(b.icon, 20) : ""}<div><div class="mk-r1">${esc(b.title)}</div>${b.text ? `<div class="mk-r2">${esc(b.text)}</div>` : ""}</div></div>`;
  R.rating = (b) => `<div class="mk-rating">${[1, 2, 3, 4, 5].map((i) => `<span class="${i <= Math.round(b.value) ? "on" : ""}">★</span>`).join("")}<em>${esc(b.value)}${b.count ? ` · ${esc(b.count)}` : ""}</em></div>`;
  R.code = (b) => `<pre class="mk-code">${b.lines.map((l, i) => `<span><i>${i + 1}</i>${esc(l)}</span>`).join("\n")}</pre>`;
  R.row = (b) => `<div class="mk-rowc">${b.blocks.map((c, i) => `<div style="flex:${(b.widths || [])[i] ?? 1} 1 0">${block(c)}</div>`).join("")}</div>`;
  R.group = (b) => `<div class="mk-group">${b.blocks.map(block).join("")}</div>`;

  function block(b) {
    const draw = R[b.type];
    if (!draw) return "";
    const inner = draw(b);
    if (b.type === "row") return inner;
    const caps = [b.cap, ...(b.caps || [])].filter(Boolean);
    const nav = caps.some(isNav);
    return `<div class="mk-b mk-b-${b.type}${caps.length ? " mk-capel" : ""}${nav ? " mk-navel" : ""}"${capAttr(b)}>${label(b)}${inner}</div>`;
  }

  function render(facetId, opts = {}) {
    const blocks = M.facets[facetId];
    if (!blocks) return null;
    const appId = facetId.split(".")[0];
    const app = M.apps[appId] || { icon: "app-window", color: "#868e96" };
    const el = document.createElement("div");
    el.className = "mk";
    el.dataset.facet = facetId;
    el.style.setProperty("--app", app.color);
    el.innerHTML = `<div class="mk-chrome"><span class="mk-appicon">${icon(app.icon, 12)}</span><span>${esc(opts.appName || appId)}</span>${opts.facetName ? `<em>${esc(opts.facetName)}</em>` : ""}</div><div class="mk-body">${blocks.map(block).join("")}</div>`;
    return el;
  }

  window.FacetMockup = { render, has: (id) => !!M.facets[id], icon, appStyle: (id) => M.apps[id] };
})();
