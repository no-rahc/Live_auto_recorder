(function () {
  "use strict";

  const AUTH_PATHS = new Set(["/login", "/logout", "/register", "/updateAccount"]);

  function authPath(value) {
    if (!value) return false;
    try {
      return AUTH_PATHS.has(new URL(value, window.location.origin).pathname);
    } catch (_) {
      return AUTH_PATHS.has(String(value).split("?")[0]);
    }
  }

  function removeLegacyAuthUi(root) {
    const host = root || document;
    host.querySelectorAll("a[href]").forEach((link) => {
      if (authPath(link.getAttribute("href"))) link.remove();
    });
    host.querySelectorAll("form[action]").forEach((form) => {
      if (authPath(form.getAttribute("action"))) form.remove();
    });
    host.querySelectorAll("#user-info, #account-fields, .lar-topbar-logout").forEach((node) => node.remove());
  }

  function ensureLocalModeInput(form) {
    if (!form) return;
    const legacy = form.querySelector("#loginMode");
    legacy?.closest(".config-section")?.remove();
    form.querySelectorAll("[name='loginMode']").forEach((node) => node.remove());

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "loginMode";
    input.value = "false";
    input.defaultValue = "false";
    input.dataset.larLocalMode = "true";
    form.appendChild(input);
  }

  function simplifyConfigWorkspace() {
    if (!document.body.classList.contains("page-config")) return;
    document.body.classList.add("lar-local-mode");
    document.body.dataset.loginMode = "false";

    const form = document.getElementById("configForm");
    ensureLocalModeInput(form);
    document.getElementById("account-fields")?.remove();

    const filesPanel = document.querySelector("[data-config-panel='files']");
    const filesGrid = filesPanel?.querySelector(".lar-config-panel-grid");
    const maintenance = document.querySelector(".lar-operations-link-card");
    if (filesGrid && maintenance) filesGrid.appendChild(maintenance);

    const securityButton = document.querySelector("[data-config-tab='security']");
    const securityPanel = document.querySelector("[data-config-panel='security']");
    const securityWasActive = securityButton?.classList.contains("is-active")
      || securityPanel?.classList.contains("is-active");
    securityButton?.remove();
    securityPanel?.remove();
    document.querySelector(".lar-config-system-extras")?.remove();

    const filesButton = document.querySelector("[data-config-tab='files']");
    const filesHint = filesButton?.querySelector("small");
    if (filesHint) filesHint.textContent = "접근 범위·운영";

    document.querySelectorAll(".lar-config-tab").forEach((button, index) => {
      button.tabIndex = index === 0 ? 0 : -1;
    });

    if (securityWasActive || !document.querySelector(".lar-config-tab.is-active")) {
      document.querySelector("[data-config-tab='basic']")?.click();
    }

    const overview = document.querySelector(".lar-config-overview-line");
    const access = overview ? Array.from(overview.children).find((node) => node.querySelector("b")?.textContent.trim() === "접속") : null;
    access?.remove();
  }

  function boot() {
    removeLegacyAuthUi(document);
    simplifyConfigWorkspace();

    const sidebar = document.getElementById("mySidenav");
    if (sidebar) {
      new MutationObserver(() => removeLegacyAuthUi(sidebar)).observe(sidebar, { childList: true, subtree: true });
    }
  }

  boot();
})();
