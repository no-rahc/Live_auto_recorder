(function () {
  "use strict";

  const THEME_KEY = "lar-console-theme";
  const pageMeta = {
    "/": ["Dashboard", "녹화 상태, 저장소와 시스템 상태를 한눈에 확인합니다.", "⌂"],
    "/recording": ["녹화 현황", "라이브 채널을 확인하고 녹화 세션을 제어합니다.", "◉"],
    "/config": ["설정 관리", "자동화, 후처리, 저장소와 알림을 구성합니다.", "⚙"],
    "/channels": ["채널 관리", "녹화 대상 채널과 품질, 저장 경로를 관리합니다.", "▣"],
    "/cookies": ["쿠키 관리", "플랫폼 인증 쿠키의 상태를 안전하게 관리합니다.", "◆"],
    "/files": ["파일 관리", "녹화 파일을 탐색하고 이동, 이름 변경, 삭제합니다.", "▤"],
    "/register": ["계정 생성", "관리자 계정을 생성합니다.", "＋"],
  };

  function currentPath() {
    const value = location.pathname.replace(/\/$/, "");
    return value || "/";
  }

  function currentInfo() {
    return pageMeta[currentPath()] || [document.title, "Live Auto Recorder 관리 화면", "•"];
  }

  function preferredTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) return stored;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function themeIcon(theme) {
    if (theme === "dark") {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>';
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    const button = document.querySelector("[data-lar-theme-toggle]");
    if (!button) return;
    button.innerHTML = themeIcon(theme);
    button.title = theme === "dark" ? "라이트 테마" : "다크 테마";
    button.setAttribute("aria-label", button.title);
  }

  function toggleTheme() {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
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
    if (nav) nav.classList.toggle("lar-open", open);
    if (menu) menu.setAttribute("aria-expanded", String(open));
  }

  function enhanceNav() {
    const nav = document.getElementById("mySidenav");
    if (!nav) return;

    document.body.classList.add("lar-desktop-nav");
    const activePath = currentPath();
    nav.querySelectorAll("a[href]").forEach(function (link) {
      if (link.classList.contains("closebtn")) return;
      let targetPath;
      try {
        targetPath = new URL(link.href, location.origin).pathname.replace(/\/$/, "") || "/";
      } catch (_) {
        return;
      }

      const meta = pageMeta[targetPath] || ["", "", "•"];
      if (!link.querySelector(".lar-nav-icon")) {
        const icon = document.createElement("span");
        icon.className = "lar-nav-icon";
        icon.textContent = meta[2];
        icon.setAttribute("aria-hidden", "true");
        link.prepend(icon);
      }
      if (targetPath === activePath) {
        link.classList.add("lar-active");
        link.setAttribute("aria-current", "page");
      }
      link.addEventListener("click", function () {
        if (innerWidth < 1100) setNavOpen(false);
      });
    });

    ensureBackdrop().addEventListener("click", function () {
      setNavOpen(false);
    });

    const menu = document.querySelector(".menu-icon");
    if (menu) {
      menu.addEventListener(
        "click",
        function (event) {
          event.preventDefault();
          event.stopPropagation();
          setNavOpen(!document.body.classList.contains("lar-nav-open"));
        },
        true
      );
    }

    const close = nav.querySelector(".closebtn");
    if (close) {
      close.setAttribute("aria-label", "메뉴 닫기");
      close.addEventListener(
        "click",
        function (event) {
          event.preventDefault();
          setNavOpen(false);
        },
        true
      );
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") setNavOpen(false);
    });
  }

  function enhanceTopbar() {
    const navbar = document.querySelector(".navbar");
    if (!navbar || navbar.querySelector(".lar-topbar-actions")) return;

    const actions = document.createElement("div");
    actions.className = "lar-topbar-actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lar-icon-button";
    button.dataset.larThemeToggle = "";
    button.addEventListener("click", toggleTheme);
    actions.appendChild(button);
    navbar.appendChild(actions);
    setTheme(preferredTheme());
  }

  function enhanceHeading() {
    const info = currentInfo();
    const heading = document.querySelector("#content > h1");
    if (heading) heading.dataset.larSubtitle = info[1];

    const content = document.getElementById("content");
    if (!content || content.querySelector(".lar-status-rail")) return;
    if (content.querySelector(".login-form") && !content.querySelector(".dash-hero")) {
      document.body.classList.add("lar-auth-page");
      return;
    }

    const rail = document.createElement("div");
    rail.className = "lar-status-rail";
    rail.innerHTML =
      '<span class="lar-status-chip">Console online</span>' +
      '<span class="lar-status-chip">UI v2</span>';
    if (heading) heading.insertAdjacentElement("afterend", rail);
    else if (!content.querySelector(".dash-hero")) content.prepend(rail);
  }

  function elementsWithin(root, selector) {
    const elements = [];
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) {
      return elements;
    }
    if (root.matches && root.matches(selector)) elements.push(root);
    if (root.querySelectorAll) elements.push.apply(elements, root.querySelectorAll(selector));
    return elements;
  }

  function enhanceA11y(root) {
    elementsWithin(root, ".error-message,.alert-error").forEach(function (element) {
      element.setAttribute("role", "alert");
      element.setAttribute("aria-live", "assertive");
    });

    elementsWithin(root, "[id*=status],[id*=message],.description").forEach(function (element) {
      if (!element.hasAttribute("aria-live")) element.setAttribute("aria-live", "polite");
    });

    elementsWithin(root, "table").forEach(function (table) {
      if (table.getAttribute("aria-label")) return;
      const section = table.closest("section,.card,.config-section");
      const heading = section && section.querySelector("h1,h2,h3,.eyebrow");
      table.setAttribute("aria-label", heading ? heading.textContent.trim() : "데이터 표");
    });

    elementsWithin(root, "img:not([alt])").forEach(function (image) {
      image.alt = "";
    });
  }

  function enhanceForms(root) {
    elementsWithin(root, "form").forEach(function (form) {
      if (form.dataset.larEnhanced) return;
      form.dataset.larEnhanced = "1";
      form.addEventListener("submit", function () {
        const button = form.querySelector("button[type=submit],input[type=submit]");
        if (!button || button.disabled) return;
        const original = button.value || button.textContent;
        setTimeout(function () {
          if (form.checkValidity && !form.checkValidity()) return;
          button.disabled = true;
          if (button.tagName === "INPUT") button.value = "저장 중...";
          else button.textContent = "저장 중...";
          setTimeout(function () {
            if (!document.body.contains(button)) return;
            button.disabled = false;
            if (button.tagName === "INPUT") button.value = original;
            else button.textContent = original;
          }, 8000);
        }, 0);
      });
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

  function toast(message, tone) {
    const item = document.createElement("div");
    item.className = "lar-toast";
    item.dataset.tone = tone || "info";
    item.textContent = message;
    toastRegion().appendChild(item);
    setTimeout(function () {
      item.remove();
    }, 3500);
  }

  function bindNetworkStatus() {
    addEventListener("offline", function () {
      toast("네트워크 연결이 끊어졌습니다.", "error");
    });
    addEventListener("online", function () {
      toast("네트워크가 다시 연결되었습니다.", "success");
    });
  }

  function observeDynamicContent() {
    const pending = new Set();
    let scheduled = false;

    function flush() {
      scheduled = false;
      pending.forEach(function (node) {
        enhanceA11y(node);
        enhanceForms(node);
      });
      pending.clear();
    }

    const observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (node.nodeType === Node.ELEMENT_NODE) pending.add(node);
        });
      });
      if (pending.size && !scheduled) {
        scheduled = true;
        requestAnimationFrame(flush);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    enhanceNav();
    enhanceTopbar();
    enhanceHeading();
    enhanceA11y(document);
    enhanceForms(document);
    bindNetworkStatus();
    observeDynamicContent();
    window.LiveAutoRecorderUI = { toast: toast, setTheme: setTheme };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
