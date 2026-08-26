// ===== Sidebar =====
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

;
// ===== Dashboard =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-index") || !document.getElementById("sys-dashboard")) {
    return;
  }

  const text = {
    subtitle: "지금 확인해야 할 녹화와 시스템 상태를 한눈에 확인하세요.",
    quick: "빠른 이동",
    menuCount: "자주 쓰는 메뉴",
    live: "녹화 중",
    liveNote: "현재 실행 중인 세션",
    channels: "관리 채널",
    channelsNote: "등록된 전체 채널",
    today: "오늘 녹화",
    todayNote: "오늘 시작된 녹화",
    failures: "오늘 실패",
    failuresNote: "확인이 필요한 이벤트",
    systemTitle: "시스템 상태",
    systemDesc: "녹화 저장소와 주요 리소스 사용량",
    activityTitle: "운영 현황",
    activityDesc: "채널별 상태와 최근 녹화 이력",
    channelsLink: "채널 관리",
    historyLink: "녹화 현황",
    healthGood: "시스템 정상",
    healthWarn: "사용량 확인",
    healthBad: "즉시 확인 필요",
    updated: "방금 갱신",
    clockNote: "Asia / Seoul",
  };

  const dockMeta = {
    "/recording": ["녹화 현황", "세션 제어", "activity"],
    "/config": ["설정 관리", "자동화 설정", "settings"],
    "/channels": ["채널 관리", "녹화 대상", "channels"],
    "/cookies": ["쿠키 관리", "인증 상태", "key"],
    "/files": ["파일 관리", "저장소 탐색", "folder"],
  };

  const icons = {
    activity: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 13h3l2-6 4 11 2-6h5"/></svg>',
    settings: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z"/></svg>',
    channels: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m9 2 3 3 3-3M8 10h5v4H8zM17 10h1m-1 4h1"/></svg>',
    key: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"/><path d="m11 12 8-8m-3 3 2 2m-5 1 2 2"/></svg>',
    folder: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v8A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z"/></svg>',
  };

  function el(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = content;
    return node;
  }

  function statCard(tone, label, valueId, note) {
    const card = el("article", "dash-v4-stat");
    card.dataset.tone = tone;
    const labelEl = el("div", "dash-v4-stat-label");
    labelEl.innerHTML = '<span class="dash-v4-stat-dot" aria-hidden="true"></span>' + label;
    const value = el("div", "dash-v4-stat-value");
    const number = el("span", "", "0");
    number.id = valueId;
    value.appendChild(number);
    value.appendChild(el("small", "", "개"));
    card.appendChild(labelEl);
    card.appendChild(value);
    card.appendChild(el("div", "dash-v4-stat-note", note));
    return card;
  }

  function sectionHead(title, desc, linkText, href) {
    const head = el("div", "dash-v4-section-head");
    const copy = el("div", "dash-v4-section-copy");
    copy.appendChild(el("h2", "", title));
    copy.appendChild(el("p", "", desc));
    head.appendChild(copy);
    if (linkText && href) {
      const link = el("a", "dash-v4-section-link", linkText + "  →");
      link.href = href;
      head.appendChild(link);
    }
    return head;
  }

  function buildLayout() {
    document.body.classList.add("lar-dashboard-v5");
    const content = document.querySelector("#content.page-index");
    const hero = content && content.querySelector(".dash-hero");
    const dock = content && content.querySelector(".dash-dock");
    const system = content && content.querySelector("#sys-dashboard");
    const activity = content && content.querySelector(".dash-two");
    if (!content || !hero || !dock || !system || !activity || content.querySelector(".dash-v5-top")) return;

    hero.querySelector(".dash-ver")?.remove();

    const subtitle = el("p", "dash-v4-subtitle", text.subtitle);
    const heroLeft = hero.querySelector(".dash-hero-left");
    const statusline = hero.querySelector(".dash-statusline");
    if (heroLeft && statusline) heroLeft.insertBefore(subtitle, statusline);

    const health = el("span", "dash-v4-health", text.healthGood);
    health.id = "dash-v4-health";
    health.dataset.state = "good";
    const updated = el("span", "dash-v4-updated", text.updated);
    updated.id = "dash-v4-updated";
    if (statusline) {
      statusline.appendChild(health);
      statusline.appendChild(updated);
    }

    const heroRight = hero.querySelector(".dash-hero-right");
    if (heroRight && !heroRight.querySelector(".dash-v4-clock-note")) {
      heroRight.appendChild(el("div", "dash-v4-clock-note", text.clockNote));
    }

    const dockHead = el("div", "dash-v4-dock-head");
    dockHead.appendChild(el("span", "dash-v4-dock-title", text.quick));
    dockHead.appendChild(el("span", "dash-v4-dock-meta", text.menuCount));
    dock.insertBefore(dockHead, dock.firstChild);

    dock.querySelectorAll("a[href]").forEach(function (link) {
      const path = new URL(link.href, location.origin).pathname.replace(/\/$/, "") || "/";
      const meta = dockMeta[path];
      if (!meta) return;
      const icon = link.querySelector(".dock-ico");
      const label = link.querySelector(".dock-label");
      if (icon) icon.innerHTML = icons[meta[2]] || icons.activity;
      if (label && !label.parentNode.classList.contains("dash-v4-dock-copy")) {
        label.textContent = meta[0];
        const copy = el("span", "dash-v4-dock-copy");
        label.parentNode.insertBefore(copy, label);
        copy.appendChild(label);
        copy.appendChild(el("span", "dock-description", meta[1]));
      }
      if (!link.querySelector(".dash-v4-dock-arrow")) {
        link.appendChild(el("span", "dash-v4-dock-arrow", "›"));
      }
    });

    const overview = el("section", "dash-v4-overview");
    overview.setAttribute("aria-label", "운영 요약");
    overview.appendChild(statCard("live", text.live, "dash-v4-live-count", text.liveNote));
    overview.appendChild(statCard("channels", text.channels, "dash-v4-channel-count", text.channelsNote));
    overview.appendChild(statCard("today", text.today, "dash-v4-today-count", text.todayNote));
    overview.appendChild(statCard("fail", text.failures, "dash-v4-failure-count", text.failuresNote));

    const top = el("section", "dash-v5-top");
    hero.parentNode.insertBefore(top, hero);
    top.appendChild(hero);
    top.appendChild(overview);
    top.insertAdjacentElement("afterend", dock);

    system.insertAdjacentElement("beforebegin", sectionHead(text.systemTitle, text.systemDesc));
    activity.insertAdjacentElement("beforebegin", sectionHead(text.activityTitle, text.activityDesc, text.channelsLink, "/channels"));

    const historySection = activity.querySelectorAll(".index-section")[1];
    if (historySection) {
      const head = historySection.querySelector(".card-head");
      if (head && !head.querySelector(".dash-v4-history-link")) {
        const link = el("a", "dash-v4-section-link dash-v4-history-link", text.historyLink + "  →");
        link.href = "/recording";
        const chip = head.querySelector(".chip");
        if (chip) chip.insertAdjacentElement("afterend", link);
        else head.appendChild(link);
      }
    }
  }

  function numberFrom(textValue) {
    const match = String(textValue || "").match(/\d+/);
    return match ? Number(match[0]) : 0;
  }

  function setValue(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = String(value);
  }

  function syncChannels() {
    const list = document.getElementById("ch-list");
    if (!list) return;
    const rows = Array.from(list.querySelectorAll(".ch-row"));
    const count = document.getElementById("ch-count");
    setValue("dash-v4-channel-count", rows.length || numberFrom(count && count.textContent));
    setValue("dash-v4-live-count", rows.filter(function (row) { return row.classList.contains("ch-row--rec"); }).length);
  }

  function syncHistory() {
    const stats = document.getElementById("hist-stats");
    const value = stats ? stats.textContent : "";
    const today = value.match(/오늘\s*(\d+)건/);
    const failures = value.match(/실패\s*(\d+)건/);
    setValue("dash-v4-today-count", today ? Number(today[1]) : 0);
    setValue("dash-v4-failure-count", failures ? Number(failures[1]) : 0);
  }

  function percent(id) {
    const node = document.getElementById(id);
    return node ? Number.parseFloat(node.textContent) || 0 : 0;
  }

  function syncHealth() {
    const health = document.getElementById("dash-v4-health");
    if (!health) return;
    const max = Math.max(percent("cpu-percent"), percent("mem-percent"), percent("stor-pct"));
    let state = "good";
    let label = text.healthGood;
    if (max >= 90) {
      state = "bad";
      label = text.healthBad;
    } else if (max >= 75) {
      state = "warn";
      label = text.healthWarn;
    }
    health.dataset.state = state;
    health.textContent = label;
  }

  function syncUpdated() {
    const node = document.getElementById("dash-v4-updated");
    if (!node) return;
    node.textContent = new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) + " 갱신";
    syncHealth();
  }

  function observe(id, callback, options) {
    const node = document.getElementById(id);
    if (!node) return;
    new MutationObserver(callback).observe(node, options || { childList: true, subtree: true, characterData: true });
  }

  buildLayout();
  syncChannels();
  syncHistory();
  syncHealth();

  observe("ch-list", syncChannels, { childList: true, subtree: true });
  observe("ch-count", syncChannels);
  observe("hist-stats", syncHistory);
  observe("cpu-percent", syncHealth);
  observe("mem-percent", syncHealth);
  observe("stor-pct", syncHealth);
  document.addEventListener("lar:sys-metrics", syncUpdated);
  window.setInterval(syncUpdated, 30000);
})();

;
// ===== Dashboard channel modal =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-index")) return;

  const list = document.getElementById("ch-list");
  if (!list) return;

  const state = {
    channels: [],
    statuses: {},
    selectedId: null,
    editing: false,
    dirty: false,
    loading: false,
    originalRecordEnabled: true,
  };

  const qualityOptions = {
    chzzk: ["best", "1080p", "720p", "480p", "360p"],
    youtube: ["best", "480p", "720p", "1080p", "1440p", "2160p"],
  };

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function requestJson(url, options) {
    return fetch(url, Object.assign({
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }, options || {})).then(async function (response) {
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        throw new Error(data.detail || data.message || ("요청 실패 (HTTP " + response.status + ")"));
      }
      return data;
    });
  }

  const overlay = node("div", "lar-channel-modal");
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = [
    '<div class="lar-channel-modal-backdrop" data-modal-close></div>',
    '<section class="lar-channel-dialog" tabindex="-1" role="dialog" aria-modal="true" aria-labelledby="lar-channel-dialog-title">',
    '  <header class="lar-channel-dialog-head">',
    '    <div class="lar-channel-dialog-identity">',
    '      <span class="lar-channel-dialog-icon" id="lar-channel-dialog-icon">치</span>',
    '      <div>',
    '        <div class="lar-channel-dialog-kicker">채널 세부 설정</div>',
    '        <h2 id="lar-channel-dialog-title">채널</h2>',
    '        <p id="lar-channel-dialog-subtitle">채널 정보를 불러오는 중입니다.</p>',
    '      </div>',
    '    </div>',
    '    <div class="lar-channel-dialog-head-actions">',
    '      <span class="lar-channel-dialog-status" id="lar-channel-dialog-status">대기</span>',
    '      <button type="button" class="lar-channel-dialog-close" data-modal-close aria-label="닫기">×</button>',
    '    </div>',
    '  </header>',
    '  <div class="lar-channel-dialog-scroll">',
    '    <section class="lar-channel-live-summary" aria-label="현재 방송 상태">',
    '      <div><span>현재 방송</span><strong id="lar-channel-live-title">라이브 종료</strong></div>',
    '      <div><span>녹화 시간</span><strong id="lar-channel-duration">-</strong></div>',
    '    </section>',
    '    <div class="lar-channel-recording-note" id="lar-channel-recording-note" hidden>',
    '      현재 녹화 중입니다. 저장 경로·품질·확장자 변경은 다음 녹화부터 적용됩니다.',
    '    </div>',
    '    <form id="lar-channel-detail-form" class="lar-channel-detail-form is-view">',
    '      <label><span>플랫폼</span><select name="platform" disabled></select></label>',
    '      <label><span>채널 ID</span><input name="id" type="text" readonly></label>',
    '      <label class="lar-channel-field-wide"><span>채널명</span><input name="name" type="text" required maxlength="100"></label>',
    '      <label class="lar-channel-field-wide"><span>저장 경로</span><input name="output_dir" type="text" required></label>',
    '      <label><span>녹화 품질</span><select name="quality"></select></label>',
    '      <label><span>파일 확장자</span><select name="extension"></select></label>',
    '      <label><span>같이보기만 녹화</span><select name="recordWatchParty"><option value="false">아니오</option><option value="true">예</option></select></label>',
    '      <label class="lar-channel-switch-field"><span>자동녹화 사용</span><input name="record_enabled" type="checkbox"></label>',
    '      <label class="lar-channel-field-wide"><span>녹화 제외 태그</span><input name="watchPartyExcludeTags" type="text" placeholder="예: LCK, VCT"><small>쉼표로 여러 태그를 구분할 수 있습니다.</small></label>',
    '    </form>',
    '    <p class="lar-channel-modal-message" id="lar-channel-modal-message" role="status" aria-live="polite"></p>',
    '  </div>',
    '  <footer class="lar-channel-dialog-footer">',
    '    <a class="lar-channel-manage-link" href="/channels">전체 채널 관리</a>',
    '    <div class="lar-channel-dialog-buttons">',
    '      <button type="button" class="lar-channel-btn lar-channel-btn-secondary" id="lar-channel-cancel" hidden>취소</button>',
    '      <button type="button" class="lar-channel-btn lar-channel-btn-secondary" id="lar-channel-edit">수정</button>',
    '      <button type="submit" form="lar-channel-detail-form" class="lar-channel-btn lar-channel-btn-primary" id="lar-channel-save" hidden>변경사항 저장</button>',
    '    </div>',
    '  </footer>',
    '</section>',
  ].join("");
  document.body.appendChild(overlay);

  const dialog = overlay.querySelector(".lar-channel-dialog");
  const form = document.getElementById("lar-channel-detail-form");
  const title = document.getElementById("lar-channel-dialog-title");
  const subtitle = document.getElementById("lar-channel-dialog-subtitle");
  const icon = document.getElementById("lar-channel-dialog-icon");
  const statusBadge = document.getElementById("lar-channel-dialog-status");
  const liveTitle = document.getElementById("lar-channel-live-title");
  const duration = document.getElementById("lar-channel-duration");
  const recordingNote = document.getElementById("lar-channel-recording-note");
  const message = document.getElementById("lar-channel-modal-message");
  const editButton = document.getElementById("lar-channel-edit");
  const cancelButton = document.getElementById("lar-channel-cancel");
  const saveButton = document.getElementById("lar-channel-save");
  const manageLink = overlay.querySelector(".lar-channel-manage-link");

  const fields = {
    platform: form.elements.platform,
    id: form.elements.id,
    name: form.elements.name,
    outputDir: form.elements.output_dir,
    quality: form.elements.quality,
    extension: form.elements.extension,
    watchParty: form.elements.recordWatchParty,
    recordEnabled: form.elements.record_enabled,
    tags: form.elements.watchPartyExcludeTags,
  };

  function platformName(platform) {
    return String(platform || "").toLowerCase() === "youtube" ? "유튜브" : "치지직";
  }

  function isRecording(status) {
    return !!(status && (status.recording || status.is_recording || status.state === "recording"));
  }

  function isReserved(status) {
    return !!(status && (status.reserved || status.is_reserved || status.state === "reserved"));
  }

  function currentChannel() {
    return state.channels.find(function (channel) {
      return String(channel.id) === String(state.selectedId);
    }) || null;
  }

  function currentStatus() {
    return state.statuses && state.selectedId != null ? (state.statuses[state.selectedId] || {}) : {};
  }

  function setOptions(select, values, selected) {
    select.innerHTML = "";
    values.forEach(function (value) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = String(value) === String(selected);
      select.appendChild(option);
    });
    if (selected && !values.includes(selected)) {
      const option = document.createElement("option");
      option.value = selected;
      option.textContent = selected;
      option.selected = true;
      select.appendChild(option);
    }
  }

  function extensionOptions(platform, quality) {
    if (platform === "youtube") {
      return ["1440p", "2160p"].includes(quality) ? [".mkv"] : [".mp4"];
    }
    return [".ts", ".mp4"];
  }

  function syncFormatOptions(preferredQuality, preferredExtension) {
    const platform = String(fields.platform.value || "chzzk").toLowerCase();
    const qualities = qualityOptions[platform] || qualityOptions.chzzk;
    const quality = preferredQuality || fields.quality.value || qualities[0];
    setOptions(fields.quality, qualities, quality);
    const extensions = extensionOptions(platform, fields.quality.value);
    setOptions(fields.extension, extensions, preferredExtension || fields.extension.value || extensions[0]);
  }

  function tagsValue(value) {
    if (Array.isArray(value)) return value.join(", ");
    return String(value || "");
  }

  function setMessage(text, tone) {
    message.textContent = text || "";
    message.dataset.tone = tone || "";
  }

  function syncTagsEnabled() {
    fields.tags.disabled = !state.editing || fields.watchParty.value !== "true";
  }

  function setEditing(editing) {
    state.editing = !!editing;
    form.classList.toggle("is-view", !state.editing);
    form.classList.toggle("is-editing", state.editing);

    [fields.name, fields.outputDir, fields.quality, fields.extension, fields.watchParty, fields.recordEnabled]
      .forEach(function (field) { field.disabled = !state.editing; });
    fields.platform.disabled = true;
    fields.id.readOnly = true;
    syncTagsEnabled();

    editButton.hidden = state.editing;
    cancelButton.hidden = !state.editing;
    saveButton.hidden = !state.editing;
    manageLink.hidden = state.editing;
    setMessage(state.editing ? "수정할 항목만 변경한 뒤 저장하세요." : "", "");

    if (!state.editing) state.dirty = false;
    if (state.editing) fields.name.focus();
  }

  function renderChannel() {
    const channel = currentChannel();
    if (!channel) return;
    const status = currentStatus();
    const platform = String(channel.platform || "chzzk").toLowerCase();
    const recording = isRecording(status);
    const reserved = isReserved(status);
    const name = channel.channel_name || channel.name || channel.id;

    title.textContent = name;
    subtitle.textContent = platformName(platform) + " · " + channel.id;
    icon.textContent = platform === "youtube" ? "▶" : "치";
    icon.dataset.platform = platform;

    statusBadge.textContent = recording ? "녹화 중" : reserved ? "예약녹화" : "대기";
    statusBadge.dataset.state = recording ? "recording" : reserved ? "reserved" : "idle";
    liveTitle.textContent = channel.live_title || status.live_title || status.title || (recording || reserved ? "방송 준비 중" : "라이브 종료");
    duration.textContent = recording ? (status.duration || status.recording_duration || "00:00:00") : "-";
    recordingNote.hidden = !recording;

    setOptions(fields.platform, [platform], platform);
    fields.id.value = channel.id || "";
    fields.name.value = name || "";
    fields.outputDir.value = channel.output_dir || channel.outputDir || "";
    syncFormatOptions(channel.quality || "best", channel.extension || (platform === "youtube" ? ".mp4" : ".ts"));
    fields.watchParty.value = String(!!channel.recordWatchParty);
    fields.tags.value = tagsValue(channel.watchPartyExcludeTags);
    state.originalRecordEnabled = channel.record_enabled !== false;
    fields.recordEnabled.checked = state.originalRecordEnabled;

    manageLink.href = "/channels#" + encodeURIComponent(String(channel.id));
    setEditing(false);
  }

  async function refreshCache() {
    if (state.loading) return;
    state.loading = true;
    try {
      const values = await Promise.all([
        requestJson("/api/channels"),
        requestJson("/status"),
      ]);
      state.channels = Array.isArray(values[0]) ? values[0] : [];
      state.statuses = values[1] || {};
      decorateRows();
      if (state.selectedId && !overlay.hidden && !state.editing) renderChannel();
    } catch (error) {
      console.error("채널 정보를 불러오지 못했습니다.", error);
      if (!overlay.hidden) setMessage(error.message, "error");
    } finally {
      state.loading = false;
    }
  }

  function decorateRows() {
    const rows = Array.from(list.querySelectorAll(".ch-row"));
    rows.forEach(function (row, index) {
      const channel = state.channels[index];
      if (!channel) return;
      row.dataset.channelId = channel.id;
      row.classList.add("lar-channel-clickable");
      row.tabIndex = 0;
      row.setAttribute("role", "button");
      row.setAttribute("aria-haspopup", "dialog");
      row.setAttribute("aria-label", (channel.channel_name || channel.name || channel.id) + " 세부 설정 열기");
    });
  }

  async function openModal(id) {
    if (!id) return;
    if (!state.channels.length) await refreshCache();
    state.selectedId = String(id);
    const channel = currentChannel();
    if (!channel) {
      setMessage("선택한 채널 정보를 찾을 수 없습니다.", "error");
      return;
    }

    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("lar-modal-open");
    renderChannel();
    dialog.focus({ preventScroll: true });
  }

  function closeModal(force) {
    if (!force && state.editing && state.dirty && !window.confirm("저장하지 않은 변경사항을 닫을까요?")) return;
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lar-modal-open");
    state.selectedId = null;
    setEditing(false);
    setMessage("", "");
  }

  async function saveChannel(event) {
    event.preventDefault();
    if (!state.editing || !state.selectedId) return;

    const channel = currentChannel();
    if (!channel) return;
    const name = fields.name.value.trim();
    const outputDir = fields.outputDir.value.trim();
    if (!name || !outputDir) {
      setMessage("채널명과 저장 경로를 입력하세요.", "error");
      return;
    }

    saveButton.disabled = true;
    saveButton.textContent = "저장 중…";
    setMessage("변경사항을 저장하고 있습니다.", "");

    try {
      const payload = {
        platform: channel.platform || "chzzk",
        name: name,
        output_dir: outputDir,
        quality: fields.quality.value,
        extension: fields.extension.value,
        recordWatchParty: fields.watchParty.value === "true",
        watchPartyExcludeTags: fields.tags.value.trim(),
      };

      const result = await requestJson("/api/channels/" + encodeURIComponent(state.selectedId), {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      if (result.status && result.status !== "success") throw new Error(result.message || "채널 수정에 실패했습니다.");

      if (fields.recordEnabled.checked !== state.originalRecordEnabled) {
        const toggleResult = await requestJson("/api/toggle_record_enabled/" + encodeURIComponent(state.selectedId), {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
        });
        if (toggleResult.status && toggleResult.status !== "success") {
          throw new Error(toggleResult.message || "자동녹화 설정 변경에 실패했습니다.");
        }
      }

      state.dirty = false;
      await refreshCache();
      renderChannel();
      setMessage("채널 설정을 저장했습니다.", "success");
      document.dispatchEvent(new CustomEvent("lar:channel-updated", { detail: { channelId: state.selectedId } }));
    } catch (error) {
      console.error("채널 설정 저장 오류:", error);
      setMessage(error.message || "채널 설정을 저장하지 못했습니다.", "error");
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = "변경사항 저장";
    }
  }

  list.addEventListener("click", function (event) {
    const row = event.target.closest(".ch-row");
    if (!row || !list.contains(row)) return;
    const id = row.dataset.channelId;
    if (id) openModal(id);
  });

  list.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const row = event.target.closest(".ch-row");
    if (!row || !row.dataset.channelId) return;
    event.preventDefault();
    openModal(row.dataset.channelId);
  });

  overlay.querySelectorAll("[data-modal-close]").forEach(function (button) {
    button.addEventListener("click", function () { closeModal(false); });
  });
  editButton.addEventListener("click", function () { setEditing(true); });
  cancelButton.addEventListener("click", function () { renderChannel(); });
  form.addEventListener("submit", saveChannel);
  form.addEventListener("input", function () { if (state.editing) state.dirty = true; });
  form.addEventListener("change", function () { if (state.editing) state.dirty = true; });
  fields.quality.addEventListener("change", function () {
    syncFormatOptions(fields.quality.value, fields.extension.value);
  });
  fields.watchParty.addEventListener("change", syncTagsEnabled);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) closeModal(false);
  });

  new MutationObserver(function () {
    window.requestAnimationFrame(decorateRows);
  }).observe(list, { childList: true, subtree: false });

  refreshCache();
  window.setInterval(refreshCache, 15000);
})();

;
// ===== Shared console UI =====
(function () {
  "use strict";

  const THEME_KEY = "lar-console-theme";
  const pageDescriptions = {
    "/": "녹화 상태, 저장소와 시스템 상태를 한눈에 확인합니다.",
    "/recording": "현재 녹화 상태와 시스템 사용량을 확인하고 채널별 녹화를 제어합니다.",
    "/config": "자동 녹화, 후처리, 파일명과 알림 설정을 관리합니다.",
    "/channels": "녹화 대상, 저장 경로, 화질과 파일 형식을 관리합니다.",
    "/cookies": "치지직과 유튜브 인증에 필요한 쿠키 정보를 관리합니다.",
    "/files": "녹화 파일을 찾고 이동하거나 이름을 변경하고 삭제합니다.",
    "/register": "콘솔을 사용할 관리자 계정을 생성합니다."
  };

  const nativeFetch = window.fetch.bind(window);
  let dirtyOwner = null;
  let dirtyBar = null;

  function currentPath() {
    const value = location.pathname.replace(/\/$/, "");
    return value || "/";
  }

  function forceLightTheme() {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
    try { localStorage.setItem(THEME_KEY, "light"); } catch (_) {}
  }

  function stripVersionFromTitle() {
    document.title = document.title
      .replace(/\s+v\d+\.\d+\.\d+(?:[.-][0-9A-Za-z.-]+)?\s*$/i, "")
      .trim() || "Live Auto Recorder";
  }

  function addPageIntro() {
    const heading = document.querySelector("#content > h1, #content > h2");
    const copy = pageDescriptions[currentPath()];
    if (!heading || !copy || heading.nextElementSibling?.classList.contains("lar-page-intro")) return;
    const intro = document.createElement("p");
    intro.className = "lar-page-intro";
    intro.textContent = copy;
    heading.insertAdjacentElement("afterend", intro);
  }

  function ensureBackdrop() {
    let backdrop = document.querySelector(".lar-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.className = "lar-backdrop";
      document.body.appendChild(backdrop);
    }
    return backdrop;
  }

  function setNavOpen(open) {
    const nav = document.getElementById("mySidenav");
    const menu = document.querySelector(".menu-icon");
    document.body.classList.toggle("lar-nav-open", open);
    nav?.classList.toggle("lar-open", open);
    menu?.setAttribute("aria-expanded", String(open));
  }

  function bindNav() {
    const menu = document.querySelector(".menu-icon");
    if (menu && menu.dataset.larBound !== "1") {
      menu.dataset.larBound = "1";
      menu.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setNavOpen(!document.body.classList.contains("lar-nav-open"));
      }, true);
    }

    const close = document.querySelector("#mySidenav .closebtn");
    if (close && close.dataset.larBound !== "1") {
      close.dataset.larBound = "1";
      close.addEventListener("click", function (event) {
        event.preventDefault();
        setNavOpen(false);
      }, true);
    }

    ensureBackdrop().addEventListener("click", function () { setNavOpen(false); });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setNavOpen(false);
    });
  }

  function toastRegion() {
    let region = document.querySelector(".lar-toast-region");
    if (!region) {
      region = document.createElement("div");
      region.className = "lar-toast-region";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    return region;
  }

  function toast(message, tone, action) {
    const item = document.createElement("div");
    item.className = "lar-toast";
    item.dataset.tone = tone || "info";

    const copy = document.createElement("span");
    copy.className = "lar-toast-message";
    copy.textContent = message;
    item.appendChild(copy);

    if (action && typeof action.run === "function") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "lar-toast-action";
      button.textContent = action.label || "다시 시도";
      button.addEventListener("click", function () {
        item.remove();
        action.run();
      });
      item.appendChild(button);
    }

    toastRegion().appendChild(item);
    window.setTimeout(function () { item.remove(); }, action ? 7000 : 3600);
    return item;
  }

  function feedbackMessage(url) {
    const value = String(url || "");
    if (/channels/i.test(value)) return "채널 정보가 저장되었습니다.";
    if (/config/i.test(value)) return "설정이 저장되었습니다.";
    if (/cookie/i.test(value)) return "쿠키 정보가 저장되었습니다.";
    if (/record/i.test(value)) return "녹화 요청이 처리되었습니다.";
    if (/file|move|rename|mkdir/i.test(value)) return "파일 작업이 처리되었습니다.";
    return "요청이 처리되었습니다.";
  }

  function installFetchFeedback() {
    window.fetch = function (input, init) {
      const request = input instanceof Request ? input : null;
      const method = String(init?.method || request?.method || "GET").toUpperCase();
      const url = String(request?.url || input || "");
      const silent = /\/api\/sys_metrics|\/ws\/sys_metrics|recording_history/i.test(url);

      return nativeFetch(input, init).then(function (response) {
        if (!silent && method !== "GET") {
          if (response.ok) toast(feedbackMessage(url), "success");
          else toast("요청 처리에 실패했습니다. (" + response.status + ")", "error");
        } else if (!silent && method === "GET" && response.status >= 500) {
          toast("데이터를 불러오지 못했습니다.", "error", {
            label: "새로고침",
            run: function () { location.reload(); }
          });
        }
        return response;
      }).catch(function (error) {
        if (!silent) {
          toast("서버에 연결할 수 없습니다.", "error", {
            label: "다시 시도",
            run: function () { location.reload(); }
          });
        }
        throw error;
      });
    };
  }

  function confirmDialog() {
    let dialog = document.querySelector("dialog.lar-confirm");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "lar-confirm";
    dialog.innerHTML = '<form method="dialog" class="lar-confirm-body"><h2 class="lar-confirm-title">작업을 진행할까요?</h2><p class="lar-confirm-copy"></p><div class="lar-confirm-actions"><button value="cancel" class="lar-confirm-cancel">취소</button><button value="confirm" class="lar-confirm-danger">진행</button></div></form>';
    document.body.appendChild(dialog);
    return dialog;
  }

  function askConfirmation(message) {
    const dialog = confirmDialog();
    dialog.querySelector(".lar-confirm-copy").textContent = message;
    return new Promise(function (resolve) {
      const done = function () {
        dialog.removeEventListener("close", done);
        resolve(dialog.returnValue === "confirm");
      };
      dialog.addEventListener("close", done);
      if (typeof dialog.showModal === "function") dialog.showModal();
      else resolve(window.confirm(message));
    });
  }

  function bindConfirmations() {
    document.addEventListener("click", function (event) {
      const target = event.target.closest("#stop-all-recording,.delete-channel,.delete-file,[data-action='delete']");
      if (!target) return;
      if (target.dataset.larConfirmed === "1") {
        delete target.dataset.larConfirmed;
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      const message = target.id === "stop-all-recording"
        ? "진행 중인 모든 녹화를 중지합니다. 현재 파일이 마무리될 때까지 잠시 걸릴 수 있습니다."
        : "삭제한 항목은 복구하기 어려울 수 있습니다. 계속 진행하시겠습니까?";

      askConfirmation(message).then(function (confirmed) {
        if (!confirmed) return;
        target.dataset.larConfirmed = "1";
        target.click();
      });
    }, true);
  }

  function dirtyBarElement() {
    if (dirtyBar) return dirtyBar;
    dirtyBar = document.createElement("div");
    dirtyBar.className = "lar-dirty-bar";
    dirtyBar.hidden = true;
    dirtyBar.innerHTML = '<strong>저장되지 않은 변경사항이 있습니다.</strong><button type="button">변경사항 저장</button>';
    dirtyBar.querySelector("button").addEventListener("click", function () {
      if (!dirtyOwner) return;
      const form = dirtyOwner.matches("form") ? dirtyOwner : dirtyOwner.closest("form");
      if (form?.requestSubmit) form.requestSubmit();
      else dirtyOwner.querySelector(".edit-channel,button[type='submit'],input[type='submit']")?.click();
    });
    document.body.appendChild(dirtyBar);
    return dirtyBar;
  }

  function markDirty(owner) {
    dirtyOwner = owner;
    owner.classList.add("lar-dirty");
    dirtyBarElement().hidden = false;
  }

  function clearDirty(owner) {
    owner?.classList.remove("lar-dirty");
    if (!owner || dirtyOwner === owner) {
      dirtyOwner = null;
      dirtyBarElement().hidden = true;
    }
  }

  function bindDirtyTracking(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll("#configForm,#updateCookiesForm,.channel-edit-form").forEach(function (owner) {
      if (owner.dataset.larDirtyBound === "1") return;
      owner.dataset.larDirtyBound = "1";
      ["input", "change"].forEach(function (type) {
        owner.addEventListener(type, function (event) {
          if (event.target.matches("input,select,textarea")) markDirty(owner);
        });
      });
      owner.addEventListener("submit", function () { clearDirty(owner); });
      owner.querySelectorAll(".edit-channel").forEach(function (button) {
        button.addEventListener("click", function () { clearDirty(owner); });
      });
    });
  }

  function bindSubmitState(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll("form").forEach(function (form) {
      if (form.dataset.larSubmitBound === "1") return;
      form.dataset.larSubmitBound = "1";
      form.addEventListener("submit", function () {
        const button = form.querySelector("button[type='submit'],input[type='submit']");
        if (!button || button.disabled) return;
        const original = button.value || button.textContent;
        requestAnimationFrame(function () {
          if (form.checkValidity && !form.checkValidity()) return;
          button.disabled = true;
          if (button.tagName === "INPUT") button.value = "저장 중...";
          else button.textContent = "저장 중...";
          window.setTimeout(function () {
            if (!document.body.contains(button)) return;
            button.disabled = false;
            if (button.tagName === "INPUT") button.value = original;
            else button.textContent = original;
          }, 8000);
        });
      });
    });
  }

  function enhanceA11y(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll(".error-message,.alert-error").forEach(function (node) {
      node.setAttribute("role", "alert");
      node.setAttribute("aria-live", "assertive");
    });
    host.querySelectorAll("[id*=status],[id*=message],.description").forEach(function (node) {
      if (!node.hasAttribute("aria-live")) node.setAttribute("aria-live", "polite");
    });
    host.querySelectorAll("table").forEach(function (table) {
      if (table.hasAttribute("aria-label")) return;
      const section = table.closest("section,.card,.config-section");
      const title = section?.querySelector("h1,h2,h3,.eyebrow");
      table.setAttribute("aria-label", title ? title.textContent.trim() : "데이터 표");
    });
    host.querySelectorAll("img:not([alt])").forEach(function (image) { image.alt = ""; });
  }

  function enhanceLongText(root) {
    const host = root?.querySelectorAll ? root : document;
    host.querySelectorAll(".channel-output,.channel-quality,[id^='filename-'],.td-file,.file-name,.file-path,.path-cell,[data-path]").forEach(function (node) {
      if (node.dataset.larEllipsis === "1") return;
      node.dataset.larEllipsis = "1";
      node.classList.add("lar-ellipsis");
      node.title = node.textContent.trim();
      node.tabIndex = 0;
      const toggle = function () { node.classList.toggle("lar-expanded-text"); };
      node.addEventListener("click", toggle);
      node.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle();
        }
      });
    });
  }

  function installSkeletons() {
    const metrics = document.querySelectorAll("#cpu-percent,#mem-percent,#net-rate,.tile-value");
    metrics.forEach(function (node) { node.classList.add("lar-skeleton"); });
    window.addEventListener("lar:sys-metrics", function () {
      metrics.forEach(function (node) { node.classList.remove("lar-skeleton"); });
    }, { once: true });
    window.setTimeout(function () {
      metrics.forEach(function (node) { node.classList.remove("lar-skeleton"); });
    }, 5000);
  }

  function mountOf(disk) {
    return String(disk?.mountpoint || disk?.mount || disk?.label || disk?.device || "");
  }

  function compactMetrics(payload) {
    const cpuName = document.getElementById("cpu-name");
    if (cpuName) {
      const actual = payload?.cpu?.name || payload?.cpu_name || cpuName.textContent;
      if (actual && actual !== "사용률") cpuName.title = actual;
      cpuName.textContent = "사용률";
    }
    const networkBrief = document.getElementById("net-brief");
    if (networkBrief) networkBrief.textContent = "실시간 송수신";

    const disks = Array.isArray(payload?.disks) ? payload.disks : [];
    const chosen = disks.filter(function (disk) {
      const mount = mountOf(disk);
      return Number(disk?.total) > 0 && !/^\/(etc|proc|sys|dev)(\/|$)/.test(mount);
    }).sort(function (a, b) {
      function score(disk) {
        const mount = mountOf(disk).toLowerCase();
        let value = Number(disk?.total) || 0;
        if (mount === "/app/chzzk") value += 1e18;
        else if (/chzzk|record/.test(mount)) value += 5e17;
        return value;
      }
      return score(b) - score(a);
    })[0];

    const chosenMount = mountOf(chosen);
    let primary = null;
    document.querySelectorAll("#disk-row-1 .tile.disk,#disk-row-2 .tile.disk").forEach(function (node) {
      const key = node.dataset.larDiskKey || node.querySelector(".tile-title")?.textContent.trim() || "";
      const selected = !!chosen && key === chosenMount;
      node.classList.toggle("lar-primary-storage", selected);
      node.hidden = !selected;
      if (selected) primary = node;
    });

    const row1 = document.getElementById("disk-row-1");
    const row2 = document.getElementById("disk-row-2");
    if (primary && row1) {
      row1.prepend(primary);
      const title = primary.querySelector(".tile-title");
      const sub = primary.querySelector(".tile-sub");
      if (title) title.textContent = "녹화 저장소";
      if (sub) sub.textContent = chosenMount || "/app/chzzk";
      row1.hidden = false;
    }
    if (row2) row2.hidden = true;
  }

  function observeDynamicContent() {
    const pending = new Set();
    let scheduled = false;
    const observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (node.nodeType === Node.ELEMENT_NODE) pending.add(node);
        });
      });
      if (!pending.size || scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        pending.forEach(function (node) {
          enhanceA11y(node);
          enhanceLongText(node);
          bindSubmitState(node);
          bindDirtyTracking(node);
        });
        pending.clear();
        scheduled = false;
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    forceLightTheme();
    stripVersionFromTitle();
    document.body.classList.add("lar-ui-v3");
    addPageIntro();
    bindNav();
    installFetchFeedback();
    bindConfirmations();
    bindSubmitState(document);
    bindDirtyTracking(document);
    enhanceA11y(document);
    enhanceLongText(document);
    installSkeletons();
    observeDynamicContent();

    window.addEventListener("offline", function () { toast("네트워크 연결이 끊어졌습니다.", "error"); });
    window.addEventListener("online", function () { toast("네트워크가 다시 연결되었습니다.", "success"); });
    window.addEventListener("beforeunload", function (event) {
      if (!dirtyOwner) return;
      event.preventDefault();
      event.returnValue = "";
    });
    window.addEventListener("lar:sys-metrics", function (event) {
      requestAnimationFrame(function () { compactMetrics(event.detail || {}); });
    });

    window.LiveAutoRecorderUI = { toast: toast, setTheme: forceLightTheme };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();

;
// ===== Recording live metadata =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-recording")) return;

  const ACTIVE_REFRESH_MS = 10000;
  const MIN_REQUEST_GAP_MS = 7000;
  const PLACEHOLDER_RETRY_MS = 4000;
  const placeholderTitles = new Set([
    "",
    "방송 준비 중",
    "방송 제목 없음",
    "불러오는 중...",
    "정보 없음",
  ]);
  const lastRequestedAt = new Map();
  const inFlight = new Map();
  const retryTimers = new Map();
  const placeholderRetryCount = new Map();

  function isRecordingCard(card) {
    const text = card.querySelector(".channel-name")?.textContent || "";
    return text.includes("녹화 중") || text.includes("예약녹화 중");
  }

  function metadataTitle(metadata) {
    return String(
      metadata?.live_title ||
      metadata?.liveTitle ||
      metadata?.video_title ||
      metadata?.title ||
      ""
    ).trim();
  }

  function metadataCategory(metadata) {
    return String(
      metadata?.category ||
      metadata?.liveCategoryValue ||
      metadata?.category_name ||
      metadata?.game_name ||
      ""
    ).trim();
  }

  function applyMetadata(card, metadata) {
    const channelId = card.dataset.channelId || "";
    const title = metadataTitle(metadata);
    const category = metadataCategory(metadata);
    const adult = Boolean(metadata?.adult);

    const titleNode = document.getElementById(`title-${channelId}`) || card.querySelector(".channel-title, .title");
    if (titleNode && title && !placeholderTitles.has(title)) {
      titleNode.textContent = adult ? `${title} (연령제한)` : title;
      titleNode.dataset.larLiveTitle = "current";
      placeholderRetryCount.delete(channelId);
    }

    const categoryNode = document.getElementById(`category-${channelId}`) || card.querySelector(".channel-category, .category");
    if (categoryNode && category && category !== "카테고리 없음") {
      categoryNode.innerHTML = `<strong>카테고리</strong>: ${category}`;
    }

    const thumbnail = metadata?.thumbnail_url || metadata?.thumbnailUrl || metadata?.thumbnail;
    const thumbnailNode = document.getElementById(`thumbnail-${channelId}`) || card.querySelector("img.channel-thumbnail, img.thumbnail, .thumb img");
    if (thumbnailNode && typeof thumbnail === "string" && /^https?:\/\//.test(thumbnail)) {
      thumbnailNode.src = thumbnail;
    }

    return title;
  }

  function schedulePlaceholderRetry(card) {
    const channelId = card.dataset.channelId || "";
    const retries = placeholderRetryCount.get(channelId) || 0;
    if (!channelId || retries >= 1 || retryTimers.has(channelId) || !isRecordingCard(card)) return;

    placeholderRetryCount.set(channelId, retries + 1);
    const timer = window.setTimeout(function () {
      retryTimers.delete(channelId);
      refreshCard(card, true);
    }, PLACEHOLDER_RETRY_MS);
    retryTimers.set(channelId, timer);
  }

  async function refreshCard(card, force) {
    const channelId = card.dataset.channelId || "";
    if (!channelId || !isRecordingCard(card)) return;

    const now = Date.now();
    if (!force && now - (lastRequestedAt.get(channelId) || 0) < MIN_REQUEST_GAP_MS) return;
    if (inFlight.has(channelId)) return inFlight.get(channelId);

    lastRequestedAt.set(channelId, now);
    const request = fetch(`/api/update_metadata/${encodeURIComponent(channelId)}`, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (!response.ok) throw new Error(`metadata HTTP ${response.status}`);
        return response.json();
      })
      .then(function (payload) {
        const metadata = payload?.metadata || {};
        const title = applyMetadata(card, metadata);
        if (placeholderTitles.has(title) && isRecordingCard(card)) {
          schedulePlaceholderRetry(card);
        }
      })
      .catch(function (error) {
        console.warn(`[recording-meta] ${channelId} 갱신 실패`, error);
      })
      .finally(function () {
        inFlight.delete(channelId);
      });

    inFlight.set(channelId, request);
    return request;
  }

  function refreshRecordingCards(force) {
    if (document.visibilityState === "hidden") return;
    document.querySelectorAll(".channel[data-channel-id]").forEach(function (card) {
      if (isRecordingCard(card)) refreshCard(card, force);
    });
  }

  function watchRecordingTransitions() {
    const list = document.getElementById("channel-list");
    if (!list) return;

    const observer = new MutationObserver(function (mutations) {
      const cards = new Set();
      mutations.forEach(function (mutation) {
        const target = mutation.target instanceof Element
          ? mutation.target
          : mutation.target.parentElement;
        const statusNode = target?.closest?.(".channel-name");
        if (!statusNode) return;
        const card = statusNode.closest(".channel[data-channel-id]");
        if (card) cards.add(card);
      });
      cards.forEach(function (card) {
        if (isRecordingCard(card)) {
          placeholderRetryCount.delete(card.dataset.channelId || "");
          refreshCard(card, true);
        }
      });
    });

    observer.observe(list, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  }

  function boot() {
    watchRecordingTransitions();
    refreshRecordingCards(true);
    window.setInterval(function () {
      refreshRecordingCards(false);
    }, ACTIVE_REFRESH_MS);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") refreshRecordingCards(true);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();

;
// ===== Config workspace =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  if (!form || form.dataset.larWorkspaceReady === "true") return;
  form.dataset.larWorkspaceReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const sectionNumber = (section) => ($(".section-num", section)?.textContent || "").trim().padStart(2, "0");
  const sectionTitle = (section) => ($(".section-head h3", section)?.textContent || "설정").trim();
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value).toLowerCase());
  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[char]));

  function dispatchChange(control) {
    control.dispatchEvent(new Event("change", { bubbles: true }));
    control.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function unwrapLegacyGrid() {
    const legacy = $(".lar-config-masonry-grid", form);
    if (!legacy) return;
    const marker = document.createDocumentFragment();
    $$(":scope > .config-section", legacy).forEach((section) => {
      section.style.removeProperty("grid-row-end");
      marker.appendChild(section);
    });
    legacy.replaceWith(marker);
  }

  function wrapSectionFields(section) {
    if (!section || section.dataset.larFieldsWrapped === "true") return;
    section.dataset.larFieldsWrapped = "true";
    const head = $(".section-head", section);
    const nodes = Array.from(section.children).filter((node) => node !== head);
    let current = null;

    nodes.forEach((node) => {
      if (node.matches && node.matches("label")) {
        current = document.createElement("div");
        current.className = "lar-setting-row";
        section.insertBefore(current, node);
      }
      if (current) current.appendChild(node);
      else node.classList?.add("lar-section-lead");
    });

    $$("select", section).forEach((select) => {
      const values = Array.from(select.options).map((option) => String(option.value).toLowerCase());
      if (values.includes("true") && values.includes("false")) select.classList.add("lar-boolean-select");
    });
  }

  function settingRow(controlId) {
    return document.getElementById(controlId)?.closest(".lar-setting-row") || null;
  }

  function moveSetting(controlId, targetSection) {
    const row = settingRow(controlId);
    if (row && targetSection) targetSection.appendChild(row);
    return row;
  }

  function setRowVisible(controlId, visible) {
    const row = settingRow(controlId);
    if (!row) return;
    row.hidden = !visible;
    row.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function enhanceHelp(section) {
    if (!section) return;
    $$("table.description", section).forEach((table) => {
      if (table.closest("details")) return;
      const details = document.createElement("details");
      details.className = "lar-help-details";
      const summary = document.createElement("summary");
      summary.textContent = "권장값과 호환 정보 보기";
      table.replaceWith(details);
      details.append(summary, table);
    });

    $$("p.description", section).forEach((paragraph) => {
      if (paragraph.closest("details") || paragraph.textContent.trim().length < 180) return;
      const details = document.createElement("details");
      details.className = "lar-help-details";
      const summary = document.createElement("summary");
      summary.textContent = /텔레그램|웹훅|BotFather|Discord/i.test(paragraph.textContent)
        ? "연결 방법 보기"
        : "자세한 설명 보기";
      paragraph.replaceWith(details);
      details.append(summary, paragraph);
    });
  }

  function renameSection(section, title, subtitle) {
    if (!section) return;
    const heading = $(".section-head h3", section);
    const tag = $(".section-tag", section);
    if (heading) heading.textContent = title;
    if (tag) tag.textContent = subtitle || "";
  }

  unwrapLegacyGrid();
  const formSections = $$(".config-section", form);
  formSections.forEach(wrapSectionFields);

  const sections = Object.fromEntries(formSections.map((section) => [sectionNumber(section), section]));
  renameSection(sections["01"], "녹화 기본 설정", "Recording");
  renameSection(sections["02"], "치지직 플러그인", "CHZZK");
  renameSection(sections["03"], "후처리", "Post-processing");
  renameSection(sections["04"], "분할 녹화", "Split recording");
  renameSection(sections["05"], "인코딩", "Encoding");
  renameSection(sections["06"], "Telegram", "Notifications");
  renameSection(sections["07"], "Discord", "Notifications");
  renameSection(sections["08"], "파일 관리자", "Files");
  renameSection(sections["09"], "로그인과 보안", "Security");

  moveSetting("recheckInterval", sections["01"]);
  moveSetting("filenamePattern", sections["01"]);
  formSections.forEach(enhanceHelp);

  const groupDefinitions = [
    { id: "basic", label: "기본 녹화", hint: "자동녹화·탐색·파일명", sections: ["01"] },
    { id: "chzzk", label: "치지직", hint: "플러그인·분할 녹화", sections: ["02", "04"] },
    { id: "processing", label: "후처리·인코딩", hint: "파일 처리·압축", sections: ["03", "05"] },
    { id: "notifications", label: "알림", hint: "Telegram·Discord", sections: ["06", "07"] },
    { id: "system", label: "시스템·보안", hint: "파일·로그인·계정", sections: ["08", "09"] }
  ];

  const workspace = document.createElement("div");
  workspace.className = "lar-config-workspace";
  const tabs = document.createElement("nav");
  tabs.className = "lar-config-tabs";
  tabs.setAttribute("aria-label", "설정 분류");
  const panels = document.createElement("div");
  panels.className = "lar-config-panels";
  const panelMap = new Map();

  groupDefinitions.forEach((group, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-config-tab";
    button.dataset.configTab = group.id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", index === 0 ? "true" : "false");
    button.innerHTML = `<strong>${escapeHtml(group.label)}</strong><small>${escapeHtml(group.hint)}</small>`;
    tabs.appendChild(button);

    const panel = document.createElement("section");
    panel.className = "lar-config-panel" + (index === 0 ? " is-active" : "");
    panel.dataset.configPanel = group.id;
    panel.setAttribute("role", "tabpanel");
    panel.hidden = index !== 0;
    const grid = document.createElement("div");
    grid.className = "lar-config-panel-grid";
    group.sections.forEach((number) => {
      if (sections[number]) grid.appendChild(sections[number]);
    });
    panel.appendChild(grid);
    panels.appendChild(panel);
    panelMap.set(group.id, panel);
  });

  workspace.append(tabs, panels);
  form.prepend(workspace);

  const accountFields = document.getElementById("account-fields");
  const systemExtras = document.createElement("div");
  systemExtras.className = "lar-config-system-extras";
  systemExtras.hidden = true;
  if (accountFields) systemExtras.appendChild(accountFields);

  const maintenanceCard = document.createElement("section");
  maintenanceCard.className = "config-section lar-operations-link-card";
  maintenanceCard.innerHTML = `
    <header class="section-head"><h3>백업과 저장소 정리</h3><span class="section-tag">Operations</span></header>
    <p>설정 백업, 복원, 저장소 임계치와 파일 정리는 운영 관리에서 한 번에 관리합니다.</p>
    <a href="/operations" class="lar-inline-primary">운영 관리 열기</a>`;
  systemExtras.appendChild(maintenanceCard);
  form.insertAdjacentElement("afterend", systemExtras);

  $$(".config-section", document).forEach((section) => {
    const title = sectionTitle(section);
    const number = sectionNumber(section);
    if ((number === "11" || number === "12") || /설정 백업|녹화 파일 정리/.test(title)) {
      if (!section.closest(".lar-config-system-extras")) section.remove();
    }
  });

  function activateGroup(groupId, focus) {
    const id = panelMap.has(groupId) ? groupId : "basic";
    $$(".lar-config-tab", tabs).forEach((button) => {
      const active = button.dataset.configTab === id;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      if (active && focus) button.focus();
    });
    panelMap.forEach((panel, panelId) => {
      const active = panelId === id;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    systemExtras.hidden = id !== "system";
    try { localStorage.setItem("lar-config-tab", id); } catch (_) { /* ignore */ }
  }

  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-config-tab]");
    if (button) activateGroup(button.dataset.configTab, false);
  });
  tabs.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const buttons = $$("[data-config-tab]", tabs);
    const current = buttons.indexOf(document.activeElement);
    const next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
    activateGroup(buttons[next].dataset.configTab, true);
  });

  let savedTab = "basic";
  try { savedTab = localStorage.getItem("lar-config-tab") || "basic"; } catch (_) { /* ignore */ }
  activateGroup(savedTab, false);

  function addFilenamePreview() {
    const input = document.getElementById("filenamePattern");
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;
    const preview = document.createElement("div");
    preview.className = "lar-filename-preview";
    preview.innerHTML = '<span>예상 파일명</span><code></code>';
    row.appendChild(preview);
    const code = $("code", preview);
    const replacements = {
      recording_time: "260805_155400", start_time: "2026-08-05", safe_live_title: "오늘의 라이브 방송",
      channel_name: "샘플채널", record_quality: "1080p", frame_rate: "60fps", file_extension: ".ts"
    };
    const update = () => {
      let result = input.value || "{recording_time}_{channel_name}_{safe_live_title}";
      Object.entries(replacements).forEach(([key, value]) => {
        result = result.replace(new RegExp(`\\{${key}\\}`, "g"), value);
      });
      code.textContent = result;
    };
    input.addEventListener("input", update);
    update();
  }

  function addPathCheck() {
    const input = document.getElementById("moveAfterProcessing");
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;
    const actions = document.createElement("div");
    actions.className = "lar-field-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-secondary-button";
    button.textContent = "경로 확인";
    const result = document.createElement("span");
    result.className = "lar-field-result";
    result.setAttribute("role", "status");
    actions.append(button, result);
    row.appendChild(actions);
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "확인 중…";
      result.className = "lar-field-result";
      result.textContent = "";
      try {
        const response = await fetch("/api/config-tools/path-check", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: input.value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.message || "경로를 확인하지 못했습니다.");
        result.classList.add(data.writable ? "is-ok" : "is-error");
        result.textContent = `${data.message} 여유 ${data.free_gb} GB`;
      } catch (error) {
        result.classList.add("is-error");
        result.textContent = error.message;
      } finally {
        button.disabled = false;
        button.textContent = "경로 확인";
      }
    });
  }

  function setControlValue(id, value) {
    const control = document.getElementById(id);
    if (!control) return;
    const normalized = String(value);
    if (control.tagName === "SELECT" && !Array.from(control.options).some((option) => option.value === normalized)) return;
    control.value = normalized;
    dispatchChange(control);
  }

  function addEncodingTools() {
    const section = sections["05"];
    if (!section) return;
    const head = $(".section-head", section);
    const profileRow = document.createElement("div");
    profileRow.className = "lar-setting-row lar-profile-row";
    profileRow.innerHTML = `
      <label for="larEncodingProfile">인코딩 프로필</label>
      <select id="larEncodingProfile"><option value="custom">현재 설정 유지</option><option value="original">원본 유지</option><option value="balanced">균형</option><option value="saving">용량 절약</option><option value="quality">고화질</option></select>
      <p class="description">프로필을 고르면 기존 인코딩 필드에 안전한 기본값을 채웁니다. 세부값은 아래에서 다시 조정할 수 있습니다.</p>`;
    head.insertAdjacentElement("afterend", profileRow);
    const diagnostic = document.createElement("div");
    diagnostic.className = "lar-encoder-diagnostic";
    diagnostic.innerHTML = '<button type="button" class="lar-secondary-button">이 서버의 인코더 확인</button><div class="lar-encoder-result" role="status"></div>';
    profileRow.insertAdjacentElement("afterend", diagnostic);
    const profile = $("#larEncodingProfile", profileRow);
    let applying = false;
    const presets = {
      original: { stream_copy: "true", audio_bitrate: "copy" },
      balanced: { stream_copy: "false", video_codec: "libx264", use_bitrate_mode: "false", video_quality: "23", audio_codec: "aac", audio_bitrate: "copy", preset: "veryfast" },
      saving: { stream_copy: "false", video_codec: "libx265", use_bitrate_mode: "false", video_quality: "28", audio_codec: "aac", audio_bitrate: "128k", preset: "fast" },
      quality: { stream_copy: "false", video_codec: "libx264", use_bitrate_mode: "false", video_quality: "18", audio_codec: "aac", audio_bitrate: "192k", preset: "slow" }
    };
    profile.addEventListener("change", () => {
      const values = presets[profile.value];
      if (!values) return;
      applying = true;
      Object.entries(values).forEach(([id, value]) => { if (id !== "preset") setControlValue(id, value); });
      window.setTimeout(() => { setControlValue("preset", values.preset || ""); applying = false; }, 60);
    });
    ["stream_copy", "video_codec", "preset", "use_bitrate_mode", "video_quality", "video_bitrate", "audio_codec", "audio_bitrate"].forEach((id) => {
      document.getElementById(id)?.addEventListener("change", () => { if (!applying) profile.value = "custom"; });
    });
    const button = $("button", diagnostic);
    const result = $(".lar-encoder-result", diagnostic);
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "확인 중…";
      result.textContent = "";
      try {
        const response = await fetch("/api/config-tools/encoders");
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "인코더를 확인하지 못했습니다.");
        result.innerHTML = data.encoders.map((encoder) => `<span class="${encoder.available ? "is-ok" : "is-off"}">${escapeHtml(encoder.label)}</span>`).join("");
      } catch (error) {
        result.innerHTML = `<span class="is-error">${escapeHtml(error.message)}</span>`;
      } finally {
        button.disabled = false;
        button.textContent = "이 서버의 인코더 확인";
      }
    });
  }

  function addNotificationTabs() {
    const panel = panelMap.get("notifications");
    if (!panel || !sections["06"] || !sections["07"]) return;
    const grid = $(".lar-config-panel-grid", panel);
    grid.classList.add("lar-notification-grid");
    const nav = document.createElement("div");
    nav.className = "lar-notification-tabs";
    nav.innerHTML = '<button type="button" data-notification="06" class="is-active">Telegram</button><button type="button" data-notification="07">Discord</button>';
    grid.prepend(nav);
    const activate = (number) => {
      ["06", "07"].forEach((id) => { sections[id].hidden = id !== number; });
      $$("button", nav).forEach((button) => button.classList.toggle("is-active", button.dataset.notification === number));
    };
    nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-notification]");
      if (button) activate(button.dataset.notification);
    });
    activate(truthy(document.getElementById("telegram_enabled")?.value) ? "06" : "07");
  }

  function updateConditionalRows() {
    setRowVisible("enableTray", false);
    setRowVisible("postNewWindow", false);
    setRowVisible("timemachine_time_shift", document.getElementById("plugin_type")?.value === "timemachine_plus");
    const split = truthy(document.getElementById("splitRecordingMode")?.value);
    ["splitPostProcessing", "autoStopInterval", "splitOverlapSec"].forEach((id) => setRowVisible(id, split));
    const post = truthy(document.getElementById("autoPostProcessing")?.value);
    ["deleteAfterPostProcessing", "removeFixedPrefix", "moveAfterProcessingEnabled"].forEach((id) => setRowVisible(id, post));
    setRowVisible("moveAfterProcessing", post && truthy(document.getElementById("moveAfterProcessingEnabled")?.value));
    const streamCopy = truthy(document.getElementById("stream_copy")?.value);
    ["video_codec", "preset", "use_bitrate_mode", "video_quality", "video_bitrate", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options"].forEach((id) => setRowVisible(id, !streamCopy));
    if (!streamCopy) {
      const bitrate = truthy(document.getElementById("use_bitrate_mode")?.value);
      setRowVisible("video_quality", !bitrate);
      ["video_bitrate", "vbv_maxrate", "vbv_bufsize"].forEach((id) => setRowVisible(id, bitrate));
    }
    const telegram = truthy(document.getElementById("telegram_enabled")?.value);
    ["telegram_bot_token", "telegram_chat_id"].forEach((id) => setRowVisible(id, telegram));
    const telegramButton = document.getElementById("testTelegramBtn")?.closest(".lar-setting-row");
    if (telegramButton) telegramButton.hidden = !telegram;
    const discord = truthy(document.getElementById("discord_enabled")?.value);
    setRowVisible("discord_webhook_url", discord);
    const discordButton = document.getElementById("testDiscordBtn")?.closest(".lar-setting-row");
    if (discordButton) discordButton.hidden = !discord;
    const manager = truthy(document.getElementById("fileManagerEnabled")?.value);
    ["fileManagerMode", "fileManagerReadOnly", "trashEnabled"].forEach((id) => setRowVisible(id, manager));
    const roots = document.getElementById("fm-roots-section");
    if (roots) roots.hidden = !(manager && document.getElementById("fileManagerMode")?.value === "whitelist");
  }

  ["plugin_type", "splitRecordingMode", "autoPostProcessing", "moveAfterProcessingEnabled", "stream_copy", "use_bitrate_mode", "telegram_enabled", "discord_enabled", "fileManagerEnabled", "fileManagerMode"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", updateConditionalRows);
  });

  function serializeForm() {
    const values = {};
    new FormData(form).forEach((value, key) => {
      const normalized = value instanceof File ? value.name : String(value);
      if (Object.prototype.hasOwnProperty.call(values, key)) values[key] = Array.isArray(values[key]) ? values[key].concat(normalized) : [values[key], normalized];
      else values[key] = normalized;
    });
    return JSON.stringify(values);
  }

  function addSaveBar() {
    const originalSubmit = $("input[type='submit'], button[type='submit']", form);
    if (originalSubmit) originalSubmit.classList.add("lar-original-submit");
    const bar = document.createElement("div");
    bar.className = "lar-config-savebar";
    bar.innerHTML = '<div><strong>저장된 상태</strong><span>설정을 변경하면 여기에 표시됩니다.</span></div><div class="lar-config-save-actions"><button type="button" data-config-reset>변경 취소</button><button type="button" data-config-save class="lar-primary-button" disabled>설정 저장</button></div>';
    document.body.appendChild(bar);
    const title = $("strong", bar);
    const subtitle = $("span", bar);
    const reset = $("[data-config-reset]", bar);
    const save = $("[data-config-save]", bar);
    let baseline = "";
    let dirty = false;
    const update = () => {
      const next = serializeForm();
      dirty = Boolean(baseline && next !== baseline);
      bar.classList.toggle("is-dirty", dirty);
      save.disabled = !dirty;
      reset.disabled = !dirty;
      title.textContent = dirty ? "저장하지 않은 변경사항" : "저장된 상태";
      subtitle.textContent = dirty ? "검토한 뒤 저장하세요. 재시작이 필요한 항목은 저장 후 안내됩니다." : "현재 설정이 적용되어 있습니다.";
    };
    window.setTimeout(() => { baseline = serializeForm(); update(); }, 120);
    form.addEventListener("input", update, true);
    form.addEventListener("change", update, true);
    form.addEventListener("submit", () => { dirty = false; });
    reset.addEventListener("click", () => {
      form.reset();
      $$("select, input, textarea", form).forEach(dispatchChange);
      window.setTimeout(update, 20);
    });
    save.addEventListener("click", () => {
      if (originalSubmit) form.requestSubmit(originalSubmit);
      else form.requestSubmit();
    });
    window.addEventListener("beforeunload", (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    });
  }

  addFilenamePreview();
  addPathCheck();
  addEncodingTools();
  addNotificationTabs();
  updateConditionalRows();
  addSaveBar();
})();

;
// ===== Config safety =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  if (!form || form.dataset.larSafetyReady === "true") return;
  form.dataset.larSafetyReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value || "").toLowerCase());
  const helperNames = new Set([
    "danger_confirmation",
    "danger_current_password",
    "danger_ack",
    "telegram_bot_token_action",
    "telegram_chat_id_action",
    "discord_webhook_url_action"
  ]);
  const restartFields = new Set(["autoRecordingMode", "loginMode"]);
  const labels = {
    autoRecordingMode: "자동 녹화",
    plugin_type: "치지직 플러그인",
    timemachine_time_shift: "타임머신 시프트",
    recheckInterval: "방송 재탐색 주기",
    filenamePattern: "파일명 규칙",
    autoPostProcessing: "자동 후처리",
    moveAfterProcessing: "후처리 이동 경로",
    splitRecordingMode: "분할 녹화",
    autoStopInterval: "분할 시간",
    stream_copy: "후처리 방식",
    video_codec: "비디오 코덱",
    preset: "인코딩 프리셋",
    telegram_enabled: "Telegram 알림",
    discord_enabled: "Discord 알림",
    fileManagerEnabled: "파일 관리자",
    fileManagerMode: "파일 관리자 경로 모드",
    fileManagerReadOnly: "파일 관리자 읽기 전용",
    trashEnabled: "파일 관리자 휴지통",
    loginMode: "로그인 모드"
  };

  function dispatchChange(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function ensureHidden(name, value) {
    let input = form.elements.namedItem(name);
    if (!input || input instanceof RadioNodeList) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      form.appendChild(input);
    }
    input.value = value;
    input.defaultValue = value;
    return input;
  }

  function fieldLabel(control) {
    if (!control) return "설정";
    return labels[control.name]
      || $(`label[for="${CSS.escape(control.id || "")}"]`)?.textContent?.replace(/\s+/g, " ").trim()
      || control.name
      || control.id
      || "설정";
  }

  function setStatus(message, kind) {
    const bar = $(".lar-config-savebar");
    if (!bar) return;
    const title = $("strong", bar);
    const subtitle = $("span", bar);
    bar.classList.toggle("is-error", kind === "error");
    bar.classList.toggle("is-saving", kind === "saving");
    bar.classList.toggle("is-success", kind === "success");
    if (title) title.textContent = message;
    if (subtitle && kind === "error") subtitle.textContent = "입력값을 확인한 뒤 다시 저장하세요.";
    if (subtitle && kind === "saving") subtitle.textContent = "검증 후 설정 파일에 반영하고 있습니다.";
    if (subtitle && kind === "success") subtitle.textContent = "저장이 완료되어 화면을 이동합니다.";
  }

  function setupSecretField(id, title) {
    const input = document.getElementById(id);
    const row = input?.closest(".lar-setting-row");
    if (!input || !row) return;

    const configured = input.dataset.storedSecret === "true";
    const action = ensureHidden(`${id}_action`, configured ? "keep" : "replace");
    input.type = "password";
    input.autocomplete = "new-password";
    input.spellcheck = false;
    input.value = "";

    const shell = document.createElement("div");
    shell.className = "lar-secret-actions";
    const state = document.createElement("span");
    state.className = "lar-secret-state";
    state.setAttribute("role", "status");
    const change = document.createElement("button");
    change.type = "button";
    change.className = "lar-secondary-button";
    const reveal = document.createElement("button");
    reveal.type = "button";
    reveal.className = "lar-secondary-button";
    reveal.textContent = "표시";
    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "lar-danger-ghost";
    clear.textContent = "삭제";
    shell.append(state, change, reveal, clear);
    row.appendChild(shell);

    function render() {
      const mode = action.value;
      row.classList.toggle("is-secret-cleared", mode === "clear");
      if (mode === "keep") {
        input.disabled = true;
        input.value = "";
        input.placeholder = `${title} 저장됨`;
        state.textContent = "저장된 값을 그대로 사용합니다.";
        change.textContent = "변경";
        reveal.hidden = true;
        clear.hidden = !configured;
      } else if (mode === "clear") {
        input.disabled = true;
        input.value = "";
        input.placeholder = "저장 시 삭제됩니다";
        state.textContent = "저장하면 기존 값이 삭제됩니다.";
        change.textContent = configured ? "삭제 취소" : "입력";
        reveal.hidden = true;
        clear.hidden = true;
      } else {
        input.disabled = false;
        input.placeholder = `새 ${title} 입력`;
        state.textContent = configured ? "새 값을 입력하면 기존 값을 교체합니다." : "저장할 값을 입력하세요.";
        change.textContent = configured ? "변경 취소" : "입력 중";
        reveal.hidden = false;
        clear.hidden = !configured;
      }
      dispatchChange(action);
    }

    change.addEventListener("click", () => {
      if (action.value === "replace" && configured) action.value = "keep";
      else if (action.value === "clear" && configured) action.value = "keep";
      else action.value = "replace";
      render();
      if (action.value === "replace") input.focus();
    });
    clear.addEventListener("click", () => {
      action.value = "clear";
      render();
    });
    reveal.addEventListener("click", () => {
      input.type = input.type === "password" ? "text" : "password";
      reveal.textContent = input.type === "password" ? "표시" : "숨김";
    });
    input.addEventListener("input", () => {
      if (action.value !== "replace") {
        action.value = "replace";
        render();
      }
    });

    render();
  }

  function validationNode(input) {
    const row = input.closest(".lar-setting-row") || input.parentElement;
    let node = $(".lar-field-validation", row);
    if (!node) {
      node = document.createElement("div");
      node.className = "lar-field-validation";
      node.setAttribute("role", "status");
      row.appendChild(node);
    }
    return node;
  }

  function setValidation(input, message, kind) {
    const node = validationNode(input);
    node.textContent = message || "";
    node.className = `lar-field-validation${kind ? ` is-${kind}` : ""}`;
    input.setCustomValidity(kind === "error" ? message : "");
  }

  function configureNumber(id, options) {
    const input = document.getElementById(id);
    if (!input) return;
    input.type = "number";
    Object.entries(options).forEach(([key, value]) => {
      if (["warningBelow", "warningText"].includes(key)) return;
      input.setAttribute(key, String(value));
    });
    const validate = () => {
      if (input.disabled || input.value === "") {
        setValidation(input, "", "");
        return true;
      }
      const value = Number(input.value);
      const min = input.min === "" ? -Infinity : Number(input.min);
      const max = input.max === "" ? Infinity : Number(input.max);
      if (!Number.isFinite(value) || value < min || value > max) {
        setValidation(input, `${min}~${max} 범위의 값을 입력하세요.`, "error");
        return false;
      }
      if (options.warningBelow != null && value < options.warningBelow) {
        setValidation(input, options.warningText, "warning");
      } else {
        setValidation(input, "", "");
      }
      return true;
    };
    input.addEventListener("input", validate);
    input.addEventListener("change", validate);
    validate();
  }

  function setupNumericValidation() {
    configureNumber("timemachine_time_shift", { min: 0, max: 3600, step: 1 });
    configureNumber("recheckInterval", {
      min: 10,
      max: 86400,
      step: 1,
      warningBelow: 120,
      warningText: "짧은 탐색 주기는 요청 제한이나 방송 누락을 유발할 수 있습니다. 120초 이상을 권장합니다."
    });
    configureNumber("autoStopInterval", { min: 60, max: 604800, step: 1 });
    configureNumber("splitOverlapSec", { min: 0, max: 30, step: 1 });
    configureNumber("video_quality", { min: 0, max: 51, step: 1 });

    const plugin = document.getElementById("plugin_type");
    const shift = document.getElementById("timemachine_time_shift");
    const updateShiftLimit = () => {
      if (!shift) return;
      shift.max = plugin?.value === "timemachine_plus" ? "3600" : "10";
      shift.dispatchEvent(new Event("input", { bubbles: true }));
    };
    plugin?.addEventListener("change", updateShiftLimit);
    updateShiftLimit();

    ["video_bitrate", "vbv_maxrate", "vbv_bufsize"].forEach((id) => {
      const input = document.getElementById(id);
      if (!input) return;
      const validate = () => {
        const value = input.value.trim();
        if (!value && id !== "video_bitrate") {
          setValidation(input, "", "");
          return true;
        }
        if (!/^\d+(?:\.\d+)?[kKmM]$/.test(value)) {
          setValidation(input, "5000k 또는 8M 형식으로 입력하세요.", "error");
          return false;
        }
        setValidation(input, "", "");
        return true;
      };
      input.addEventListener("input", validate);
      validate();
    });
  }

  function setupFilenameValidation() {
    const input = document.getElementById("filenamePattern");
    if (!input) return;
    const allowed = new Set([
      "recording_time", "start_time", "safe_live_title", "channel_name",
      "record_quality", "frame_rate", "file_extension"
    ]);
    const validate = () => {
      const value = input.value.trim();
      const tokens = Array.from(value.matchAll(/\{([^{}]+)\}/g), (match) => match[1]);
      const unknown = tokens.filter((token) => !allowed.has(token));
      const withoutTokens = value.replace(/\{[^{}]+\}/g, "");
      if (!value) {
        setValidation(input, "파일명 규칙을 입력하세요.", "error");
        return false;
      }
      if (unknown.length || /[{}]/.test(withoutTokens)) {
        setValidation(input, `지원하지 않는 변수: ${unknown.join(", ") || "중괄호 형식 오류"}`, "error");
        return false;
      }
      if (/[\\/:*?"<>|]/.test(withoutTokens)) {
        setValidation(input, "파일명에 사용할 수 없는 문자(\\ / : * ? \" < > |)가 있습니다.", "error");
        return false;
      }
      setValidation(input, "", "");
      return true;
    };
    input.addEventListener("input", validate);
    validate();
  }

  async function checkPath(input, result, button) {
    const path = input.value.trim();
    if (!path) {
      result.className = "lar-field-result is-error";
      result.textContent = "경로를 입력하세요.";
      return;
    }
    button.disabled = true;
    button.textContent = "확인 중…";
    result.className = "lar-field-result";
    result.textContent = "";
    try {
      const response = await fetch("/api/config-tools/path-check", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ path })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.message || "경로를 확인하지 못했습니다.");
      result.classList.add(data.writable ? "is-ok" : "is-error");
      result.textContent = `${data.message} · 여유 ${data.free_gb} GB`;
    } catch (error) {
      result.classList.add("is-error");
      result.textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = "경로 확인";
    }
  }

  function enhanceRootRow(row) {
    if (row.dataset.larPathCheck === "true") return;
    const input = $("input[name='fileManagerRoots']", row);
    if (!input) return;
    row.dataset.larPathCheck = "true";
    row.classList.add("lar-root-row");
    const result = document.createElement("span");
    result.className = "lar-field-result lar-root-result";
    result.setAttribute("role", "status");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-secondary-button lar-root-check";
    button.textContent = "경로 확인";
    const remove = $(".rm-root", row);
    row.insertBefore(button, remove || null);
    row.appendChild(result);
    button.addEventListener("click", () => checkPath(input, result, button));
  }

  function setupRootPathChecks() {
    const host = document.getElementById("fm-roots-list");
    if (!host) return;
    const enhance = () => $$(".fm-root-row", host).forEach(enhanceRootRow);
    enhance();
    new MutationObserver(enhance).observe(host, { childList: true, subtree: true });
  }

  function dangerNote(controlId, message) {
    const control = document.getElementById(controlId);
    const row = control?.closest(".lar-setting-row");
    if (!control || !row) return null;
    let note = $(".lar-danger-note", row);
    if (!note) {
      note = document.createElement("div");
      note.className = "lar-danger-note";
      note.setAttribute("role", "alert");
      row.appendChild(note);
    }
    note.textContent = message;
    return note;
  }

  function setupDangerWarnings() {
    const login = document.getElementById("loginMode");
    const manager = document.getElementById("fileManagerEnabled");
    const mode = document.getElementById("fileManagerMode");
    const readOnly = document.getElementById("fileManagerReadOnly");
    const trash = document.getElementById("trashEnabled");

    const loginNote = dangerNote("loginMode", "로그인을 끄면 로컬 접속만 허용됩니다. 저장 시 현재 비밀번호와 확인 문구가 필요합니다.");
    const modeNote = dangerNote("fileManagerMode", "블랙리스트 모드는 허용 범위가 넓습니다. 공개·외부 접속 환경에서는 화이트리스트를 사용하세요.");
    const readNote = dangerNote("fileManagerReadOnly", "읽기 전용을 끄면 웹에서 이동·이름 변경·삭제가 가능해집니다.");
    const trashNote = dangerNote("trashEnabled", "휴지통을 끄면 삭제한 파일을 복구할 수 없습니다.");

    const update = () => {
      if (loginNote) loginNote.hidden = truthy(login?.value);
      if (modeNote) modeNote.hidden = !(truthy(manager?.value) && mode?.value === "blacklist");
      if (readNote) readNote.hidden = !(truthy(manager?.value) && !truthy(readOnly?.value));
      if (trashNote) trashNote.hidden = !(truthy(manager?.value) && !truthy(trash?.value));
    };
    [login, manager, mode, readOnly, trash].forEach((control) => control?.addEventListener("change", update));
    update();
  }

  function snapshot() {
    const values = new Map();
    const data = new FormData(form);
    data.forEach((value, key) => {
      if (helperNames.has(key)) return;
      const normalized = value instanceof File ? value.name : String(value);
      const current = values.get(key);
      if (current == null) values.set(key, normalized);
      else values.set(key, `${current}\u001f${normalized}`);
    });
    return values;
  }

  let baseline = snapshot();

  function changedFields() {
    const current = snapshot();
    const keys = new Set([...baseline.keys(), ...current.keys()]);
    return Array.from(keys).filter((key) => (baseline.get(key) || "") !== (current.get(key) || ""));
  }

  function setupChangeSummary() {
    const install = () => {
      const bar = $(".lar-config-savebar");
      const host = bar?.firstElementChild;
      if (!bar || !host) return false;
      let summary = $(".lar-config-change-summary", host);
      if (!summary) {
        summary = document.createElement("div");
        summary.className = "lar-config-change-summary";
        host.appendChild(summary);
      }
      const update = () => {
        const changed = changedFields();
        if (!changed.length) {
          summary.hidden = true;
          summary.textContent = "";
          return;
        }
        const restartCount = changed.filter((name) => restartFields.has(name)).length;
        const names = changed.slice(0, 4).map((name) => fieldLabel(form.elements.namedItem(name))).join(" · ");
        const extra = changed.length > 4 ? ` 외 ${changed.length - 4}개` : "";
        summary.hidden = false;
        summary.textContent = `변경 ${changed.length}개${restartCount ? ` · 재시작 필요 ${restartCount}개` : ""} — ${names}${extra}`;
      };
      form.addEventListener("input", () => window.setTimeout(update, 0), true);
      form.addEventListener("change", () => window.setTimeout(update, 0), true);
      update();
      return true;
    };
    if (!install()) window.setTimeout(install, 80);
  }

  function fileRisk(values) {
    return truthy(values.get("fileManagerEnabled")) && (
      values.get("fileManagerMode") === "blacklist"
      || !truthy(values.get("fileManagerReadOnly"))
      || !truthy(values.get("trashEnabled"))
    );
  }

  function currentValues() {
    const values = new Map();
    ["loginMode", "fileManagerEnabled", "fileManagerMode", "fileManagerReadOnly", "trashEnabled"].forEach((name) => {
      const control = form.elements.namedItem(name);
      values.set(name, control && !(control instanceof RadioNodeList) ? control.value : "");
    });
    return values;
  }

  function dangerTransitions() {
    const next = currentValues();
    const currentLogin = truthy(baseline.get("loginMode"));
    const nextLogin = truthy(next.get("loginMode"));
    const loginOff = currentLogin && !nextLogin;

    const baseRiskValues = new Map([
      ["fileManagerEnabled", baseline.get("fileManagerEnabled") || "false"],
      ["fileManagerMode", baseline.get("fileManagerMode") || "whitelist"],
      ["fileManagerReadOnly", baseline.get("fileManagerReadOnly") || "true"],
      ["trashEnabled", baseline.get("trashEnabled") || "true"]
    ]);
    const riskyFieldsChanged = ["fileManagerEnabled", "fileManagerMode", "fileManagerReadOnly", "trashEnabled"]
      .some((name) => (baseRiskValues.get(name) || "") !== (next.get(name) || ""));
    const riskyFileManager = fileRisk(next) && (!fileRisk(baseRiskValues) || riskyFieldsChanged);
    return { loginOff, riskyFileManager };
  }

  function buildDangerDialog() {
    let dialog = document.getElementById("lar-config-danger-dialog");
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.id = "lar-config-danger-dialog";
    dialog.className = "lar-config-danger-dialog";
    dialog.innerHTML = `
      <form method="dialog">
        <div class="lar-danger-dialog-head"><strong>위험 설정 확인</strong><button value="cancel" aria-label="닫기">×</button></div>
        <p data-danger-summary></p>
        <label data-danger-password-row>현재 비밀번호<input type="password" data-danger-password autocomplete="current-password"></label>
        <label>확인 문구 <code data-danger-phrase-label></code><input type="text" data-danger-phrase autocomplete="off"></label>
        <div class="lar-danger-dialog-actions"><button value="cancel">취소</button><button value="confirm" class="lar-danger-confirm">확인하고 적용</button></div>
      </form>`;
    document.body.appendChild(dialog);
    return dialog;
  }

  async function confirmDanger(transitions) {
    if (!transitions.loginOff && !transitions.riskyFileManager) return true;
    const expected = transitions.loginOff ? "로그인 해제" : "위험 설정 적용";
    const summary = [
      transitions.loginOff ? "로그인 보호를 해제합니다." : "",
      transitions.riskyFileManager ? "파일 관리자에서 넓은 경로 접근 또는 복구 불가능한 삭제를 허용합니다." : ""
    ].filter(Boolean).join(" ");

    const confirmation = ensureHidden("danger_confirmation", "");
    const password = ensureHidden("danger_current_password", "");
    const acknowledgement = ensureHidden("danger_ack", "");

    if (typeof HTMLDialogElement === "undefined") {
      const phrase = window.prompt(`${summary}\n확인 문구를 입력하세요: ${expected}`) || "";
      if (phrase !== expected) return false;
      const currentPassword = transitions.loginOff ? (window.prompt("현재 비밀번호를 입력하세요.") || "") : "";
      confirmation.value = phrase;
      password.value = currentPassword;
      acknowledgement.value = phrase;
      return !transitions.loginOff || Boolean(currentPassword);
    }

    const dialog = buildDangerDialog();
    $("[data-danger-summary]", dialog).textContent = summary;
    $("[data-danger-phrase-label]", dialog).textContent = expected;
    const passwordRow = $("[data-danger-password-row]", dialog);
    const passwordInput = $("[data-danger-password]", dialog);
    const phraseInput = $("[data-danger-phrase]", dialog);
    passwordRow.hidden = !transitions.loginOff;
    passwordInput.value = "";
    phraseInput.value = "";

    return new Promise((resolve) => {
      const onClose = () => {
        dialog.removeEventListener("close", onClose);
        const accepted = dialog.returnValue === "confirm"
          && phraseInput.value.trim() === expected
          && (!transitions.loginOff || Boolean(passwordInput.value));
        if (accepted) {
          confirmation.value = expected;
          password.value = passwordInput.value;
          acknowledgement.value = expected;
          dispatchChange(confirmation);
          dispatchChange(acknowledgement);
        }
        resolve(accepted);
      };
      dialog.addEventListener("close", onClose);
      dialog.showModal();
      phraseInput.focus();
    });
  }

  function validateAll() {
    $$("input, select, textarea", form).forEach((control) => {
      if (!control.disabled) control.dispatchEvent(new Event("input", { bubbles: true }));
    });
    if (!form.checkValidity()) {
      form.reportValidity();
      const invalid = $(":invalid", form);
      invalid?.focus();
      setStatus("저장할 수 없는 값이 있습니다", "error");
      return false;
    }
    return true;
  }

  function normalizedFormData() {
    const data = new FormData(form);
    if (!data.has("enableTray")) data.append("enableTray", "false");
    if (!data.has("timemachine_time_shift")) data.append("timemachine_time_shift", "0");
    [
      "autoPostProcessing", "deleteAfterPostProcessing", "removeFixedPrefix",
      "moveAfterProcessingEnabled", "postNewWindow", "stream_copy",
      "use_bitrate_mode", "splitRecordingMode", "fileManagerEnabled",
      "loginMode", "fileManagerReadOnly", "trashEnabled", "enableTray"
    ].forEach((name) => { if (!data.has(name)) data.append(name, "false"); });
    const mode = String(data.get("fileManagerMode") || "");
    if (!["blacklist", "whitelist"].includes(mode)) data.set("fileManagerMode", "whitelist");
    ["autoStopInterval", "splitOverlapSec"].forEach((name) => {
      if (String(data.get(name) || "") === "") data.delete(name);
    });
    [
      "moveAfterProcessing", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options",
      "telegram_enabled", "telegram_bot_token", "telegram_chat_id",
      "discord_enabled", "discord_webhook_url"
    ].forEach((name) => { if (!data.has(name)) data.append(name, ""); });
    return data;
  }

  let submitting = false;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (submitting) return;

    if (!validateAll()) return;
    const loginModeOn = document.getElementById("loginMode")?.value === "true";
    if (loginModeOn && form.dataset.hasAccount !== "1") {
      setStatus("로그인 모드를 켜려면 관리자 계정이 필요합니다", "error");
      window.location.href = "/register?need_account=1";
      return;
    }

    if (!await confirmDanger(dangerTransitions())) {
      setStatus("위험 설정 적용이 취소되었습니다", "error");
      return;
    }

    submitting = true;
    setStatus("설정을 저장하는 중", "saving");
    const saveButton = $("[data-config-save]", document);
    if (saveButton) saveButton.disabled = true;

    try {
      const payload = new URLSearchParams();
      normalizedFormData().forEach((value, key) => payload.append(key, String(value)));
      const response = await fetch(form.action || "/config", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "Accept": "application/json, text/html"
        },
        credentials: "same-origin",
        body: payload,
        redirect: "follow"
      });

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json")
          ? await response.json()
          : { message: "설정 저장 중 오류가 발생했습니다." };
        throw new Error(data.message || data.detail || "설정 저장 중 오류가 발생했습니다.");
      }

      setStatus("설정이 저장되었습니다", "success");
      baseline = snapshot();
      form.reset();
      $$("input, select, textarea", form).forEach(dispatchChange);
      const destination = response.redirected && response.url ? response.url : "/";
      window.setTimeout(() => window.location.replace(destination), 80);
    } catch (error) {
      setStatus(error.message || "설정 저장에 실패했습니다", "error");
      if (saveButton) saveButton.disabled = false;
      submitting = false;
    }
  }, true);

  setupSecretField("telegram_bot_token", "봇 토큰");
  setupSecretField("telegram_chat_id", "채팅 ID");
  setupSecretField("discord_webhook_url", "웹훅 URL");
  setupNumericValidation();
  setupFilenameValidation();
  setupRootPathChecks();
  setupDangerWarnings();
  baseline = snapshot();
  setupChangeSummary();
})();

;
// ===== Config overview =====
(function () {
  "use strict";

  if (!document.body.classList.contains("page-config")) return;

  const form = document.getElementById("configForm");
  const tabs = document.querySelector(".lar-config-tabs");
  const panelsHost = document.querySelector(".lar-config-panels");
  const systemExtras = document.querySelector(".lar-config-system-extras");
  if (!form || !tabs || !panelsHost || form.dataset.larOverviewReady === "true") return;
  form.dataset.larOverviewReady = "true";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const truthy = (value) => ["true", "1", "on", "yes"].includes(String(value || "").toLowerCase());
  const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", "\"": "&quot;"
  }[char]));
  const helperNames = new Set(["danger_confirmation", "danger_current_password", "danger_ack"]);
  const secretValueNames = new Set(["telegram_bot_token", "telegram_chat_id", "discord_webhook_url"]);
  const restartFields = new Set(["autoRecordingMode", "loginMode"]);
  const fieldNames = {
    autoRecordingMode: "자동 녹화",
    plugin_type: "치지직 플러그인",
    timemachine_time_shift: "타임머신 시프트",
    recheckInterval: "방송 재탐색 주기",
    filenamePattern: "파일명 규칙",
    autoPostProcessing: "자동 후처리",
    deleteAfterPostProcessing: "후처리 후 원본 삭제",
    removeFixedPrefix: "고정 접두사 제거",
    moveAfterProcessingEnabled: "후처리 후 파일 이동",
    moveAfterProcessing: "후처리 이동 경로",
    splitRecordingMode: "분할 녹화",
    splitPostProcessing: "분할 파일 후처리",
    autoStopInterval: "분할 시간",
    splitOverlapSec: "분할 겹침 시간",
    stream_copy: "후처리 방식",
    video_codec: "비디오 코덱",
    preset: "인코딩 프리셋",
    use_bitrate_mode: "비트레이트 모드",
    video_quality: "화질 값",
    video_bitrate: "비디오 비트레이트",
    vbv_maxrate: "최대 비트레이트",
    vbv_bufsize: "버퍼 크기",
    extra_ffmpeg_options: "FFmpeg 추가 옵션",
    audio_codec: "오디오 코덱",
    audio_bitrate: "오디오 비트레이트",
    telegram_enabled: "Telegram 알림",
    telegram_bot_token_action: "Telegram 봇 토큰",
    telegram_chat_id_action: "Telegram 채팅 ID",
    discord_enabled: "Discord 알림",
    discord_webhook_url_action: "Discord 웹훅",
    fileManagerEnabled: "파일 관리자",
    fileManagerMode: "파일 접근 범위",
    fileManagerReadOnly: "읽기 전용",
    trashEnabled: "휴지통",
    fileManagerRoots: "허용 경로",
    loginMode: "로그인 보호"
  };

  function emit(control) {
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function sectionNumber(section) {
    return ($(".section-num", section)?.textContent || "").trim().padStart(2, "0");
  }

  function findSection(number) {
    return $$(".config-section", document).find((section) => sectionNumber(section) === number) || null;
  }

  function buildInformationArchitecture() {
    const securityButton = $("[data-config-tab='system']", tabs);
    const securityPanel = $("[data-config-panel='system']", panelsHost);
    const fileSection = findSection("08");
    if (!securityButton || !securityPanel || !fileSection) return;

    securityButton.dataset.configTab = "security";
    $("strong", securityButton).textContent = "접속 보안";
    $("small", securityButton).textContent = "로그인·계정";
    securityPanel.dataset.configPanel = "security";

    const filesButton = document.createElement("button");
    filesButton.type = "button";
    filesButton.className = "lar-config-tab";
    filesButton.dataset.configTab = "files";
    filesButton.setAttribute("role", "tab");
    filesButton.innerHTML = "<strong>파일 관리</strong><small>접근 범위·삭제 정책</small>";
    tabs.insertBefore(filesButton, securityButton);

    const filesPanel = document.createElement("section");
    filesPanel.className = "lar-config-panel";
    filesPanel.dataset.configPanel = "files";
    filesPanel.setAttribute("role", "tabpanel");
    filesPanel.hidden = true;
    const filesGrid = document.createElement("div");
    filesGrid.className = "lar-config-panel-grid lar-config-files-grid";
    filesGrid.appendChild(fileSection);
    filesPanel.appendChild(filesGrid);
    panelsHost.insertBefore(filesPanel, securityPanel);

    tabs.setAttribute("role", "tablist");
    $$(".lar-config-tab", tabs).forEach((button, index) => {
      const id = button.dataset.configTab;
      button.id = `lar-config-tab-${id}`;
      button.setAttribute("aria-controls", `lar-config-panel-${id}`);
      button.tabIndex = index === 0 ? 0 : -1;
    });
    $$(".lar-config-panel", panelsHost).forEach((panel) => {
      const id = panel.dataset.configPanel;
      panel.id = `lar-config-panel-${id}`;
      panel.setAttribute("aria-labelledby", `lar-config-tab-${id}`);
    });

    function activate(id, focus) {
      const available = new Set($$(".lar-config-tab", tabs).map((button) => button.dataset.configTab));
      const target = available.has(id) ? id : "basic";
      $$(".lar-config-tab", tabs).forEach((button) => {
        const active = button.dataset.configTab === target;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus();
      });
      $$(".lar-config-panel", panelsHost).forEach((panel) => {
        const active = panel.dataset.configPanel === target;
        panel.hidden = !active;
        panel.classList.toggle("is-active", active);
      });
      if (systemExtras) systemExtras.hidden = target !== "security";
      try { localStorage.setItem("lar-config-tab", target); } catch (_) { /* ignore */ }
    }

    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-config-tab]");
      if (!button) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      activate(button.dataset.configTab, false);
    }, true);

    tabs.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const buttons = $$("[data-config-tab]", tabs);
      const current = Math.max(0, buttons.indexOf(document.activeElement));
      let next = current;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else next = (current + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      activate(buttons[next].dataset.configTab, true);
    }, true);

    let saved = "basic";
    try { saved = localStorage.getItem("lar-config-tab") || "basic"; } catch (_) { /* ignore */ }
    if (saved === "system") saved = "security";
    activate(saved, false);
  }

  function setupBooleanSwitches() {
    $$("select", form).forEach((select) => {
      const values = Array.from(select.options).map((option) => String(option.value).toLowerCase());
      if (!values.includes("true") || !values.includes("false") || select.dataset.larSwitch === "true") return;
      select.dataset.larSwitch = "true";
      select.classList.add("lar-switch-source");

      const label = select.id ? $(`label[for='${CSS.escape(select.id)}']`) : null;
      if (label && !label.id) label.id = `lar-label-${select.id}`;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "lar-setting-switch";
      button.setAttribute("role", "switch");
      if (label?.id) button.setAttribute("aria-labelledby", label.id);
      button.innerHTML = '<span class="lar-switch-track" aria-hidden="true"><span></span></span><strong></strong>';
      select.insertAdjacentElement("afterend", button);

      const render = () => {
        const enabled = truthy(select.value);
        button.setAttribute("aria-checked", enabled ? "true" : "false");
        button.classList.toggle("is-on", enabled);
        button.disabled = select.disabled;
        $("strong", button).textContent = enabled ? "ON" : "OFF";
      };
      button.addEventListener("click", () => {
        if (button.disabled) return;
        select.value = truthy(select.value) ? "false" : "true";
        emit(select);
      });
      select.addEventListener("change", render);
      new MutationObserver(render).observe(select, { attributes: true, attributeFilter: ["disabled"] });
      render();
    });
  }

  function optionText(id) {
    const control = document.getElementById(id);
    if (!control) return "";
    if (control.tagName === "SELECT") return control.selectedOptions[0]?.textContent?.trim() || control.value;
    return control.value || "";
  }

  function encodingSummary() {
    const copy = truthy(document.getElementById("stream_copy")?.value);
    if (copy) {
      return {
        title: "원본 유지",
        detail: "재인코딩 없이 원본 영상과 음성을 유지합니다.",
        compact: "원본 유지"
      };
    }
    const codec = optionText("video_codec") || "비디오 인코딩";
    const bitrateMode = truthy(document.getElementById("use_bitrate_mode")?.value);
    const quality = bitrateMode
      ? (document.getElementById("video_bitrate")?.value || "비트레이트 미지정")
      : `화질 ${document.getElementById("video_quality")?.value || "-"}`;
    const audio = document.getElementById("audio_bitrate")?.value === "copy"
      ? "오디오 원본"
      : `${optionText("audio_codec")} ${optionText("audio_bitrate")}`.trim();
    return {
      title: `${codec} · ${quality}`,
      detail: `${optionText("preset")} 프리셋 · ${audio}`,
      compact: codec.replace(/\s*\([^)]*\)/g, "")
    };
  }

  function setupEncodingDisclosure() {
    const section = findSection("05");
    if (!section || section.dataset.larAdvancedEncoding === "true") return;
    section.dataset.larAdvancedEncoding = "true";

    const profileRow = $(".lar-profile-row", section);
    const diagnostic = $(".lar-encoder-diagnostic", section);
    const card = document.createElement("div");
    card.className = "lar-encoding-current";
    card.innerHTML = '<span>현재 적용 결과</span><strong></strong><p></p>';
    (diagnostic || profileRow || $(".section-head", section)).insertAdjacentElement("afterend", card);

    const details = document.createElement("details");
    details.className = "lar-encoding-advanced";
    details.innerHTML = '<summary><span><strong>고급 인코딩 설정</strong><small>코덱·화질·비트레이트·FFmpeg 옵션</small></span><em>펼치기</em></summary><div class="lar-encoding-advanced-body"></div>';
    card.insertAdjacentElement("afterend", details);
    const body = $(".lar-encoding-advanced-body", details);
    const advancedIds = [
      "stream_copy", "video_codec", "preset", "use_bitrate_mode", "video_quality",
      "video_bitrate", "vbv_maxrate", "vbv_bufsize", "extra_ffmpeg_options",
      "audio_codec", "audio_bitrate"
    ];
    advancedIds.forEach((id) => {
      const row = document.getElementById(id)?.closest(".lar-setting-row");
      if (row) body.appendChild(row);
    });

    const render = () => {
      const summary = encodingSummary();
      $("strong", card).textContent = summary.title;
      $("p", card).textContent = summary.detail;
      $("em", details).textContent = details.open ? "접기" : "펼치기";
    };
    details.addEventListener("toggle", render);
    advancedIds.forEach((id) => {
      document.getElementById(id)?.addEventListener("change", render);
      document.getElementById(id)?.addEventListener("input", render);
      document.getElementById(id)?.addEventListener("invalid", () => { details.open = true; }, true);
    });
    document.getElementById("larEncodingProfile")?.addEventListener("change", () => window.setTimeout(render, 80));
    render();
  }

  function secretConfigured(id) {
    const input = document.getElementById(id);
    if (!input) return false;
    const action = form.elements.namedItem(`${id}_action`);
    const mode = action && !(action instanceof RadioNodeList) ? action.value : "";
    if (mode === "clear") return false;
    if (mode === "replace") return Boolean(input.value.trim());
    return input.dataset.storedSecret === "true" || Boolean(input.value.trim());
  }

  function lastTestLabel(kind) {
    try {
      const raw = localStorage.getItem(`lar-${kind}-test-ok`);
      if (!raw) return "";
      const date = new Date(raw);
      if (Number.isNaN(date.getTime())) return "";
      return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")} 확인`;
    } catch (_) {
      return "";
    }
  }

  function setupNotificationState() {
    const nav = $(".lar-notification-tabs");
    if (!nav) return () => {};
    const buttons = {
      telegram: $("[data-notification='06']", nav),
      discord: $("[data-notification='07']", nav)
    };
    Object.values(buttons).forEach((button) => {
      if (!button || $(".lar-notification-status", button)) return;
      const status = document.createElement("span");
      status.className = "lar-notification-status";
      button.appendChild(status);
    });

    const update = () => {
      const telegramEnabled = truthy(document.getElementById("telegram_enabled")?.value);
      const telegramReady = secretConfigured("telegram_bot_token") && secretConfigured("telegram_chat_id");
      const discordEnabled = truthy(document.getElementById("discord_enabled")?.value);
      const discordReady = secretConfigured("discord_webhook_url");
      const states = [
        [buttons.telegram, telegramEnabled, telegramReady, lastTestLabel("telegram")],
        [buttons.discord, discordEnabled, discordReady, lastTestLabel("discord")]
      ];
      states.forEach(([button, enabled, ready, tested]) => {
        if (!button) return;
        const status = $(".lar-notification-status", button);
        button.classList.toggle("is-configured", enabled && ready);
        button.classList.toggle("is-incomplete", enabled && !ready);
        status.textContent = !enabled ? "사용 안 함" : ready ? (tested || "연결됨") : "설정 필요";
      });
    };

    ["telegram_enabled", "telegram_bot_token", "telegram_chat_id", "discord_enabled", "discord_webhook_url"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", update);
      document.getElementById(id)?.addEventListener("change", update);
      const action = form.elements.namedItem(`${id}_action`);
      if (action && !(action instanceof RadioNodeList)) action.addEventListener("change", update);
    });

    if (!window.__larNotificationFetchWrapped) {
      window.__larNotificationFetchWrapped = true;
      const nativeFetch = window.fetch.bind(window);
      window.fetch = async function (...args) {
        const response = await nativeFetch(...args);
        try {
          const url = String(args[0] instanceof Request ? args[0].url : args[0] || "");
          let kind = "";
          if (url.includes("/api/test_telegram")) kind = "telegram";
          if (url.includes("/api/discord_test")) kind = "discord";
          if (kind && response.ok) {
            const payload = await response.clone().json();
            if (payload.status === "success") {
              localStorage.setItem(`lar-${kind}-test-ok`, new Date().toISOString());
              window.setTimeout(update, 0);
            }
          }
        } catch (_) { /* keep fetch transparent */ }
        return response;
      };
    }
    update();
    return update;
  }

  function ensureTabStatus(button) {
    let status = $(".lar-tab-status", button);
    if (!status) {
      status = document.createElement("span");
      status.className = "lar-tab-status";
      button.appendChild(status);
    }
    return status;
  }

  function setupTabStatuses(updateNotifications) {
    const overview = document.createElement("div");
    overview.className = "lar-config-overview-line";
    overview.setAttribute("role", "status");
    overview.setAttribute("aria-live", "polite");
    tabs.insertAdjacentElement("afterend", overview);

    const set = (id, text, tone) => {
      const button = $(`[data-config-tab='${id}']`, tabs);
      if (!button) return;
      const status = ensureTabStatus(button);
      status.textContent = text;
      status.dataset.tone = tone || "neutral";
    };

    const update = () => {
      const auto = truthy(document.getElementById("autoRecordingMode")?.value);
      const plugin = document.getElementById("plugin_type")?.value === "timemachine_plus" ? "타임머신+" : "기본 모드";
      const encoding = encodingSummary();
      const telegram = truthy(document.getElementById("telegram_enabled")?.value)
        && secretConfigured("telegram_bot_token") && secretConfigured("telegram_chat_id");
      const discord = truthy(document.getElementById("discord_enabled")?.value) && secretConfigured("discord_webhook_url");
      const notificationCount = Number(telegram) + Number(discord);
      const manager = truthy(document.getElementById("fileManagerEnabled")?.value);
      const risks = manager ? [
        document.getElementById("fileManagerMode")?.value === "blacklist",
        !truthy(document.getElementById("fileManagerReadOnly")?.value),
        !truthy(document.getElementById("trashEnabled")?.value)
      ].filter(Boolean).length : 0;
      const login = truthy(document.getElementById("loginMode")?.value);

      set("basic", auto ? "자동 녹화 ON" : "수동 녹화", auto ? "success" : "neutral");
      set("chzzk", plugin, "neutral");
      set("processing", encoding.compact, truthy(document.getElementById("stream_copy")?.value) ? "success" : "neutral");
      set("notifications", notificationCount ? `${notificationCount}개 연결` : "사용 안 함", notificationCount ? "success" : "neutral");
      set("files", !manager ? "사용 안 함" : risks ? `주의 ${risks}` : "안전", risks ? "danger" : manager ? "success" : "neutral");
      set("security", login ? "로그인 ON" : "로컬 전용", login ? "success" : "warning");

      overview.innerHTML = [
        `<span><b>녹화</b>${auto ? "자동" : "수동"}</span>`,
        `<span><b>인코딩</b>${encoding.compact}</span>`,
        `<span><b>알림</b>${notificationCount ? `${notificationCount}개 연결` : "없음"}</span>`,
        `<span class="${risks ? "is-danger" : ""}"><b>파일 관리</b>${!manager ? "꺼짐" : risks ? `주의 ${risks}` : "안전"}</span>`,
        `<span class="${login ? "" : "is-warning"}"><b>접속</b>${login ? "로그인 보호" : "로컬 전용"}</span>`
      ].join("");
      updateNotifications();
    };

    form.addEventListener("input", () => window.setTimeout(update, 0), true);
    form.addEventListener("change", () => window.setTimeout(update, 0), true);
    update();
  }

  function controlLabel(name) {
    if (fieldNames[name]) return fieldNames[name];
    const control = form.elements.namedItem(name);
    const node = control && !(control instanceof RadioNodeList) ? control : null;
    const label = node?.id ? $(`label[for='${CSS.escape(node.id)}']`) : null;
    return label?.textContent?.replace(/\s+/g, " ").replace(/:$/, "").trim() || name;
  }

  function snapshot() {
    const result = new Map();
    const grouped = new Map();
    Array.from(form.elements).forEach((control) => {
      if (!control.name || helperNames.has(control.name) || secretValueNames.has(control.name) || control.type === "submit" || control.type === "button") return;
      let value = "";
      if ((control.type === "checkbox" || control.type === "radio") && !control.checked) return;
      if (control instanceof HTMLSelectElement) value = control.value;
      else value = control.value || "";
      if (!grouped.has(control.name)) grouped.set(control.name, []);
      grouped.get(control.name).push(String(value));
    });
    grouped.forEach((values, name) => result.set(name, values.join("\u001f")));
    return result;
  }

  function friendlyValue(name, value) {
    if (name.endsWith("_action")) return ({ keep: "유지", replace: "변경", clear: "삭제" })[value] || value;
    if (value === "true") return "ON";
    if (value === "false") return "OFF";
    const control = form.elements.namedItem(name);
    if (control instanceof HTMLSelectElement) {
      return Array.from(control.options).find((option) => option.value === value)?.textContent?.trim() || value;
    }
    if (name === "fileManagerRoots") return value.split("\u001f").filter(Boolean).join(", ") || "없음";
    if (["recheckInterval", "autoStopInterval", "splitOverlapSec", "timemachine_time_shift"].includes(name) && value) return `${value}초`;
    return value || "비어 있음";
  }

  function setupDetailedSaveSummary() {
    const bar = $(".lar-config-savebar");
    const host = bar?.firstElementChild;
    if (!bar || !host) return;
    const oldSummary = $(".lar-config-change-summary", host);
    if (oldSummary) oldSummary.hidden = true;
    const details = document.createElement("div");
    details.className = "lar-config-change-details";
    details.hidden = true;
    host.appendChild(details);

    let baseline = snapshot();
    const update = () => {
      const current = snapshot();
      const names = new Set([...baseline.keys(), ...current.keys()]);
      const changes = Array.from(names)
        .filter((name) => (baseline.get(name) || "") !== (current.get(name) || ""))
        .map((name) => ({ name, before: baseline.get(name) || "", after: current.get(name) || "" }));
      if (!changes.length) {
        details.hidden = true;
        details.innerHTML = "";
        return;
      }
      const shown = changes.slice(0, 3);
      details.hidden = false;
      details.innerHTML = shown.map((change) => {
        const restart = restartFields.has(change.name) ? '<em>재시작</em>' : "";
        return `<span><b>${escapeHtml(controlLabel(change.name))}</b><del>${escapeHtml(friendlyValue(change.name, change.before))}</del><i aria-hidden="true">→</i><ins>${escapeHtml(friendlyValue(change.name, change.after))}</ins>${restart}</span>`;
      }).join("") + (changes.length > shown.length ? `<small>외 ${changes.length - shown.length}개 변경</small>` : "");
    };
    form.addEventListener("input", () => window.setTimeout(update, 0), true);
    form.addEventListener("change", () => window.setTimeout(update, 0), true);
    form.addEventListener("reset", () => window.setTimeout(update, 20), true);
    window.setTimeout(() => { baseline = snapshot(); update(); }, 180);
  }

  buildInformationArchitecture();
  setupBooleanSwitches();
  setupEncodingDisclosure();
  const updateNotifications = setupNotificationState();
  setupTabStatuses(updateNotifications);
  setupDetailedSaveSummary();
})();

;
// ===== Project UI audit =====
(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";

  function makeButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function addPasswordToggle(input) {
    if (!input || input.dataset.larPasswordToggle === "1") return;
    input.dataset.larPasswordToggle = "1";

    const wrapper = document.createElement("div");
    wrapper.className = "lar-password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const toggle = makeButton("보기", "lar-password-toggle");
    toggle.setAttribute("aria-label", "비밀번호 표시");
    toggle.setAttribute("aria-pressed", "false");
    toggle.addEventListener("click", function () {
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      toggle.textContent = reveal ? "숨기기" : "보기";
      toggle.setAttribute("aria-label", reveal ? "비밀번호 숨기기" : "비밀번호 표시");
      toggle.setAttribute("aria-pressed", String(reveal));
    });
    wrapper.appendChild(toggle);
  }

  function enhanceAuth() {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
      document.body.classList.add("lar-auth-mode");
      const card = loginForm.parentElement;
      card?.classList.add("lar-auth-card");
      const heading = card?.querySelector(":scope > h2");
      if (heading && !heading.nextElementSibling?.classList.contains("lar-workspace-copy")) {
        const copy = document.createElement("p");
        copy.className = "lar-workspace-copy";
        copy.textContent = "관리자 계정으로 로그인해 녹화와 저장소 상태를 관리합니다.";
        heading.insertAdjacentElement("afterend", copy);
      }
      addPasswordToggle(loginForm.querySelector('input[name="password"]'));
      loginForm.querySelector('input[name="username"]')?.setAttribute("autocomplete", "username");
      loginForm.querySelector('input[name="password"]')?.setAttribute("autocomplete", "current-password");
    }

    if (document.body.classList.contains("page-register")) {
      document.body.classList.add("lar-auth-mode");
      const form = document.querySelector(".register-form");
      if (!form) return;
      form.querySelector('input[name="username"]')?.setAttribute("autocomplete", "username");
      const password = form.querySelector('input[name="password"]');
      const confirm = form.querySelector('input[name="password_confirm"]');
      password?.setAttribute("autocomplete", "new-password");
      confirm?.setAttribute("autocomplete", "new-password");
      addPasswordToggle(password);
      addPasswordToggle(confirm);

      if (confirm && !form.querySelector(".lar-password-match")) {
        const status = document.createElement("p");
        status.className = "lar-password-match";
        status.setAttribute("role", "status");
        status.setAttribute("aria-live", "polite");
        confirm.closest(".lar-password-field")?.insertAdjacentElement("afterend", status);
        const refresh = function () {
          if (!confirm.value) {
            status.textContent = "";
            status.dataset.state = "";
          } else if (password?.value === confirm.value) {
            status.textContent = "비밀번호가 일치합니다.";
            status.dataset.state = "ok";
          } else {
            status.textContent = "비밀번호가 일치하지 않습니다.";
            status.dataset.state = "error";
          }
        };
        password?.addEventListener("input", refresh);
        confirm.addEventListener("input", refresh);
      }
    }
  }

  function wrapFormFields(form) {
    if (!form || form.dataset.larFieldGrid === "1") return;
    form.dataset.larFieldGrid = "1";
    const children = Array.from(form.children);
    let field = null;

    children.forEach(function (node) {
      if (node.tagName === "LABEL") {
        field = document.createElement("div");
        field.className = "lar-field";
        form.insertBefore(field, node);
        field.appendChild(node);
        return;
      }
      if (node.matches?.('button[type="submit"],input[type="submit"]')) {
        field = null;
        return;
      }
      if (field) field.appendChild(node);
    });

    form.querySelectorAll(".lar-field").forEach(function (item) {
      const label = item.querySelector("label")?.textContent.trim() || "";
      if (/저장 경로|녹화 제외/.test(label)) item.classList.add("lar-field--full");
    });
  }

  function platformValue(card) {
    return card.querySelector(".edit-platform")?.value || "";
  }

  function openChannelEditor(card, open) {
    const form = card.querySelector(".channel-edit-form");
    const toggle = card.querySelector(".lar-channel-edit-toggle");
    if (!form || !toggle) return;
    form.hidden = !open;
    card.classList.toggle("lar-edit-open", open);
    toggle.textContent = open ? "설정 닫기" : "설정 열기";
    toggle.setAttribute("aria-expanded", String(open));
    if (open) form.querySelector("input,select,button")?.focus({ preventScroll: true });
  }

  function enhanceChannels() {
    if (path !== "/channels" && !document.body.classList.contains("page-channels")) return;
    wrapFormFields(document.getElementById("addChannelForm"));

    const list = document.querySelector(".channel-list");
    if (list && !list.querySelector(".channel-card")) {
      const empty = document.createElement("div");
      empty.className = "lar-empty-state";
      empty.textContent = "등록된 채널이 없습니다. 위 양식에서 첫 녹화 채널을 추가하세요.";
      list.appendChild(empty);
    }

    document.querySelectorAll(".channel-card").forEach(function (card, index) {
      if (card.dataset.larChannelAudit === "1") return;
      card.dataset.larChannelAudit = "1";

      const body = card.querySelector(".channel-card-body");
      const form = card.querySelector(".channel-edit-form");
      if (!body || !form) return;
      form.style.removeProperty("display");
      form.hidden = true;
      form.id = form.id || `lar-channel-editor-${index + 1}`;

      const actions = document.createElement("div");
      actions.className = "lar-channel-summary-actions";
      const badge = document.createElement("span");
      badge.className = "lar-platform-badge";
      badge.dataset.platform = platformValue(card);
      badge.textContent = badge.dataset.platform === "youtube" ? "YouTube" : "CHZZK";
      const toggle = makeButton("설정 열기", "lar-channel-edit-toggle");
      toggle.setAttribute("aria-controls", form.id);
      toggle.setAttribute("aria-expanded", "false");
      actions.append(badge, toggle);
      body.appendChild(actions);

      toggle.addEventListener("click", function () {
        openChannelEditor(card, form.hidden);
      });

      const platform = form.querySelector(".edit-platform");
      platform?.addEventListener("change", function () {
        badge.dataset.platform = platform.value;
        badge.textContent = platform.value === "youtube" ? "YouTube" : "CHZZK";
      });

      const row = form.querySelector(".button-row");
      if (row && !row.querySelector(".lar-channel-edit-close")) {
        const close = makeButton("닫기", "lar-channel-edit-close");
        row.insertBefore(close, row.firstChild);
        close.addEventListener("click", function () {
          if (form.classList.contains("lar-dirty") && !window.confirm("저장하지 않은 변경사항이 있습니다. 설정을 닫을까요?")) return;
          openChannelEditor(card, false);
        });
      }
    });
  }

  function panelHeader(title, copy) {
    const fragment = document.createDocumentFragment();
    const heading = document.createElement("h2");
    heading.textContent = title;
    const description = document.createElement("p");
    description.className = "lar-workspace-copy";
    description.textContent = copy;
    fragment.append(heading, description);
    return fragment;
  }

  function enhanceCookies() {
    if (path !== "/cookies" && !document.body.classList.contains("page-cookies")) return;
    const content = document.getElementById("content");
    const form = document.getElementById("updateCookiesForm");
    const notices = Array.from(content?.querySelectorAll(":scope > .notice") || []);
    const youtubeHeading = Array.from(content?.children || []).find(function (node) {
      return node.tagName === "H2" && /유튜브/.test(node.textContent);
    });
    if (!content || !form || !notices.length || !youtubeHeading) return;

    const grid = document.createElement("div");
    grid.className = "lar-cookie-workspace";
    const chzzkPanel = document.createElement("section");
    chzzkPanel.className = "lar-cookie-panel";
    chzzkPanel.appendChild(panelHeader("치지직 인증", "NID_AUT와 NID_SES를 저장하고 인증 상태를 관리합니다."));
    chzzkPanel.append(notices[0], form);
    const modified = content.querySelector(":scope > .last-modified");
    if (modified) chzzkPanel.appendChild(modified);
    const security = document.createElement("p");
    security.className = "lar-cookie-security";
    security.textContent = "쿠키 값은 비밀번호처럼 가려서 표시합니다. 필요한 경우에만 보기 버튼으로 확인하세요.";
    chzzkPanel.appendChild(security);

    const youtubePanel = document.createElement("section");
    youtubePanel.className = "lar-cookie-panel";
    youtubePanel.appendChild(panelHeader("YouTube 인증", "cookies.txt 파일을 준비하는 절차를 확인합니다."));
    if (notices[1]) youtubePanel.appendChild(notices[1]);

    youtubeHeading.remove();
    content.appendChild(grid);
    grid.append(chzzkPanel, youtubePanel);

    form.querySelectorAll('input[type="text"]:not([type="submit"])').forEach(function (input) {
      input.type = "password";
      input.dataset.larSensitive = "1";
      input.autocomplete = "off";
      input.spellcheck = false;
      addPasswordToggle(input);
    });
  }

  function wrapToolbar(row) {
    if (!row || row.dataset.larToolbarAudit === "1") return;
    row.dataset.larToolbarAudit = "1";
    const children = Array.from(row.children);
    const actions = document.createElement("div");
    actions.className = "lar-toolbar-actions";

    for (let i = 0; i < children.length; i += 1) {
      const node = children[i];
      if (node.tagName === "LABEL") {
        const control = children[i + 1];
        if (control && /^(INPUT|SELECT|TEXTAREA)$/.test(control.tagName)) {
          const field = document.createElement("div");
          field.className = "lar-toolbar-field";
          if (control.id === "pathInput") field.classList.add("lar-toolbar-path");
          row.insertBefore(field, node);
          field.append(node, control);
          i += 1;
          continue;
        }
      }
      if (node.tagName === "BUTTON") actions.appendChild(node);
    }
    if (actions.childElementCount) row.appendChild(actions);
  }

  function visibleFileModal() {
    return Array.from(document.querySelectorAll("body.page-files .modal")).find(function (modal) {
      return !modal.classList.contains("hidden") && getComputedStyle(modal).display !== "none";
    });
  }

  function enhanceFileModals() {
    const modals = document.querySelectorAll("body.page-files .modal");
    modals.forEach(function (modal, index) {
      modal.setAttribute("role", "dialog");
      modal.setAttribute("aria-modal", "true");
      const heading = modal.querySelector("h3");
      if (heading) {
        heading.id = heading.id || `lar-file-modal-title-${index + 1}`;
        modal.setAttribute("aria-labelledby", heading.id);
      }
    });

    document.addEventListener("keydown", function (event) {
      const modal = visibleFileModal();
      if (!modal) return;
      if (event.key === "Escape") {
        const close = modal.querySelector("#close-fm-modal,#mp-cancel,#detail-close,.secondary");
        if (close) {
          event.preventDefault();
          close.click();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(modal.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])'))
        .filter(function (node) { return node.offsetParent !== null; });
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        const modal = mutation.target;
        if (!(modal instanceof Element) || !modal.classList.contains("modal")) return;
        if (!modal.classList.contains("hidden")) {
          requestAnimationFrame(function () {
            modal.querySelector("button,input,select,textarea,a[href]")?.focus({ preventScroll: true });
          });
        }
      });
    });
    modals.forEach(function (modal) { observer.observe(modal, { attributes: true, attributeFilter: ["class"] }); });
  }

  function enhanceFiles() {
    if (path !== "/files" && !document.body.classList.contains("page-files")) return;
    document.querySelectorAll(".file-toolbar .toolbar-row").forEach(wrapToolbar);
    enhanceFileModals();
  }

  function boot() {
    document.body.classList.add("lar-project-ui-audit");
    enhanceAuth();
    enhanceChannels();
    enhanceCookies();
    enhanceFiles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();

;
// ===== Operations =====
(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";
  const state = { summary: null, settings: null, health: [], jobs: [], backups: [], statistics: null, audit: [], cleanupPreview: null };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char];
    });
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    const type = response.headers.get("content-type") || "";
    const body = type.includes("json") ? await response.json() : await response.text();
    if (!response.ok) throw new Error(body?.detail || body?.message || String(body) || `HTTP ${response.status}`);
    return body;
  }

  function notice(message, tone) {
    const node = document.getElementById("ops-notice");
    if (!node) return;
    node.hidden = false;
    node.dataset.tone = tone || "info";
    node.textContent = message;
    clearTimeout(notice.timer);
    notice.timer = setTimeout(function () { node.hidden = true; }, 5000);
  }

  function ensureOperationsLink() {
    const nav = document.getElementById("mySidenav");
    if (!nav || nav.querySelector('a[href="/operations"]')) return;
    const link = document.createElement("a");
    link.href = "/operations";
    link.className = "restricted-menu ops-nav-link";
    link.textContent = "운영 관리";
    const user = nav.querySelector("#user-info");
    nav.insertBefore(link, user || null);
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    return `${h}시간 ${m}분`;
  }

  function statusLabel(status) {
    const labels = { ok: "정상", warning: "주의", critical: "위험", recording: "녹화 중", checking: "확인 중", waiting: "대기", stalled: "기록 멈춤", failed: "실패", reconnecting: "재연결", blocked: "차단", completed: "완료", running: "진행 중", queued: "대기", cancelled: "취소", cancelling: "취소 중" };
    return labels[status] || status || "-";
  }

  async function loadLightweightStatus() {
    try {
      const [summary, health] = await Promise.all([
        request("/api/operations/summary"),
        request("/api/operations/health")
      ]);
      showStorageBanner(summary.storage);
      applyHealthBadges(health.channels || []);
    } catch (_) {}
  }

  function showStorageBanner(storage) {
    if (!storage || storage.status === "ok" || !["/", "/recording"].includes(path)) return;
    let banner = document.querySelector(".ops-storage-banner");
    if (!banner) {
      banner = document.createElement("a");
      banner.href = "/operations";
      banner.className = "ops-storage-banner";
      const content = document.getElementById("content");
      content?.insertBefore(banner, content.firstChild);
    }
    banner.dataset.tone = storage.status;
    banner.textContent = `녹화 저장소 남은 공간 ${storage.free_text} (${storage.free_percent}%) · 운영 관리에서 확인`;
  }

  function applyHealthBadges(items) {
    items.forEach(function (item) {
      const card = document.querySelector(`.channel[data-channel-id="${CSS.escape(String(item.channel_id))}"]`);
      if (!card) return;
      let badge = card.querySelector(".ops-health-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "ops-health-badge";
        card.querySelector(".channel-name")?.appendChild(badge);
      }
      badge.dataset.state = item.state;
      badge.textContent = item.label || statusLabel(item.state);
      badge.title = [item.write_rate_text, item.last_error].filter(Boolean).join(" · ");
    });
  }

  function bindTabs() {
    document.querySelectorAll("[data-ops-tab]").forEach(function (button) {
      button.addEventListener("click", function () {
        document.querySelectorAll("[data-ops-tab]").forEach(function (node) { node.classList.toggle("is-active", node === button); });
        document.querySelectorAll("[data-ops-panel]").forEach(function (node) { node.classList.toggle("is-active", node.dataset.opsPanel === button.dataset.opsTab); });
      });
    });
  }

  function summaryCard(label, value, sub, tone) {
    return `<article class="ops-kpi" data-tone="${escapeHtml(tone || "")}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(sub || "")}</small></article>`;
  }

  function renderSummary() {
    const root = document.getElementById("ops-summary");
    if (!root || !state.summary) return;
    const storage = state.summary.storage || {};
    const health = state.summary.health_counts || {};
    const jobs = state.summary.jobs || {};
    root.innerHTML = [
      summaryCard("녹화 저장소", `${storage.free_percent ?? 0}% 남음`, `${storage.free_text || "-"} 사용 가능`, storage.status),
      summaryCard("현재 녹화", state.summary.active_recordings || 0, `확인 중 ${health.checking || 0}개`, "recording"),
      summaryCard("상태 이상", (health.stalled || 0) + (health.failed || 0) + (health.blocked || 0), `재연결 ${health.reconnecting || 0}개`, (health.stalled || health.failed || health.blocked) ? "critical" : "ok"),
      summaryCard("후처리", (jobs.running || 0) + (jobs.queued || 0), `실패 ${jobs.failed || 0}건`, jobs.failed ? "warning" : "ok"),
      summaryCard("백업", state.summary.backups || 0, "보관 중", "ok")
    ].join("");
  }

  function renderStorage() {
    const node = document.getElementById("ops-storage-detail");
    const storage = state.summary?.storage || {};
    const runway = state.runway || {};
    const runwayText = runway.hours_remaining == null ? "예측 데이터 부족" : `약 ${escapeHtml(runway.hours_remaining)}시간`;
    if (node) node.innerHTML = `<div class="ops-storage-card" data-tone="${escapeHtml(storage.status)}"><div><span>녹화 저장소</span><strong>${escapeHtml(storage.path || "-")}</strong></div><div class="ops-storage-number"><strong>${escapeHtml(storage.free_text || "-")}</strong><span>${escapeHtml(storage.free_percent ?? 0)}% 남음</span></div><div class="ops-progress"><i style="width:${Math.max(0, Math.min(100, Number(storage.used_percent) || 0))}%"></i></div><small>${escapeHtml(storage.used_text || "-")} / ${escapeHtml(storage.total_text || "-")} · ${escapeHtml(runway.bytes_per_hour_text || "0 B/h")} · ${runwayText}</small></div>`;
    const form = document.getElementById("ops-storage-form");
    const cfg = state.settings?.storage;
    if (form && cfg && !form.dataset.filled) {
      ["warning_free_percent", "block_free_percent", "cleanup_mode", "retention_days", "max_total_gb", "keep_recent_per_channel"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg[name] ?? ""; });
      form.elements.auto_cleanup.checked = Boolean(cfg.auto_cleanup);
      form.dataset.filled = "1";
    }
  }

  function renderHealth() {
    const root = document.getElementById("ops-health-list");
    if (!root) return;
    root.innerHTML = state.health.length ? state.health.map(function (item) {
      return `<article class="ops-health-card" data-state="${escapeHtml(item.state)}"><div class="ops-card-head"><div><strong>${escapeHtml(item.channel_name)}</strong><small>${escapeHtml(item.platform).toUpperCase()}</small></div><span class="ops-status">${escapeHtml(item.label || statusLabel(item.state))}</span></div><dl><div><dt>기록 속도</dt><dd>${escapeHtml(item.write_rate_text || "-")}</dd></div><div><dt>파일 크기</dt><dd>${escapeHtml(item.file_size_text || "-")}</dd></div><div><dt>마지막 기록</dt><dd>${escapeHtml(item.last_write_at || "-")}</dd></div><div><dt>재연결</dt><dd>${escapeHtml(item.restart_attempts || 0)}회</dd></div><div><dt>시작 지연</dt><dd>${escapeHtml(item.start_delay_seconds || 0)}초</dd></div><div><dt>녹화 도구</dt><dd>${escapeHtml(item.tool || "-")}</dd></div></dl>${item.last_error ? `<p class="ops-error">${escapeHtml(item.last_error)}</p>` : ""}<div class="ops-inline-buttons"><button type="button" class="ops-action-secondary" data-health-recover="${escapeHtml(item.channel_id)}">복구</button><button type="button" class="ops-action-secondary" data-health-trace="${escapeHtml(item.channel_id)}">실시간 로그</button></div><pre class="ops-trace" data-trace-output="${escapeHtml(item.channel_id)}" hidden></pre></article>`;
    }).join("") : '<div class="ops-empty">등록된 채널 상태가 없습니다.</div>';
    const form = document.getElementById("ops-health-form");
    const cfg = state.settings?.health;
    if (form && cfg && !form.dataset.filled) {
      ["stall_seconds", "max_restart_attempts", "restart_cooldown_seconds", "missed_recording_seconds", "circuit_breaker_after", "circuit_breaker_seconds"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg[name] ?? ""; });
      form.elements.auto_restart.checked = Boolean(cfg.auto_restart);
      form.dataset.filled = "1";
    }
  }

  function jobActions(job) {
    const retry = ["failed", "cancelled", "completed"].includes(job.status) ? `<button data-job-retry="${escapeHtml(job.id)}">재시도</button>` : "";
    const cancel = ["running", "queued"].includes(job.status) ? `<button class="ops-danger-text" data-job-cancel="${escapeHtml(job.id)}">취소</button>` : "";
    return retry + cancel || "-";
  }

  function renderJobs() {
    const body = document.getElementById("ops-jobs-body");
    if (!body) return;
    body.innerHTML = state.jobs.length ? state.jobs.map(function (job) {
      return `<tr><td><span class="ops-pill" data-state="${escapeHtml(job.status)}">${escapeHtml(statusLabel(job.status))}</span></td><td><div class="ops-job-progress"><i style="width:${Math.max(0, Math.min(100, Number(job.progress) || 0))}%"></i></div><small>${escapeHtml(job.progress || 0)}%</small></td><td>${escapeHtml(job.channel_name || job.channel_id)}</td><td class="ops-path" title="${escapeHtml(job.source)}">${escapeHtml(job.source || "-")}</td><td>${escapeHtml(job.started_at || job.created_at || "-")}</td><td>${escapeHtml(job.finished_at || "-")}</td><td>${jobActions(job)}</td></tr>`;
    }).join("") : '<tr><td colspan="7" class="ops-empty">후처리 작업 이력이 없습니다.</td></tr>';
  }

  function renderBackups() {
    const body = document.getElementById("ops-backups-body");
    if (!body) return;
    body.innerHTML = state.backups.length ? state.backups.map(function (item) {
      const name = encodeURIComponent(item.name);
      return `<tr><td class="ops-path">${escapeHtml(item.name)}</td><td>${escapeHtml(item.size_text)}</td><td>${escapeHtml(item.created_at)}</td><td><a class="ops-button-small" href="/api/operations/backups/${name}/download">다운로드</a><button class="ops-danger-text" data-backup-restore="${escapeHtml(item.name)}">복원</button></td></tr>`;
    }).join("") : '<tr><td colspan="4" class="ops-empty">생성된 백업이 없습니다.</td></tr>';
    const form = document.getElementById("ops-backup-form");
    const cfg = state.settings?.backup;
    if (form && cfg && !form.dataset.filled) {
      form.elements.interval_hours.value = cfg.interval_hours ?? 24;
      form.elements.keep.value = cfg.keep ?? 7;
      form.elements.scheduled.checked = Boolean(cfg.scheduled);
      form.dataset.filled = "1";
    }
  }

  function renderStatistics() {
    const stats = state.statistics;
    if (!stats) return;
    const cards = document.getElementById("ops-stat-cards");
    if (cards) cards.innerHTML = [summaryCard("전체 녹화", stats.total_recordings, "이력 기준"), summaryCard("실패", stats.total_failures, "녹화·후처리"), summaryCard("성공률", `${stats.success_rate}%`, "전체 기간"), summaryCard("누적 시간", formatDuration(stats.total_duration_seconds), "기록된 종료 이력")].join("");
    const chart = document.getElementById("ops-daily-chart");
    const max = Math.max(1, ...stats.daily.map(function (item) { return item.recordings; }));
    if (chart) chart.innerHTML = stats.daily.map(function (item) { const height = Math.max(4, item.recordings / max * 100); return `<div title="${escapeHtml(item.date)} · 녹화 ${item.recordings} · 실패 ${item.failures}"><span style="height:${height}%"></span><small>${escapeHtml(item.date.slice(5))}</small></div>`; }).join("");
    const body = document.getElementById("ops-channel-stats");
    if (body) body.innerHTML = stats.by_channel.length ? stats.by_channel.map(function (item) { return `<tr><td>${escapeHtml(item.channel)}</td><td>${item.recordings}</td><td>${item.failures}</td><td>${escapeHtml(formatDuration(item.duration_seconds))}</td><td>${escapeHtml(item.storage_text || "-")}</td></tr>`; }).join("") : '<tr><td colspan="5" class="ops-empty">통계 데이터가 없습니다.</td></tr>';
  }

  function renderAudit() {
    const body = document.getElementById("ops-audit-body");
    if (!body) return;
    body.innerHTML = state.audit.length ? state.audit.map(function (item) { return `<tr><td>${escapeHtml(item.ts)}</td><td>${escapeHtml(item.action)}</td><td><span class="ops-pill" data-state="${escapeHtml(item.result)}">${escapeHtml(item.result)}</span></td><td>${escapeHtml(item.detail || "-")}</td></tr>`; }).join("") : '<tr><td colspan="4" class="ops-empty">작업 기록이 없습니다.</td></tr>';
  }

  function renderCleanup(result) {
    const root = document.getElementById("ops-cleanup-result");
    if (!root || !result) return;
    const deleted = result.deleted?.length ? `<p>${result.deleted.length}개 파일을 삭제했습니다.</p>` : "";
    root.innerHTML = `<div class="ops-cleanup-box"><strong>삭제 대상 ${result.candidate_count}개 · ${escapeHtml(result.candidate_text)}</strong><span>보호된 파일 ${result.protected_count}개</span>${deleted}<ul>${(result.candidates || []).slice(0, 20).map(function (item) { return `<li><span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.size_text)} · ${escapeHtml(item.modified_at)}</small></li>`; }).join("")}</ul></div>`;
  }

  async function loadAll() {
    const [summary, settings, health, jobs, backups, statistics, audit] = await Promise.all([
      request("/api/operations/summary"), request("/api/operations/settings"), request("/api/operations/health"), request("/api/operations/jobs"), request("/api/operations/backups"), request("/api/operations/statistics"), request("/api/operations/audit?limit=150")
    ]);
    Object.assign(state, { summary, settings, health: health.channels || [], runway: health.storage_runway || {}, jobs: jobs.jobs || [], backups: backups.backups || [], statistics, audit: audit.entries || [] });
    renderSummary(); renderStorage(); renderHealth(); renderJobs(); renderBackups(); renderStatistics(); renderAudit(); applyHealthBadges(state.health);
  }

  async function saveSection(section, data) {
    const next = JSON.parse(JSON.stringify(state.settings));
    next[section] = Object.assign({}, next[section], data);
    state.settings = await request("/api/operations/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next) });
    notice("설정을 저장했습니다.", "success");
  }

  function commaList(value) { return String(value || "").split(",").map(function (item) { return item.trim(); }).filter(Boolean); }

  function bindForms() {
    document.getElementById("ops-storage-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; try { const retention = Object.assign({}, state.settings?.storage?.retention_days_by_channel || {}); if (f.retention_channel.value) { const days = Number(f.retention_channel_days.value || 0); if (days > 0) retention[f.retention_channel.value] = days; else delete retention[f.retention_channel.value]; } await saveSection("storage", { warning_free_percent: Number(f.warning_free_percent.value), block_free_percent: Number(f.block_free_percent.value), cleanup_mode: f.cleanup_mode.value, retention_days: Number(f.retention_days.value), max_total_gb: Number(f.max_total_gb.value), keep_recent_per_channel: Number(f.keep_recent_per_channel.value || 0), retention_days_by_channel: retention, auto_cleanup: f.auto_cleanup.checked }); await loadAll(); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-health-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; const payload = { stall_seconds: Number(f.stall_seconds.value), max_restart_attempts: Number(f.max_restart_attempts.value), restart_cooldown_seconds: Number(f.restart_cooldown_seconds.value), missed_recording_seconds: Number(f.missed_recording_seconds.value || 0), circuit_breaker_after: Number(f.circuit_breaker_after.value || 5), circuit_breaker_seconds: Number(f.circuit_breaker_seconds.value || 300), auto_restart: f.auto_restart.checked, enabled: true }; try { if (f.channel_id.value) { await request(`/api/operations/channels/${encodeURIComponent(f.channel_id.value)}/health-settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); notice("채널별 감시 설정을 저장했습니다.", "success"); } else { await saveSection("health", payload); } await loadAll(); } catch (error) { notice(error.message, "error"); } });
    document.querySelector('#ops-health-form [name="channel_id"]')?.addEventListener("change", async function (event) { const form = document.getElementById("ops-health-form"); const id = event.currentTarget.value; try { const cfg = id ? await request(`/api/operations/channels/${encodeURIComponent(id)}/health-settings`) : state.settings?.health; ["stall_seconds", "max_restart_attempts", "restart_cooldown_seconds", "missed_recording_seconds", "circuit_breaker_after", "circuit_breaker_seconds"].forEach(function (name) { if (form.elements[name]) form.elements[name].value = cfg?.[name] ?? ""; }); form.elements.auto_restart.checked = Boolean(cfg?.auto_restart); } catch (error) { notice(error.message, "error"); } });
    document.querySelector('#ops-storage-form [name="retention_channel"]')?.addEventListener("change", function (event) { const form = document.getElementById("ops-storage-form"); form.elements.retention_channel_days.value = state.settings?.storage?.retention_days_by_channel?.[event.currentTarget.value] || 0; });
    document.getElementById("ops-backup-form")?.addEventListener("submit", async function (event) { event.preventDefault(); const f = event.currentTarget.elements; try { await saveSection("backup", { interval_hours: Number(f.interval_hours.value), keep: Number(f.keep.value), scheduled: f.scheduled.checked }); await loadAll(); } catch (error) { notice(error.message, "error"); } });

    const ruleChannel = document.getElementById("ops-rule-channel");
    ruleChannel?.addEventListener("change", async function () {
      const form = document.getElementById("ops-rule-form");
      if (!ruleChannel.value || !form) return;
      try {
        const rule = await request(`/api/operations/rules/${encodeURIComponent(ruleChannel.value)}`);
        ["title_include", "title_exclude", "categories"].forEach(function (name) { form.elements[name].value = (rule[name] || []).join(", "); });
        ["time_start", "time_end", "start_delay_seconds", "max_duration_minutes", "minimum_duration_minutes", "quality_override"].forEach(function (name) { form.elements[name].value = rule[name] ?? ""; });
        form.elements.enabled.checked = rule.enabled !== false;
        form.querySelectorAll(".ops-days input").forEach(function (box) { box.checked = (rule.days || []).includes(Number(box.value)); });
      } catch (error) { notice(error.message, "error"); }
    });
    document.getElementById("ops-rule-form")?.addEventListener("submit", async function (event) {
      event.preventDefault(); const f = event.currentTarget; const channel = f.elements.channel_id.value; if (!channel) return notice("채널을 선택해 주세요.", "error");
      const payload = { enabled: f.elements.enabled.checked, title_include: commaList(f.elements.title_include.value), title_exclude: commaList(f.elements.title_exclude.value), categories: commaList(f.elements.categories.value), days: Array.from(f.querySelectorAll(".ops-days input:checked")).map(function (box) { return Number(box.value); }), time_start: f.elements.time_start.value, time_end: f.elements.time_end.value, start_delay_seconds: Number(f.elements.start_delay_seconds.value || 0), max_duration_minutes: Number(f.elements.max_duration_minutes.value || 0), minimum_duration_minutes: Number(f.elements.minimum_duration_minutes.value || 0), quality_override: f.elements.quality_override.value };
      try { await request(`/api/operations/rules/${encodeURIComponent(channel)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); notice("채널 규칙을 저장했습니다.", "success"); } catch (error) { notice(error.message, "error"); }
    });
  }

  function cleanupPayload(confirm) {
    const f = document.getElementById("ops-storage-form").elements;
    return { mode: f.cleanup_mode.value, retention_days: Number(f.retention_days.value), max_total_gb: Number(f.max_total_gb.value), warning_free_percent: Number(f.warning_free_percent.value), confirm: Boolean(confirm) };
  }

  function bindActions() {
    document.getElementById("ops-refresh")?.addEventListener("click", function () { loadAll().then(function () { notice("최신 상태로 갱신했습니다.", "success"); }).catch(function (error) { notice(error.message, "error"); }); });
    document.getElementById("ops-cleanup-preview")?.addEventListener("click", async function () { try { state.cleanupPreview = await request("/api/operations/cleanup/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cleanupPayload(false)) }); renderCleanup(state.cleanupPreview); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-cleanup-run")?.addEventListener("click", async function () { if (!state.cleanupPreview) return notice("먼저 삭제 대상을 미리 확인해 주세요.", "error"); if (!confirm(`${state.cleanupPreview.candidate_count}개 파일을 삭제할까요? 녹화 중 파일은 제외됩니다.`)) return; try { const result = await request("/api/operations/cleanup/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cleanupPayload(true)) }); state.cleanupPreview = result; renderCleanup(result); await loadAll(); notice("파일 정리를 완료했습니다.", "success"); } catch (error) { notice(error.message, "error"); } });
    document.getElementById("ops-backup-create")?.addEventListener("click", async function () { try { await request("/api/operations/backups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ include_secrets: document.getElementById("ops-backup-secrets").checked }) }); await loadAll(); notice("백업을 생성했습니다.", "success"); } catch (error) { notice(error.message, "error"); } });
    document.addEventListener("click", async function (event) {
      const retry = event.target.closest("[data-job-retry]"); const cancel = event.target.closest("[data-job-cancel]"); const restore = event.target.closest("[data-backup-restore]"); const recover = event.target.closest("[data-health-recover]"); const trace = event.target.closest("[data-health-trace]");
      try {
        if (retry) { await request(`/api/operations/jobs/${retry.dataset.jobRetry}/retry`, { method: "POST" }); notice("후처리 재시도를 요청했습니다.", "success"); await loadAll(); }
        if (cancel && confirm("실행 중인 후처리 작업을 취소할까요?")) { await request(`/api/operations/jobs/${cancel.dataset.jobCancel}/cancel`, { method: "POST" }); notice("취소를 요청했습니다.", "success"); await loadAll(); }
        if (restore) { const name = restore.dataset.backupRestore; const typed = prompt(`복원하려면 백업 파일명을 입력하세요.\n${name}`); if (typed !== name) return; await request(`/api/operations/backups/${encodeURIComponent(name)}/restore`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: name }) }); notice("백업을 복원했습니다. 컨테이너 재시작을 권장합니다.", "success"); await loadAll(); }
        if (recover) { const id = recover.dataset.healthRecover; await request(`/api/operations/channels/${encodeURIComponent(id)}/recover`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "restart" }) }); notice("채널 복구를 요청했습니다.", "success"); await loadAll(); }
        if (trace) { const id = trace.dataset.healthTrace; const output = document.querySelector(`[data-trace-output="${id}"]`); const data = await request(`/api/operations/channels/${encodeURIComponent(id)}/trace`); if (output) { output.hidden = false; output.textContent = data.process_stderr_tail || "현재 수집된 stderr 로그가 없습니다."; } }
      } catch (error) { notice(error.message, "error"); }
    });
  }

  function initOperationsPage() {
    bindTabs(); bindForms(); bindActions();
    loadAll().catch(function (error) { notice(`운영 정보를 불러오지 못했습니다: ${error.message}`, "error"); });
    setInterval(function () { loadAll().catch(function () {}); }, 15000);
  }

  ensureOperationsLink();
  if (path === "/operations") initOperationsPage();
  else { loadLightweightStatus(); setInterval(loadLightweightStatus, 15000); }
})();

;
// ===== Operations controls =====
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

;
// ===== Operations platform =====
(function () {
  "use strict";
  if (!document.body.classList.contains("page-operations")) return;

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const api = async (url, options) => {
    const response = await fetch(url, {headers:{"Accept":"application/json","Content-Type":"application/json", ...(options?.headers || {})}, ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.message || `HTTP ${response.status}`);
    return data;
  };
  const notice = (message, type) => {
    const host = $("#ops-notice");
    if (!host) return;
    host.hidden = false;
    host.textContent = message;
    host.classList.toggle("is-error", type === "error");
    window.clearTimeout(notice.timer);
    notice.timer = window.setTimeout(() => { host.hidden = true; }, 4500);
  };

  const tabs = $(".ops-tabs");
  const main = $(".ops-page");
  if (!tabs || !main || document.body.dataset.platformV3 === "1") return;
  document.body.dataset.platformV3 = "1";

  const tabDefs = [
    ["history", "녹화 기록"],
    ["system", "시스템 점검"],
    ["notifications", "알림 센터"],
    ["archive", "외부 보관"],
    ["automation", "API·웹훅"]
  ];
  tabDefs.forEach(([id, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.id = `ops-tab-${id}`;
    button.dataset.opsTab = id;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", `ops-panel-${id}`);
    button.setAttribute("aria-selected", "false");
    button.tabIndex = -1;
    button.textContent = label;
    tabs.appendChild(button);
  });

  function panel(id, title, description, inner) {
    const section = document.createElement("section");
    section.id = `ops-panel-${id}`;
    section.className = "ops-panel";
    section.dataset.opsPanel = id;
    section.setAttribute("role", "tabpanel");
    section.setAttribute("aria-labelledby", `ops-tab-${id}`);
    section.setAttribute("aria-hidden", "true");
    section.tabIndex = 0;
    section.innerHTML = `<div class="ops-section-head"><div><h2>${title}</h2><p>${description}</p></div></div>${inner}`;
    main.appendChild(section);
    return section;
  }

  panel("history", "녹화 기록", "SQLite에 누적된 녹화 이력, 파일 검증, 복구와 외부 보관 상태를 확인합니다.", `
    <div class="ops-platform-toolbar">
      <label>검색<input id="ops-history-query" placeholder="채널·제목·파일·오류"></label>
      <label>보기<select id="ops-history-view"><option value="broadcasts">방송 단위</option><option value="segments">세그먼트 단위</option></select></label>
      <label>상태<select id="ops-history-status"><option value="">전체</option><option value="recording">녹화 중</option><option value="completed">완료</option><option value="failed">실패</option></select></label>
      <button id="ops-history-refresh" type="button" class="ops-action-secondary">조회</button>
    </div>
    <div class="ops-table-wrap"><table><thead><tr><th>시작</th><th>채널</th><th>파일</th><th>녹화</th><th>검증</th><th>보관</th><th>작업</th></tr></thead><tbody id="ops-history-body"></tbody></table></div>
    <div id="ops-history-meta" class="ops-empty"></div><div id="ops-history-detail" class="ops-platform-card" hidden></div>`);

  panel("system", "시스템 점검", "녹화에 필요한 도구, 저장소, SQLite, 쿠키, 알림, 네트워크와 업데이트 상태를 한 번에 확인합니다.", `
    <div class="ops-platform-actions"><button id="ops-diagnostics-run" type="button" class="ops-action-primary">전체 점검 실행</button><button id="ops-version-check" type="button" class="ops-action-secondary">새 버전 확인</button><button id="ops-db-backup" type="button" class="ops-action-secondary">DB 지금 백업</button></div>
    <div id="ops-system-summary" class="ops-platform-card" style="margin-top:14px"></div>
    <div id="ops-diagnostics-list" class="ops-platform-grid" style="margin-top:14px"></div>
    <div class="ops-platform-grid" style="margin-top:14px"><div id="ops-version-card" class="ops-platform-card"></div><div id="ops-cookie-card" class="ops-platform-card"></div><div id="ops-db-card" class="ops-platform-card"></div></div>
    <form id="ops-group-settings" class="ops-platform-form" style="margin-top:14px"><h3 class="is-wide">재연결 세그먼트 자동 합치기</h3><label>자동 합치기<select name="auto_merge"><option value="false">사용 안 함</option><option value="true">사용</option></select></label><label>방송 종료 대기(초)<input name="quiet_seconds" type="number" min="30" max="7200" value="900"></label><label>합친 뒤 원본 삭제<select name="delete_segments_after_merge"><option value="false">보존</option><option value="true">삭제</option></select></label><div class="is-wide ops-platform-actions"><button class="ops-action-primary" type="submit">합치기 설정 저장</button><span class="ops-platform-status is-warn">원본 삭제는 기본적으로 꺼져 있습니다.</span></div></form>`);

  panel("notifications", "알림 센터", "이벤트별 알림을 선택하고 실패한 전송을 자동 재시도합니다.", `
    <form id="ops-notification-form" class="ops-platform-form">
      <label>알림 센터<select name="enabled"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>최대 재시도<input type="number" name="max_attempts" min="1" max="20"></label>
      <label>조용한 시간 시작<input type="time" name="quiet_start"></label>
      <label>조용한 시간 종료<input type="time" name="quiet_end"></label>
      <div id="ops-notification-events" class="ops-event-grid"></div>
      <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">알림 설정 저장</button><button id="ops-notification-refresh" class="ops-action-secondary" type="button">전송 기록 새로고침</button></div>
    </form>
    <div class="ops-table-wrap"><table><thead><tr><th>이벤트</th><th>상태</th><th>시도</th><th>오류</th><th>작업</th></tr></thead><tbody id="ops-notification-body"></tbody></table></div>`);

  panel("archive", "외부 보관", "rclone remote로 녹화 파일을 복사하고 원격 크기 검증 후 선택적으로 로컬 파일을 삭제합니다.", `
    <div class="ops-platform-card" style="margin-bottom:14px"><h3>rclone 준비</h3><p>컨테이너의 <code>/app/json/rclone.conf</code>에 rclone 설정을 두세요. Google Drive, S3, WebDAV, OneDrive 등 rclone이 지원하는 원격 저장소를 사용할 수 있습니다.</p></div>
    <form id="ops-archive-form" class="ops-platform-form">
      <label>외부 보관<select name="enabled"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>rclone remote 경로<input name="remote" placeholder="예: gdrive:LiveAutoRecorder"></label>
      <label>검증 완료 후 자동 업로드<select name="auto_after_validation"><option value="true">사용</option><option value="false">사용 안 함</option></select></label>
      <label>원격 크기 확인<select name="verify_size"><option value="true">확인</option><option value="false">건너뜀</option></select></label>
      <label>업로드 후 로컬 삭제<select name="delete_after"><option value="false">보존</option><option value="true">삭제</option></select></label>
      <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">보관 설정 저장</button><span class="ops-platform-status is-warn">로컬 삭제는 원격 검증 성공 후에만 실행됩니다</span></div>
    </form>`);

  panel("automation", "API 토큰·웹훅", "외부 자동화에는 비밀번호 대신 범위 제한 토큰을 사용하고 이벤트 웹훅을 연결합니다.", `
    <div class="ops-platform-grid">
      <div class="ops-platform-card">
        <h3>API 토큰</h3><p>토큰 원문은 생성 직후 한 번만 표시됩니다.</p>
        <form id="ops-token-form" class="ops-platform-form" style="margin-top:12px">
          <label>이름<input name="name" required placeholder="Home Assistant"></label>
          <label>만료 일수<input type="number" name="expires_days" min="0" max="3650" value="90"><small>0 = 만료 없음</small></label>
          <div class="is-wide ops-event-grid"><label><input type="checkbox" name="scope" value="read" checked> read</label><label><input type="checkbox" name="scope" value="control"> control</label><label><input type="checkbox" name="scope" value="admin"> admin</label></div>
          <div class="ops-platform-actions"><button class="ops-action-primary" type="submit">토큰 생성</button></div>
        </form>
        <div id="ops-token-once"></div>
        <div class="ops-table-wrap"><table><thead><tr><th>이름</th><th>범위</th><th>마지막 사용</th><th></th></tr></thead><tbody id="ops-token-body"></tbody></table></div>
      </div>
      <div class="ops-platform-card">
        <h3>이벤트 웹훅</h3><p>요청 본문은 JSON이며 secret이 있으면 <code>X-LAR-Signature-256</code> HMAC 서명을 보냅니다.</p>
        <div id="ops-webhook-list"></div>
        <button id="ops-webhook-add" class="ops-action-secondary" type="button" style="margin-top:10px">웹훅 추가</button>
        <div class="ops-platform-actions" style="margin-top:12px"><button id="ops-webhook-save" class="ops-action-primary" type="button">웹훅 저장</button></div>
      </div>
    </div>
    <div class="ops-platform-card" style="margin-top:14px"><h3>자동화 API</h3><p><code>GET /api/v3/automation/status</code> · <code>GET /api/v3/automation/recordings</code> · <code>POST /api/v3/automation/channels/{id}/start</code> · <code>/stop</code><br>헤더: <code>Authorization: Bearer lar_...</code></p></div>`);

  function activate(id) {
    $$('[data-ops-tab]', tabs).forEach((button) => {
      const active = button.dataset.opsTab === id;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    $$('[data-ops-panel]', main).forEach((section) => {
      const active = section.dataset.opsPanel === id;
      section.classList.toggle("is-active", active);
      section.setAttribute("aria-hidden", active ? "false" : "true");
    });
    if (id === "history") loadHistory();
    if (id === "system") loadSystemStatus();
    if (id === "notifications") loadNotifications();
    if (id === "archive" || id === "automation") loadPlatformSettings();
    if (id === "automation") loadTokens();
  }
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-ops-tab]");
    if (!button) return;
    activate(button.dataset.opsTab);
  }, true);

  const boolValue = (v) => String(v) === "true";
  const statusBadge = (value) => {
    const map = {ok:["정상","is-ok"], repaired:["복구 완료","is-ok"], invalid:["손상","is-error"], missing:["파일 없음","is-error"], completed:["완료","is-ok"], failed:["실패","is-error"], uploading:["업로드 중","is-warn"], recording:["녹화 중","is-warn"]};
    const item = map[value] || [value || "미검사", ""];
    return `<span class="ops-platform-status ${item[1]}">${esc(item[0])}</span>`;
  };

  async function loadHistory() {
    const body = $("#ops-history-body");
    if (!body) return;
    const q = encodeURIComponent($("#ops-history-query")?.value || "");
    const status = encodeURIComponent($("#ops-history-status")?.value || "");
    const view = $("#ops-history-view")?.value || "broadcasts";
    try {
      const data = view === "broadcasts"
        ? await api(`/api/v3/broadcasts?limit=150&q=${q}`)
        : await api(`/api/v3/recordings?limit=150&q=${q}&status=${status}`);
      const rows = view === "broadcasts" ? data.items.filter((item) => !status || item.status === status) : data.items;
      body.innerHTML = rows.length ? rows.map((item) => view === "broadcasts" ? `<tr>
        <td>${esc(item.started_at || "-")}</td>
        <td><strong>${esc(item.channel_name || item.channel_id || "-")}</strong><br><small>${esc(item.platform || "")}</small></td>
        <td class="ops-recording-title">${esc(item.title || "방송")}${item.segment_count > 1 ? `<span class="ops-recording-path">세그먼트 ${esc(item.segment_count)}개 · 재연결 ${esc(item.reconnects || 0)}회</span>` : ""}</td>
        <td>${statusBadge(item.status)}${item.failure_detail ? `<br><small>${esc(item.failure_detail.slice(0,90))}</small>` : ""}</td>
        <td>${statusBadge(item.merge_status)}<br><small>${esc(item.merged_path || "")}</small></td>
        <td>${esc(item.file_size ? `${Math.round(item.file_size/1024/1024)} MB` : "-")}</td>
        <td><div class="ops-inline-buttons"><button type="button" class="ops-action-secondary" data-broadcast-detail="${esc(item.broadcast_id)}">상세</button>${item.segment_count > 1 && item.status !== "recording" ? `<button type="button" class="ops-action-secondary" data-merge="${esc(item.broadcast_id)}">세그먼트 합치기</button>` : ""}</div></td>
      </tr>` : `<tr>
        <td>${esc(item.started_at || "-")}</td>
        <td><strong>${esc(item.channel_name || item.channel_id || "-")}</strong><br><small>${esc(item.platform || "")}</small></td>
        <td class="ops-recording-title">${esc(item.title || item.filename || "-")}<span class="ops-recording-path" title="${esc(item.file_path || "")}">${esc(item.file_path || item.filename || "")}</span></td>
        <td>${statusBadge(item.status)}<br><small>${esc(item.duration || "")}</small></td>
        <td>${statusBadge(item.validation_status)}<br><small>${esc((item.validation_detail || "").slice(0,90))}</small></td>
        <td>${statusBadge(item.archive_status)}<br><small>${esc(item.archive_target || "")}</small></td>
        <td><div class="ops-inline-buttons"><button type="button" class="ops-action-secondary" data-detail="${item.id}">상세</button><button type="button" class="ops-action-secondary" data-verify="${item.id}">검증·복구</button><button type="button" class="ops-action-secondary" data-protect="${esc(item.file_path || "")}">보호</button><button type="button" class="ops-action-secondary" data-archive="${item.id}">외부 보관</button></div></td>
      </tr>`).join("") : '<tr><td colspan="7" class="ops-empty">녹화 기록이 없습니다.</td></tr>';
      $("#ops-history-meta").textContent = `총 ${view === "broadcasts" ? rows.length : data.total}건 · ${view === "broadcasts" ? "재연결 세그먼트는 같은 방송으로 묶어 표시합니다." : "세그먼트 원본 기록입니다."}`;
    } catch (error) { body.innerHTML = `<tr><td colspan="7" class="ops-empty">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-history-refresh")?.addEventListener("click", loadHistory);
  $("#ops-history-view")?.addEventListener("change", loadHistory);
  $("#ops-history-query")?.addEventListener("keydown", (e) => { if (e.key === "Enter") loadHistory(); });
  $("#ops-history-body")?.addEventListener("click", async (event) => {
    const verify = event.target.closest("[data-verify]");
    const archive = event.target.closest("[data-archive]");
    const protect = event.target.closest("[data-protect]");
    const detail = event.target.closest("[data-detail]");
    const broadcastDetail = event.target.closest("[data-broadcast-detail]");
    const merge = event.target.closest("[data-merge]");
    try {
      if (verify) { verify.disabled = true; notice("파일을 검사하고 있습니다."); await api(`/api/v3/recordings/${verify.dataset.verify}/verify`, {method:"POST", body:JSON.stringify({repair:true})}); notice("파일 검증을 완료했습니다."); await loadHistory(); }
      if (archive) { archive.disabled = true; await api(`/api/v3/recordings/${archive.dataset.archive}/archive`, {method:"POST", body:"{}"}); notice("외부 보관 대기열에 추가했습니다."); }
      if (protect) { if (!protect.dataset.protect) throw new Error("보호할 파일 경로가 없습니다."); await api("/api/operations/files/protection", {method:"PUT", body:JSON.stringify({path:protect.dataset.protect, protected:true})}); notice("자동 정리에서 제외하도록 파일을 보호했습니다."); }
      if (detail) { const item = await api(`/api/v3/recordings/${detail.dataset.detail}`); const box = $("#ops-history-detail"); if (box) { box.hidden = false; box.innerHTML = `<h3>${esc(item.channel_name || item.channel_id || "녹화 상세")}</h3><dl class="ops-detail-list"><div><dt>세션</dt><dd>${esc(item.session_id || "-")}</dd></div><div><dt>종료 이유</dt><dd>${esc(item.stop_reason || "-")}</dd></div><div><dt>재연결</dt><dd>${esc(item.reconnects || 0)}회</dd></div><div><dt>녹화 시간</dt><dd>${esc(item.duration || "-")}</dd></div><div><dt>검증</dt><dd>${esc(item.validation_status || "미검사")} · ${esc(item.validation_detail || "")}</dd></div><div><dt>후처리</dt><dd>${esc(item.postprocess_status || "-")} ${esc(item.postprocess_error || "")}</dd></div><div><dt>파일</dt><dd>${esc(item.file_path || item.filename || "-")}</dd></div></dl>`; } }
      if (broadcastDetail) { const item = await api(`/api/v3/broadcasts/${broadcastDetail.dataset.broadcastDetail}`); const box = $("#ops-history-detail"); if (box) { box.hidden = false; box.innerHTML = `<h3>${esc(item.channel_name || item.channel_id || "방송 상세")}</h3><p>${esc(item.title || "")}</p><dl class="ops-detail-list"><div><dt>방송 ID</dt><dd>${esc(item.broadcast_id)}</dd></div><div><dt>세그먼트</dt><dd>${esc(item.segment_count)}개</dd></div><div><dt>재연결</dt><dd>${esc(item.reconnects || 0)}회</dd></div><div><dt>합친 파일</dt><dd>${esc(item.merge?.output_path || "-")}</dd></div></dl><div class="ops-table-wrap"><table><thead><tr><th>#</th><th>시작</th><th>상태</th><th>파일</th><th>실패 원인</th></tr></thead><tbody>${item.segments.map((segment)=>`<tr><td>${esc(segment.segment_index)}</td><td>${esc(segment.started_at)}</td><td>${statusBadge(segment.status)}</td><td>${esc(segment.file_path || segment.filename || "-")}</td><td>${esc(segment.failure_detail || segment.error || "-")}<br><small>${esc(segment.failure_remedy || "")}</small></td></tr>`).join("")}</tbody></table></div>`; } }
      if (merge) { merge.disabled = true; notice("세그먼트를 합치고 있습니다."); await api(`/api/v3/broadcasts/${merge.dataset.merge}/merge`, {method:"POST", body:JSON.stringify({delete_segments:false})}); notice("세그먼트 합치기를 완료했습니다."); await loadHistory(); }
    } catch (error) { notice(error.message, "error"); if (verify) verify.disabled = false; if (archive) archive.disabled = false; }
  });

  async function loadSystemStatus() {
    const summary = $("#ops-system-summary");
    try {
      const [version, cookies, database, settings] = await Promise.all([api("/api/operations/version"), api("/api/operations/cookies/health"), api("/api/operations/database"), api("/api/operations/settings")]);
      if (summary) summary.innerHTML = `<h3>현재 상태</h3><p>버전 ${esc(version.current || "-")} · DB ${esc(database.integrity || "-")} · 쿠키 ${esc(cookies.status || "-")}</p>`;
      const versionCard = $("#ops-version-card"); if (versionCard) versionCard.innerHTML = `<h3>업데이트</h3><p>현재 <strong>${esc(version.current || "-")}</strong><br>최신 <strong>${esc(version.latest || "확인 실패")}</strong></p>${version.update_available ? `<p class="ops-platform-status is-warn">새 버전 사용 가능</p><p>${esc((version.notes || "").slice(0,600))}</p>` : ""}`;
      const cookieCard = $("#ops-cookie-card"); if (cookieCard) cookieCard.innerHTML = `<h3>쿠키 상태</h3>${cookies.items.map((item)=>`<p><strong>${esc(item.platform.toUpperCase())}</strong> · ${esc(item.status)}<br><small>${esc(item.detail)}</small></p>`).join("")}`;
      const dbCard = $("#ops-db-card"); if (dbCard) dbCard.innerHTML = `<h3>SQLite</h3><p>무결성 <strong>${esc(database.integrity || "-")}</strong><br>${esc(database.size_text || "")}</p>`;
      const gf = $("#ops-group-settings"); const groups = settings.recording_groups || {}; if (gf) { gf.elements.auto_merge.value=String(Boolean(groups.auto_merge)); gf.elements.quiet_seconds.value=groups.quiet_seconds || 900; gf.elements.delete_segments_after_merge.value=String(Boolean(groups.delete_segments_after_merge)); }
    } catch (error) { if (summary) summary.textContent = error.message; }
  }
  async function runDiagnostics() { const host=$("#ops-diagnostics-list"); try { notice("전체 시스템을 점검하고 있습니다."); const data=await api("/api/operations/diagnostics"); if(host) host.innerHTML=data.checks.map((item)=>`<div class="ops-platform-card"><h3>${esc(item.name)} · ${esc(item.status)}</h3><p>${esc(item.detail)}</p>${item.remedy?`<small>${esc(item.remedy)}</small>`:""}</div>`).join(""); notice(`점검 완료 · 정상 ${data.counts.ok} / 경고 ${data.counts.warning} / 문제 ${data.counts.problem}`); } catch(error){notice(error.message,"error");} }
  $("#ops-diagnostics-run")?.addEventListener("click", runDiagnostics);
  $("#ops-version-check")?.addEventListener("click", async()=>{try{await api("/api/operations/version?force=true"); await loadSystemStatus(); notice("최신 버전을 확인했습니다.");}catch(error){notice(error.message,"error");}});
  $("#ops-db-backup")?.addEventListener("click", async()=>{try{await api("/api/operations/database/backups",{method:"POST",body:"{}"}); await loadSystemStatus(); notice("SQLite 백업을 생성했습니다.");}catch(error){notice(error.message,"error");}});
  $("#ops-group-settings")?.addEventListener("submit", async(event)=>{event.preventDefault(); const f=event.currentTarget; try{const settings=await api("/api/operations/settings"); settings.recording_groups={...(settings.recording_groups||{}),auto_merge:boolValue(f.elements.auto_merge.value),quiet_seconds:Number(f.elements.quiet_seconds.value||900),delete_segments_after_merge:boolValue(f.elements.delete_segments_after_merge.value)}; await api("/api/operations/settings",{method:"PUT",body:JSON.stringify(settings)}); notice("자동 합치기 설정을 저장했습니다.");}catch(error){notice(error.message,"error");}});

  let platformSettings = null;
  const eventLabels = {"recording.started":"녹화 시작","recording.completed":"녹화 완료","recording.failed":"녹화 실패","recording.validated":"파일 검증","recording.reconnecting":"자동 재연결","recording.missed":"녹화 시작 누락","recording.circuit_breaker":"자동 복구 일시중지","recording.merged":"세그먼트 합치기 완료","recording.merge_failed":"세그먼트 합치기 실패","auth.cookie_warning":"쿠키 인증 경고","database.integrity_failed":"DB 무결성/백업 실패","system.update_available":"새 버전 알림","postprocess.failed":"후처리 실패","storage.warning":"저장소 경고","archive.completed":"외부 보관 완료","archive.failed":"외부 보관 실패"};
  async function loadPlatformSettings() {
    try {
      platformSettings = await api("/api/v3/platform/settings");
      const nf = $("#ops-notification-form");
      const n = platformSettings.notifications || {};
      if (nf) {
        nf.elements.enabled.value = String(n.enabled !== false);
        nf.elements.max_attempts.value = n.max_attempts || 5;
        nf.elements.quiet_start.value = n.quiet_start || "";
        nf.elements.quiet_end.value = n.quiet_end || "";
        $("#ops-notification-events").innerHTML = Object.entries(eventLabels).map(([key,label]) => `<label><input type="checkbox" data-notify-event="${esc(key)}" ${n.events?.[key] ? "checked" : ""}> ${esc(label)}</label>`).join("");
      }
      const af = $("#ops-archive-form");
      const a = platformSettings.archive || {};
      if (af) {
        ["enabled","auto_after_validation","verify_size","delete_after"].forEach((name) => af.elements[name].value = String(Boolean(a[name])));
        af.elements.remote.value = a.remote || "";
      }
      renderWebhooks(platformSettings.webhooks || []);
    } catch (error) { notice(error.message, "error"); }
  }
  async function savePlatform(partial) {
    const data = await api("/api/v3/platform/settings", {method:"PUT", body:JSON.stringify(partial)});
    platformSettings = data;
    notice("설정을 저장했습니다.");
    return data;
  }
  $("#ops-notification-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget;
    const events = {}; $$('[data-notify-event]', f).forEach((input) => events[input.dataset.notifyEvent] = input.checked);
    try { await savePlatform({notifications:{enabled:boolValue(f.elements.enabled.value),max_attempts:Number(f.elements.max_attempts.value || 5),quiet_start:f.elements.quiet_start.value,quiet_end:f.elements.quiet_end.value,events}}); } catch (error) { notice(error.message,"error"); }
  });
  $("#ops-archive-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget;
    try { await savePlatform({archive:{enabled:boolValue(f.elements.enabled.value),remote:f.elements.remote.value.trim(),auto_after_validation:boolValue(f.elements.auto_after_validation.value),verify_size:boolValue(f.elements.verify_size.value),delete_after:boolValue(f.elements.delete_after.value)}}); } catch (error) { notice(error.message,"error"); }
  });

  async function loadNotifications() {
    await loadPlatformSettings();
    const body = $("#ops-notification-body"); if (!body) return;
    try {
      const data = await api("/api/v3/notifications?limit=100");
      body.innerHTML = data.items.length ? data.items.map((item) => `<tr><td>${esc(eventLabels[item.event_type] || item.event_type)}</td><td>${statusBadge(item.status)}</td><td>${item.attempts}</td><td><small>${esc(item.last_error || "-")}</small></td><td>${item.status === "failed" ? `<button type="button" class="ops-action-secondary" data-notify-retry="${item.id}">재시도</button>` : ""}</td></tr>`).join("") : '<tr><td colspan="5" class="ops-empty">전송 기록이 없습니다.</td></tr>';
    } catch (error) { body.innerHTML = `<tr><td colspan="5">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-notification-refresh")?.addEventListener("click", loadNotifications);
  $("#ops-notification-body")?.addEventListener("click", async (event) => { const button = event.target.closest("[data-notify-retry]"); if (!button) return; try { await api(`/api/v3/notifications/${button.dataset.notifyRetry}/retry`, {method:"POST",body:"{}"}); await loadNotifications(); } catch(error){notice(error.message,"error");} });

  async function loadTokens() {
    const body = $("#ops-token-body"); if (!body) return;
    try {
      const data = await api("/api/v3/tokens");
      body.innerHTML = data.items.length ? data.items.map((item) => `<tr><td>${esc(item.name)}<br><small>${esc(item.token_prefix)}…</small></td><td>${esc(item.scopes)}</td><td>${item.last_used_epoch ? new Date(item.last_used_epoch*1000).toLocaleString() : "사용 전"}</td><td>${item.revoked ? "폐기됨" : `<button type="button" class="ops-action-danger" data-token-revoke="${item.id}">폐기</button>`}</td></tr>`).join("") : '<tr><td colspan="4" class="ops-empty">API 토큰이 없습니다.</td></tr>';
    } catch (error) { body.innerHTML = `<tr><td colspan="4">${esc(error.message)}</td></tr>`; }
  }
  $("#ops-token-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const f = event.currentTarget; const scopes = $$('input[name="scope"]:checked', f).map((x) => x.value);
    try {
      const data = await api("/api/v3/tokens", {method:"POST", body:JSON.stringify({name:f.elements.name.value,expires_days:Number(f.elements.expires_days.value || 0),scopes})});
      $("#ops-token-once").innerHTML = `<div class="ops-token-once"><strong>지금 복사하세요. 다시 표시되지 않습니다.</strong><code>${esc(data.token)}</code></div>`;
      f.reset(); f.elements.expires_days.value = 90; $('input[value="read"]', f).checked = true; await loadTokens();
    } catch (error) { notice(error.message,"error"); }
  });
  $("#ops-token-body")?.addEventListener("click", async (event) => { const button = event.target.closest("[data-token-revoke]"); if (!button || !confirm("이 API 토큰을 폐기할까요?")) return; try { await api(`/api/v3/tokens/${button.dataset.tokenRevoke}`, {method:"DELETE"}); await loadTokens(); } catch(error){notice(error.message,"error");} });

  function renderWebhooks(items) {
    const host = $("#ops-webhook-list"); if (!host) return;
    host.innerHTML = "";
    (items || []).forEach((item) => addWebhook(item));
  }
  function addWebhook(item) {
    const host = $("#ops-webhook-list"); if (!host) return;
    const row = document.createElement("div"); row.className = "ops-webhook-row";
    row.innerHTML = `<input data-webhook-url placeholder="https://example.com/webhook" value="${esc(item?.url || "")}"><input data-webhook-events placeholder="recording.completed,archive.completed 또는 *" value="${esc((item?.events || ["*"]).join(","))}"><input data-webhook-secret type="password" placeholder="서명 secret (선택)" value="${item?.secret === "••••••••" ? "••••••••" : esc(item?.secret || "")}"><button type="button" class="ops-action-danger" data-webhook-remove>삭제</button>`;
    row.querySelector("[data-webhook-remove]").addEventListener("click", () => row.remove()); host.appendChild(row);
  }
  $("#ops-webhook-add")?.addEventListener("click", () => addWebhook({events:["*"]}));
  $("#ops-webhook-save")?.addEventListener("click", async () => {
    const webhooks = $$(".ops-webhook-row", $("#ops-webhook-list")).map((row) => ({url:$("[data-webhook-url]",row).value.trim(),events:$("[data-webhook-events]",row).value.split(",").map((x)=>x.trim()).filter(Boolean),secret:$("[data-webhook-secret]",row).value,enabled:true})).filter((x)=>x.url);
    try { await savePlatform({webhooks}); } catch(error){notice(error.message,"error");}
  });

  loadPlatformSettings();
})();

;
// ===== UI refinement =====
(function () {
  "use strict";

  const path = location.pathname.replace(/\/$/, "") || "/";
  const mobile = window.matchMedia("(max-width: 700px)");

  function makeButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function enhanceRecording() {
    if (path !== "/recording" && !document.body.classList.contains("page-recording")) return;

    const content = document.getElementById("content");
    const system = document.getElementById("sys-dashboard");
    const channels = document.getElementById("channel-list");
    const filters = document.querySelector(".filter-container");
    if (!content || !system || !channels) return;

    const systemAnchor = document.createComment("lar-system-dashboard-origin");
    system.parentNode.insertBefore(systemAnchor, system);

    let filterToggle = document.querySelector(".lar-recording-filter-toggle");
    if (filters && !filterToggle) {
      filterToggle = makeButton("검색·필터 열기", "lar-recording-filter-toggle");
      filterToggle.setAttribute("aria-expanded", "false");
      filters.insertAdjacentElement("beforebegin", filterToggle);
      filterToggle.addEventListener("click", function () {
        const collapsed = filters.classList.toggle("lar-mobile-collapsed");
        filterToggle.setAttribute("aria-expanded", String(!collapsed));
        filterToggle.textContent = collapsed ? "검색·필터 열기" : "검색·필터 닫기";
      });
    }

    let systemHead = document.querySelector(".lar-recording-section-head");
    if (!systemHead) {
      systemHead = document.createElement("div");
      systemHead.className = "lar-recording-section-head";
      systemHead.innerHTML = "<strong>시스템 상태</strong><span>CPU · 메모리 · 네트워크 · 저장소</span>";
      system.insertAdjacentElement("beforebegin", systemHead);
    }

    function applyLayout() {
      if (mobile.matches) {
        filters?.classList.add("lar-mobile-collapsed");
        if (filterToggle) {
          filterToggle.setAttribute("aria-expanded", "false");
          filterToggle.textContent = "검색·필터 열기";
        }
        channels.insertAdjacentElement("afterend", systemHead);
        systemHead.insertAdjacentElement("afterend", system);
      } else {
        filters?.classList.remove("lar-mobile-collapsed");
        systemAnchor.parentNode.insertBefore(system, systemAnchor.nextSibling);
        system.insertAdjacentElement("beforebegin", systemHead);
      }
    }

    applyLayout();
    mobile.addEventListener?.("change", applyLayout);
  }

  function enhanceConfigSaveBar() {
    if (path !== "/config" && !document.body.classList.contains("page-config")) return;

    const bar = document.querySelector(".lar-config-savebar");
    if (bar) {
      const title = bar.querySelector("strong");
      const syncTitle = function () {
        if (bar.classList.contains("is-dirty") && title && title.textContent !== "변경사항 저장") {
          title.textContent = "변경사항 저장";
        }
      };
      const observer = new MutationObserver(syncTitle);
      observer.observe(bar, { attributes: true, attributeFilter: ["class"] });
      syncTitle();
    }

    const viewport = window.visualViewport;
    if (!viewport) return;
    const updateKeyboard = function () {
      const keyboardOpen = viewport.height < window.innerHeight * 0.72;
      document.body.classList.toggle("lar-virtual-keyboard", keyboardOpen);
    };
    viewport.addEventListener("resize", updateKeyboard);
    updateKeyboard();
  }

  function enhanceChannelRegistration() {
    if (path !== "/channels" && !document.body.classList.contains("page-channels")) return;
    const form = document.getElementById("addChannelForm");
    if (!form || form.dataset.larAdvancedReady === "1") return;

    const fields = Array.from(form.querySelectorAll(":scope > .lar-field"));
    if (fields.length <= 3) return;
    form.dataset.larAdvancedReady = "1";

    const advanced = document.createElement("div");
    advanced.className = "lar-channel-advanced-fields";
    advanced.hidden = mobile.matches;
    fields.slice(3).forEach((field) => advanced.appendChild(field));

    const toggle = makeButton("고급 설정 열기", "lar-channel-advanced-toggle");
    toggle.setAttribute("aria-expanded", String(!advanced.hidden));
    toggle.addEventListener("click", function () {
      advanced.hidden = !advanced.hidden;
      toggle.setAttribute("aria-expanded", String(!advanced.hidden));
      toggle.textContent = advanced.hidden ? "고급 설정 열기" : "고급 설정 닫기";
    });

    const submit = form.querySelector(":scope > button[type='submit'], :scope > input[type='submit']");
    if (submit) {
      form.insertBefore(toggle, submit);
      form.insertBefore(advanced, submit);
    } else {
      form.append(toggle, advanced);
    }

    function syncForViewport() {
      if (!mobile.matches) {
        advanced.hidden = false;
        toggle.hidden = true;
      } else {
        toggle.hidden = false;
        advanced.hidden = toggle.getAttribute("aria-expanded") !== "true";
      }
    }

    syncForViewport();
    mobile.addEventListener?.("change", syncForViewport);
  }

  function setFileButtonClass(button, kind) {
    if (!button) return;
    button.classList.remove("lar-file-action-primary", "lar-file-action-secondary", "lar-file-action-danger");
    button.classList.add(`lar-file-action-${kind}`);
  }

  function enhanceFiles() {
    if (path !== "/files" && !document.body.classList.contains("page-files")) return;

    ["btnUp", "btnRefresh", "btnStreamCopy", "mobMove", "mobRename", "mobDetail", "mobSelect", "mobCancel"].forEach((id) => {
      setFileButtonClass(document.getElementById(id), "secondary");
    });
    ["btnMkdir"].forEach((id) => setFileButtonClass(document.getElementById(id), "primary"));
    ["btnDelete", "mobDelete"].forEach((id) => setFileButtonClass(document.getElementById(id), "danger"));

    const actionBar = document.querySelector(".mobile-actionbar");
    if (!actionBar) return;

    function updateSelection() {
      const selected = Array.from(document.querySelectorAll(".file-browser input[type='checkbox']:checked"))
        .some((input) => !input.closest("thead"));
      actionBar.classList.toggle("lar-has-selection", selected);
      actionBar.setAttribute("aria-hidden", selected ? "false" : "true");
    }

    document.addEventListener("change", function (event) {
      if (event.target.matches?.(".file-browser input[type='checkbox']")) updateSelection();
    });
    const observer = new MutationObserver(updateSelection);
    const browser = document.querySelector(".file-browser");
    if (browser) observer.observe(browser, { subtree: true, childList: true, attributes: true, attributeFilter: ["checked", "class"] });
    updateSelection();
  }

  function enhanceOperationsTabs() {
    if (path !== "/operations" && !document.body.classList.contains("page-operations")) return;
    const tabs = document.querySelector(".ops-tabs");
    if (!tabs) return;

    function updateScrollState() {
      tabs.classList.toggle("lar-can-scroll", tabs.scrollWidth > tabs.clientWidth + 4);
    }

    tabs.addEventListener("click", function (event) {
      const button = event.target.closest("button");
      if (!button) return;
      button.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    });
    window.addEventListener("resize", updateScrollState);
    updateScrollState();
  }

  function boot() {
    document.body.classList.add("lar-ui-refinement-v1");
    enhanceRecording();
    enhanceConfigSaveBar();
    enhanceChannelRegistration();
    enhanceFiles();
    enhanceOperationsTabs();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();

;
// ===== Local mode =====
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
