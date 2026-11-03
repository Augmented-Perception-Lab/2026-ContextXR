// First-person riso-print views of the four MineXR environments, in the style of the
// "Glasses that understand" explainer: charcoal linework on cream paper, shading with warm-gray
// halftone dots, flat and front-facing. The eye sits just above the table (kitchen island, café
// table, desk, coffee table), so the room fills the upper part of the view and the objects for
// the participant's task stand on the table; a few tasks move the camera (standing at the café
// counter to order, standing over a mat to work out). Simple one-point perspective, paper fills
// so near objects hide far ones.
//
//   XRScenes.svg(env, taskCat, task) -> SVG markup (viewBox 1600×900)
(function () {
  "use strict";

  // ---------- camera and projection ----------
  // Metres: X right, Y up, Z away from the viewer. A view sets the camera (x, z, eye height, horizon).
  const F = 1000, CX = 800, NEAR = 0.12, TAU = 2 * Math.PI;
  let HY = 190, EYE = 1.2, CAMX = 0, CAMZ = 0, uid = 0, rnd = Math.random;
  const r1 = (v) => Math.round(v * 10) / 10;
  const rel = ([X, Y, Z]) => [X - CAMX, Y, Z - CAMZ];
  const proj = ([x, Y, z]) => [CX + (F * x) / z, HY - (F * (Y - EYE)) / z];
  const pt = (p) => proj(rel(p));
  const depth = (p) => Math.max(NEAR, p[2] - CAMZ);
  const range = (a, b, step) => { const out = []; for (let v = a; v <= b + 1e-9; v += step) out.push(v); return out; };
  function seeded(str) {
    let h = 2166136261;
    for (const c of str) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
    return () => { h = (h + 0x6d2b79f5) | 0; let t = Math.imul(h ^ (h >>> 15), 1 | h); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  // Clip against the near plane (camera-relative points). Closed: one polygon; open: runs.
  function clipNear(P, closed) {
    const ins = (p) => p[2] >= NEAR;
    const cut = (a, b) => { const t = (NEAR - a[2]) / (b[2] - a[2]); return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, NEAR]; };
    if (closed) {
      const out = [];
      P.forEach((a, i) => { const b = P[(i + 1) % P.length]; if (ins(a)) { out.push(a); if (!ins(b)) out.push(cut(a, b)); } else if (ins(b)) out.push(cut(a, b)); });
      return out.length >= 3 ? [out] : [];
    }
    const runs = []; let cur = [];
    P.forEach((a, i) => {
      if (ins(a)) { if (i && !ins(P[i - 1])) cur.push(cut(P[i - 1], a)); cur.push(a); }
      else if (i && ins(P[i - 1])) { cur.push(cut(P[i - 1], a)); runs.push(cur); cur = []; }
    });
    if (cur.length > 1) runs.push(cur);
    return runs;
  }
  const xy = (q) => `${r1(q[0])} ${r1(q[1])}`;
  function fillD(pts) {
    const runs = clipNear(pts.map(rel), true);
    return runs.length ? "M" + runs[0].map((p) => xy(proj(p))).join("L") + "Z" : "";
  }
  function inkD(pts, closed) {
    return clipNear(pts.map(rel), closed).map((run) => "M" + run.map((p) => xy(proj(p))).join("L") + (closed ? "Z" : "")).join("");
  }
  // Line weight: a touch heavier up close.
  const wAt = (z) => Math.max(1.05, Math.min(1.9, 0.95 + 0.7 / z)).toFixed(2);
  const wOf = (pts) => wAt(pts.reduce((a, p) => a + depth(p), 0) / pts.length);
  const stroke = (dd, w) => (dd ? `<path class="n" style="--w:${w}" d="${dd}"/>` : "");
  const line = (...pts) => stroke(inkD(pts, false), wOf(pts));
  // A smooth curve through the points (Catmull-Rom as cubic Béziers).
  function curveD(pts) {
    let s = "";
    for (const run of clipNear(pts.map(rel), false)) {
      const P = run.map(proj);
      s += `M${xy(P[0])}`;
      for (let i = 0; i < P.length - 1; i++) {
        const p0 = P[i - 1] || P[i], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2] || p2;
        s += `C${r1(p1[0] + (p2[0] - p0[0]) / 6)} ${r1(p1[1] + (p2[1] - p0[1]) / 6)} ${r1(p2[0] - (p3[0] - p1[0]) / 6)} ${r1(p2[1] - (p3[1] - p1[1]) / 6)} ${xy(p2)}`;
      }
    }
    return s;
  }
  const curve = (pts) => stroke(curveD(pts), wOf(pts));
  const thin = (s) => `<g class="thin">${s}</g>`;

  // Shade: a layer of transparent halftone dots over a face (no outline). Denser when `cover` is high.
  function hatch(pts, { cover = 0.5 } = {}) {
    const f = fillD(pts);
    return f ? `<path class="${cover > 0.6 ? "s2" : "s1"}" d="${f}"/>` : "";
  }
  // A filled, inked polygon. cls: f0 (paper), d1–d5 (halftone, light to dark), n (outline only);
  // h1 / h2 are the light and dark halftones used for side faces and dark objects.
  const FILL = { h1: "d2", h2: "d4" };
  function poly(pts, cls = "f0") {
    const f = fillD(pts);
    if (!f) return "";
    return (cls === "n" ? "" : `<path class="${FILL[cls] || cls}" d="${f}"/>`) + stroke(inkD(pts, true), wOf(pts));
  }
  const backRect = (x0, x1, y0, y1, z, cls = "f0") => poly([[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]], cls);
  const sideRect = (X, z0, z1, y0, y1, cls = "f0") => poly([[X, y0, z0], [X, y0, z1], [X, y1, z1], [X, y1, z0]], cls);
  const flatRect = (x0, x1, z0, z1, Y, cls = "f0") => poly([[x0, Y, z0], [x1, Y, z0], [x1, Y, z1], [x0, Y, z1]], cls);
  // A face parallel to the picture plane projects to an axis-aligned rectangle: round its corners.
  function softRect(x0, x1, y0, y1, z, r = 0.04, cls = "f0") {
    if (z - CAMZ < NEAR) return "";
    const [ax, ay] = pt([x0, y1, z]), [bx, by] = pt([x1, y0, z]), k = F / (z - CAMZ);
    const rr = Math.min(r * k, (bx - ax) / 2, (by - ay) / 2);
    return `<rect class="${FILL[cls] || cls}" style="--w:${wAt(z - CAMZ)}" x="${r1(ax)}" y="${r1(ay)}" width="${r1(bx - ax)}" height="${r1(by - ay)}" rx="${r1(rr)}"/>` +
      `<rect class="n" style="--w:${wAt(z - CAMZ)}" x="${r1(ax)}" y="${r1(ay)}" width="${r1(bx - ax)}" height="${r1(by - ay)}" rx="${r1(rr)}"/>`;
  }

  // Axis-aligned box: the faces the eye can see; side faces get a hatch patch.
  function box(x0, x1, y0, y1, z0, z1, cls = "f0", side = "h1") {
    let s = "";
    if (x0 > CAMX) s += poly([[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]], side, { from: 1 });
    if (x1 < CAMX) s += poly([[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], side);
    if (y1 < EYE) s += poly([[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], "f0");
    if (y0 > EYE) s += poly([[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], side);
    return s + poly([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], cls);
  }
  const ell = (X, Y, Z, rx, rz, a0 = 0, a1 = TAU, n = 28) =>
    Array.from({ length: n + 1 }, (_, i) => { const t = a0 + ((a1 - a0) * i) / n; return [X + rx * Math.cos(t), Y, Z + rz * Math.sin(t)]; });
  const disc = (X, Y, Z, rx, rz = rx, cls = "f0") => poly(ell(X, Y, Z, rx, rz).slice(0, -1), cls);
  const frontArc = (X, Y, Z, r) => curve(ell(X, Y, Z, r, r, Math.PI, TAU, 16));
  // Round object standing on a surface (cup, pot, bottle): side band, then the top.
  function frustum(X, Z, y0, y1, r0, r1v, cls = "f0", top = "f0") {
    const a = ell(X, y0, Z, r0, r0, Math.PI, TAU, 16), b = ell(X, y1, Z, r1v, r1v, Math.PI, TAU, 16).reverse();
    return poly(a.concat(b), cls, { cover: 0.35, from: 1, gap: 4 }) + (top ? disc(X, y1, Z, r1v, r1v, top) : "");
  }
  // A disc standing in the plane X = const (dumbbell plates, the end of a rolled mat).
  const vdiscX = (X, Y, Z, r, cls = "f0") => poly(Array.from({ length: 24 }, (_, i) => [X, Y + r * Math.sin((i / 24) * TAU), Z + r * Math.cos((i / 24) * TAU)]), cls);
  // A thin sheet lying on a surface, turned by `ang`; `at(u, v)` maps sheet coordinates onto it.
  function flat(cx, cz, w, dd, ang, Y, h = 0.01, cls = "f0") {
    const c = Math.cos(ang), sn = Math.sin(ang);
    const at = (u, v, y = Y + h + 0.001) => [cx + u * c - v * sn, y, cz + u * sn + v * c];
    const q = (y) => [at(-w / 2, -dd / 2, y), at(w / 2, -dd / 2, y), at(w / 2, dd / 2, y), at(-w / 2, dd / 2, y)];
    return { s: (h ? poly(q(Y), "f0") : "") + poly(q(Y + h), cls), at, q };
  }
  function clipped(outline3d, inner) {
    const f = fillD(outline3d);
    if (!f) return "";
    const id = `xrc${++uid}`;
    return `<clipPath id="${id}"><path d="${f}"/></clipPath><g clip-path="url(#${id})">${inner}</g>`;
  }
  const bbox = (pts) => { const p = pts.map(pt); return [Math.min(...p.map((q) => q[0])), Math.min(...p.map((q) => q[1])), Math.max(...p.map((q) => q[0])), Math.max(...p.map((q) => q[1]))]; };
  // 2D drawing placed at a 3D anchor and scaled with depth; `u` = metres -> px.
  function at2d(X, Y, Z, fn) {
    if (Z - CAMZ < NEAR) return "";
    const [x, y] = pt([X, Y, Z]), k = F / (Z - CAMZ);
    return `<g style="--w:${wAt(Z - CAMZ)}">${fn(x, y, k)}</g>`;
  }
  const scribbleLines = ([x0, y0, x1, y1], n, gap = 0.18) =>
    thin(`<path class="n" d="${Array.from({ length: n }, (_, i) => { const y = y0 + ((y1 - y0) * (i + 0.6)) / (n + 0.4); return `M${r1(x0 + (x1 - x0) * 0.1)} ${r1(y)}H${r1(x0 + (x1 - x0) * (0.9 - gap * ((i * 5) % 3)))}`; }).join("")}"/>`);

  // ---------- views through windows (2D) ----------
  function tree2d(x, base, h) {
    const cy = base - h * 0.62, rx = h * 0.3, ry = h * 0.32, n = 13;
    let p = `M${r1(x - 3)} ${r1(base)}Q${r1(x - 2)} ${r1(base - h * 0.2)} ${r1(x - 6)} ${r1(cy + ry * 0.4)}M${r1(x + 3)} ${r1(base)}Q${r1(x + 2)} ${r1(base - h * 0.2)} ${r1(x + 7)} ${r1(cy + ry * 0.5)}M${r1(x)} ${r1(base - h * 0.3)}L${r1(x + rx * 0.4)} ${r1(cy)}`;
    const pts = Array.from({ length: n + 1 }, (_, i) => { const t = (i / n) * TAU + 0.4; return [x + rx * Math.cos(t) * (1 + 0.14 * Math.sin(i * 2.3)), cy + ry * Math.sin(t) * (1 + 0.12 * Math.cos(i * 1.7))]; });
    p += `M${xy(pts[0])}` + pts.slice(1).map((q, i) => { const r = Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]) * 0.62; return `A${r1(r)} ${r1(r)} 0 0 1 ${xy(q)}`; }).join("");
    let sc = "";
    for (let i = 0; i < 7; i++) { const a = rnd() * TAU, rr = 0.55 * rnd(); sc += `M${r1(x + rx * rr * Math.cos(a))} ${r1(cy + ry * rr * Math.sin(a))}c4 -5 9 -5 12 0`; }
    return `<path class="f0" d="${p.slice(p.lastIndexOf("M"))}"/><path class="n" d="${p}"/>` + thin(`<path class="n" d="${sc}"/>`);
  }
  function city2d(x0, x1, base, hMax) {
    let s = "", x = x0;
    for (let i = 0; x < x1; i++) {
      const w = hMax * (0.35 + rnd() * 0.4), h = hMax * (0.4 + rnd() * 0.6);
      s += `<path class="f0" d="M${r1(x)} ${r1(base)}V${r1(base - h)}H${r1(x + w)}V${r1(base)}"/><path class="n" d="M${r1(x)} ${r1(base)}V${r1(base - h)}H${r1(x + w)}V${r1(base)}"/>`;
      let win = "";
      for (let yy = base - h + 9; yy < base - 8; yy += 15) for (let xx = x + 6; xx < x + w - 9; xx += 12) if (rnd() > 0.3) win += `M${r1(xx)} ${r1(yy)}h5`;
      s += thin(`<path class="n" d="${win}"/>`);
      x += w + 3 + rnd() * 8;
    }
    return s;
  }
  // A window on the back wall (side == null) or the side wall X = side, with a view and glints.
  function windowAt(a0, a1, y0, y1, depthZ, side, view, { cols = 2, rows = 1 } = {}) {
    const P = side == null ? (u, y) => [u, y, depthZ] : (u, y) => [side, y, u];
    const outline = [P(a0, y0), P(a1, y0), P(a1, y1), P(a0, y1)];
    let s = poly(outline, "f0") + clipped(outline, view(bbox(outline)));
    for (let i = 1; i < cols; i++) { const u = a0 + ((a1 - a0) * i) / cols; s += line(P(u, y0), P(u, y1)); }
    for (let j = 1; j < rows; j++) { const y = y0 + ((y1 - y0) * j) / rows; s += line(P(a0, y), P(a1, y)); }
    let g = "";
    for (let i = 0; i < cols; i++) {
      const du = (a1 - a0) / cols, u = a0 + du * (i + 0.5), yy = y0 + (y1 - y0) * 0.5, dy = (y1 - y0) / rows;
      g += line(P(u, yy), P(u + du * 0.22, yy + dy * 0.25)) + line(P(u + du * 0.08, yy - dy * 0.06), P(u + du * 0.3, yy + dy * 0.18));
    }
    return s + thin(g) + poly(outline, "n");
  }
  const streetView = (trees, city = true) => ([x0, y0, x1, y1]) => {
    let s = city ? city2d(x0 - 10, x1 + 10, y1 - (y1 - y0) * 0.22, (y1 - y0) * 0.45) : "";
    for (let i = 0; i < trees; i++) s += tree2d(x0 + ((x1 - x0) * (i + 0.3 + 0.4 * rnd())) / trees, y1 + 4, (y1 - y0) * (0.6 + 0.2 * rnd()));
    return s;
  };

  // ---------- room pieces ----------
  function shell({ W, H, B, floor, N = -2 }) {
    let s = poly([[-W, 0, N], [W, 0, N], [W, 0, B], [-W, 0, B]]) + poly([[-W, H, N], [W, H, N], [W, H, B], [-W, H, B]], "d1") +
      poly([[-W, 0, N], [-W, H, N], [-W, H, B], [-W, 0, B]], "d1") + poly([[W, 0, N], [W, H, N], [W, H, B], [W, 0, B]], "d1") + backRect(-W, W, 0, H, B);
    let l = "";
    if (floor === "planks") {
      for (let x = -W + 0.24; x < W; x += 0.24) l += line([x, 0, N], [x, 0, B]);
      for (let z = 0.3, i = 0; z < B; z += 0.6, i++) for (let x = -W + 0.24 * (i % 4); x < W; x += 0.96) l += line([x, 0, z], [x + 0.24, 0, z]);
    }
    if (floor === "tiles") {
      for (let x = -W; x <= W + 0.01; x += 0.5) l += line([x, 0, N], [x, 0, B]);
      for (let z = 0; z <= B; z += 0.5) l += line([-W, 0, z], [W, 0, z]);
    }
    // skirting, cornice, wall corners in a little shade
    l += line([-W, 0.1, N], [-W, 0.1, B], [W, 0.1, B], [W, 0.1, N]) + line([-W, H - 0.08, N], [-W, H - 0.08, B], [W, H - 0.08, B], [W, H - 0.08, N]);
    return s + thin(l) + hatch([[-W, 0, B - 1.4], [-W, H, B - 1.4], [-W, H, B], [-W, 0, B]], { cover: 0.25, from: 1, gap: 7, ang: -1.45 }) +
      hatch([[W, 0, B], [W, H, B], [W, H, B - 1.4], [W, 0, B - 1.4]], { cover: 0.25, gap: 7, ang: -1.45 });
  }
  // A soft shadow patch on the floor or a table top.
  const shadow = (X, Y, Z, rx, rz) => hatch(ell(X, Y, Z, rx, rz, 0, TAU, 20), { gap: 5, cover: 0.55, ang: -0.3, from: 1 });

  function pendantCone(X, Z, low) {
    const [, top] = pt([X, 3.2, Z]);
    return at2d(X, low, Z, (x, y, k) => `<path class="n" d="M${r1(x)} ${r1(top)}V${r1(y - 0.32 * k)}"/><path class="f0" d="M${r1(x - 0.03 * k)} ${r1(y - 0.32 * k)}L${r1(x - 0.13 * k)} ${r1(y)}Q${r1(x)} ${r1(y + 0.035 * k)} ${r1(x + 0.13 * k)} ${r1(y)}L${r1(x + 0.03 * k)} ${r1(y - 0.32 * k)}Z"/><path class="n" d="M${r1(x - 0.03 * k)} ${r1(y - 0.32 * k)}L${r1(x - 0.13 * k)} ${r1(y)}Q${r1(x)} ${r1(y + 0.035 * k)} ${r1(x + 0.13 * k)} ${r1(y)}L${r1(x + 0.03 * k)} ${r1(y - 0.32 * k)}Z"/>` +
      thin(`<path class="n" d="${range(0, 4, 1).map((i) => `M${r1(x + (0.02 + i * 0.022) * k)} ${r1(y - (0.29 - i * 0.065) * k)}l${r1(0.012 * k)} ${r1(0.06 * k)}`).join("")}"/>`));
  }
  function pendantGlobe(X, Z, low) {
    const [, top] = pt([X, 3.2, Z]);
    return at2d(X, low, Z, (x, y, k) => `<path class="n" d="M${r1(x)} ${r1(top)}V${r1(y - 0.13 * k)}"/><path class="f0" d="M${r1(x - 0.02 * k)} ${r1(y - 0.13 * k)}h${r1(0.04 * k)}v${r1(0.04 * k)}h${r1(-0.04 * k)}z"/><path class="n" d="M${r1(x - 0.02 * k)} ${r1(y - 0.13 * k)}h${r1(0.04 * k)}v${r1(0.04 * k)}h${r1(-0.04 * k)}z"/>` +
      `<circle class="f0" cx="${r1(x)}" cy="${r1(y)}" r="${r1(0.1 * k)}"/><circle class="n" cx="${r1(x)}" cy="${r1(y)}" r="${r1(0.1 * k)}"/>` +
      thin(`<path class="n" d="M${r1(x - 0.06 * k)} ${r1(y - 0.02 * k)}a${r1(0.06 * k)} ${r1(0.06 * k)} 0 0 1 ${r1(0.05 * k)} ${r1(-0.05 * k)}M${r1(x - 0.02 * k)} ${r1(y + 0.03 * k)}q${r1(0.02 * k)} ${r1(-0.06 * k)} ${r1(0.04 * k)} 0"/>`));
  }
  function pendantDrum(X, Z, low, r = 0.25) {
    const [, top] = pt([X, 3.2, Z]);
    return at2d(X, low, Z, (x, y, k) => `<path class="n" d="M${r1(x)} ${r1(top)}V${r1(y - 0.2 * k)}"/><path class="f0" d="M${r1(x - r * k)} ${r1(y - 0.2 * k)}V${r1(y)}A${r1(r * k)} ${r1(0.04 * k)} 0 0 0 ${r1(x + r * k)} ${r1(y)}V${r1(y - 0.2 * k)}Z"/><path class="n" d="M${r1(x - r * k)} ${r1(y - 0.2 * k)}V${r1(y)}A${r1(r * k)} ${r1(0.04 * k)} 0 0 0 ${r1(x + r * k)} ${r1(y)}V${r1(y - 0.2 * k)}Z"/>` +
      thin(`<path class="n" d="${range(-0.8, 0.8, 0.4).map((f) => `M${r1(x + f * r * k)} ${r1(y - 0.17 * k)}v${r1(0.14 * k)}`).join("")}"/>`));
  }
  // Potted plant: a pot with a rim and long pointed leaves.
  function plant(X, Z, h = 1, Y = 0) {
    return at2d(X, Y, Z, (x, y, k) => {
      const s = k / 1000;
      const leaves = Array.from({ length: 11 }, (_, i) => {
        const a = -1.2 + i * 0.24 + (rnd() - 0.5) * 0.15, L = (330 + rnd() * 260) * h, bend = (rnd() - 0.5) * 0.6;
        const tx = Math.sin(a) * L, ty = -Math.cos(a) * L - 230, mx = Math.sin(a + bend) * L * 0.5, my = -Math.cos(a + bend) * L * 0.5 - 230, wdt = 26 + rnd() * 16;
        const nx = -Math.cos(a) * wdt, ny = -Math.sin(a) * wdt;
        return `M0 -220Q${r1(mx + nx)} ${r1(my + ny)} ${r1(tx)} ${r1(ty)}Q${r1(mx - nx)} ${r1(my - ny)} 0 -220Z`;
      });
      const pot = "M-120 -230h240l-26 230h-188z";
      return `<g transform="translate(${r1(x)} ${r1(y)}) scale(${s.toFixed(3)})">` + leaves.map((p) => `<path class="f0" d="${p}"/><path class="n" d="${p}"/>`).join("") +
        `<path class="f0" d="${pot}"/><path class="n" d="${pot}M-132 -230h264v-34h-264z"/><path class="f0" d="M-130 -232h260v-30h-260z"/><path class="n" d="M-132 -230h264v-34h-264z"/>` +
        `<g class="thin"><path class="n" d="M-100 -190l60 0M80 -150l-6 120M60 -120l-5 80"/></g></g>`;
    });
  }
  // Bistro chair (bentwood hoop back) seen from the front (facing 1) or the back (facing -1).
  function bistroChair(X, Z, facing = 1) {
    const w = 0.2, bz = Z + facing * 0.19;
    let legs = [[-w, -w], [w, -w], [-w, w], [w, w]].map(([dx, dz]) => line([X + dx * 1.08, 0, Z + dz * 1.08], [X + dx, 0.45, Z + dz])).join("") +
      thin(curve(ell(X, 0.17, Z, w * 1.04, w * 1.04, 0, TAU, 24)));
    const hoop = (r) => Array.from({ length: 15 }, (_, i) => { const t = Math.PI * (i / 14); return [X - r * Math.cos(t), 0.47 + (0.42 * Math.sin(t) * r) / w, bz]; });
    const back = () => {
      const o = hoop(w), inr = hoop(w * 0.72);
      return curve(o) + curve(inr) + line([X - w * 0.72, 0.47, bz], [X - w * 0.72, 0.5, bz]) + thin(line([X, 0.47, bz], [X, 0.47 + 0.42 * 0.72, bz]));
    };
    let s = legs;
    if (facing > 0) s += back();
    s += frustum(X, Z, 0.43, 0.47, w * 1.02, w * 1.04) + thin(disc(X, 0.471, Z, w * 0.82, w * 0.82, "n"));
    if (facing < 0) s += back();
    return s;
  }
  function roundTable(X, Z, top = 0.75, r = 0.34) {
    return shadow(X, 0.001, Z, r * 0.8, r * 0.6) + line([X, 0.02, Z], [X, top - 0.03, Z]) + frustum(X, Z, 0, 0.03, 0.22, 0.2) + frustum(X, Z, top - 0.035, top, r, r);
  }
  function officeChair(X, Z, facing = 1) {
    const bz = Z + facing * 0.2;
    let s = shadow(X, 0.001, Z, 0.32, 0.26);
    s += Array.from({ length: 5 }, (_, i) => { const a = (i / 5) * TAU + 0.3; return line([X, 0.09, Z], [X + 0.28 * Math.cos(a), 0.05, Z + 0.28 * Math.sin(a)]) + disc(X + 0.28 * Math.cos(a), 0.025, Z + 0.28 * Math.sin(a), 0.025); }).join("");
    s += line([X - 0.012, 0.09, Z], [X - 0.012, 0.44, Z]) + line([X + 0.012, 0.09, Z], [X + 0.012, 0.44, Z]);
    const back = () => {
      const pts = Array.from({ length: 21 }, (_, i) => { const t = (i / 20) * TAU; return [X + 0.22 * Math.sign(Math.cos(t)) * Math.pow(Math.abs(Math.cos(t)), 0.6), 0.82 + 0.24 * Math.sign(Math.sin(t)) * Math.pow(Math.abs(Math.sin(t)), 0.6), bz]; });
      return line([X, 0.48, Z + facing * 0.12], [X, 0.6, bz]) + poly(pts, "f0") + thin(curve(pts.map(([x, y, z]) => [X + (x - X) * 0.85, 0.82 + (y - 0.82) * 0.85, z])));
    };
    if (facing > 0) s += back();
    s += box(X - 0.25, X + 0.25, 0.44, 0.5, Z - 0.23, Z + 0.23) + line([X - 0.25, 0.5, Z], [X - 0.27, 0.66, Z], [X - 0.27, 0.66, Z + 0.15]) + line([X + 0.25, 0.5, Z], [X + 0.27, 0.66, Z], [X + 0.27, 0.66, Z + 0.15]);
    if (facing < 0) s += back();
    return s;
  }
  // Glass pastry case on a counter (top at Y = 1.1): two shelves of croissants, cakes and muffins.
  function pastryCase(x0, x1, z0, z1) {
    const Y = 1.1, H = 0.36, n = 3;
    let s = box(x0, x1, Y, Y + H, z0, z1, "f0", "f0") + box(x0, x1, Y + H, Y + H + 0.02, z0, z1);
    s += line([x0, Y + 0.17, z0 + 0.04], [x1, Y + 0.17, z0 + 0.04]) + thin(line([x0, Y + 0.17, z0 + 0.04], [x0, Y + 0.17, z1]));
    for (let i = 0; i < n; i++) {
      const x = x0 + ((x1 - x0) * (i + 0.5)) / n;
      s += croissant(x, Y, z0 + 0.15);
      s += i === 1 ? frustum(x, z0 + 0.16, Y + 0.17, Y + 0.24, 0.07, 0.07) + thin(line([x, Y + 0.24, z0 + 0.16], [x + 0.07, Y + 0.24, z0 + 0.12]) + line([x, Y + 0.24, z0 + 0.16], [x, Y + 0.17, z0 + 0.09]))
        : frustum(x, z0 + 0.15, Y + 0.17, Y + 0.215, 0.03, 0.04) + at2d(x, Y + 0.215, z0 + 0.15, (xx, yy, k) => `<path class="f0" d="M${r1(xx - 0.045 * k)} ${r1(yy)}q${r1(0.045 * k)} ${r1(-0.07 * k)} ${r1(0.09 * k)} 0z"/><path class="n" d="M${r1(xx - 0.045 * k)} ${r1(yy)}q${r1(0.045 * k)} ${r1(-0.07 * k)} ${r1(0.09 * k)} 0z"/>`);
    }
    return s + backRect(x0, x1, Y, Y + H, z0, "n") + thin(line([x0 + 0.08, Y + 0.32, z0], [x0 + 0.2, Y + 0.2, z0]) + line([x0 + 0.13, Y + 0.32, z0], [x0 + 0.25, Y + 0.2, z0]) + line([x1 - 0.2, Y + 0.12, z0], [x1 - 0.1, Y + 0.03, z0]));
  }
  // Upholstered armchair facing the viewer: rounded front faces, a cushion, splayed legs.
  function armchair(X, Z) {
    const w = 0.44, z0 = Z - 0.36, z1 = Z + 0.36;
    let s = shadow(X, 0.001, Z, 0.55, 0.42);
    s += [[-w + 0.06, z0 + 0.05, -1], [w - 0.06, z0 + 0.05, 1]].map(([dx, z, sg]) => line([X + dx, 0.12, z], [X + dx + sg * 0.03, 0, z - 0.03])).join("");
    s += box(X - w, X + w, 0.12, 0.98, z1 - 0.2, z1, "f0") + softRect(X - w, X + w, 0.12, 0.98, z1 - 0.2, 0.12);
    s += softRect(X - 0.24, X + 0.24, 0.5, 0.86, z1 - 0.24, 0.08) + thin(line([X - 0.2, 0.53, z1 - 0.241], [X + 0.18, 0.82, z1 - 0.241]));
    for (const sg of [-1, 1]) s += box(sg < 0 ? X - w : X + w - 0.13, sg < 0 ? X - w + 0.13 : X + w, 0.12, 0.66, z0, z1 - 0.2);
    s += box(X - w + 0.13, X + w - 0.13, 0.12, 0.46, z0 + 0.02, z1 - 0.2) + softRect(X - w + 0.13, X + w - 0.13, 0.32, 0.46, z0 + 0.02, 0.04) + thin(line([X - w + 0.15, 0.462, z0 + 0.25], [X + w - 0.15, 0.462, z0 + 0.25]));
    for (const sg of [-1, 1]) s += softRect(sg < 0 ? X - w : X + w - 0.13, sg < 0 ? X - w + 0.13 : X + w, 0.12, 0.66, z0, 0.06);
    return s;
  }
  function framePic(X, z0, z1, y0, y1, kind = 0) {
    const iz = (z1 - z0) * 0.14, iy = (y1 - y0) * 0.14;
    let s = sideRect(X, z0, z1, y0, y1) + sideRect(X, z0 + iz, z1 - iz, y0 + iy, y1 - iy);
    if (kind === 0) s += thin(line([X, y0 + iy, z0 + iz], [X, (y0 + y1) / 2, (z0 + z1) / 2], [X, y0 + iy + (y1 - y0) * 0.2, z1 - iz]) + line([X, y1 - iy * 2, z0 + iz * 2], [X, y1 - iy * 2, z0 + iz * 3]));
    else s += thin(Array.from({ length: 3 }, (_, i) => { const y = y0 + iy + ((y1 - y0 - 2 * iy) * (i + 1)) / 4; return curve([[X, y, z0 + iz], [X, y + 0.03, (z0 * 2 + z1) / 3], [X, y - 0.02, (z0 + z1 * 2) / 3], [X, y, z1 - iz]]); }).join(""));
    return s;
  }
  function backFrame(x0, x1, y0, y1, z, kind = 0) {
    const ix = (x1 - x0) * 0.12, iy = (y1 - y0) * 0.12;
    let s = backRect(x0, x1, y0, y1, z) + backRect(x0 + ix, x1 - ix, y0 + iy, y1 - iy, z, "n");
    if (kind === 0) s += thin(line([x0 + ix, y0 + iy, z], [x0 + (x1 - x0) * 0.45, y0 + (y1 - y0) * 0.55, z], [x0 + (x1 - x0) * 0.62, y0 + (y1 - y0) * 0.38, z], [x1 - ix, y0 + (y1 - y0) * 0.62, z]));
    if (kind === 1) s += thin(range(0.3, 0.75, 0.15).map((f) => curve([[x0 + ix, y0 + (y1 - y0) * f, z], [(x0 + x1) / 2, y0 + (y1 - y0) * (f + 0.05), z], [x1 - ix, y0 + (y1 - y0) * f, z]])).join(""));
    if (kind === 2) s += thin(curve(ell((x0 + x1) / 2, 0, 0, (x1 - x0) * 0.2, (y1 - y0) * 0.2).map(([x, , zz]) => [x, (y0 + y1) / 2 + zz, z])));
    return s;
  }

  // ---------- props (origin X, Y = surface, Z) ----------
  function mug(X, Y, Z, r = 0.042, h = 0.095) {
    return shadow(X + 0.02, Y, Z + 0.02, r * 1.4, r * 1.1) + `<path class="n" style="--w:${wAt(Z - CAMZ)}" d="M${xy(pt([X + r * 0.95, Y + h * 0.8, Z]))}C${xy(pt([X + r + 0.045, Y + h * 0.85, Z]))} ${xy(pt([X + r + 0.045, Y + h * 0.2, Z]))} ${xy(pt([X + r * 0.92, Y + h * 0.25, Z]))}"/>` +
      frustum(X, Z, Y, Y + h, r * 0.92, r) + disc(X, Y + h - 0.012, Z, r * 0.84, r * 0.84, "h1");
  }
  function cupSaucer(X, Y, Z, art = true) {
    let s = shadow(X + 0.02, Y, Z + 0.02, 0.08, 0.06) + frustum(X, Z, Y, Y + 0.012, 0.055, 0.078) + thin(disc(X, Y + 0.0125, Z, 0.045, 0.045, "n"));
    s += `<path class="n" style="--w:${wAt(Z - CAMZ)}" d="M${xy(pt([X + 0.038, Y + 0.058, Z]))}C${xy(pt([X + 0.075, Y + 0.062, Z]))} ${xy(pt([X + 0.07, Y + 0.025, Z]))} ${xy(pt([X + 0.034, Y + 0.028, Z]))}"/>`;
    s += frustum(X, Z, Y + 0.012, Y + 0.065, 0.028, 0.042) + disc(X, Y + 0.058, Z, 0.036, 0.036);
    if (art) s += at2d(X, Y + 0.059, Z, (x, y, k) => thin(`<path class="n" d="M${r1(x)} ${r1(y + 0.012 * k)}c${r1(-0.03 * k)} ${r1(-0.012 * k)} ${r1(-0.018 * k)} ${r1(-0.03 * k)} 0 ${r1(-0.016 * k)}c${r1(0.018 * k)} ${r1(-0.014 * k)} ${r1(0.03 * k)} ${r1(0.004 * k)} 0 ${r1(0.016 * k)}M${r1(x)} ${r1(y + 0.012 * k)}v${r1(-0.022 * k)}"/>`));
    s += line([X - 0.06, Y + 0.014, Z - 0.02], [X - 0.02, Y + 0.016, Z - 0.035]) + disc(X - 0.068, Y + 0.014, Z - 0.017, 0.012, 0.008);
    return s;
  }
  function takeawayCup(X, Y, Z) {
    return shadow(X + 0.02, Y, Z + 0.02, 0.06, 0.045) + frustum(X, Z, Y, Y + 0.13, 0.03, 0.043, "f0", null) + frustum(X, Z, Y + 0.035, Y + 0.085, 0.034, 0.039, "h1", null) +
      frustum(X, Z, Y + 0.13, Y + 0.142, 0.046, 0.046) + frustum(X, Z, Y + 0.142, Y + 0.152, 0.042, 0.036) + disc(X - 0.012, Y + 0.153, Z - 0.02, 0.008, 0.004, "h2");
  }
  function screenQuad(x0, x1, y, z, h, lean) {
    return [[x0, y, z], [x1, y, z], [x1, y + h, z + lean], [x0, y + h, z + lean]];
  }
  function screenContent(kind, [x0, y0, x1, y1]) {
    const w = x1 - x0, h = y1 - y0, P = (fx, fy) => `${r1(x0 + w * fx)} ${r1(y0 + h * fy)}`;
    if (kind === "call") {
      let s = "";
      for (const [i, j] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
        const cx = x0 + w * (0.25 + 0.5 * i), cy = y0 + h * (0.25 + 0.5 * j), r = h * 0.075;
        s += `<path class="n" d="M${P(0.5 * i + 0.02, 0.5 * j + 0.03)}H${r1(x0 + w * (0.5 * i + 0.48))}V${r1(y0 + h * (0.5 * j + 0.47))}H${r1(x0 + w * (0.5 * i + 0.02))}Z"/>`;
        s += `<circle class="f0" cx="${r1(cx)}" cy="${r1(cy - r * 0.5)}" r="${r1(r)}"/><circle class="n" cx="${r1(cx)}" cy="${r1(cy - r * 0.5)}" r="${r1(r)}"/><path class="n" d="M${r1(cx - r * 2.1)} ${r1(cy + h * 0.21)}q${r1(r * 2.1)} ${r1(-r * 3.4)} ${r1(r * 4.2)} 0"/>`;
      }
      return thin(s);
    }
    if (kind === "play") return `<path class="n" d="M${P(0.44, 0.3)}L${P(0.6, 0.45)}L${P(0.44, 0.6)}Z"/>` + thin(`<path class="n" d="M${P(0.08, 0.84)}H${r1(x1 - w * 0.08)}M${P(0.08, 0.84)}m0 -2h${r1(w * 0.35)}"/>`) + hatch2d(x0, y0, x1, y0 + h * 0.75, 5);
    if (kind === "game") return thin(`<path class="n" d="M${P(0, 0.75)}L${P(0.2, 0.45)}L${P(0.35, 0.62)}L${P(0.55, 0.3)}L${P(0.8, 0.66)}L${P(1, 0.5)}M${P(0, 0.85)}H${r1(x1)}M${P(0.45, 0.85)}v${r1(-h * 0.12)}h${r1(w * 0.05)}v${r1(h * 0.12)}"/><circle class="n" cx="${r1(x0 + w * 0.8)}" cy="${r1(y0 + h * 0.2)}" r="${r1(h * 0.08)}"/>`);
    if (kind === "map") return thin(`<path class="n" d="M${P(0, 0.3)}C${P(0.3, 0.4)} ${P(0.5, 0.1)} ${P(1, 0.25)}M${P(0.2, 0)}C${P(0.3, 0.4)} ${P(0.15, 0.7)} ${P(0.4, 1)}M${P(0, 0.75)}L${P(1, 0.65)}M${P(0.7, 0)}L${P(0.75, 1)}"/>`) + `<path class="n" d="M${P(0.55, 0.52)}c${r1(-w * 0.12)} ${r1(-h * 0.1)} ${r1(-w * 0.08)} ${r1(-h * 0.24)} 0 ${r1(-h * 0.24)}c${r1(w * 0.08)} 0 ${r1(w * 0.12)} ${r1(h * 0.14)} 0 ${r1(h * 0.24)}z"/>`;
    if (kind === "shop") return thin([0, 1].map((i) => [0, 1, 2].map((j) => `<path class="n" d="M${P(0.08 + 0.46 * i, 0.06 + 0.31 * j)}h${r1(w * 0.38)}v${r1(h * 0.2)}h${r1(-w * 0.38)}zM${P(0.08 + 0.46 * i, 0.3 + 0.31 * j)}h${r1(w * 0.25)}"/>`).join("")).join(""));
    if (kind === "reader") return thin(`<path class="n" d="M${P(0.3, 0.2)}h${r1(w * 0.4)}v${r1(h * 0.2)}h${r1(-w * 0.4)}z"/>` + [0, 1, 2].map((j) => [0, 1, 2].map((i) => `<circle class="n" cx="${r1(x0 + w * (0.3 + 0.2 * i))}" cy="${r1(y0 + h * (0.58 + 0.13 * j))}" r="${r1(w * 0.04)}"/>`).join("")).join(""));
    return scribbleLines([x0, y0 + h * 0.12, x1, y1 - h * 0.08], 6, 0.2) + thin(`<path class="n" d="M${P(0.1, 0.1)}h${r1(w * 0.3)}"/>`);
  }
  function hatch2d(x0, y0, x1, y1, gap) {
    let s = "";
    for (let o = 0; o < x1 - x0 + (y1 - y0); o += gap) s += `M${r1(x0 + o)} ${r1(y0)}l${r1(-(y1 - y0))} ${r1(y1 - y0)}`;
    return `<g class="thin" opacity=".55"><path class="n" d="${s}"/></g>`;
  }
  function laptop(X, Y, Z, kind) {
    const w = 0.165, dd = 0.115;
    let s = shadow(X + 0.03, Y, Z + 0.03, w * 1.1, dd * 1.1) + box(X - w, X + w, Y, Y + 0.012, Z - dd, Z + dd);
    const kb = [];
    for (let i = 0; i <= 4; i++) kb.push(line([X - w + 0.02, Y + 0.013, Z + 0.005 + i * 0.022], [X + w - 0.02, Y + 0.013, Z + 0.005 + i * 0.022]));
    for (let i = 0; i <= 12; i++) kb.push(line([X - w + 0.02 + i * 0.0242, Y + 0.013, Z + 0.005], [X - w + 0.02 + i * 0.0242, Y + 0.013, Z + 0.093]));
    s += thin(kb.join("")) + flatRect(X - 0.055, X + 0.055, Z - 0.1, Z - 0.03, Y + 0.013, "n");
    const scr = screenQuad(X - w, X + w, Y + 0.012, Z + dd, 0.21, 0.055);
    const inner = screenQuad(X - w + 0.012, X + w - 0.012, Y + 0.025, Z + dd + 0.003, 0.18, 0.048);
    return s + poly(scr) + poly(inner, "n") + clipped(inner, screenContent(kind, bbox(inner)));
  }
  // Someone else's laptop across the table: we see the lid.
  function laptopBack(X, Y, Z) {
    const w = 0.165;
    return box(X - w, X + w, Y, Y + 0.012, Z - 0.23, Z) + poly(screenQuad(X - w, X + w, Y + 0.012, Z - 0.23, 0.21, 0.05), "h1", { cover: 0.4 }) + at2d(X, Y + 0.12, Z - 0.205, (x, y, k) => `<circle class="n" cx="${r1(x)}" cy="${r1(y)}" r="${r1(0.018 * k)}"/>`);
  }
  function tablet(X, Y, Z, kind) {
    const w = 0.12;
    const scr = screenQuad(X - w, X + w, Y + 0.01, Z, 0.17, 0.06), inner = screenQuad(X - w + 0.01, X + w - 0.01, Y + 0.02, Z + 0.004, 0.15, 0.053);
    return shadow(X, Y, Z + 0.04, 0.13, 0.06) + box(X - 0.05, X + 0.05, Y, Y + 0.012, Z - 0.03, Z + 0.08) + poly(scr) + poly(inner, "n") + clipped(inner, screenContent(kind, bbox(inner)));
  }
  function phone(X, Y, Z, ang, kind) {
    const p = flat(X, Z, 0.072, 0.148, ang, Y, 0.009);
    let s = shadow(X + 0.015, Y, Z + 0.015, 0.06, 0.08) + p.s;
    if (!kind) return s + flat(X, Z, 0.062, 0.13, ang, Y + 0.009, 0.0005, "h2").s;
    const q = [p.at(-0.031, -0.065), p.at(0.031, -0.065), p.at(0.031, 0.065), p.at(-0.031, 0.065)];
    return s + poly(q, "n") + clipped(q, screenContent(kind, bbox(q)));
  }
  function notebook(X, Y, Z, ang, checks = false) {
    const nb = flat(X, Z, 0.15, 0.21, ang, Y, 0.012);
    let s = shadow(X + 0.02, Y, Z + 0.02, 0.1, 0.12) + nb.s;
    const ls = [];
    for (let i = 0; i < 6; i++) {
      const v = -0.07 + i * 0.03;
      if (checks) ls.push(poly([nb.at(-0.055, v - 0.008), nb.at(-0.04, v - 0.008), nb.at(-0.04, v + 0.007), nb.at(-0.055, v + 0.007)], "n"));
      ls.push(line(nb.at(checks ? -0.03 : -0.06, v), nb.at(0.06 - (i % 3) * 0.025, v)));
    }
    if (checks) ls.push(line(nb.at(-0.054, -0.07), nb.at(-0.048, -0.064), nb.at(-0.036, -0.08)), line(nb.at(-0.054, -0.04), nb.at(-0.048, -0.034), nb.at(-0.036, -0.05)));
    for (let i = 0; i < 7; i++) ls.push(disc(...nb.at(-0.068, -0.09 + i * 0.03), 0.004, 0.004, "n"));
    return s + thin(ls.join(""));
  }
  function pen(X, Y, Z, ang, L = 0.14, fat = 0.008) {
    const p = flat(X, Z, L, fat, ang, Y, fat);
    return p.s + line(p.at(L * 0.25, -fat / 2), p.at(L * 0.25, fat / 2));
  }
  function papers(X, Y, Z, ang) {
    let s = shadow(X + 0.02, Y, Z + 0.02, 0.12, 0.15);
    [0.12, -0.05, 0].forEach((da, i) => { s += flat(X + i * 0.01, Z - i * 0.005, 0.21, 0.297, ang + da, Y + i * 0.002, 0.001).s; });
    const top = flat(X + 0.02, Z - 0.01, 0.21, 0.297, ang, Y + 0.004, 0.001);
    const ls = [line(top.at(-0.08, -0.12), top.at(0.03, -0.12))];
    for (let i = 0; i < 9; i++) ls.push(line(top.at(-0.085, -0.09 + i * 0.024), top.at(0.085 - (i % 4 === 3 ? 0.06 : 0), -0.09 + i * 0.024)));
    ls.push(line(top.at(-0.098, -0.14), top.at(-0.088, -0.13)));
    return s + thin(ls.join(""));
  }
  function openBook(X, Y, Z) {
    const w = 0.2, dd = 0.14, n = 10;
    const page = (sgn) => {
      const front = Array.from({ length: n + 1 }, (_, i) => { const u = i / n; return [X + sgn * w * u, Y + 0.025 * Math.sin(Math.PI * u * 0.9) + 0.004, Z - dd]; });
      const back = front.map(([x, y]) => [x, y, Z + dd]).reverse();
      return poly(front.concat(back)) + thin(Array.from({ length: 7 }, (_, j) => {
        const z = Z - dd + 0.035 + j * 0.032;
        return curve(Array.from({ length: 7 }, (_, i) => { const u = 0.15 + (i / 6) * (j % 3 ? 0.68 : 0.5); return [X + sgn * w * u, Y + 0.025 * Math.sin(Math.PI * u * 0.9) + 0.005, z]; }));
      }).join(""));
    };
    return shadow(X + 0.03, Y, Z + 0.02, 0.24, 0.16) + flatRect(X - w - 0.012, X + w + 0.012, Z - dd - 0.01, Z + dd + 0.01, Y + 0.002) + page(-1) + page(1) + hatch([[X - 0.03, Y, Z - dd], [X, Y, Z - dd], [X, Y, Z + dd], [X - 0.03, Y, Z + dd]], { cover: 1, gap: 3 });
  }
  function bookStack(X, Y, Z) {
    return shadow(X + 0.03, Y, Z + 0.02, 0.13, 0.13) + box(X - 0.1, X + 0.1, Y, Y + 0.035, Z - 0.12, Z + 0.12) + thin(line([X - 0.1, Y + 0.012, Z - 0.12], [X + 0.1, Y + 0.012, Z - 0.12]) + line([X - 0.1, Y + 0.024, Z - 0.12], [X + 0.1, Y + 0.024, Z - 0.12])) +
      box(X - 0.085, X + 0.09, Y + 0.035, Y + 0.06, Z - 0.11, Z + 0.11, "h1") + box(X - 0.095, X + 0.08, Y + 0.06, Y + 0.09, Z - 0.115, Z + 0.105) + thin(line([X - 0.095, Y + 0.075, Z - 0.115], [X + 0.08, Y + 0.075, Z - 0.115]));
  }
  function bowl(X, Y, Z, r = 0.09, h = 0.06, fill = "dots") {
    let s = shadow(X + 0.02, Y, Z + 0.02, r * 1.1, r * 0.9) + frustum(X, Z, Y, Y + h, r * 0.55, r) + thin(frontArc(X, Y + h * 0.75, Z, r * 0.9));
    if (fill === "dots") s += Array.from({ length: 8 }, (_, i) => disc(X + r * 0.55 * Math.cos(i * 0.8), Y + h + 0.005, Z + r * 0.45 * Math.sin(i * 0.8), 0.018, 0.016, "f0")).join("");
    if (fill === "leaves") s += Array.from({ length: 9 }, (_, i) => at2d(X + r * 0.5 * Math.cos(i * 0.7), Y + h + 0.01, Z + r * 0.45 * Math.sin(i * 0.7), (x, y, k) => `<path class="f0" d="M${r1(x - 0.02 * k)} ${r1(y)}q${r1(0.02 * k)} ${r1(-0.03 * k)} ${r1(0.04 * k)} 0q${r1(-0.02 * k)} ${r1(0.015 * k)} ${r1(-0.04 * k)} 0z"/><path class="n" d="M${r1(x - 0.02 * k)} ${r1(y)}q${r1(0.02 * k)} ${r1(-0.03 * k)} ${r1(0.04 * k)} 0q${r1(-0.02 * k)} ${r1(0.015 * k)} ${r1(-0.04 * k)} 0zm0 0h${r1(0.04 * k)}"/>`)).join("");
    if (fill === "popcorn") s += Array.from({ length: 11 }, (_, i) => at2d(X + r * 0.6 * Math.cos(i * 0.6), Y + h + 0.012, Z + r * 0.5 * Math.sin(i * 0.6), (x, y, k) => { const p = `M${r1(x - 0.013 * k)} ${r1(y)}a${r1(0.011 * k)} ${r1(0.011 * k)} 0 1 1 ${r1(0.012 * k)} ${r1(-0.011 * k)}a${r1(0.011 * k)} ${r1(0.011 * k)} 0 1 1 ${r1(0.013 * k)} ${r1(0.011 * k)}a${r1(0.009 * k)} ${r1(0.009 * k)} 0 0 1 ${r1(-0.025 * k)} 0z`; return `<path class="f0" d="${p}"/><path class="n" d="${p}"/>`; })).join("");
    if (fill === "chips") s += Array.from({ length: 8 }, (_, i) => disc(X + r * 0.5 * Math.cos(i * 0.8), Y + h + 0.004 + (i % 3) * 0.004, Z + r * 0.4 * Math.sin(i * 0.8), 0.022, 0.014, "f0")).join("");
    return s;
  }
  function plate(X, Y, Z, r = 0.12) {
    return shadow(X + 0.02, Y, Z + 0.02, r * 1.05, r * 0.85) + frustum(X, Z, Y, Y + 0.014, r * 0.7, r) + thin(disc(X, Y + 0.0145, Z, r * 0.72, r * 0.72, "n"));
  }
  function croissant(X, Y, Z) {
    return at2d(X, Y + 0.018, Z, (x, y, k) => {
      const s = k / 1000, P = (u, v) => `${r1(x + u * s)} ${r1(y + v * s)}`;
      const o = `M${P(-62, 6)}Q${P(-70, -26)} ${P(-34, -34)}Q${P(0, -46)} ${P(34, -34)}Q${P(70, -26)} ${P(62, 6)}Q${P(40, -8)} ${P(0, -6)}Q${P(-40, -8)} ${P(-62, 6)}Z`;
      return `<path class="f0" d="${o}"/><path class="n" d="${o}"/>` + thin(`<path class="n" d="M${P(-36, -32)}Q${P(-30, -18)} ${P(-38, -8)}M${P(-12, -40)}Q${P(-6, -22)} ${P(-14, -6)}M${P(12, -40)}Q${P(6, -22)} ${P(14, -6)}M${P(36, -32)}Q${P(30, -18)} ${P(38, -8)}"/>`);
    });
  }
  function vase(X, Y, Z) {
    const flowers = at2d(X, Y + 0.12, Z, (x, y, k) => {
      const s = k / 1000;
      const st = [[-28, -150], [40, -170], [6, -120], [-48, -105]];
      return `<path class="n" d="${st.map(([dx, dy]) => `M${r1(x)} ${r1(y)}Q${r1(x + dx * 0.2 * s)} ${r1(y + dy * 0.5 * s)} ${r1(x + dx * s)} ${r1(y + dy * s)}`).join("")}"/>` +
        st.map(([dx, dy], i) => { const cx = x + dx * s, cy = y + dy * s, r = (i === 3 ? 9 : 13) * s; return Array.from({ length: 5 }, (_, j) => { const a = (j / 5) * TAU; return `<circle class="f0" cx="${r1(cx + Math.cos(a) * r)}" cy="${r1(cy + Math.sin(a) * r)}" r="${r1(r * 0.75)}"/><circle class="n" cx="${r1(cx + Math.cos(a) * r)}" cy="${r1(cy + Math.sin(a) * r)}" r="${r1(r * 0.75)}"/>`; }).join("") + `<circle class="f0" cx="${r1(cx)}" cy="${r1(cy)}" r="${r1(r * 0.5)}"/><circle class="n" cx="${r1(cx)}" cy="${r1(cy)}" r="${r1(r * 0.5)}"/>`; }).join("") +
        `<path class="n" d="M${r1(x - 6 * s)} ${r1(y - 60 * s)}q${r1(-25 * s)} ${r1(-10 * s)} ${r1(-34 * s)} ${r1(-30 * s)}q${r1(20 * s)} 0 ${r1(34 * s)} ${r1(30 * s)}"/>`;
    });
    return shadow(X + 0.02, Y, Z + 0.02, 0.04, 0.03) + flowers + frustum(X, Z, Y, Y + 0.12, 0.032, 0.022) + thin(frontArc(X, Y + 0.08, Z, 0.027));
  }
  function glass(X, Y, Z, h = 0.12, level = 0.6) {
    return shadow(X + 0.015, Y, Z + 0.015, 0.045, 0.035) + frustum(X, Z, Y, Y + h, 0.03, 0.035, "f0", null) + thin(frontArc(X, Y + h * level, Z, 0.033)) +
      hatch(ell(X, Y + h * level, Z, 0.033, 0.033, Math.PI, TAU, 10).concat(ell(X, Y, Z, 0.03, 0.03, Math.PI, TAU, 10).reverse()), { gap: 4, cover: 0.5 }) + disc(X, Y + h, Z, 0.035, 0.035, "n") + thin(line([X - 0.02, Y + h * 0.85, Z - 0.034], [X - 0.022, Y + h * 0.4, Z - 0.034]));
  }
  function wineGlass(X, Y, Z) {
    return shadow(X + 0.015, Y, Z + 0.015, 0.04, 0.03) + disc(X, Y + 0.002, Z, 0.035) + line([X, Y, Z], [X, Y + 0.09, Z]) + frustum(X, Z, Y + 0.09, Y + 0.17, 0.012, 0.042, "f0", null) +
      thin(frontArc(X, Y + 0.12, Z, 0.03)) + hatch(ell(X, Y + 0.12, Z, 0.03, 0.03, Math.PI, TAU, 10).concat(ell(X, Y + 0.095, Z, 0.014, 0.014, Math.PI, TAU, 10).reverse()), { gap: 3, cover: 1 }) + disc(X, Y + 0.17, Z, 0.042, 0.042, "n");
  }
  function bottle(X, Y, Z) {
    return shadow(X + 0.015, Y, Z + 0.015, 0.045, 0.035) + frustum(X, Z, Y, Y + 0.2, 0.034, 0.034) + frustum(X, Z, Y + 0.2, Y + 0.235, 0.022, 0.022, "h1") + thin(frontArc(X, Y + 0.13, Z, 0.034) + frontArc(X, Y + 0.07, Z, 0.034));
  }
  function can(X, Y, Z) {
    return shadow(X + 0.015, Y, Z + 0.015, 0.04, 0.03) + frustum(X, Z, Y, Y + 0.12, 0.033, 0.033) + thin(frontArc(X, Y + 0.105, Z, 0.033) + disc(X, Y + 0.121, Z + 0.01, 0.01, 0.007, "n"));
  }
  function dumbbell(X, Y, Z, ang = 0) {
    const y = Y + 0.055;
    let s = shadow(X, Y, Z + 0.02, 0.2, 0.06) + line([X - 0.17, y, Z], [X + 0.17, y, Z]) + line([X - 0.17, y + 0.012, Z], [X + 0.17, y + 0.012, Z]);
    for (const sgn of [-1, 1]) s += vdiscX(X + sgn * 0.11, y, Z, 0.055, "h1") + vdiscX(X + sgn * 0.135, y, Z, 0.055) + vdiscX(X + sgn * 0.16, y, Z, 0.045);
    return s;
  }
  function paperBag(X, Y, Z) {
    const w = 0.11, dd = 0.07, h = 0.26;
    return shadow(X + 0.03, Y, Z + 0.03, 0.14, 0.09) + poly([[X - 0.05, Y + h, Z + 0.02], [X - 0.02, Y + h + 0.13, Z + 0.02], [X + 0.012, Y + h + 0.13, Z + 0.02], [X - 0.018, Y + h, Z + 0.02]]) +
      thin(range(0.02, 0.11, 0.03).map((t) => line([X - 0.05 + t * 0.25, Y + h + t, Z + 0.02], [X - 0.018 + t * 0.25, Y + h + t, Z + 0.02])).join("")) +
      poly([[X + 0.02, Y + h, Z], [X + 0.035, Y + h + 0.07, Z], [X + 0.07, Y + h + 0.1, Z], [X + 0.095, Y + h + 0.06, Z], [X + 0.07, Y + h, Z]]) +
      box(X - w, X + w, Y, Y + h, Z - dd, Z + dd) + thin(line([X - w, Y + h - 0.03, Z - dd], [X + w, Y + h - 0.03, Z - dd]) + line([X - w + 0.01, Y + 0.02, Z - dd], [X - w + 0.01, Y + h - 0.04, Z - dd]) + line([X + w - 0.02, Y + 0.02, Z - dd], [X + w - 0.03, Y + h - 0.05, Z - dd]));
  }
  function keys(X, Y, Z) {
    return disc(X, Y + 0.003, Z, 0.022, 0.022, "n") + thin(disc(X, Y + 0.003, Z, 0.017, 0.017, "n")) + flat(X + 0.045, Z - 0.012, 0.06, 0.02, 0.35, Y + 0.002, 0.004).s + flat(X + 0.012, Z - 0.05, 0.022, 0.055, 0.15, Y + 0.002, 0.004).s +
      disc(X - 0.03, Y + 0.004, Z + 0.02, 0.016, 0.012, "h1");
  }
  function pot(X, Y, Z) {
    const r = 0.11, h = 0.12;
    const steam = at2d(X, Y + h + 0.05, Z, (x, y, k) => thin(`<path class="n" d="M${r1(x - 0.03 * k)} ${r1(y)}c${r1(-0.02 * k)} ${r1(-0.04 * k)} ${r1(0.02 * k)} ${r1(-0.06 * k)} 0 ${r1(-0.1 * k)}M${r1(x + 0.03 * k)} ${r1(y)}c${r1(-0.02 * k)} ${r1(-0.04 * k)} ${r1(0.02 * k)} ${r1(-0.06 * k)} 0 ${r1(-0.1 * k)}"/>`));
    return shadow(X + 0.03, Y, Z + 0.03, r * 1.2, r) + box(X - r - 0.045, X - r + 0.005, Y + h - 0.03, Y + h - 0.012, Z - 0.015, Z + 0.015) + box(X + r - 0.005, X + r + 0.045, Y + h - 0.03, Y + h - 0.012, Z - 0.015, Z + 0.015) +
      frustum(X, Z, Y, Y + h, r, r) + thin(frontArc(X, Y + 0.02, Z, r)) + disc(X, Y + h + 0.008, Z, r * 1.03, r * 1.03) + thin(disc(X, Y + h + 0.009, Z, r * 0.85, r * 0.85, "n")) + frustum(X, Z, Y + h + 0.008, Y + h + 0.03, 0.018, 0.014) + steam;
  }
  function board(X, Y, Z) {
    const b = flat(X, Z, 0.34, 0.2, 0.06, Y, 0.018);
    let s = shadow(X + 0.03, Y, Z + 0.03, 0.2, 0.13) + b.s + thin(curve([b.at(-0.15, -0.08), b.at(-0.02, -0.075), b.at(0.12, -0.08)]) + curve([b.at(-0.15, 0.085), b.at(0, 0.08), b.at(0.1, 0.085)]));
    s += [[-0.1, -0.03], [-0.06, 0.0], [-0.11, 0.04], [-0.03, 0.045], [-0.075, 0.07]].map(([u, v]) => { const [x, , z] = b.at(u, v); return frustum(x, z, Y + 0.018, Y + 0.026, 0.022, 0.022) + thin(disc(x, Y + 0.027, z, 0.012, 0.012, "n")); }).join("");
    const blade = [b.at(0.0, -0.02), b.at(0.15, -0.035), b.at(0.15, 0.0), b.at(0.02, 0.005)];
    const [hx, , hz] = b.at(0.21, -0.017);
    return s + poly(blade) + flat(hx, hz, 0.1, 0.024, 0.0, Y + 0.02, 0.014, "h1").s;
  }
  function towel(X, Y, Z) {
    const t = flat(X, Z, 0.22, 0.13, 0.12, Y, 0.035, "f0");
    return shadow(X + 0.02, Y, Z + 0.02, 0.13, 0.08) + t.s + thin(line(t.at(-0.11, 0.0), t.at(0.11, 0.0)) + line(t.at(-0.11, 0.045), t.at(0.11, 0.045)) + range(-0.09, 0.09, 0.03).map((u) => line(t.at(u, -0.065), t.at(u, -0.058))).join(""));
  }
  function remote(X, Y, Z) {
    const r = flat(X, Z, 0.045, 0.16, 0.55, Y, 0.015);
    return r.s + [0.05, 0.02, -0.01, -0.04].map((v) => disc(...r.at(0, v), 0.008, 0.008, "n")).join("") + disc(...r.at(0, -0.062), 0.01, 0.01, "h2");
  }
  function mouse(X, Y, Z) {
    return shadow(X + 0.01, Y, Z + 0.01, 0.04, 0.06) + disc(X, Y, Z, 0.033, 0.056) + disc(X, Y + 0.025, Z + 0.004, 0.027, 0.046) + line([X, Y + 0.0255, Z + 0.004], [X, Y + 0.0255, Z + 0.048]) + curve([[X, Y + 0.026, Z + 0.05], [X + 0.01, Y + 0.02, Z + 0.09], [X - 0.02, Y + 0.002, Z + 0.15]]);
  }
  function gamepad(X, Y, Z) {
    const o = [[-0.08, 0.02], [-0.05, 0.035], [0.05, 0.035], [0.08, 0.02], [0.095, -0.03], [0.07, -0.05], [0.04, -0.02], [-0.04, -0.02], [-0.07, -0.05], [-0.095, -0.03]];
    const P = (u, v, y = Y + 0.03) => [X + u, y, Z + v];
    return shadow(X + 0.02, Y, Z + 0.02, 0.11, 0.05) + poly(o.map(([u, v]) => P(u, v, Y)), "f0") + poly(o.map(([u, v]) => P(u, v)), "f0") + line(P(-0.065, 0.0), P(-0.035, 0.0)) + line(P(-0.05, -0.015), P(-0.05, 0.015)) +
      [[0.05, 0.012], [0.065, 0], [0.05, -0.012], [0.035, 0]].map(([u, v]) => disc(X + u, Y + 0.031, Z + v, 0.007, 0.007, "n")).join("") + disc(X - 0.02, Y + 0.031, Z - 0.008, 0.011, 0.011, "h1") + disc(X + 0.02, Y + 0.031, Z - 0.008, 0.011, 0.011, "h1");
  }
  function card(X, Y, Z, ang) {
    const c = flat(X, Z, 0.085, 0.054, ang, Y, 0.002);
    return c.s + poly([c.at(-0.03, -0.012), c.at(-0.015, -0.012), c.at(-0.015, 0.0), c.at(-0.03, 0.0)], "n") + thin(line(c.at(-0.03, 0.015), c.at(0.03, 0.015)));
  }
  function receipt(X, Y, Z, ang) {
    const r = flat(X, Z, 0.06, 0.16, ang, Y, 0.001);
    return r.s + thin(range(-0.06, 0.06, 0.016).map((v, i) => line(r.at(-0.022, v), r.at(i % 3 ? 0.022 : 0.005, v))).join(""));
  }
  function cardReader(X, Y, Z) {
    const scr = screenQuad(X - 0.04, X + 0.04, Y + 0.02, Z, 0.13, 0.05);
    return shadow(X + 0.02, Y, Z + 0.03, 0.06, 0.05) + box(X - 0.045, X + 0.045, Y, Y + 0.02, Z - 0.02, Z + 0.06) + poly(scr) + clipped(scr, screenContent("reader", bbox(scr)));
  }
  function tipJar(X, Y, Z) {
    return frustum(X, Z, Y, Y + 0.14, 0.05, 0.05, "f0", null) + Array.from({ length: 6 }, (_, i) => disc(X + 0.03 * Math.cos(i), Y + 0.01 + i * 0.006, Z + 0.025 * Math.sin(i), 0.012, 0.005, "n")).join("") + disc(X, Y + 0.14, Z, 0.05, 0.05, "n") + thin(line([X - 0.03, Y + 0.12, Z - 0.045], [X - 0.032, Y + 0.04, Z - 0.045]));
  }
  function menuCard(X, Y, Z) {
    const q = screenQuad(X - 0.06, X + 0.06, Y, Z, 0.18, 0.04);
    return poly(q) + line([X - 0.04, Y, Z + 0.06], [X - 0.05, Y + 0.17, Z + 0.04]) + clipped(q, scribbleLines(bbox(q), 7, 0.25));
  }
  function earbuds(X, Y, Z) {
    return shadow(X + 0.01, Y, Z + 0.01, 0.035, 0.025) + frustum(X, Z, Y, Y + 0.025, 0.03, 0.03) + thin(frontArc(X, Y + 0.018, Z, 0.03));
  }
  function frenchPress(X, Y, Z) {
    return shadow(X + 0.02, Y, Z + 0.02, 0.07, 0.05) + `<path class="n" style="--w:${wAt(Z - CAMZ)}" d="M${xy(pt([X + 0.05, Y + 0.17, Z]))}C${xy(pt([X + 0.1, Y + 0.17, Z]))} ${xy(pt([X + 0.1, Y + 0.05, Z]))} ${xy(pt([X + 0.05, Y + 0.05, Z]))}"/>` +
      frustum(X, Z, Y, Y + 0.18, 0.05, 0.05, "f0", null) + hatch(ell(X, Y + 0.07, Z, 0.05, 0.05, Math.PI, TAU, 10).concat(ell(X, Y + 0.005, Z, 0.05, 0.05, Math.PI, TAU, 10).reverse()), { gap: 2.8, cover: 1 }) +
      thin(frontArc(X, Y + 0.07, Z, 0.05)) + frustum(X, Z, Y + 0.18, Y + 0.2, 0.053, 0.05, "h1") + line([X, Y + 0.2, Z], [X, Y + 0.25, Z]) + disc(X, Y + 0.25, Z, 0.012, 0.012);
  }
  function coffeeBag(X, Y, Z) {
    return shadow(X + 0.02, Y, Z + 0.02, 0.07, 0.04) + box(X - 0.055, X + 0.055, Y, Y + 0.17, Z - 0.03, Z + 0.03) + box(X - 0.055, X + 0.055, Y + 0.17, Y + 0.2, Z - 0.012, Z + 0.012, "f0", "f0") +
      softRect(X - 0.035, X + 0.035, Y + 0.05, Y + 0.12, Z - 0.031, 0.01) + at2d(X, Y + 0.085, Z - 0.031, (x, y, k) => thin(`<path class="n" d="M${r1(x)} ${r1(y - 0.02 * k)}c${r1(0.016 * k)} 0 ${r1(0.016 * k)} ${r1(0.04 * k)} 0 ${r1(0.04 * k)}c${r1(-0.016 * k)} 0 ${r1(-0.016 * k)} ${r1(-0.04 * k)} 0 ${r1(-0.04 * k)}c${r1(-0.004 * k)} ${r1(0.014 * k)} ${r1(0.004 * k)} ${r1(0.026 * k)} 0 ${r1(0.04 * k)}"/>`));
  }
  function mixingBowl(X, Y, Z) {
    return bowl(X, Y, Z, 0.13, 0.085, "") + at2d(X + 0.03, Y + 0.075, Z, (x, y, k) => `<path class="n" d="M${r1(x)} ${r1(y)}l${r1(0.07 * k)} ${r1(-0.15 * k)}"/><path class="n" d="M${r1(x + 0.07 * k)} ${r1(y - 0.15 * k)}l${r1(0.03 * k)} ${r1(-0.07 * k)}" style="--w:${(+wAt(Z - CAMZ) * 2).toFixed(2)}"/>` +
      thin(`<path class="n" d="${[-0.022, -0.008, 0.008, 0.022].map((dx) => `M${r1(x + 0.065 * k)} ${r1(y - 0.14 * k)}C${r1(x + (0.04 + dx) * k)} ${r1(y - 0.06 * k)} ${r1(x + (dx - 0.01) * k)} ${r1(y + 0.01 * k)} ${r1(x)} ${r1(y + 0.01 * k)}`).join("")}"/>`));
  }
  function rollingPin(X, Y, Z) {
    const r = 0.028, L = 0.15, y = Y + r;
    return shadow(X, Y, Z + 0.02, 0.24, 0.04) + line([X - L - 0.07, y, Z], [X - L, y, Z]) + line([X + L, y, Z], [X + L + 0.07, y, Z]) + vdiscX(X - L - 0.07, y, Z, 0.012) + vdiscX(X + L + 0.07, y, Z, 0.012) +
      poly([[X - L, y + r, Z], [X + L, y + r, Z], [X + L, y - r, Z], [X - L, y - r, Z]]) + vdiscX(X - L, y, Z, r) + vdiscX(X + L, y, Z, r);
  }
  function eggs(X, Y, Z) {
    let s = box(X - 0.08, X + 0.08, Y, Y + 0.04, Z - 0.05, Z + 0.05);
    for (const [u, v] of [[-0.05, 0.025], [0, 0.025], [0.05, 0.025], [-0.05, -0.022], [0.05, -0.022]]) s += at2d(X + u, Y + 0.04, Z + v, (x, y, k) => `<ellipse class="f0" cx="${r1(x)}" cy="${r1(y - 0.02 * k)}" rx="${r1(0.017 * k)}" ry="${r1(0.023 * k)}"/><ellipse class="n" cx="${r1(x)}" cy="${r1(y - 0.02 * k)}" rx="${r1(0.017 * k)}" ry="${r1(0.023 * k)}"/>`);
    return s;
  }
  function flourBag(X, Y, Z) {
    return shadow(X + 0.03, Y, Z + 0.02, 0.09, 0.05) + box(X - 0.07, X + 0.07, Y, Y + 0.2, Z - 0.045, Z + 0.045) + poly([[X - 0.07, Y + 0.2, Z - 0.045], [X - 0.05, Y + 0.24, Z - 0.02], [X + 0.05, Y + 0.24, Z - 0.02], [X + 0.07, Y + 0.2, Z - 0.045]]) +
      softRect(X - 0.05, X + 0.05, Y + 0.06, Y + 0.14, Z - 0.046, 0.01) + thin(line([X - 0.035, Y + 0.115, Z - 0.047], [X + 0.035, Y + 0.115, Z - 0.047]) + line([X - 0.025, Y + 0.09, Z - 0.047], [X + 0.025, Y + 0.09, Z - 0.047]));
  }
  function cutlery(X, Y, Z, ang = Math.PI / 2) {
    const f = flat(X, Z, 0.17, 0.012, ang, Y, 0.002);
    return f.s + thin(range(-0.004, 0.004, 0.004).map((v) => line(f.at(0.05, v), f.at(0.085, v))).join(""));
  }
  function knife(X, Y, Z, ang = Math.PI / 2) {
    const f = flat(X, Z, 0.19, 0.014, ang, Y, 0.002);
    return f.s + line(f.at(-0.005, -0.007), f.at(-0.005, 0.007));
  }
  function food(X, Y, Z, kind = "pasta") {
    if (kind === "toast") return [[-0.03, 0.01, 0.2], [0.035, -0.015, -0.25]].map(([u, v, a]) => { const t = flat(X + u, Z + v, 0.08, 0.085, a, Y, 0.012); return t.s + thin(poly([t.at(-0.032, -0.034), t.at(0.032, -0.034), t.at(0.032, 0.03), t.at(-0.032, 0.03)], "n")); }).join("");
    if (kind === "cookies") return Array.from({ length: 5 }, (_, i) => frustum(X + 0.05 * Math.cos(i * 1.25), Z + 0.035 * Math.sin(i * 1.25), Y, Y + 0.01, 0.026, 0.026) + disc(X + 0.05 * Math.cos(i * 1.25) + 0.008, Y + 0.011, Z + 0.035 * Math.sin(i * 1.25), 0.005, 0.004, "h2")).join("");
    if (kind === "sandwich") { const t = flat(X, Z, 0.11, 0.09, 0.3, Y, 0.035); return t.s + line(t.at(-0.055, -0.045), t.at(0.055, 0.045)) + thin(line(t.at(-0.055, -0.045), t.at(0.055, -0.045))); }
    // pasta: a swirl of noodles with a leaf on top
    return at2d(X, Y + 0.012, Z, (x, y, k) => `<path class="f0" d="M${r1(x - 0.07 * k)} ${r1(y)}q${r1(0.07 * k)} ${r1(-0.06 * k)} ${r1(0.14 * k)} 0q${r1(-0.07 * k)} ${r1(0.025 * k)} ${r1(-0.14 * k)} 0z"/><path class="n" d="M${r1(x - 0.07 * k)} ${r1(y)}q${r1(0.07 * k)} ${r1(-0.06 * k)} ${r1(0.14 * k)} 0q${r1(-0.07 * k)} ${r1(0.025 * k)} ${r1(-0.14 * k)} 0z"/>` +
      thin(`<path class="n" d="${range(0, 5, 1).map((i) => `M${r1(x + (-0.05 + i * 0.02) * k)} ${r1(y + 0.004 * k)}c${r1(0.01 * k)} ${r1(-0.03 * k)} ${r1(0.03 * k)} ${r1(-0.02 * k)} ${r1(0.02 * k)} ${r1(-0.035 * k)}`).join("")}"/>`) +
      `<path class="n" d="M${r1(x + 0.01 * k)} ${r1(y - 0.03 * k)}q${r1(0.02 * k)} ${r1(-0.02 * k)} ${r1(0.035 * k)} ${r1(-0.005 * k)}q${r1(-0.02 * k)} ${r1(0.01 * k)} ${r1(-0.035 * k)} ${r1(0.005 * k)}z"/>`);
  }
  function lunchBox(X, Y, Z) {
    return shadow(X + 0.02, Y, Z + 0.02, 0.13, 0.09) + box(X - 0.11, X + 0.11, Y, Y + 0.06, Z - 0.075, Z + 0.075) + flatRect(X - 0.1, X + 0.1, Z - 0.065, Z + 0.065, Y + 0.06, "n") + line([X, Y + 0.06, Z - 0.065], [X, Y + 0.06, Z + 0.065]) + food(X - 0.05, Y + 0.04, Z, "sandwich") + bowl(X + 0.05, Y + 0.035, Z + 0.005, 0.035, 0.02, "leaves");
  }
  function boardGame(X, Y, Z) {
    const b = flat(X, Z, 0.36, 0.36, 0.0, Y, 0.012);
    let s = shadow(X + 0.03, Y, Z + 0.03, 0.22, 0.2) + b.s, g = "";
    for (let i = 0; i <= 6; i++) { const u = -0.15 + i * 0.05; g += line(b.at(u, -0.15), b.at(u, 0.15)) + line(b.at(-0.15, u), b.at(0.15, u)); }
    s += thin(g);
    for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) if ((i + j) % 2) s += hatch([b.at(-0.15 + i * 0.05, -0.15 + j * 0.05), b.at(-0.1 + i * 0.05, -0.15 + j * 0.05), b.at(-0.1 + i * 0.05, -0.1 + j * 0.05), b.at(-0.15 + i * 0.05, -0.1 + j * 0.05)], { gap: 3, cover: 1 });
    for (const [i, j, dark] of [[0, 0, 1], [2, 0, 1], [1, 1, 1], [4, 4, 0], [3, 5, 0], [5, 5, 0], [2, 2, 1]]) { const [x, , z] = b.at(-0.125 + i * 0.05, -0.125 + j * 0.05); s += frustum(x, z, Y + 0.012, Y + 0.022, 0.018, 0.018, "f0", dark ? "h2" : "f0"); }
    return s;
  }
  function dice(X, Y, Z) {
    return box(X - 0.012, X + 0.012, Y, Y + 0.024, Z - 0.012, Z + 0.012) + disc(X, Y + 0.0245, Z, 0.003, 0.003, "h2") + box(X + 0.03, X + 0.054, Y, Y + 0.024, Z + 0.01, Z + 0.034) + disc(X + 0.036, Y + 0.0245, Z + 0.016, 0.003, 0.003, "h2") + disc(X + 0.048, Y + 0.0245, Z + 0.028, 0.003, 0.003, "h2");
  }
  function cards(X, Y, Z) {
    return [-0.3, 0, 0.3].map((a, i) => { const c = flat(X + i * 0.012, Z, 0.063, 0.088, a, Y + i * 0.001, 0.001); return c.s + thin(poly([c.at(-0.024, -0.036), c.at(0.024, -0.036), c.at(0.024, 0.036), c.at(-0.024, 0.036)], "n")); }).join("");
  }
  function yogaMat(X, Y, Z) {
    const w = 0.31, z0 = Z - 0.75, z1 = Z + 0.6, r = 0.06;
    return hatch([[X - w - 0.05, 0, z0], [X + w + 0.08, 0, z0], [X + w + 0.08, 0, z1], [X - w - 0.05, 0, z1]], { gap: 6, cover: 0.2, from: 1 }) +
      flatRect(X - w, X + w, z0, z1, Y + 0.004) + thin(flatRect(X - w + 0.02, X + w - 0.02, z0 + 0.02, z1 - 0.02, Y + 0.005, "n")) +
      poly([[X - w, Y + 2 * r, z1 + r], [X + w, Y + 2 * r, z1 + r], [X + w, Y, z1 + r], [X - w, Y, z1 + r]]) + box(X - w, X + w, Y, Y + 2 * r, z1, z1 + r * 2, "f0") + vdiscX(X + w, Y + r, z1 + r, r) + thin(vdiscX(X + w + 0.001, Y + r, z1 + r, r * 0.6, "n") + vdiscX(X + w + 0.002, Y + r, z1 + r, r * 0.25, "n"));
  }

  // Objects on the near surface for each kind of task, given the surface origin (X, Y, Z).
  const PROPS = {
    work: (X, Y, Z, e) => notebook(X - 0.31, Y, Z + 0.02, -0.18) + pen(X - 0.3, Y + 0.012, Z - 0.03, 1.2) + phone(X + 0.28, Y, Z + 0.16, 0.25) + laptop(X, Y, Z + 0.01, "text") + (e === "Coffee shop" ? cupSaucer(X + 0.29, Y, Z - 0.07) : mug(X + 0.29, Y, Z - 0.06)),
    workTogether: (X, Y, Z) => laptopBack(X + 0.02, Y, Z + 0.42) + cupSaucer(X - 0.24, Y, Z + 0.3, false) + laptop(X - 0.02, Y, Z - 0.02, "text") + cupSaucer(X + 0.3, Y, Z - 0.05) + phone(X - 0.3, Y, Z - 0.05, 0.3),
    call: (X, Y, Z, e) => notebook(X - 0.32, Y, Z - 0.02, 0.12) + pen(X - 0.29, Y + 0.012, Z - 0.05, -1.0) + laptop(X, Y, Z + 0.02, "call") + earbuds(X + 0.24, Y, Z - 0.13) + (e === "Coffee shop" ? cupSaucer(X + 0.31, Y, Z + 0.07) : mug(X + 0.3, Y, Z + 0.06)),
    discussion: (X, Y, Z) => mug(X + 0.05, Y, Z + 0.32) + notebook(X - 0.02, Y, Z + 0.3, 3.0) + notebook(X - 0.12, Y, Z - 0.05, -0.1) + pen(X - 0.02, Y + 0.012, Z - 0.08, 1.3) + mug(X + 0.26, Y, Z - 0.02) + phone(X - 0.34, Y, Z + 0.08, 0.2),
    readBook: (X, Y, Z, e) => bookStack(X + 0.33, Y, Z + 0.17) + (e === "Coffee shop" ? cupSaucer(X - 0.33, Y, Z + 0.12) : mug(X - 0.33, Y, Z + 0.14)) + openBook(X - 0.02, Y, Z - 0.02) + pen(X + 0.29, Y, Z - 0.12, 0.35, 0.15),
    study: (X, Y, Z, e) => openBook(X - 0.12, Y, Z + 0.06) + notebook(X + 0.22, Y, Z - 0.04, 0.15) + pen(X + 0.12, Y + 0.002, Z - 0.13, 0.4, 0.13, 0.016) + (e === "Coffee shop" ? cupSaucer(X + 0.33, Y, Z + 0.2) : mug(X + 0.33, Y, Z + 0.2)),
    readPaper: (X, Y, Z, e) => papers(X + 0.24, Y, Z + 0.12, 0.2) + papers(X - 0.05, Y, Z - 0.02, -0.08) + pen(X + 0.18, Y + 0.006, Z - 0.13, 0.5, 0.12, 0.016) + (e === "Coffee shop" ? cupSaucer(X - 0.34, Y, Z + 0.08) : mug(X - 0.33, Y, Z + 0.08)),
    phoneCafe: (X, Y, Z) => cupSaucer(X + 0.22, Y, Z + 0.12) + plate(X - 0.22, Y, Z + 0.14, 0.09) + croissant(X - 0.22, Y + 0.014, Z + 0.13) + phone(X - 0.02, Y, Z - 0.1, -0.15, "text"),
    shopping: (X, Y, Z, e) => (e === "Coffee shop" ? cupSaucer(X + 0.26, Y, Z + 0.12) : mug(X + 0.26, Y, Z + 0.12)) + card(X - 0.18, Y, Z - 0.02, 0.3) + phone(X + 0.02, Y, Z - 0.08, -0.12, "shop"),
    phoneDesk: (X, Y, Z) => laptop(X - 0.05, Y, Z + 0.12, "text") + mug(X + 0.3, Y, Z + 0.02) + phone(X + 0.08, Y, Z - 0.16, -0.25, "text"),
    pcGames: (X, Y, Z) => laptop(X - 0.04, Y, Z + 0.04, "game") + mouse(X + 0.24, Y, Z - 0.03) + can(X - 0.32, Y, Z + 0.1),
    watchCafe: (X, Y, Z) => tablet(X - 0.02, Y, Z + 0.1, "play") + earbuds(X - 0.2, Y, Z - 0.1) + cupSaucer(X + 0.27, Y, Z + 0.02),
    order: (X, Y, Z) => tipJar(X + 0.32, Y, Z + 0.15) + cardReader(X - 0.02, Y, Z + 0.1) + receipt(X - 0.22, Y, Z - 0.05, 0.25) + takeawayCup(X + 0.17, Y, Z - 0.02) + phone(X + 0.0, Y, Z - 0.16, -0.2),
    lunchHunt: (X, Y, Z) => tipJar(X + 0.33, Y, Z + 0.15) + menuCard(X - 0.18, Y, Z + 0.12) + phone(X + 0.06, Y, Z - 0.1, -0.15, "map") + card(X - 0.2, Y, Z - 0.12, -0.3),
    coffeeAtTable: (X, Y, Z) => cupSaucer(X - 0.02, Y, Z - 0.05) + glass(X - 0.2, Y, Z + 0.14, 0.09) + plate(X + 0.22, Y, Z + 0.12, 0.08) + croissant(X + 0.22, Y + 0.014, Z + 0.11) + phone(X - 0.3, Y, Z - 0.1, 0.25) + flat(X + 0.13, Z - 0.13, 0.025, 0.07, 0.6, Y, 0.006).s,
    whereNext: (X, Y, Z) => takeawayCup(X + 0.25, Y, Z + 0.1) + keys(X - 0.27, Y, Z - 0.05) + phone(X - 0.02, Y, Z - 0.06, -0.12, "map"),
    leaving: (X, Y, Z) => takeawayCup(X - 0.05, Y, Z + 0.04) + keys(X + 0.2, Y, Z - 0.1) + phone(X - 0.26, Y, Z - 0.05, 0.3) + cupSaucer(X + 0.25, Y, Z + 0.18, false),
    friendsCafe: (X, Y, Z) => cupSaucer(X + 0.06, Y, Z + 0.26) + vase(X - 0.22, Y, Z + 0.2) + plate(X + 0.22, Y, Z - 0.02, 0.1) + croissant(X + 0.22, Y + 0.014, Z - 0.03) + cupSaucer(X - 0.1, Y, Z - 0.1),
    cooking: (X, Y, Z) => pot(X + 0.3, Y, Z + 0.16) + bowl(X - 0.33, Y, Z + 0.12, 0.09, 0.06, "leaves") + frustum(X + 0.1, Z + 0.24, Y, Y + 0.07, 0.018, 0.018, "f0", "h1") + board(X - 0.03, Y, Z - 0.06),
    baking: (X, Y, Z) => flourBag(X + 0.32, Y, Z + 0.18) + mixingBowl(X - 0.05, Y, Z + 0.08) + eggs(X - 0.34, Y, Z + 0.12) + rollingPin(X + 0.05, Y, Z - 0.14),
    coffeeMaking: (X, Y, Z) => coffeeBag(X + 0.3, Y, Z + 0.16) + frenchPress(X - 0.04, Y, Z + 0.1) + mug(X - 0.3, Y, Z + 0.02) + mug(X + 0.18, Y, Z - 0.1),
    eating: (X, Y, Z) => plate(X, Y, Z - 0.02, 0.13) + food(X, Y + 0.014, Z - 0.03) + cutlery(X - 0.18, Y, Z - 0.02) + knife(X + 0.18, Y, Z - 0.02) + glass(X + 0.24, Y, Z + 0.17) + flat(X - 0.26, Z + 0.1, 0.12, 0.12, 0.2, Y, 0.004).s,
    dining: (X, Y, Z) => plate(X, Y, Z + 0.32, 0.12) + food(X, Y + 0.014, Z + 0.31) + wineGlass(X + 0.2, Y, Z + 0.3) + plate(X, Y, Z - 0.1, 0.13) + food(X, Y + 0.014, Z - 0.11) + cutlery(X - 0.18, Y, Z - 0.1) + knife(X + 0.18, Y, Z - 0.1) + wineGlass(X + 0.27, Y, Z + 0.06) + glass(X - 0.28, Y, Z + 0.12, 0.13, 0.75),
    breakfast: (X, Y, Z) => plate(X - 0.02, Y, Z - 0.03, 0.11) + food(X - 0.02, Y + 0.014, Z - 0.03, "toast") + mug(X + 0.26, Y, Z + 0.05) + glass(X - 0.24, Y, Z + 0.16, 0.12, 0.7) + keys(X + 0.2, Y, Z - 0.16) + phone(X - 0.3, Y, Z - 0.1, 0.3),
    checklist: (X, Y, Z) => notebook(X - 0.04, Y, Z - 0.03, -0.1, true) + pen(X + 0.08, Y + 0.012, Z - 0.02, 1.4) + mug(X + 0.28, Y, Z + 0.12) + phone(X - 0.3, Y, Z - 0.06, 0.2, "text"),
    dinnerPlan: (X, Y, Z) => notebook(X - 0.06, Y, Z - 0.03, -0.1, true) + pen(X + 0.07, Y + 0.012, Z - 0.02, 1.4) + phone(X + 0.24, Y, Z - 0.08, -0.2, "shop") + mug(X - 0.32, Y, Z + 0.12) + laptop(X + 0.05, Y, Z + 0.3, "text"),
    errands: (X, Y, Z) => paperBag(X + 0.3, Y, Z + 0.16) + mug(X - 0.32, Y, Z + 0.12) + notebook(X - 0.06, Y, Z - 0.04, -0.1, true) + pen(X + 0.07, Y + 0.012, Z - 0.02, 1.4) + keys(X + 0.2, Y, Z - 0.12) + phone(X - 0.3, Y, Z - 0.1, 0.2),
    lunchDesk: (X, Y, Z) => laptop(X - 0.12, Y, Z + 0.42, "text") + lunchBox(X - 0.03, Y, Z - 0.08) + cutlery(X + 0.15, Y, Z - 0.04) + can(X + 0.28, Y, Z + 0.06) + flat(X - 0.28, Z + 0.02, 0.12, 0.12, -0.2, Y, 0.004).s,
    watching: (X, Y, Z) => mug(X - 0.28, Y, Z + 0.06) + bowl(X + 0.2, Y, Z + 0.08, 0.11, 0.065, "popcorn") + remote(X - 0.06, Y, Z - 0.12),
    games: (X, Y, Z) => bowl(X + 0.25, Y, Z + 0.1, 0.1, 0.06, "chips") + can(X - 0.3, Y, Z + 0.08) + gamepad(X - 0.02, Y, Z - 0.08),
    phoneSofa: (X, Y, Z) => mug(X - 0.26, Y, Z + 0.06) + remote(X + 0.24, Y, Z + 0.1) + phone(X, Y, Z - 0.1, -0.15, "play"),
    friendsHome: (X, Y, Z) => glass(X - 0.22, Y, Z + 0.22, 0.12, 0.65) + wineGlass(X + 0.08, Y, Z + 0.3) + bowl(X + 0.02, Y, Z + 0.04, 0.11, 0.06, "chips") + glass(X + 0.27, Y, Z - 0.02, 0.12, 0.5) + glass(X - 0.3, Y, Z - 0.06, 0.1, 0.7),
    movieNight: (X, Y, Z) => bowl(X, Y, Z + 0.06, 0.12, 0.07, "popcorn") + glass(X - 0.27, Y, Z + 0.14, 0.13, 0.7) + can(X + 0.28, Y, Z + 0.16) + remote(X + 0.2, Y, Z - 0.14),
    boardGame: (X, Y, Z) => boardGame(X, Y, Z + 0.04) + dice(X - 0.3, Y, Z - 0.12) + cards(X + 0.3, Y, Z - 0.05) + glass(X + 0.3, Y, Z + 0.24, 0.12, 0.6),
    snacksDesk: (X, Y, Z) => mug(X + 0.08, Y, Z + 0.3) + plate(X - 0.05, Y, Z - 0.02, 0.1) + food(X - 0.05, Y + 0.014, Z - 0.02, "cookies") + mug(X + 0.26, Y, Z - 0.04) + phone(X - 0.3, Y, Z + 0.05, 0.2),
    workout: (X, Y, Z) => yogaMat(X, Y, Z) + dumbbell(X + 0.62, Y, Z - 0.35) + dumbbell(X + 0.62, Y, Z - 0.05) + bottle(X - 0.55, Y, Z + 0.25) + towel(X - 0.6, Y, Z - 0.25) + phone(X - 0.45, Y, Z - 0.6, 0.3, "play"),
  };

  // Environment -> view and props, per raw MineXR task label (lower-case), with a per-category default.
  const SCENE = {
    "Coffee shop": {
      byTask: {
        buyingadrink: ["counter", "order"], lookingforlunch: ["counter", "lunchHunt"], drinkingcoffee: ["seat", "coffeeAtTable"],
        remotemeeting: ["seat", "call"], reading: ["seat", "readBook"], studying: ["seat", "study"], readingpaper: ["seat", "readPaper"], readpaper: ["seat", "readPaper"],
        scrollingonphone: ["seat", "phoneCafe"], browsing: ["seat", "phoneCafe"], browsinginternet: ["seat", "work"], shopping: ["seat", "shopping"], watchingtv: ["seat", "watchCafe"],
        wheretogonext: ["seat", "whereNext"], leaving: ["seat", "leaving"], workingwithfriend: ["seat", "workTogether"], workingwithfriends: ["seat", "workTogether"],
      },
      byCat: { Work: "work", Meetings: "call", "Reading & study": "readBook", "Cooking & food": "coffeeAtTable", Socializing: "friendsCafe", "Relaxing & media": "phoneCafe", "Routines & errands": "whereNext", Workout: "leaving" },
    },
    Kitchen: {
      byTask: { bakingwithfriends: ["seat", "baking"], makingcoffee: ["seat", "coffeeMaking"], coffeemaking: ["seat", "coffeeMaking"], eating: ["seat", "eating"], morningroutine: ["seat", "breakfast"], morning: ["seat", "breakfast"], figuringoutnexttask: ["seat", "checklist"] },
      byCat: { "Cooking & food": "cooking", "Routines & errands": "breakfast", Work: "checklist", Meetings: "call", "Reading & study": "readBook", Socializing: "friendsHome", "Relaxing & media": "phoneSofa", Workout: "breakfast" },
    },
    "Living room": {
      byTask: {
        dining: ["seat", "dining"], studying: ["seat", "study"], playgames: ["seat", "games"], playiphone: ["seat", "phoneSofa"], dailyroutine: ["seat", "checklist"],
        watchingmoviewithfriends: ["seat", "movieNight"], playingboardgame: ["seat", "boardGame"], workingout: ["floor", "workout"], workout: ["floor", "workout"],
      },
      byCat: { "Cooking & food": "dining", "Reading & study": "readBook", "Relaxing & media": "watching", "Routines & errands": "checklist", Socializing: "friendsHome", Work: "work", Workout: "workout", Meetings: "call" },
    },
    Office: {
      byTask: {
        planningfordinner: ["seat", "dinnerPlan"], eating: ["seat", "lunchDesk"], discussion: ["seat", "discussion"], inpersonmeeting: ["seat", "discussion"],
        readingpaper: ["seat", "readPaper"], playingpcgames: ["seat", "pcGames"], shopping: ["seat", "shopping"], scrollingonphone: ["seat", "phoneDesk"], browsing: ["seat", "phoneDesk"],
      },
      byCat: { Work: "work", Meetings: "call", "Reading & study": "readPaper", "Cooking & food": "lunchDesk", Socializing: "snacksDesk", "Relaxing & media": "phoneDesk", "Routines & errands": "checklist", Workout: "checklist" },
    },
  };

  // ---------- rooms ----------
  const ROOMS = {
    Office: {
      views: { seat: { cam: [0, 0, 1.16, 290], table: [0, 0.74, 1.2] } },
      draw() {
        const W = 3.2, B = 6.5;
        let s = shell({ W, H: 2.9, B, floor: "planks" });
        // glazed back wall over the city, with a low sill
        s += box(-W, W, 0, 0.82, B - 0.25, B - 0.01, "f0", "f0") + thin(range(-W + 0.4, W, 0.8).map((x) => line([x, 0.05, B - 0.25], [x, 0.78, B - 0.25])).join(""));
        s += windowAt(-3.0, 3.0, 0.86, 2.75, B - 0.01, null, (bb) => city2d(bb[0], bb[2], bb[3], (bb[3] - bb[1]) * 0.75), { cols: 6, rows: 2 });
        s += pendantCone(-1.6, 5.2, 2.0) + pendantCone(0, 5.2, 2.0) + pendantCone(1.6, 5.2, 2.0);
        // door and whiteboard on the left wall; shelving with books and binders on the right
        s += sideRect(-W, 4.7, 5.7, 0, 2.15) + thin(sideRect(-W, 4.78, 5.62, 0.04, 2.1, "n")) + line([-W, 1.0, 5.5], [-W, 1.0, 5.35]);
        s += sideRect(-W, 2.0, 3.9, 0.95, 1.95) + thin(sideRect(-W, 2.05, 3.85, 1.0, 1.9, "n") + line([-W, 1.75, 2.3], [-W, 1.75, 3.0]) + line([-W, 1.62, 2.3], [-W, 1.62, 3.3]) + line([-W, 1.49, 2.3], [-W, 1.49, 2.8]) + curve([[-W, 1.32, 3.0], [-W, 1.5, 3.25], [-W, 1.25, 3.45], [-W, 1.45, 3.65]]) + sideRect(-W, 3.3, 3.75, 1.2, 1.5, "n")) + box(-W, -W + 0.07, 0.92, 0.95, 2.0, 3.9);
        s += box(2.75, W, 0, 1.9, 3.3, 5.0, "f0", "f0") + hatch([[2.75, 0, 3.3], [2.75, 1.9, 3.3], [2.75, 1.9, 5.0], [2.75, 0, 5.0]], { cover: 0.3, gap: 7 });
        for (let y = 0.38; y < 1.9; y += 0.38) s += line([2.75, y, 3.3], [2.75, y, 5.0]);
        s += thin(Array.from({ length: 4 }, (_, row) => Array.from({ length: 12 }, (_, i) => { const z = 3.4 + i * 0.12, y0 = 0.4 + row * 0.38, h = 0.2 + rnd() * 0.12; return i % 5 === 4 ? "" : sideRect(2.75, z, z + 0.08, y0, y0 + h, "n"); }).join("")).join(""));
        s += plant(2.5, 5.9, 1.1) + plant(-2.6, 6.0, 0.9);
        // a bench desk across the room, monitors, chairs and a colleague's things
        s += officeChair(-1.0, 4.85, 1) + officeChair(0.9, 4.85, 1);
        s += shadow(-0.1, 0.001, 4.05, 1.9, 0.4) + box(-2.0, 1.8, 0.71, 0.75, 3.7, 4.4) + line([-1.95, 0, 3.75], [-1.95, 0.71, 3.75]) + line([1.75, 0, 3.75], [1.75, 0.71, 3.75]) + line([-1.95, 0, 4.35], [-1.95, 0.71, 4.35]) + line([1.75, 0, 4.35], [1.75, 0.71, 4.35]);
        for (const x of [-1.0, 0.85]) s += line([x, 0.75, 4.22], [x, 0.93, 4.22]) + box(x - 0.12, x + 0.12, 0.75, 0.76, 4.15, 4.3) + box(x - 0.34, x + 0.34, 0.92, 1.3, 4.17, 4.22, "f0", "h1");
        s += mug(-0.45, 0.75, 3.85) + plant(1.45, 3.95, 0.35, 0.75);
        s += officeChair(-0.4, 3.3, -1) + officeChair(1.3, 3.35, -1);
        // my desk, with a lamp and a pen pot
        s += box(-1.1, 1.1, 0.7, 0.74, -0.2, 1.75) + thin(line([-1.05, 0.741, 1.7], [1.05, 0.741, 1.7]));
        s += shadow(-0.75, 0.741, 1.3, 0.12, 0.08) + frustum(-0.8, 1.28, 0.74, 0.755, 0.075, 0.07) + line([-0.8, 0.755, 1.28], [-0.86, 1.02, 1.3], [-0.68, 1.12, 1.3]) + thin(line([-0.79, 0.755, 1.28], [-0.85, 1.02, 1.3], [-0.67, 1.115, 1.3])) + frustum(-0.66, 1.3, 1.0, 1.1, 0.075, 0.025, "h1");
        s += frustum(0.78, 1.25, 0.74, 0.84, 0.04, 0.04) + line([0.77, 0.84, 1.25], [0.75, 0.94, 1.27]) + line([0.79, 0.84, 1.25], [0.82, 0.93, 1.24]) + line([0.8, 0.84, 1.26], [0.79, 0.92, 1.28]);
        return s;
      },
    },
    "Coffee shop": {
      views: { seat: { cam: [0, 0, 1.17, 290], table: [0, 0.75, 1.22] }, counter: { cam: [-0.3, 3.4, 1.52, 290], table: [-0.1, 1.1, 4.82] } },
      draw(view) {
        const W = 3, B = 6;
        let s = shell({ W, H: 3, B, floor: "planks" });
        // left wall: big window onto the street, with a ledge
        s += windowAt(1.2, 5.6, 0.75, 2.7, null, -W, streetView(3), { cols: 4, rows: 2 });
        s += box(-W, -W + 0.22, 0.7, 0.75, 1.2, 5.6);
        // menu boards, wall clock, shelves with cups and jars
        s += backRect(-2.3, -1.15, 1.95, 2.65, B - 0.01) + backRect(-1.05, 0.1, 1.95, 2.65, B - 0.01);
        s += scribbleLines(bbox([[-2.25, 1.98, B], [-1.2, 2.5, B]]), 7) + scribbleLines(bbox([[-1.0, 1.98, B], [0.05, 2.5, B]]), 7) + thin(line([-2.0, 2.56, B], [-1.45, 2.56, B]) + line([-0.75, 2.56, B], [-0.25, 2.56, B]));
        s += at2d(0.75, 2.35, B - 0.01, (x, y, k) => `<circle class="f0" cx="${r1(x)}" cy="${r1(y)}" r="${r1(0.2 * k)}"/><circle class="n" cx="${r1(x)}" cy="${r1(y)}" r="${r1(0.2 * k)}"/><path class="n" d="M${r1(x)} ${r1(y)}v${r1(-0.13 * k)}M${r1(x)} ${r1(y)}h${r1(0.09 * k)}"/>` + thin(`<path class="n" d="${range(0, 11, 1).map((i) => { const a = (i / 12) * TAU; return `M${r1(x + Math.cos(a) * 0.16 * k)} ${r1(y + Math.sin(a) * 0.16 * k)}L${r1(x + Math.cos(a) * 0.185 * k)} ${r1(y + Math.sin(a) * 0.185 * k)}`; }).join("")}"/>`));
        s += box(-2.5, 0.4, 1.6, 1.64, 5.75, B) + [-2.35, -2.15, -1.95, -1.6, -1.35, -1.1, -0.75, -0.5, -0.2, 0.15].map((x, i) => i % 3 === 2 ? frustum(x, 5.88, 1.64, 1.8, 0.05, 0.05, "f0", "h1") : frustum(x, 5.88, 1.64, 1.72, 0.035, 0.045)).join("");
        // back counter with the espresso machine, grinder and cups
        s += box(-2.6, 0.9, 0, 0.92, 5.6, B, "f0", "f0") + thin(range(-2.6, 0.9, 0.5).map((x) => backRect(x + 0.03, x + 0.47, 0.08, 0.84, 5.6, "n")).join("")) + box(-2.6, 0.9, 0.92, 0.95, 5.57, B);
        s += box(-1.25, -0.45, 0.95, 1.38, 5.62, 5.95) + thin(line([-1.25, 1.3, 5.62], [-0.45, 1.3, 5.62]) + backRect(-1.15, -0.9, 1.0, 1.06, 5.61, "n")) + [-1.05, -0.85, -0.65].map((x) => frustum(x, 5.57, 1.13, 1.2, 0.035, 0.04, "f0", "h1") + line([x, 1.16, 5.55], [x + 0.02, 1.15, 5.4])).join("") +
          [-1.1, -0.95, -0.8, -0.65].map((x) => frustum(x, 5.8, 1.38, 1.43, 0.03, 0.038)).join("") + line([-0.5, 1.2, 5.6], [-0.48, 1.08, 5.58]);
        s += box(-0.25, -0.05, 0.95, 1.25, 5.65, 5.85) + frustum(-0.15, 5.75, 1.25, 1.42, 0.04, 0.1, "f0", "h1") + frustum(-2.2, 5.75, 0.95, 1.12, 0.06, 0.06, "f0", "h1") + frustum(-1.95, 5.78, 0.95, 1.05, 0.04, 0.05) + frustum(0.3, 5.75, 0.95, 1.2, 0.08, 0.08) + frustum(0.5, 5.78, 0.95, 1.1, 0.05, 0.05, "f0", "h1");
        // service counter: board-clad front, worktop, pastry case, register
        s += box(-2.6, 0.9, 0, 1.05, 4.6, 5.15, "f0", "f0") + thin(range(-2.5, 0.85, 0.12).map((x) => line([x, 0.08, 4.6], [x, 0.98, 4.6])).join("")) + hatch([[-2.6, 0, 4.6], [0.9, 0, 4.6], [0.9, 1.05, 4.6], [-2.6, 1.05, 4.6]], { cover: 0.22, gap: 6, ang: -1.2 });
        s += box(-2.65, 0.95, 1.05, 1.1, 4.55, 5.2);
        s += pastryCase(-1.45, -0.62, 4.62, 5.05);
        s += box(0.35, 0.8, 1.1, 1.18, 4.8, 5.05) + poly(screenQuad(0.4, 0.75, 1.18, 4.9, 0.18, 0.06)) + thin(poly(screenQuad(0.42, 0.73, 1.2, 4.902, 0.14, 0.05), "n"));
        // right of the counter: a doorway, prints, a bench with cushions
        s += backRect(1.4, 2.5, 0, 2.2, B - 0.01) + thin(backRect(1.48, 2.42, 0, 2.12, B - 0.02, "n") + backRect(1.6, 2.3, 1.2, 2.0, B - 0.02, "n")) + line([1.6, 1.0, B - 0.03], [1.6, 1.15, B - 0.03]);
        s += framePic(W, 3.3, 4.0, 1.45, 2.05, 1) + framePic(W, 4.25, 4.75, 1.55, 2.1) + framePic(W, 4.25, 4.75, 1.05, 1.45, 1);
        s += box(2.5, W, 0.0, 0.45, 2.4, 5.0) + box(2.85, W, 0.45, 0.95, 2.4, 5.0, "f0", "f0") + [2.6, 3.2, 3.8, 4.4].map((z) => softRect(2.9, 2.95, 0.48, 0.85, z, 0.05)).join("") + thin(range(2.65, 4.8, 0.6).map((z) => line([2.5, 0.45, z], [2.85, 0.45, z])).join(""));
        s += pendantGlobe(-2.0, 4.25, 2.05) + pendantGlobe(-1.4, 4.25, 2.15) + pendantGlobe(-0.8, 4.25, 2.0) + pendantGlobe(-0.2, 4.25, 2.12) + pendantGlobe(0.4, 4.25, 2.02);
        s += plant(2.6, 5.5, 1.25) + plant(-2.6, 5.65, 0.9);
        // other tables
        s += bistroChair(-2.05, 3.85, 1) + roundTable(-2.1, 3.3, 0.75, 0.32) + cupSaucer(-2.15, 0.75, 3.25, false) + bistroChair(-2.1, 2.7, -1);
        s += bistroChair(1.75, 3.95, 1) + roundTable(1.75, 3.4, 0.75, 0.32) + takeawayCup(1.8, 0.75, 3.35) + bistroChair(2.25, 2.9, 1);
        if (view === "seat") {
          s += bistroChair(0, 2.05, 1);
          s += frustum(0, 1.25, 0.72, 0.75, 0.46, 0.46);
        }
        return s;
      },
    },
    Kitchen: {
      views: { seat: { cam: [0, 0, 1.34, 290], table: [0, 0.92, 1.2] } },
      draw() {
        const W = 2.4, B = 4.6;
        let s = shell({ W, H: 2.8, B, floor: "tiles" });
        // subway-tile splashback, window with a roman blind and plants on the sill
        s += thin(range(0.98, 1.56, 0.075).map((y, i) => line([-W, y, B - 0.01], [W, y, B - 0.01]) + range(-W + (i % 2) * 0.075, W, 0.15).map((x) => line([x, y, B - 0.01], [x, y + 0.075, B - 0.01])).join("")).join(""));
        s += backRect(-0.85, 0.85, 1.08, 2.32, B - 0.01) + windowAt(-0.75, 0.75, 1.15, 2.25, B - 0.02, null, streetView(2, false), { cols: 2 });
        s += box(-0.85, 0.85, 1.06, 1.1, 4.45, B);
        s += poly([[-0.8, 2.3, B - 0.05], [0.8, 2.3, B - 0.05], [0.8, 1.88, B - 0.05], [-0.8, 1.88, B - 0.05]]);
        s += thin([1.95, 2.03, 2.11, 2.19, 2.27].map((y) => curve([[-0.8, y, B - 0.06], [-0.4, y - 0.025, B - 0.06], [0, y, B - 0.06], [0.4, y - 0.025, B - 0.06], [0.8, y, B - 0.06]])).join("")) + hatch([[-0.8, 1.88, B - 0.06], [0.8, 1.88, B - 0.06], [0.8, 2.3, B - 0.06], [-0.8, 2.3, B - 0.06]], { cover: 0.3, gap: 5 });
        s += plant(-0.5, 4.5, 0.25, 1.1) + frustum(0.45, 4.5, 1.1, 1.2, 0.05, 0.06) + vase(0.2, 1.1, 4.52);
        // upper glass cabinets with crockery
        for (const [x0, x1] of [[-2.35, -1.15], [1.15, 2.35]]) {
          s += box(x0, x1, 1.65, 2.55, 4.25, B);
          const xm = (x0 + x1) / 2;
          s += backRect(x0 + 0.06, xm - 0.03, 1.71, 2.49, 4.25, "n") + backRect(xm + 0.03, x1 - 0.06, 1.71, 2.49, 4.25, "n") + box(x0 - 0.04, x1 + 0.04, 2.55, 2.62, 4.2, B);
          s += thin([1.96, 2.22].map((y) => line([x0 + 0.06, y, 4.25], [x1 - 0.06, y, 4.25])).join("") + range(x0 + 0.1, x1 - 0.1, 0.08).map((x, i) => (i % 4 === 3 ? "" : line([x, 1.73, 4.26], [x, 1.85 + (i % 2) * 0.03, 4.26]))).join("") + range(x0 + 0.12, x1 - 0.12, 0.12).map((x) => curve(ell(x, 0, 0, 0.05, 0.05, 0, TAU, 12).map(([xx, , zz]) => [xx, 2.08 + zz, 4.26]))).join("")) +
            line([xm - 0.06, 1.8, 4.24], [xm - 0.06, 1.95, 4.24]) + line([xm + 0.06, 1.8, 4.24], [xm + 0.06, 1.95, 4.24]) + hatch([[x0 + 0.06, 1.71, 4.25], [xm - 0.03, 1.71, 4.25], [xm - 0.03, 2.49, 4.25], [x0 + 0.06, 2.49, 4.25]], { cover: 0.3, gap: 6 });
        }
        // rail with utensils, worktop with sink, hob, kettle, bottles
        s += line([1.15, 1.45, B - 0.02], [2.05, 1.45, B - 0.02]) + [1.25, 1.4, 1.55, 1.7, 1.85, 1.98].map((x, i) => line([x, 1.45, B - 0.02], [x, 1.25 + (i % 2) * 0.06, B - 0.02]) + disc(x, 1.23 + (i % 2) * 0.06, B - 0.02, 0.022, 0.008, i % 3 ? "f0" : "h1")).join("");
        s += box(-W, W, 0.9, 0.94, 3.95, B);
        s += flatRect(-0.4, 0.4, 4.1, 4.42, 0.941, "h1", { cover: 0.5 }) + line([0, 0.94, 4.5], [0, 1.22, 4.5], [0, 1.26, 4.42], [0.0, 1.2, 4.32]) + line([0.1, 0.94, 4.5], [0.1, 1.02, 4.5]);
        s += box(1.05, 1.95, 0.94, 0.95, 4.05, 4.55) + [[1.28, 4.18], [1.72, 4.18], [1.28, 4.42], [1.72, 4.42]].map(([x, z]) => disc(x, 0.951, z, 0.12, 0.1, "n") + thin(disc(x, 0.951, z, 0.07, 0.06, "n"))).join("");
        s += frustum(-1.6, 4.3, 0.94, 1.1, 0.085, 0.065) + line([-1.68, 1.04, 4.3], [-1.76, 1.1, 4.3]) + curve([[-1.65, 1.1, 4.3], [-1.6, 1.16, 4.3], [-1.55, 1.1, 4.3]]);
        s += frustum(-2.05, 4.4, 0.94, 1.14, 0.03, 0.03) + frustum(-1.95, 4.45, 0.94, 1.18, 0.028, 0.018, "h1") + frustum(-2.15, 4.35, 0.94, 1.05, 0.05, 0.05, "f0", "h1");
        s += box(-W, W, 0.1, 0.9, 3.98, B);
        for (const x of range(-2.3, 1.9, 0.6)) s += backRect(x + 0.02, x + 0.56, 0.16, 0.6, 3.98, "n") + thin(backRect(x + 0.06, x + 0.52, 0.2, 0.56, 3.98, "n")) + backRect(x + 0.02, x + 0.56, 0.66, 0.84, 3.98, "n") + line([x + 0.22, 0.75, 3.97], [x + 0.36, 0.75, 3.97]) + line([x + 0.48, 0.3, 3.97], [x + 0.48, 0.46, 3.97]);
        s += hatch([[-W, 0.1, 3.98], [W, 0.1, 3.98], [W, 0.9, 3.98], [-W, 0.9, 3.98]], { cover: 0.15, gap: 6, from: 1, ang: -1.3 });
        // tall fridge on the right, prints on the left, a plant in the corner
        s += box(1.75, W, 0, 2.15, 2.5, 3.5, "f0", "f0") + line([1.75, 1.35, 2.5], [1.75, 1.35, 3.5]) + line([1.75, 1.0, 2.62], [1.75, 1.25, 2.62]) + line([1.75, 1.45, 2.62], [1.75, 1.75, 2.62]) + hatch([[1.75, 0, 2.5], [1.75, 2.15, 2.5], [1.75, 2.15, 3.5], [1.75, 0, 3.5]], { cover: 0.25, gap: 6 }) + box(1.75, W, 2.15, 2.8, 2.5, 3.5, "f0", "f0");
        s += framePic(-W, 2.6, 3.05, 1.55, 1.95) + framePic(-W, 2.6, 3.05, 1.05, 1.45, 1) + framePic(-W, 2.6, 3.05, 2.05, 2.45, 1);
        s += plant(-2.0, 3.6, 1.0);
        // the island I sit at, with a marble top
        s += box(-0.95, 0.95, 0.88, 0.92, -0.2, 1.75) + thin(curve([[-0.9, 0.921, 1.5], [-0.5, 0.921, 1.42], [-0.1, 0.921, 1.48]]) + curve([[0.4, 0.921, 1.52], [0.7, 0.921, 1.4], [0.92, 0.921, 1.45]]));
        return s;
      },
    },
    "Living room": {
      views: { seat: { cam: [0, 0, 0.84, 290], table: [0, 0.42, 1.2] }, floor: { cam: [0, -0.4, 1.75, 20], table: [0, 0, 2.55] } },
      draw(view) {
        const W = 3, B = 5.5;
        let s = shell({ W, H: 2.8, B, floor: "planks" });
        // left wall: balcony door with long curtains
        s += windowAt(2.1, 4.7, 0, 2.35, null, -W, streetView(2), { cols: 2, rows: 1 }) + thin(line([-W, 1.1, 2.1], [-W, 1.1, 4.7]));
        for (const [z0, z1] of [[1.65, 2.2], [4.6, 5.15]]) s += poly([[-W + 0.05, 0, z0], [-W + 0.05, 0, z1], [-W + 0.05, 2.55, z1], [-W + 0.05, 2.55, z0]]) + thin(range(z0 + 0.07, z1 - 0.03, 0.07).map((z, i) => curve([[-W + 0.05, 2.5, z], [-W + 0.05, 1.3, z + (i % 2 ? 0.01 : -0.01)], [-W + 0.05, 0.03, z + 0.02]])).join("")) + hatch([[-W + 0.05, 0, z0], [-W + 0.05, 0, z1], [-W + 0.05, 2.55, z1], [-W + 0.05, 2.55, z0]], { cover: 0.35, gap: 5, ang: -1.5 });
        s += line([-W + 0.06, 2.6, 1.55], [-W + 0.06, 2.6, 5.25]);
        // back wall: TV over a low cabinet, a shelf of books, prints, floor lamp, plant
        s += backRect(-0.9, 0.9, 0.95, 1.95, B - 0.01) + backRect(-0.85, 0.85, 0.99, 1.91, B - 0.02, "h1", { cover: 0.3, gap: 5 }) + thin(line([0.3, 1.25, B - 0.02], [0.55, 1.65, B - 0.02]) + line([0.42, 1.2, B - 0.02], [0.7, 1.62, B - 0.02]));
        s += shadow(0, 0.001, 5.25, 1.6, 0.2) + box(-1.5, 1.5, 0.12, 0.52, 5.05, B) + thin(line([-0.5, 0.14, 5.05], [-0.5, 0.5, 5.05]) + line([0.5, 0.14, 5.05], [0.5, 0.5, 5.05])) + line([-0.6, 0.32, 5.04], [-0.6, 0.38, 5.04]) + line([0.6, 0.32, 5.04], [0.6, 0.38, 5.04]) + line([-1.4, 0, 5.1], [-1.42, 0.12, 5.1]) + line([1.4, 0, 5.1], [1.42, 0.12, 5.1]);
        s += vase(1.1, 0.52, 5.25) + box(-1.25, -0.85, 0.52, 0.56, 5.15, 5.35) + box(-1.2, -0.9, 0.56, 0.59, 5.17, 5.33, "h1");
        s += box(1.0, 2.2, 2.08, 2.12, 5.25, B) + range(1.05, 1.62, 0.045).map((x, i) => backRect(x, x + 0.04, 2.12, 2.3 + (i * 7 % 4) * 0.025, 5.32, i % 4 === 1 ? "h1" : "f0", { cover: 1, gap: 3 })).join("") + frustum(1.9, 5.35, 2.12, 2.24, 0.05, 0.06);
        s += backFrame(-2.4, -1.5, 1.35, 2.15, B - 0.01, 1);
        s += shadow(-2.2, 0.001, 4.9, 0.2, 0.12) + line([-2.2, 0, 4.9], [-2.2, 1.6, 4.9]) + disc(-2.2, 0.01, 4.9, 0.15) + at2d(-2.2, 1.55, 4.9, (x, y, k) => `<path class="f0" d="M${r1(x - 0.2 * k)} ${r1(y)}L${r1(x - 0.16 * k)} ${r1(y - 0.3 * k)}H${r1(x + 0.16 * k)}L${r1(x + 0.2 * k)} ${r1(y)}Z"/><path class="n" d="M${r1(x - 0.2 * k)} ${r1(y)}L${r1(x - 0.16 * k)} ${r1(y - 0.3 * k)}H${r1(x + 0.16 * k)}L${r1(x + 0.2 * k)} ${r1(y)}Z"/>` + thin(`<path class="n" d="M${r1(x - 0.12 * k)} ${r1(y - 0.26 * k)}v${r1(0.22 * k)}M${r1(x - 0.06 * k)} ${r1(y - 0.27 * k)}v${r1(0.24 * k)}"/>`));
        s += plant(2.4, 5.0, 1.15);
        // right wall: a gallery of frames; armchair with cushion and side table
        for (const [i, j] of [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1]]) s += framePic(W, 2.6 + i * 0.55, 3.0 + i * 0.55, 1.25 + j * 0.5, 1.65 + j * 0.5, (i + j) % 2);
        s += shadow(2.3, 0.001, 3.95, 0.25, 0.2) + line([2.3, 0, 3.95], [2.3, 0.55, 3.95]) + frustum(2.3, 3.95, 0, 0.02, 0.15, 0.15) + frustum(2.3, 3.95, 0.55, 0.58, 0.22, 0.22) + frustum(2.3, 3.95, 0.58, 0.72, 0.06, 0.05) + at2d(2.3, 0.72, 3.95, (x, y, k) => `<path class="f0" d="M${r1(x - 0.1 * k)} ${r1(y)}l${r1(0.03 * k)} ${r1(-0.16 * k)}h${r1(0.14 * k)}l${r1(0.03 * k)} ${r1(0.16 * k)}z"/><path class="n" d="M${r1(x - 0.1 * k)} ${r1(y)}l${r1(0.03 * k)} ${r1(-0.16 * k)}h${r1(0.14 * k)}l${r1(0.03 * k)} ${r1(0.16 * k)}z"/>`);
        s += armchair(1.55, 3.3);
        if (view === "seat") {
          // rug, then my coffee table
          s += flatRect(-1.5, 1.5, 0.9, 3.4, 0.005) + thin(flatRect(-1.38, 1.38, 1.0, 3.28, 0.006, "n") + range(-1.2, 1.2, 0.3).map((x) => line([x, 0.006, 1.0], [x + 0.15, 0.006, 3.28])).join("") + range(-1.45, 1.45, 0.1).map((x) => line([x, 0.005, 3.4], [x, 0.005, 3.48])).join(""));
          s += shadow(0, 0.001, 1.3, 0.55, 0.4) + frustum(0, 1.22, 0.0, 0.03, 0.4, 0.4) + frustum(0, 1.22, 0.03, 0.36, 0.42, 0.42, "f0", null) + frustum(0, 1.22, 0.36, 0.42, 0.5, 0.5);
        } else {
          s += flatRect(-1.5, 1.5, 1.6, 3.6, 0.005) + thin(flatRect(-1.38, 1.38, 1.7, 3.48, 0.006, "n"));
        }
        return s;
      },
    },
  };

  function propsFor(env, taskCat, task) {
    const cfg = SCENE[env] || SCENE.Office, t = String(task || "").toLowerCase();
    if (cfg.byTask[t]) return cfg.byTask[t];
    const key = cfg.byCat[taskCat] || "work";
    return [key === "workout" && env === "Living room" ? "floor" : "seat", key];
  }

  function svg(env, taskCat, task) {
    const room = ROOMS[env] || ROOMS.Office;
    let [view, key] = propsFor(env in ROOMS ? env : "Office", taskCat, task);
    if (!room.views[view]) view = "seat";
    const v = room.views[view];
    [CAMX, CAMZ, EYE, HY] = v.cam;
    uid = 0;
    rnd = seeded(`${env}|${view}`);
    const art = room.draw(view);
    rnd = seeded(`${env}|${key}`);
    const [tx, ty, tz] = v.table;
    const props = PROPS[key] ? PROPS[key](tx, ty, tz, env) : "";
    return `<svg class="xr-scene-svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><defs>${DEFS}</defs>` +
      `<g class="sk">${art}<g class="mis">${props}</g>${props}</g></svg>`;
  }

  // Riso halftones (45° screen): gray and charcoal dots on paper, and transparent dots for shade.
  const INK = { charcoal: "#1F2A3C", paper: "#F5F8FC", gray: "#9AA8BC" };
  const dots = (id, r, color, ground) => `<pattern id="${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">${ground ? `<rect width="6" height="6" fill="${INK.paper}"/>` : ""}<circle cx="3" cy="3" r="${r}" fill="${color}"/></pattern>`;
  const DEFS = dots("xh1", 1.05, INK.gray, 1) + dots("xh2", 1.75, INK.gray, 1) + dots("xh3", 1.55, INK.charcoal, 1) + dots("xh4", 2.25, INK.charcoal, 1) + dots("xh5", 2.9, INK.charcoal, 1) +
    dots("xt1", 1.2, INK.charcoal, 0) + dots("xt2", 1.9, INK.charcoal, 0);

  window.XRScenes = { svg };
})();
