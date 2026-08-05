(function () {
  "use strict";

  if (!document.body.classList.contains("page-index") || !document.getElementById("sys-dashboard")) {
    return;
  }

  const text = {
    subtitle: "녹화 상태, 채널, 저장소와 오류를 한 화면에서 우선순위대로 확인하세요.",
    quick: "빠른 이동",
    menuCount: "5개 메뉴",
    live: "녹화 중",
    liveNote: "현재 실행 중인 세션",
    channels: "관리 채널",
    channelsNote: "등록된 전체 채널",
    today: "오늘 녹화",
    todayNote: "오늘 시작된 녹화",
    failures: "오늘 실패",
    failuresNote: "확인이 필요한 이벤트",
    systemTitle: "시스템 상태",
    systemDesc: "저장소와 주요 리소스 사용량",
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
    "/recording": ["녹화 현황", "실시간 세션 제어", "activity"],
    "/config": ["설정 관리", "자동화와 알림 규칙", "settings"],
    "/channels": ["채널 관리", "녹화 대상과 품질", "channels"],
    "/cookies": ["쿠키 관리", "플랫폼 인증 상태", "key"],
    "/files": ["파일 관리", "녹화 파일과 저장소", "folder"],
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
    document.body.classList.add("lar-dashboard-v4");
    const content = document.querySelector("#content.page-index");
    const hero = content && content.querySelector(".dash-hero");
    const dock = content && content.querySelector(".dash-dock");
    const system = content && content.querySelector("#sys-dashboard");
    const activity = content && content.querySelector(".dash-two");
    if (!content || !hero || !dock || !system || !activity || content.querySelector(".dash-v4-intro")) return;

    const intro = el("section", "dash-v4-intro");
    hero.parentNode.insertBefore(intro, hero);
    intro.appendChild(hero);
    intro.appendChild(dock);

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
    if (heroRight) heroRight.appendChild(el("div", "dash-v4-clock-note", text.clockNote));

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
      if (label) {
        label.textContent = meta[0];
        const copy = el("span", "dash-v4-dock-copy");
        label.parentNode.insertBefore(copy, label);
        copy.appendChild(label);
        copy.appendChild(el("span", "dock-description", meta[1]));
      }
      link.appendChild(el("span", "dash-v4-dock-arrow", "›"));
    });

    const overview = el("section", "dash-v4-overview");
    overview.setAttribute("aria-label", "운영 요약");
    overview.appendChild(statCard("live", text.live, "dash-v4-live-count", text.liveNote));
    overview.appendChild(statCard("channels", text.channels, "dash-v4-channel-count", text.channelsNote));
    overview.appendChild(statCard("today", text.today, "dash-v4-today-count", text.todayNote));
    overview.appendChild(statCard("fail", text.failures, "dash-v4-failure-count", text.failuresNote));
    intro.insertAdjacentElement("afterend", overview);

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
  setInterval(syncUpdated, 30000);
})();
