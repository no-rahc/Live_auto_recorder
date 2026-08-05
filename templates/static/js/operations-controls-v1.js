(function () {
  "use strict";

  if (!document.body.classList.contains("page-operations")) return;

  function tabs() {
    return Array.from(document.querySelectorAll("[data-ops-tab]"));
  }

  function syncTabs(active) {
    tabs().forEach(function (tab) {
      const selected = tab === active || (!active && tab.classList.contains("is-active"));
      const panel = document.querySelector(`[data-ops-panel="${CSS.escape(tab.dataset.opsTab || "")}"]`);
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (panel) {
        panel.classList.toggle("is-active", selected);
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute("aria-hidden", String(!selected));
        panel.tabIndex = 0;
      }
    });
  }

  function bindTabKeyboard() {
    const nav = document.querySelector(".ops-tabs");
    if (!nav) return;
    nav.setAttribute("role", "tablist");

    nav.addEventListener("click", function (event) {
      const tab = event.target.closest("[data-ops-tab]");
      if (!tab) return;
      queueMicrotask(function () { syncTabs(tab); });
    });

    nav.addEventListener("keydown", function (event) {
      const current = event.target.closest("[data-ops-tab]");
      if (!current || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const items = tabs();
      const index = items.indexOf(current);
      if (index < 0) return;
      event.preventDefault();
      let next = current;
      if (event.key === "Home") next = items[0];
      if (event.key === "End") next = items[items.length - 1];
      if (event.key === "ArrowLeft") next = items[(index - 1 + items.length) % items.length];
      if (event.key === "ArrowRight") next = items[(index + 1) % items.length];
      syncTabs(next);
      next.focus();
    });
  }

  function syncCleanupAction() {
    const run = document.getElementById("ops-cleanup-run");
    const result = document.getElementById("ops-cleanup-result");
    if (!run || !result) return;
    const text = result.textContent || "";
    const match = text.match(/삭제 대상\s+(\d+)개/);
    const count = match ? Number(match[1]) : 0;
    run.disabled = count <= 0;
    run.setAttribute("aria-disabled", String(run.disabled));
    run.title = run.disabled ? "삭제 대상 미리보기를 먼저 실행하세요." : `${count}개 미리보기 항목 삭제`;
  }

  function bindCleanupState() {
    const result = document.getElementById("ops-cleanup-result");
    if (!result) return;
    syncCleanupAction();
    new MutationObserver(syncCleanupAction).observe(result, { childList: true, subtree: true, characterData: true });
    document.getElementById("ops-cleanup-preview")?.addEventListener("click", function () {
      const run = document.getElementById("ops-cleanup-run");
      if (run) {
        run.disabled = true;
        run.setAttribute("aria-disabled", "true");
        run.title = "미리보기 결과를 불러오는 중입니다.";
      }
    });
  }

  function boot() {
    bindTabKeyboard();
    syncTabs();
    bindCleanupState();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
