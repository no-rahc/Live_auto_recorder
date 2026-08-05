(function () {
  "use strict";

  const THEME_KEY = "lar-console-theme";
  const descriptions = {
    "/recording": "현재 녹화 상태와 시스템 사용량을 확인하고 채널별 녹화를 제어합니다.",
    "/config": "자동 녹화, 후처리, 파일명, 알림 등 프로그램 동작을 설정합니다.",
    "/channels": "녹화할 채널과 저장 경로, 화질 및 파일 형식을 관리합니다.",
    "/cookies": "치지직과 유튜브 인증에 필요한 쿠키 정보를 관리합니다.",
    "/files": "녹화 파일을 찾고 이동하거나 이름을 변경하고 삭제합니다.",
    "/register": "콘솔을 사용할 관리자 계정을 생성합니다.",
  };

  function currentPath() {
    const path = location.pathname.replace(/\/$/, "");
    return path || "/";
  }

  function setDefaultLightTheme() {
    if (localStorage.getItem(THEME_KEY)) return;
    document.documentElement.dataset.theme = "light";
    localStorage.setItem(THEME_KEY, "light");

    if (window.LiveAutoRecorderUI && typeof window.LiveAutoRecorderUI.setTheme === "function") {
      window.LiveAutoRecorderUI.setTheme("light");
    }
  }

  function updateThemeColor() {
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.name = "theme-color";
      document.head.appendChild(meta);
    }
    meta.content = document.documentElement.dataset.theme === "dark" ? "#222428" : "#ff6f0f";
  }

  function addPageIntro() {
    const path = currentPath();
    const copy = descriptions[path];
    const heading = document.querySelector("#content > h1");
    if (!copy || !heading || document.querySelector(".carrot-page-intro")) return;

    const intro = document.createElement("p");
    intro.className = "carrot-page-intro";
    intro.textContent = copy;
    heading.insertAdjacentElement("afterend", intro);
  }

  function polishBrand() {
    document.querySelectorAll(".brand-sub").forEach(function (node) {
      node.textContent = "RECORDER CONSOLE";
    });
  }

  function labelPage() {
    document.body.classList.add("carrot-ui");
    document.documentElement.dataset.carrotUi = "1";
  }

  function watchTheme() {
    const observer = new MutationObserver(function () {
      updateThemeColor();
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }

  function boot() {
    setDefaultLightTheme();
    labelPage();
    updateThemeColor();
    addPageIntro();
    polishBrand();
    watchTheme();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
