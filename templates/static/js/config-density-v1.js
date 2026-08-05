(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  if (!form || form.querySelector(".lar-config-masonry-grid")) return;

  const sections = Array.from(form.children).filter(function (node) {
    return node.classList && node.classList.contains("config-section");
  });
  if (!sections.length) return;

  const grid = document.createElement("div");
  grid.className = "lar-config-masonry-grid";
  form.insertBefore(grid, sections[0]);
  sections.forEach(function (section) {
    grid.appendChild(section);
  });

  const singleColumn = window.matchMedia("(max-width: 1099px)");
  let frame = 0;

  function layout() {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(function () {
      frame = 0;

      if (singleColumn.matches) {
        sections.forEach(function (section) {
          section.style.removeProperty("grid-row-end");
        });
        return;
      }

      const styles = getComputedStyle(grid);
      const rowHeight = Number.parseFloat(styles.gridAutoRows) || 8;
      const rowGap = Number.parseFloat(styles.rowGap) || 14;

      sections.forEach(function (section) {
        const height = section.getBoundingClientRect().height;
        const span = Math.max(1, Math.ceil((height + rowGap) / (rowHeight + rowGap)));
        const value = "span " + span;
        if (section.style.gridRowEnd !== value) {
          section.style.gridRowEnd = value;
        }
      });
    });
  }

  const observer = new ResizeObserver(layout);
  sections.forEach(function (section) {
    observer.observe(section);
  });

  singleColumn.addEventListener("change", layout);
  window.addEventListener("load", layout, { once: true });
  document.addEventListener("change", layout, true);
  layout();
})();
