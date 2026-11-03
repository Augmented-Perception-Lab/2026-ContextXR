// Side navigation: marks the section currently in view.
(function () {
  "use strict";

  const links = [...document.querySelectorAll(".side a[href^='#']:not(.side-home)")];
  const sections = links.map((a) => document.getElementById(a.hash.slice(1))).filter(Boolean);
  if (!sections.length) return;

  function update() {
    // The current section is the last one whose top has passed a third of the viewport.
    const line = window.innerHeight / 3;
    let cur = null;
    for (const s of sections) if (s.getBoundingClientRect().top <= line) cur = s;
    // At the bottom of the page the last sections are too short to reach the line.
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) cur = sections[sections.length - 1];
    for (const a of links) {
      const on = !!cur && a.hash === "#" + cur.id;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    }
    // In the narrow layout the nav scrolls sideways; keep the current link visible.
    const on = links.find((a) => a.classList.contains("on"));
    const nav = on && on.parentElement;
    if (nav && nav.scrollWidth > nav.clientWidth) {
      const l = on.offsetLeft - nav.clientWidth / 2 + on.offsetWidth / 2;
      if (Math.abs(nav.scrollLeft - l) > 4) nav.scrollTo({ left: l });
    }
  }

  let raf = 0;
  window.addEventListener("scroll", () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(update); }, { passive: true });
  window.addEventListener("resize", update);
  update();

  const copy = document.getElementById("cite-copy");
  if (copy && navigator.clipboard) {
    copy.addEventListener("click", () => {
      navigator.clipboard.writeText(document.getElementById("cite-bib").textContent).then(() => {
        copy.textContent = "Copied";
        setTimeout(() => { copy.textContent = "Copy BibTeX"; }, 1500);
      });
    });
  } else if (copy) copy.hidden = true;
})();
