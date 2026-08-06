(function () {
  "use strict";

  const LOGIN_TRUE = new Set(["1", "true", "yes", "on"]);

  function loginModeEnabled() {
    return LOGIN_TRUE.has(String(document.body.dataset.loginMode || "").trim().toLowerCase());
  }

  function logoutIcon() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4"/><path d="m15 8 4 4-4 4m4-4H9"/></svg>';
  }

  function ensureTopbarActions() {
    const navbar = document.querySelector(".navbar");
    if (!navbar) return null;

    let actions = navbar.querySelector(".lar-topbar-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "lar-topbar-actions";
      navbar.appendChild(actions);
    }
    return actions;
  }

  function addCompactLogout(logout) {
    if (!loginModeEnabled() || !logout) return;

    const actions = ensureTopbarActions();
    if (!actions || actions.querySelector(".lar-topbar-logout")) return;

    const link = document.createElement("a");
    link.className = "lar-topbar-logout";
    link.href = logout.getAttribute("href") || "/logout";
    link.title = "로그아웃";
    link.setAttribute("aria-label", "로그아웃");
    link.innerHTML = logoutIcon() + '<span class="lar-sr-only">로그아웃</span>';
    actions.appendChild(link);
  }

  function cleanSidebarAccount() {
    const userInfo = document.getElementById("user-info");
    const logout = userInfo?.querySelector("#logout-btn") || document.getElementById("logout-btn");

    addCompactLogout(logout);
    userInfo?.remove();
    document.body.classList.add("lar-sidebar-account-clean");
  }

  function boot() {
    cleanSidebarAccount();

    const sidebar = document.getElementById("mySidenav");
    if (!sidebar) return;

    const observer = new MutationObserver(function () {
      if (document.getElementById("user-info")) cleanSidebarAccount();
    });
    observer.observe(sidebar, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      requestAnimationFrame(boot);
    }, { once: true });
  } else {
    requestAnimationFrame(boot);
  }
})();
