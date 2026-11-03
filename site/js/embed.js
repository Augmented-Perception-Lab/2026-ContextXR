// Embedded mode (set in index.html when the page is framed). With a same-origin host page the
// frame grows to fit its content, so the host page does the scrolling; dialogs open in the part
// of the frame that is visible in the host's window.
(function () {
  "use strict";

  if (!document.documentElement.classList.contains("embed")) return;
  let frame = null;
  try { frame = window.frameElement; } catch (e) { /* cross-origin host */ }
  if (!frame) return;
  const host = window.parent;

  function fit() {
    const h = document.documentElement.scrollHeight;
    if (Math.abs(frame.offsetHeight - h) > 1) frame.style.height = h + "px";
  }
  new ResizeObserver(fit).observe(document.body);
  fit();

  // Keep the visible part of the frame still when content above it changes height.
  window.ContextXREmbed = { scrollBy(dy) { fit(); host.scrollBy(0, dy); } };

  const showModal = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = function () {
    showModal.call(this);
    const top = Math.max(0, -frame.getBoundingClientRect().top);
    const avail = host.innerHeight;
    this.style.maxHeight = avail - 48 + "px";
    this.style.margin = "0 auto";
    this.style.bottom = "auto";
    this.style.top = top + Math.max(24, (avail - this.offsetHeight) / 2) + "px";
    const root = host.document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    this.addEventListener("close", () => { root.style.overflow = overflow; }, { once: true });
  };
})();
