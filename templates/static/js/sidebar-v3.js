(function () {
  "use strict";

  const COLLAPSE_KEY = "lar-sidebar-collapsed";
  const DESKTOP_QUERY = "(min-width: 1100px)";

  const navMeta = {
    "/": {
      label: "대시보드",
      hint: "전체 상태",
      icon: "home",
    },
    "/recording": {
      label: "녹화 현황",
      hint: "세션 제어",
      icon: "activity",
    },
    "/config": {
      label: "설정 관리",
      hint: "자동화 구성",
      icon: "settings",
    },
    "/channels": {
      label: "채널 관리",
      hint: "녹화 대상",
      icon: "channels",
    },
    "/cookies": {
      label: "쿠키 관리",
      hint: "인증 상태",
      icon: "key",
    },
    "/files": {
      label: "파일 관리",
      hint: "저장소 탐색",
      icon: "folder",
    },
    "/operations": {
      label: "운영 관리",
      hint: "상태와 정책",
      icon: "operations",
    },
    "/register": {
      label: "계정 생성",
      hint: "관리자 등록",
      icon: "userPlus",
    },
  };

  const iconPaths = {
    home: '<path d="M3 10.8 12 3l9 7.8"/><path d="M5.5 9.5V21h13V9.5"/><path d="M9.5 21v-6h5v6"/>',
    activity: '<path d="M3 12h4l2.2-5 4.1 10 2.1-5H21"/><circle cx="12" cy="12" r="9" opacity=".18" fill="currentColor" stroke="none"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
    channels: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m8 2 4 3 4-3M8 10h3v4H8zm6 0h2m-2 4h2"/>',
    key: '<circle cx="8" cy="15" r="4"/><path d="m11 12 8-8m-3 3 2 2m-5 1 2 2"/>',
    folder: '<path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5Z"/><path d="M3 9h18"/>',
    operations: '<path d="M4 18v-5m0-4V6m8 12v-8m0-4V4m8 14v-3m0-4V6"/><path d="M2 13h4m4-3h4m4 5h4"/>',
    userPlus: '<circle cx="9" cy="8" r="4"/><path d="M3 21a6 6 0 0 1 12 0m4-9v6m-3-3h6"/>',
    logout: '<path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4"/><path d="m15 8 4 4-4 4m4-4H9"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    panelLeft: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m5-11 3 3-3 3"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    logo: '<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4m8.4-8.4a6 6 0 0 1 0 8.4M4.6 4.6a10.5 10.5 0 0 0 0 14.8m14.8-14.8a10.5 10.5 0 0 1 0 14.8"/>',
  };

  function svgIcon(name, className) {
    const path = iconPaths[name] || iconPaths.home;
    return (
      '<svg class="' +
      (className || "") +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      path +
      "</svg>"
    );
  }

  function normalizedPath(value) {
    try {
      const path = new URL(value, location.origin).pathname.replace(/\/$/, "");
      return path || "/";
    } catch (_) {
      return "";
    }
  }

  function currentPath() {
    return normalizedPath(location.href) || "/";
  }

  function detectVersion() {
    const candidates = [
      document.querySelector(".dash-ver")?.textContent || "",
      document.title || "",
      document.body.textContent || "",
    ];
    for (const candidate of candidates) {
      const match = candidate.match(/v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?/);
      if (match) return match[0];
    }
    return "Console";
  }

  function readCollapsed() {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function writeCollapsed(value) {
    try {
      localStorage.setItem(COLLAPSE_KEY, value ? "1" : "0");
    } catch (_) {
      // Storage may be disabled; the current session still keeps the class.
    }
  }

  function setCollapsed(collapsed, button) {
    document.body.classList.toggle("lar-sidebar-collapsed", collapsed);
    if (button) {
      button.setAttribute("aria-pressed", String(collapsed));
      button.setAttribute("aria-label", collapsed ? "사이드바 펼치기" : "사이드바 접기");
      button.title = collapsed ? "사이드바 펼치기" : "사이드바 접기";
    }
    writeCollapsed(collapsed);
  }

  function createSidebarHeader(closeButton) {
    const header = document.createElement("div");
    header.className = "lar-sidenav-head";

    const brand = document.createElement("a");
    brand.href = "/";
    brand.className = "lar-sidebar-brand";
    brand.setAttribute("aria-label", "Live Auto Recorder 대시보드");
    brand.innerHTML =
      '<span class="lar-sidebar-logo">' +
      svgIcon("logo") +
      "</span>" +
      '<span class="lar-sidebar-brand-copy"><strong>Live Auto Recorder</strong><small>' +
      detectVersion() +
      "</small></span>";

    const collapse = document.createElement("button");
    collapse.type = "button";
    collapse.className = "lar-sidebar-collapse";
    collapse.dataset.larSidebarCollapse = "";
    collapse.innerHTML = svgIcon("panelLeft");

    header.append(brand, collapse);

    if (closeButton) {
      closeButton.classList.add("lar-drawer-close");
      closeButton.innerHTML = svgIcon("close");
      closeButton.setAttribute("aria-label", "메뉴 닫기");
      closeButton.removeAttribute("title");
      header.appendChild(closeButton);
    }

    collapse.addEventListener("click", function () {
      setCollapsed(!document.body.classList.contains("lar-sidebar-collapsed"), collapse);
    });

    setCollapsed(readCollapsed(), collapse);
    return header;
  }

  function enhancePrimaryLink(link, activePath) {
    const targetPath = normalizedPath(link.href);
    const fallbackLabel = link.dataset.navLabel || link.textContent.trim() || "메뉴";
    const meta = navMeta[targetPath] || {
      label: fallbackLabel,
      hint: "메뉴",
      icon: "home",
    };

    link.querySelector(".lar-nav-icon")?.remove();
    link.classList.add("lar-sidebar-link");
    link.dataset.larSidebarLink = "1";
    link.dataset.navLabel = meta.label;
    link.title = meta.label;
    link.innerHTML =
      '<span class="lar-sidebar-link-icon">' +
      svgIcon(meta.icon) +
      "</span>" +
      '<span class="lar-sidebar-link-copy"><strong>' +
      meta.label +
      "</strong><small>" +
      meta.hint +
      "</small></span>" +
      '<span class="lar-sidebar-link-arrow">' +
      svgIcon("chevron") +
      "</span>";

    const isActive = targetPath === activePath;
    link.classList.toggle("lar-active", isActive);
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }

  function integrateSidebarLink(link, navList, activePath) {
    if (!link?.matches?.("a[href]:not(.closebtn)")) return;
    if (link.id === "logout-btn" || link.classList.contains("lar-sidebar-brand")) return;

    if (link.dataset.larSidebarLink !== "1") {
      enhancePrimaryLink(link, activePath);
    }
    if (link.parentElement !== navList) {
      navList.appendChild(link);
    }
  }

  function watchLateSidebarLinks(nav, navList, activePath) {
    if (nav.dataset.larSidebarObserver === "1") return;
    nav.dataset.larSidebarObserver = "1";

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (!(node instanceof Element)) return;
          if (node.matches("a[href]")) integrateSidebarLink(node, navList, activePath);
          node.querySelectorAll?.("a[href]").forEach(function (link) {
            integrateSidebarLink(link, navList, activePath);
          });
        });
      });
    });
    observer.observe(nav, { childList: true, subtree: true });
  }

  function enhanceUserCard(userInfo) {
    if (!userInfo || userInfo.dataset.larSidebarUser === "1") return;
    userInfo.dataset.larSidebarUser = "1";
    userInfo.classList.add("lar-sidebar-user");

    const usernameNode = userInfo.querySelector("#username-display");
    const logout = userInfo.querySelector("#logout-btn");
    const username = usernameNode?.textContent.trim() || "사용자";
    const initial = Array.from(username)[0] || "U";

    const profile = document.createElement("div");
    profile.className = "lar-sidebar-profile";
    profile.innerHTML =
      '<span class="lar-sidebar-avatar" aria-hidden="true">' +
      initial +
      "</span>" +
      '<span class="lar-sidebar-user-copy"><small>현재 계정</small><strong>' +
      username.replace(/[&<>"']/g, function (character) {
        return {
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        }[character];
      }) +
      "</strong></span>" +
      '<span class="lar-sidebar-online" title="접속 중" aria-label="접속 중"></span>';

    userInfo.replaceChildren(profile);

    if (logout) {
      logout.querySelector(".lar-nav-icon")?.remove();
      logout.className = "lar-sidebar-logout";
      logout.title = "로그아웃";
      logout.innerHTML =
        '<span class="lar-sidebar-logout-icon">' +
        svgIcon("logout") +
        '</span><span class="lar-sidebar-logout-label">로그아웃</span>';
      userInfo.appendChild(logout);
    }
  }

  function enhanceSidebar() {
    const nav = document.getElementById("mySidenav");
    if (!nav || nav.dataset.larSidebarV3 === "1") return;
    nav.dataset.larSidebarV3 = "1";
    nav.setAttribute("aria-label", "주요 메뉴");
    document.body.classList.add("lar-sidebar-v3", "lar-desktop-nav");

    const closeButton = Array.from(nav.children).find(function (child) {
      return child.matches?.("a.closebtn");
    });
    const userInfo = Array.from(nav.children).find(function (child) {
      return child.id === "user-info";
    });
    const primaryLinks = Array.from(nav.children).filter(function (child) {
      return child.matches?.("a[href]:not(.closebtn)");
    });

    const header = createSidebarHeader(closeButton);
    const sectionLabel = document.createElement("div");
    sectionLabel.className = "lar-sidebar-section-label";
    sectionLabel.textContent = "메뉴";

    const navList = document.createElement("nav");
    navList.className = "lar-sidebar-list";
    navList.setAttribute("aria-label", "관리 메뉴");

    const activePath = currentPath();
    primaryLinks.forEach(function (link) {
      integrateSidebarLink(link, navList, activePath);
    });

    nav.prepend(header);
    header.insertAdjacentElement("afterend", sectionLabel);
    sectionLabel.insertAdjacentElement("afterend", navList);
    enhanceUserCard(userInfo);

    if (userInfo && userInfo.parentElement === nav) nav.appendChild(userInfo);
    watchLateSidebarLinks(nav, navList, activePath);
  }

  function enhanceTopbarContext() {
    const navbar = document.querySelector(".navbar");
    if (!navbar || navbar.querySelector(".lar-topbar-context")) return;

    const meta = navMeta[currentPath()] || {
      label: "관리 화면",
      hint: "Live Auto Recorder",
      icon: "home",
    };
    const context = document.createElement("div");
    context.className = "lar-topbar-context";
    context.innerHTML =
      '<span class="lar-topbar-context-icon">' +
      svgIcon(meta.icon) +
      "</span>" +
      '<span><small>Live Auto Recorder</small><strong>' +
      meta.label +
      "</strong></span>";

    const actions = navbar.querySelector(".lar-topbar-actions");
    navbar.insertBefore(context, actions || null);
  }

  function boot() {
    enhanceSidebar();
    enhanceTopbarContext();

    const desktop = matchMedia(DESKTOP_QUERY);
    const syncViewport = function () {
      if (!desktop.matches) {
        document.body.classList.remove("lar-sidebar-collapsed-preview");
      }
    };
    desktop.addEventListener?.("change", syncViewport);
    syncViewport();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
